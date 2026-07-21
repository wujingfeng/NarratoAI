from __future__ import annotations

import hashlib
import ipaddress
import os
import posixpath
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import BinaryIO, Protocol
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import httpx


ALLOWED_ARTIFACT_EXTENSIONS = frozenset(
    {"srt", "json", "mp3", "wav", "mp4", "mov", "avi", "zip"}
)
_PERCENT_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")
_MAX_PATH_DECODE_DEPTH = 12


class InfrastructureError(RuntimeError):
    """Core 基础设施适配器的稳定错误基类。"""

    code = "INFRASTRUCTURE_ERROR"
    retryable = False


class InputSecurityError(InfrastructureError):
    """输入 URL 不符合公开 CDN 安全策略。"""

    code = "SOURCE_URL_REJECTED"


class DownloadTooLargeError(InfrastructureError):
    """下载对象超过该原子能力允许的最大字节数。"""

    code = "SOURCE_TOO_LARGE"


class DownloadTemporaryError(InfrastructureError):
    """公开 CDN 暂时无法完成下载。"""

    code = "SOURCE_DOWNLOAD_FAILED"
    retryable = True


class OssTemporaryError(InfrastructureError):
    """Core OSS 暂时无法完成上传。"""

    code = "OSS_UPLOAD_FAILED"
    retryable = True


def normalize_extension(extension: str) -> str:
    """规范化受控扩展名并拒绝路径、编码和双扩展。"""

    raw = str(extension or "").strip()
    if raw.startswith("."):
        raw = raw[1:]
    normalized = raw.lower()
    if (
        not normalized
        or normalized not in ALLOWED_ARTIFACT_EXTENSIONS
        or normalized != raw.lower()
        or any(char in raw for char in ("/", "\\", "%", "."))
    ):
        raise ValueError("不受支持的扩展名")
    return normalized


def build_object_key(*, now: date, extension: str, seed: str) -> str:
    """按固定 Core 前缀生成不可解析的 MD5 对象键。"""

    ext = normalize_extension(extension)
    if not seed:
        raise ValueError("对象键 seed 不能为空")
    digest = hashlib.md5(seed.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"narrato/coreApi/{now:%Y/%m/%d}/{digest}.{ext}"


@dataclass(frozen=True, slots=True)
class DownloadReceipt:
    """公开 CDN 流式下载的安全摘要。"""

    url: str
    size: int
    content_type: str | None


@dataclass(frozen=True, slots=True)
class OssUploadResult:
    """OSS 上传后可公开登记的对象引用。"""

    bucket: str
    object_key: str
    url: str


class Downloader(Protocol):
    """供媒体适配器注入的受限下载协议。"""

    def download(
        self, url: str, destination: Path, *, max_bytes: int
    ) -> DownloadReceipt:
        """将受限 URL 流式写入调用方控制的目标。"""

        ...


class OssClient(Protocol):
    """供 ArtifactStore 注入的最薄 OSS 上传协议。"""

    def upload_stream(
        self,
        stream: BinaryIO,
        object_key: str,
        *,
        content_type: str,
        size: int,
    ) -> OssUploadResult:
        """从已打开 regular-file stream 上传并返回公开引用。"""

        ...

    def delete_object(self, object_key: str) -> None:
        """补偿删除尚未登记的 attempt 私有对象。"""
        ...


class CdnUrlPolicy:
    """只允许精确 HTTPS CDN Host 与业务对象前缀。"""

    def __init__(
        self, allowed_hosts: set[str] | frozenset[str], *, prefix: str = "/narrato/api/"
    ) -> None:
        normalized_hosts: set[str] = set()
        for value in allowed_hosts:
            raw = str(value or "").strip().lower().rstrip(".")
            try:
                parsed = urlsplit(f"//{raw}")
                host = parsed.hostname or ""
                port = parsed.port
            except ValueError as exc:
                raise ValueError("CDN allowlist Host 无效") from exc
            if (
                not raw
                or host != raw
                or port is not None
                or parsed.username is not None
                or "/" in raw
                or "\\" in raw
            ):
                raise ValueError("CDN allowlist Host 无效")
            try:
                host = host.encode("idna").decode("ascii").lower()
            except UnicodeError as exc:
                raise ValueError("CDN allowlist IDNA Host 无效") from exc
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise ValueError("CDN allowlist 不允许 IP literal")
            normalized_hosts.add(host)
        self.allowed_hosts = frozenset(normalized_hosts)
        self.prefix = prefix
        if not self.allowed_hosts or not prefix.startswith("/"):
            raise ValueError("CDN allowlist 和对象前缀不能为空")

    def validate(self, url: str) -> str:
        """验证并返回保持 query 的规范公开 URL。"""

        try:
            parsed = urlsplit(str(url or ""))
            host = (parsed.hostname or "").lower().rstrip(".")
            host = host.encode("idna").decode("ascii").lower()
            port = parsed.port
        except ValueError as exc:
            raise InputSecurityError("SOURCE_URL_REJECTED") from exc
        if (
            parsed.scheme.lower() != "https"
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or port not in (None, 443)
            or host not in self.allowed_hosts
        ):
            raise InputSecurityError("SOURCE_URL_REJECTED")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            # 生产策略永远拒绝 IP literal；测试使用 Fake Downloader 而非放宽策略。
            raise InputSecurityError("SOURCE_URL_REJECTED")

        raw_path = parsed.path or "/"
        if "\\" in raw_path:
            raise InputSecurityError("SOURCE_URL_REJECTED")
        decoded = raw_path
        for _ in range(_MAX_PATH_DECODE_DEPTH):
            if "%" not in decoded:
                break
            escapes = _PERCENT_ESCAPE.findall(decoded)
            if not escapes or len(escapes) != decoded.count("%"):
                raise InputSecurityError("SOURCE_URL_REJECTED")
            if any(int(value, 16) in {0x25, 0x2E, 0x2F, 0x5C} for value in escapes):
                # 百分号、点和路径分隔符在任意编码层出现都拒绝，避免下游再次解释。
                raise InputSecurityError("SOURCE_URL_REJECTED")
            next_decoded = unquote(decoded)
            if next_decoded == decoded:
                raise InputSecurityError("SOURCE_URL_REJECTED")
            decoded = next_decoded
        else:
            raise InputSecurityError("SOURCE_URL_REJECTED")
        if "%" in decoded:
            raise InputSecurityError("SOURCE_URL_REJECTED")
        if "\\" in decoded or any(part == ".." for part in decoded.split("/")):
            raise InputSecurityError("SOURCE_URL_REJECTED")
        normalized_path = posixpath.normpath(decoded)
        if not decoded.startswith(self.prefix) or not normalized_path.startswith(
            self.prefix
        ):
            raise InputSecurityError("SOURCE_URL_REJECTED")
        if decoded != normalized_path:
            raise InputSecurityError("SOURCE_URL_REJECTED")
        return urlunsplit(("https", host, decoded, parsed.query, ""))


class HttpCdnDownloader:
    """带重定向复核、双重大小限制和总时限的流式下载器。"""

    def __init__(
        self,
        policy: CdnUrlPolicy,
        *,
        transport: httpx.BaseTransport | None = None,
        connect_timeout: float = 5.0,
        read_timeout: float = 30.0,
        total_timeout: float = 120.0,
        max_redirects: int = 3,
    ) -> None:
        self.policy = policy
        self.transport = transport
        self.timeout = httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=read_timeout,
            pool=connect_timeout,
        )
        self.total_timeout = total_timeout
        self.max_redirects = max_redirects

    def download(
        self, url: str, destination: Path, *, max_bytes: int
    ) -> DownloadReceipt:
        """流式写入受控路径，失败时删除任何部分文件。"""

        if max_bytes <= 0:
            raise ValueError("max_bytes 必须大于零")
        current = self.policy.validate(url)
        destination = Path(destination)
        if not destination.is_absolute() or destination.name in {"", ".", ".."}:
            raise DownloadTemporaryError("SOURCE_DOWNLOAD_FAILED")
        parent_fd = self._open_parent_dirfd(destination)
        filename = destination.name
        created = False
        started = time.monotonic()
        try:
            with httpx.Client(
                transport=self.transport,
                timeout=self.timeout,
                follow_redirects=False,
            ) as client:
                for redirect_no in range(self.max_redirects + 1):
                    with client.stream("GET", current) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            if redirect_no >= self.max_redirects:
                                raise InputSecurityError("SOURCE_REDIRECT_REJECTED")
                            location = response.headers.get("Location", "")
                            current = self.policy.validate(urljoin(current, location))
                            continue
                        if response.status_code >= 500 or response.status_code in {
                            408,
                            429,
                        }:
                            raise DownloadTemporaryError("SOURCE_DOWNLOAD_FAILED")
                        if response.status_code != 200:
                            raise InputSecurityError("SOURCE_NOT_AVAILABLE")
                        declared = response.headers.get("Content-Length")
                        if declared:
                            try:
                                if int(declared) > max_bytes:
                                    raise DownloadTooLargeError("SOURCE_TOO_LARGE")
                            except ValueError as exc:
                                raise InputSecurityError(
                                    "SOURCE_LENGTH_INVALID"
                                ) from exc
                        size = 0
                        flags = (
                            os.O_WRONLY
                            | os.O_CREAT
                            | os.O_EXCL
                            | getattr(os, "O_NOFOLLOW", 0)
                            | getattr(os, "O_CLOEXEC", 0)
                        )
                        descriptor = os.open(filename, flags, 0o600, dir_fd=parent_fd)
                        created = True
                        with os.fdopen(descriptor, "wb") as handle:
                            for chunk in response.iter_bytes(64 * 1024):
                                if time.monotonic() - started > self.total_timeout:
                                    raise DownloadTemporaryError(
                                        "SOURCE_DOWNLOAD_TIMEOUT"
                                    )
                                size += len(chunk)
                                if size > max_bytes:
                                    raise DownloadTooLargeError("SOURCE_TOO_LARGE")
                                handle.write(chunk)
                            handle.flush()
                            os.fsync(handle.fileno())
                        return DownloadReceipt(
                            url=current,
                            size=size,
                            content_type=response.headers.get("Content-Type"),
                        )
            raise InputSecurityError("SOURCE_REDIRECT_REJECTED")
        except InfrastructureError:
            if created:
                self._unlink_at(parent_fd, filename)
            raise
        except (httpx.HTTPError, OSError) as exc:
            if created:
                self._unlink_at(parent_fd, filename)
            raise DownloadTemporaryError("SOURCE_DOWNLOAD_FAILED") from exc
        finally:
            os.close(parent_fd)

    @staticmethod
    def _open_parent_dirfd(destination: Path) -> int:
        """从根逐层 O_NOFOLLOW 打开父目录，消除祖先替换竞态。"""

        flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor = os.open("/", flags)
        try:
            for part in destination.parent.parts[1:]:
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
            return descriptor
        except OSError as exc:
            os.close(descriptor)
            raise DownloadTemporaryError("SOURCE_DOWNLOAD_FAILED") from exc

    @staticmethod
    def _unlink_at(parent_fd: int, filename: str) -> None:
        """仅从已验证 dirfd 删除本次受控临时文件。"""

        try:
            os.unlink(filename, dir_fd=parent_fd)
        except FileNotFoundError:
            return


class Oss2Client:
    """使用私有 TOML 凭据上传 Core 产物的 oss2 Adapter。"""

    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key_id: str,
        access_key_secret: str,
        public_base_url: str,
        connect_timeout: float = 5.0,
        read_timeout: float = 5.0,
    ) -> None:
        endpoint_url = urlsplit(endpoint)
        public_url = urlsplit(public_base_url)
        if (
            endpoint_url.scheme.lower() != "https"
            or not endpoint_url.hostname
            or endpoint_url.username is not None
            or endpoint_url.fragment
            or public_url.scheme.lower() != "https"
            or not public_url.hostname
            or public_url.username is not None
            or public_url.query
            or public_url.fragment
            or not bucket
            or not access_key_id
            or not access_key_secret
            or connect_timeout <= 0
            or read_timeout <= 0
        ):
            raise ValueError("OSS 配置必须使用完整 HTTPS 地址和非空私有凭据")
        self.endpoint = endpoint
        self.bucket = bucket
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.public_base_url = public_base_url.rstrip("/")
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout

    def _bucket(self):
        """创建真实下传 connect/read timeout 的 OSS Bucket。"""

        import oss2

        auth = oss2.Auth(self.access_key_id, self.access_key_secret)
        return oss2.Bucket(
            auth,
            self.endpoint,
            self.bucket,
            connect_timeout=(self.connect_timeout, self.read_timeout),
        )

    def upload_stream(
        self,
        stream: BinaryIO,
        object_key: str,
        *,
        content_type: str,
        size: int,
    ) -> OssUploadResult:
        """禁止覆盖地上传已打开文件流并仅返回公开对象引用。"""

        if not object_key.startswith("narrato/coreApi/"):
            raise ValueError("Core 产物对象键前缀无效")
        try:
            bucket = self._bucket()
            headers = {
                "Content-Type": content_type,
                "x-oss-forbid-overwrite": "true",
                "Content-Length": str(size),
            }
            bucket.put_object(object_key, stream, headers=headers)
        except Exception as exc:
            # 供应商响应不进入公开错误或任务结果。
            raise OssTemporaryError("OSS_UPLOAD_FAILED") from exc
        return OssUploadResult(
            bucket=self.bucket,
            object_key=object_key,
            url=f"{self.public_base_url}/{object_key}",
        )

    def check_ready(self) -> None:
        """执行最小 bucket 元数据探针，不返回供应商响应。"""

        try:
            bucket = self._bucket()
            bucket.get_bucket_info()
        except Exception as exc:
            raise OssTemporaryError("OSS_NOT_READY") from exc

    def delete_object(self, object_key: str) -> None:
        """仅允许补偿删除 Core 命名空间对象，不暴露供应商响应。"""
        if not object_key.startswith("narrato/coreApi/"):
            raise ValueError("Core 产物对象键前缀无效")
        try:
            self._bucket().delete_object(object_key)
        except Exception as exc:
            raise OssTemporaryError("OSS_CLEANUP_FAILED") from exc

    def object_exists(self, object_key: str) -> bool:
        """Confirm remote absence before a cleanup tombstone may retire."""
        if not object_key.startswith("narrato/coreApi/"):
            raise ValueError("Core 产物对象键前缀无效")
        try:
            return bool(self._bucket().object_exists(object_key))
        except Exception as exc:
            raise OssTemporaryError("OSS_HEAD_FAILED") from exc

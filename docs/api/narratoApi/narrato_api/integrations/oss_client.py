from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import format_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import quote, urlsplit

from narrato_api.assets.constraints import (
    AssetDeclaration,
    AssetDeclarationError,
    validate_asset_declaration,
)

_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".srt": "application/octet-stream",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
}


class OssClientError(RuntimeError):
    """OSS 对象读取或配置无法满足上传确认要求。"""


@dataclass(frozen=True, slots=True)
class OssObject:
    """OSS HEAD 返回的最小可信对象元数据。"""

    size_bytes: int
    content_type: str


@dataclass(frozen=True, slots=True)
class OssStoredObject:
    """供应商结果流式转存后的已验证对象信息。"""

    bucket: str
    object_key: str
    cdn_url: str
    size_bytes: int
    content_type: str


@dataclass(frozen=True, slots=True)
class OssPostPolicy:
    """浏览器直传所需的短期 OSS 表单字段。"""

    url: str
    key: str
    fields: dict[str, str]
    max_size_bytes: int


class OssPostPolicyService:
    """生成对象键固定且只允许单一类型和长度的 OSS POST Policy。"""

    def __init__(
        self,
        *,
        upload_url: str,
        bucket: str,
        access_key_id: str,
        access_key_secret: str,
        today: Callable[[], date] = date.today,
        token_factory: Callable[[], str] = lambda: secrets.token_hex(16),
    ) -> None:
        self.upload_url = upload_url.rstrip("/")
        self.bucket = bucket
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.today = today
        self.token_factory = token_factory

    def create_policy(
        self,
        *,
        asset_type: str,
        filename: str,
        size_bytes: int,
        existing_video_count: int,
        content_type: str | None = None,
    ) -> OssPostPolicy:
        """校验声明并签发仅可写入单个对象的十分钟表单。"""

        if (
            not self.upload_url
            or not self.bucket
            or not self.access_key_id
            or not self.access_key_secret
        ):
            raise OssClientError("OSS POST policy is not configured")
        declaration = validate_asset_declaration(
            asset_type=asset_type,
            filename=filename,
            size_bytes=size_bytes,
            existing_video_count=existing_video_count,
        )
        key = self._object_key(declaration)
        expected_content_type = _CONTENT_TYPES[declaration.extension]
        if content_type is not None and content_type != expected_content_type:
            raise AssetDeclarationError("unsupported content type")
        expires_at = datetime.now(UTC) + timedelta(minutes=10)
        document = {
            "expiration": expires_at.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "conditions": [
                {"bucket": self.bucket},
                ["eq", "$key", key],
                ["eq", "$Content-Type", expected_content_type],
                ["content-length-range", 0, declaration.max_size_bytes],
            ],
        }
        encoded = base64.b64encode(
            json.dumps(document, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        signature = base64.b64encode(
            hmac.new(
                self.access_key_secret.encode(), encoded.encode(), hashlib.sha1
            ).digest()
        ).decode("ascii")
        return OssPostPolicy(
            url=self.upload_url,
            key=key,
            max_size_bytes=declaration.max_size_bytes,
            fields={
                "key": key,
                "OSSAccessKeyId": self.access_key_id,
                "policy": encoded,
                "Signature": signature,
                "Content-Type": expected_content_type,
            },
        )

    def _object_key(self, declaration: AssetDeclaration) -> str:
        """按产品固定 API 前缀创建不可猜测的对象键。"""

        today = self.today()
        return f"narrato/api/{today:%Y/%m/%d}/{self.token_factory()}.{declaration.extension.lstrip('.')}"


class HttpOssClient:
    """通过 HEAD 读取 OSS 对象，不把文件内容回流到业务服务。"""

    def __init__(
        self,
        *,
        endpoint: str,
        access_key_id: str = "",
        access_key_secret: str = "",
        cdn_public_base_url: str = "",
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.cdn_public_base_url = cdn_public_base_url.rstrip("/")
        self.now = now

    def head_object(self, bucket: str, object_key: str) -> OssObject:
        """验证对象存在并返回服务端声明的长度与类型。"""

        if not self.endpoint:
            raise OssClientError("OSS endpoint is not configured")
        url = self.public_url(bucket, object_key)
        try:
            with urlopen(Request(url, method="HEAD"), timeout=5) as response:
                raw_size = response.headers.get("Content-Length")
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            raise OssClientError("OSS object could not be verified") from error
        if raw_size is None or not raw_size.isdecimal() or not content_type:
            raise OssClientError("OSS object metadata is incomplete")
        return OssObject(size_bytes=int(raw_size), content_type=content_type)

    def delete_object(self, bucket: str, object_key: str) -> None:
        """删除明确登记的 OSS 对象；404 视为已达成删除终态。"""

        if (
            not self.endpoint
            or not bucket
            or not object_key
            or not self.access_key_id
            or not self.access_key_secret
        ):
            raise OssClientError("OSS delete is not configured")
        request_date = format_datetime(self.now().astimezone(UTC), usegmt=True)
        string_to_sign = f"DELETE\n\n\n{request_date}\n/{bucket}/{object_key}"
        signature = base64.b64encode(
            hmac.new(
                self.access_key_secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("ascii")
        request = Request(
            self.public_url(bucket, object_key),
            method="DELETE",
            headers={
                "Date": request_date,
                "Authorization": f"OSS {self.access_key_id}:{signature}",
            },
        )
        try:
            with urlopen(request, timeout=10):
                return
        except HTTPError as error:
            if error.code == 404:
                return
            raise OssClientError("OSS object could not be deleted") from error
        except (URLError, TimeoutError) as error:
            raise OssClientError("OSS object could not be deleted") from error

    def copy_from_url(
        self,
        *,
        bucket: str,
        object_key: str,
        source_url: str,
        content_type: str | None = None,
        max_size_bytes: int = 1024 * 1024 * 1024,
    ) -> OssStoredObject:
        """从供应商 HTTPS URL 流式写入自有 OSS，不将大文件读入内存。"""

        if (
            not self.endpoint
            or not bucket
            or not object_key
            or not self.access_key_id
            or not self.access_key_secret
        ):
            raise OssClientError("OSS copy is not configured")
        parsed_source = urlsplit(source_url)
        if (
            parsed_source.scheme != "https"
            or not parsed_source.hostname
            or parsed_source.username
            or parsed_source.password
        ):
            raise OssClientError("provider result URL is invalid")
        # 结果 URL 由已接入 Provider 的任务状态接口返回。不同供应商可能使用
        # 不同 CDN、临时域名或本地代理 DNS，因此不在此处维护域名/IP 白名单。
        # 仍只接受无凭据 HTTPS URL，且结果必须成功转存到自有 OSS 才会完成任务。
        try:
            with urlopen(Request(source_url, method="GET"), timeout=30) as source:
                raw_length = source.headers.get("Content-Length")
                if raw_length is None or not raw_length.isdecimal():
                    raise OssClientError("provider result length is unavailable")
                size_bytes = int(raw_length)
                if size_bytes <= 0 or size_bytes > max_size_bytes:
                    raise OssClientError("provider result size is invalid")
                resolved_type = content_type or source.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0]
                if not resolved_type:
                    resolved_type = "application/octet-stream"
                self._put_stream(
                    bucket=bucket,
                    object_key=object_key,
                    content_type=resolved_type,
                    size_bytes=size_bytes,
                    source=source,
                )
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            raise OssClientError("provider result could not be copied") from error
        cdn_base = self.cdn_public_base_url or f"https://{bucket}.{self.endpoint}"
        return OssStoredObject(
            bucket=bucket,
            object_key=object_key,
            cdn_url=f"{cdn_base}/{quote(object_key, safe='/')}",
            size_bytes=size_bytes,
            content_type=resolved_type,
        )

    def _put_stream(
        self,
        *,
        bucket: str,
        object_key: str,
        content_type: str,
        size_bytes: int,
        source: object,
    ) -> None:
        """使用 OSS Signature V1 按固定 Content-Length 将来源流转发。"""

        request_date = format_datetime(self.now().astimezone(UTC), usegmt=True)
        canonical_resource = f"/{bucket}/{object_key}"
        string_to_sign = f"PUT\n\n{content_type}\n{request_date}\n{canonical_resource}"
        signature = base64.b64encode(
            hmac.new(
                self.access_key_secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("ascii")
        connection = http.client.HTTPSConnection(f"{bucket}.{self.endpoint}", timeout=30)
        try:
            connection.putrequest("PUT", f"/{quote(object_key, safe='/')}")
            connection.putheader("Date", request_date)
            connection.putheader("Content-Type", content_type)
            connection.putheader("Content-Length", str(size_bytes))
            connection.putheader("Authorization", f"OSS {self.access_key_id}:{signature}")
            connection.endheaders()
            remaining = size_bytes
            reader = getattr(source, "read", None)
            if reader is None:
                raise OssClientError("provider result stream is invalid")
            while remaining:
                chunk = reader(min(1024 * 1024, remaining))
                if not chunk:
                    raise OssClientError("provider result ended early")
                if not isinstance(chunk, bytes):
                    raise OssClientError("provider result stream is invalid")
                connection.send(chunk)
                remaining -= len(chunk)
            response = connection.getresponse()
            response.read()
            if response.status not in {200, 201}:
                raise OssClientError("OSS object could not be stored")
        finally:
            connection.close()

    def public_url(self, bucket: str, object_key: str) -> str:
        """返回部署配置对应的公开对象 URL。"""

        if not self.endpoint or not bucket:
            raise OssClientError("OSS endpoint is not configured")
        return f"https://{bucket}.{self.endpoint}/{object_key}"

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from narrato_api.assets.constraints import (
    AssetDeclaration,
    AssetDeclarationError,
    validate_asset_declaration,
)

_CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".srt": "application/x-subrip",
}


class OssClientError(RuntimeError):
    """OSS 对象读取或配置无法满足上传确认要求。"""


@dataclass(frozen=True, slots=True)
class OssObject:
    """OSS HEAD 返回的最小可信对象元数据。"""

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

    def __init__(self, *, endpoint: str) -> None:
        self.endpoint = endpoint.rstrip("/")

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

        if not self.endpoint or not bucket or not object_key:
            raise OssClientError("OSS delete is not configured")
        request = Request(f"{self.endpoint}/{bucket}/{object_key}", method="DELETE")
        try:
            with urlopen(request, timeout=10):
                return
        except HTTPError as error:
            if error.code == 404:
                return
            raise OssClientError("OSS object could not be deleted") from error
        except (URLError, TimeoutError) as error:
            raise OssClientError("OSS object could not be deleted") from error

    def public_url(self, bucket: str, object_key: str) -> str:
        """返回部署配置对应的公开对象 URL。"""

        prefix = f"{self.endpoint}/{bucket}" if bucket else self.endpoint
        return f"{prefix}/{object_key}"

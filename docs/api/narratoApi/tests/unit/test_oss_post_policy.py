from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, date, datetime
from email.utils import format_datetime
from typing import Any

import pytest

from narrato_api.assets.constraints import AssetDeclarationError, validate_asset_declaration
from narrato_api.assets.service import project_for_update_statement
from narrato_api.integrations.oss_client import (
    HttpOssClient,
    OssClientError,
    OssPostPolicyService,
)


def test_oss_client_composes_bucket_url_from_endpoint_host() -> None:
    client = HttpOssClient(endpoint="oss-cn-shanghai.aliyuncs.com")

    assert client.public_url("game339", "narrato/api/episode.mp4") == (
        "https://game339.oss-cn-shanghai.aliyuncs.com/narrato/api/episode.mp4"
    )


def test_oss_delete_uses_aliyun_access_key_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 5, 8, 9, 10, tzinfo=UTC)
    captured: dict[str, Any] = {}

    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_urlopen(request: Any, *, timeout: int) -> _Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("narrato_api.integrations.oss_client.urlopen", fake_urlopen)
    client = HttpOssClient(
        endpoint="oss-cn-shanghai.aliyuncs.com",
        access_key_id="access-key",
        access_key_secret="access-secret",
        now=lambda: now,
    )

    client.delete_object("game339", "narrato/api/episode.mp4")

    request = captured["request"]
    request_date = format_datetime(now, usegmt=True)
    string_to_sign = (
        "DELETE\n\n\n" f"{request_date}\n" "/game339/narrato/api/episode.mp4"
    )
    signature = base64.b64encode(
        hmac.new(
            b"access-secret", string_to_sign.encode("utf-8"), hashlib.sha1
        ).digest()
    ).decode("ascii")
    assert request.full_url == (
        "https://game339.oss-cn-shanghai.aliyuncs.com/" "narrato/api/episode.mp4"
    )
    assert request.method == "DELETE"
    assert request.get_header("Date") == request_date
    assert request.get_header("Authorization") == f"OSS access-key:{signature}"
    assert captured["timeout"] == 10


def test_oss_delete_requires_access_key_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "narrato_api.integrations.oss_client.urlopen",
        lambda *args, **kwargs: pytest.fail("network must not be called"),
    )
    client = HttpOssClient(endpoint="oss-cn-shanghai.aliyuncs.com")

    with pytest.raises(OssClientError, match="OSS delete is not configured"):
        client.delete_object("game339", "narrato/api/episode.mp4")


def test_copy_from_url_allows_provider_cdn_local_proxy_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider CDN 的 DNS 映射不影响 HTTPS 结果转存。"""

    class _Response:
        headers = {"Content-Length": "7", "Content-Type": "video/mp4"}

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, _size: int) -> bytes:
            return b"content"

    monkeypatch.setattr(
        "narrato_api.integrations.oss_client.urlopen",
        lambda *_args, **_kwargs: _Response(),
    )
    client = HttpOssClient(
        endpoint="oss-cn-shanghai.aliyuncs.com",
        access_key_id="access-key",
        access_key_secret="access-secret",
        cdn_public_base_url="https://cdn.example.test",
    )
    stored: dict[str, object] = {}
    monkeypatch.setattr(client, "_put_stream", lambda **kwargs: stored.update(kwargs))

    result = client.copy_from_url(
        bucket="game339",
        object_key="narrato/model-results/task/0.mp4",
        source_url="https://storage.deepwl.cn/result.mp4",
    )

    assert stored["size_bytes"] == 7
    assert result.cdn_url == "https://cdn.example.test/narrato/model-results/task/0.mp4"


def test_copy_from_url_rejects_non_https_provider_result() -> None:
    client = HttpOssClient(
        endpoint="oss-cn-shanghai.aliyuncs.com",
        access_key_id="access-key",
        access_key_secret="access-secret",
    )

    with pytest.raises(OssClientError, match="invalid"):
        client.copy_from_url(
            bucket="game339",
            object_key="narrato/model-results/task/0.mp4",
            source_url="http://provider.example/result.mp4",
        )


def test_video_policy_uses_fixed_api_prefix_type_and_300_mib_limit() -> None:
    service = OssPostPolicyService(
        upload_url="https://uploads.example.test",
        bucket="narrato",
        access_key_id="access-key",
        access_key_secret="access-secret",
        today=lambda: date(2026, 7, 17),
        token_factory=lambda: "token",
    )

    policy = service.create_policy(
        asset_type="video",
        filename="Episode.MP4",
        size_bytes=314_572_800,
        existing_video_count=0,
    )

    decoded = json.loads(base64.b64decode(policy.fields["policy"]))
    assert policy.key == "narrato/api/2026/07/17/token.mp4"
    assert policy.max_size_bytes == 314_572_800
    assert policy.fields["key"] == policy.key
    assert policy.fields["Content-Type"] == "video/mp4"
    assert ["eq", "$key", policy.key] in decoded["conditions"]
    assert ["eq", "$Content-Type", "video/mp4"] in decoded["conditions"]
    assert ["content-length-range", 0, 314_572_800] in decoded["conditions"]


def test_subtitle_policy_uses_octet_stream_for_oss_form_compatibility() -> None:
    """SRT 直传统一使用 OSS 可稳定识别的二进制 MIME 类型。"""

    service = OssPostPolicyService(
        upload_url="https://uploads.example.test",
        bucket="narrato",
        access_key_id="key",
        access_key_secret="secret",
        today=lambda: date(2026, 7, 17),
        token_factory=lambda: "token",
    )

    policy = service.create_policy(
        asset_type="subtitle",
        filename="episode.srt",
        size_bytes=1,
        existing_video_count=0,
        content_type="application/octet-stream",
    )

    decoded = json.loads(base64.b64decode(policy.fields["policy"]))
    assert policy.fields["Content-Type"] == "application/octet-stream"
    assert ["eq", "$Content-Type", "application/octet-stream"] in decoded["conditions"]


@pytest.mark.parametrize(
    ("asset_type", "filename", "size_bytes"),
    [
        ("video", "episode.mkv", 1),
        ("video", "episode.mp4", 314_572_801),
        ("subtitle", "episode.srt", 5_242_881),
        ("subtitle", "episode.txt", 1),
    ],
)
def test_policy_rejects_disallowed_extension_or_file_boundary(
    asset_type: str, filename: str, size_bytes: int
) -> None:
    service = OssPostPolicyService(
        upload_url="https://uploads.example.test",
        bucket="narrato",
        access_key_id="access-key",
        access_key_secret="access-secret",
    )

    with pytest.raises(AssetDeclarationError):
        service.create_policy(
            asset_type=asset_type,
            filename=filename,
            size_bytes=size_bytes,
            existing_video_count=0,
        )


def test_policy_rejects_content_type_that_does_not_match_extension() -> None:
    service = OssPostPolicyService(
        upload_url="https://uploads.example.test",
        bucket="narrato",
        access_key_id="access-key",
        access_key_secret="access-secret",
    )

    with pytest.raises(AssetDeclarationError):
        service.create_policy(
            asset_type="video",
            filename="episode.mp4",
            size_bytes=1,
            content_type="video/quicktime",
            existing_video_count=0,
        )


def test_video_reservation_uses_postgresql_project_row_lock() -> None:
    from sqlalchemy.dialects import postgresql

    statement = project_for_update_statement(user_id="usr_1", project_id="prj_1")

    assert "FOR UPDATE" in str(statement.compile(dialect=postgresql.dialect()))


def test_image_policy_uses_fixed_mime_and_20_mib_limit() -> None:
    service = OssPostPolicyService(
        upload_url="https://uploads.example.test", bucket="narrato",
        access_key_id="key", access_key_secret="secret", today=lambda: date(2026, 7, 17), token_factory=lambda: "image-token",
    )
    policy = service.create_policy(asset_type="image", filename="reference.PNG", size_bytes=20_971_520, existing_video_count=0)
    assert policy.key == "narrato/api/2026/07/17/image-token.png"
    assert policy.fields["Content-Type"] == "image/png"
    assert policy.max_size_bytes == 20_971_520


def test_ai_video_video_capacity_can_exceed_legacy_five_limit() -> None:
    declaration = validate_asset_declaration(asset_type="video", filename="reference.mp4", size_bytes=1, existing_video_count=9, max_video_count=50)
    assert declaration.extension == ".mp4"

from __future__ import annotations

import base64
import json
from datetime import date

import pytest

from narrato_api.assets.constraints import AssetDeclarationError
from narrato_api.assets.service import project_for_update_statement
from narrato_api.integrations.oss_client import HttpOssClient, OssPostPolicyService


def test_oss_client_composes_bucket_url_from_endpoint_host() -> None:
    client = HttpOssClient(endpoint="oss-cn-shanghai.aliyuncs.com")

    assert client.public_url("game339", "narrato/api/episode.mp4") == (
        "https://game339.oss-cn-shanghai.aliyuncs.com/narrato/api/episode.mp4"
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

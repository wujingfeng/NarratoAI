from __future__ import annotations

import base64
import json
from datetime import date

import pytest

from narrato_api.assets.constraints import AssetDeclarationError
from narrato_api.integrations.oss_client import OssPostPolicyService


def test_video_policy_uses_fixed_api_prefix_type_and_300_mib_limit() -> None:
    service = OssPostPolicyService(
        endpoint="https://oss.example.test",
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
        endpoint="https://oss.example.test",
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

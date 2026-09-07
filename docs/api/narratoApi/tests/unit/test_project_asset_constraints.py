from __future__ import annotations

import pytest
from types import SimpleNamespace

from narrato_api.api.errors import ApiError
from narrato_api.assets.constraints import (
    AssetDeclarationError,
    AssetLimitError,
    validate_asset_declaration,
)
from narrato_api.assets.service import UploadService


def test_video_declaration_accepts_the_fifth_video_at_300_mib() -> None:
    declaration = validate_asset_declaration(
        asset_type="video",
        filename="episode-05.mp4",
        size_bytes=314_572_800,
        existing_video_count=4,
    )

    assert declaration.extension == ".mp4"
    assert declaration.max_size_bytes == 314_572_800


@pytest.mark.parametrize(
    ("asset_type", "filename", "size_bytes"),
    [
        ("video", "episode.mkv", 1),
        ("video", "episode.mov", 314_572_801),
        ("subtitle", "episode.txt", 1),
        ("subtitle", "episode.srt", 5_242_881),
        ("video", "a" * 252 + ".mp4", 1),
    ],
)
def test_asset_declaration_rejects_invalid_filename_or_size(
    asset_type: str, filename: str, size_bytes: int
) -> None:
    with pytest.raises(AssetDeclarationError):
        validate_asset_declaration(
            asset_type=asset_type,
            filename=filename,
            size_bytes=size_bytes,
            existing_video_count=0,
        )


def test_video_declaration_rejects_a_sixth_video_for_one_project() -> None:
    with pytest.raises(AssetLimitError):
        validate_asset_declaration(
            asset_type="video",
            filename="episode-06.avi",
            size_bytes=1,
            existing_video_count=5,
        )


def test_short_drama_multimodal_limit_does_not_lower_other_product_limits() -> None:
    with pytest.raises(ApiError) as caught:
        UploadService._validate_short_drama_multimodal_size(
            project=SimpleNamespace(product="short_drama_narration"),
            asset_type="video",
            size_bytes=52_428_801,
        )
    assert caught.value.code == "VIDEO_TOO_LARGE_FOR_MULTIMODAL"

    UploadService._validate_short_drama_multimodal_size(
        project=SimpleNamespace(product="video_translation"),
        asset_type="video",
        size_bytes=314_572_800,
    )

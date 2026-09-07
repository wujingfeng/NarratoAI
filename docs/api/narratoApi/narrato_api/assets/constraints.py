from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath

MAX_FILENAME_LENGTH = 255
MAX_PROJECT_VIDEO_COUNT = 5
MAX_AI_VIDEO_PROJECT_VIDEO_COUNT = 50
MAX_VIDEO_SIZE_BYTES = 314_572_800
MAX_SHORT_DRAMA_MULTIMODAL_VIDEO_SIZE_BYTES = 52_428_800
MAX_IMAGE_SIZE_BYTES = 20_971_520
MAX_SUBTITLE_SIZE_BYTES = 5_242_880
MAX_AUDIO_SIZE_BYTES = 104_857_600
_ALLOWED_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".webp"},
    "video": {".mp4", ".mov", ".avi"},
    "subtitle": {".srt"},
    "audio": {".mp3", ".wav", ".m4a", ".aac", ".ogg"},
}


class AssetDeclarationError(ValueError):
    """资产声明未满足文件名、格式或大小约束。"""


class AssetLimitError(AssetDeclarationError):
    """项目已达到视频资产数量上限。"""


@dataclass(frozen=True, slots=True)
class AssetDeclaration:
    """经验证、可用于后续上传流程的最小文件声明。"""

    extension: str
    max_size_bytes: int


def validate_asset_declaration(
    *, asset_type: str, filename: str, size_bytes: int, existing_video_count: int,
    max_video_count: int = MAX_PROJECT_VIDEO_COUNT,
) -> AssetDeclaration:
    """校验项目资产的类型、文件名、大小和视频数量上限。"""

    if asset_type not in _ALLOWED_EXTENSIONS:
        raise AssetDeclarationError("unsupported asset type")
    if not filename or len(filename) > MAX_FILENAME_LENGTH:
        raise AssetDeclarationError("invalid filename length")
    extension = PurePath(filename).suffix.lower()
    if extension not in _ALLOWED_EXTENSIONS[asset_type]:
        raise AssetDeclarationError("unsupported file extension")
    if size_bytes < 0:
        raise AssetDeclarationError("invalid file size")
    if asset_type == "image":
        max_size_bytes = MAX_IMAGE_SIZE_BYTES
    elif asset_type == "video":
        if existing_video_count >= max_video_count:
            raise AssetLimitError("project video limit exceeded")
        max_size_bytes = MAX_VIDEO_SIZE_BYTES
    elif asset_type == "subtitle":
        max_size_bytes = MAX_SUBTITLE_SIZE_BYTES
    else:
        max_size_bytes = MAX_AUDIO_SIZE_BYTES
    if size_bytes > max_size_bytes:
        raise AssetDeclarationError("file size exceeds limit")
    return AssetDeclaration(extension=extension, max_size_bytes=max_size_bytes)

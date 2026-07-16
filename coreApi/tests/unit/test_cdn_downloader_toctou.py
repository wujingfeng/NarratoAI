from __future__ import annotations

import httpx
import pytest

from core_api.infrastructure.oss_client import (
    CdnUrlPolicy,
    DownloadTemporaryError,
    HttpCdnDownloader,
)
from core_api.runtime.workspace import CoreTaskWorkspace


def test_downloader_rejects_replaced_workspace_ancestor(tmp_path):
    """校验后替换祖先目录为 symlink 不得向工作区外写入。"""

    workspace = CoreTaskWorkspace.create(tmp_path / "work", "ctask_safe1", 1)
    target = workspace.controlled_path("input", "source", "mp4")
    original = workspace.root / "input-original"
    workspace.input_dir.rename(original)
    outside = tmp_path / "outside"
    outside.mkdir()
    workspace.input_dir.symlink_to(outside, target_is_directory=True)
    downloader = HttpCdnDownloader(
        CdnUrlPolicy({"cdn.example.test"}),
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=b"owned")),
    )

    with pytest.raises(DownloadTemporaryError, match="SOURCE_DOWNLOAD_FAILED"):
        downloader.download("https://cdn.example.test/narrato/api/source.mp4", target, max_bytes=100)
    assert not (outside / "source.mp4").exists()


def test_downloader_does_not_delete_preexisting_destination(tmp_path):
    """O_EXCL 失败不得把非本次创建的同名文件当临时文件删除。"""

    destination = tmp_path / "existing.mp4"
    destination.write_bytes(b"keep")
    downloader = HttpCdnDownloader(
        CdnUrlPolicy({"cdn.example.test"}),
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=b"new")),
    )
    with pytest.raises(DownloadTemporaryError):
        downloader.download(
            "https://cdn.example.test/narrato/api/source.mp4",
            destination,
            max_bytes=100,
        )
    assert destination.read_bytes() == b"keep"

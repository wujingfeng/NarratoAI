from __future__ import annotations

import re
from datetime import date

import httpx
import pytest

from core_api.infrastructure.oss_client import (
    CdnUrlPolicy,
    DownloadTooLargeError,
    HttpCdnDownloader,
    InputSecurityError,
    Oss2Client,
    build_object_key,
)
from core_api.runtime.workspace import CoreTaskWorkspace, WorkspaceSecurityError


def test_core_object_key_uses_required_prefix():
    key = build_object_key(now=date(2026, 7, 16), extension="srt", seed="fixed")
    assert re.fullmatch(r"narrato/coreApi/2026/07/16/[0-9a-f]{32}\.srt", key)


@pytest.mark.parametrize(
    "extension",
    ["../srt", "video.mp4", "srt.exe", "/srt", "s%72t", ""],
)
def test_core_object_key_rejects_uncontrolled_extensions(extension):
    with pytest.raises(ValueError):
        build_object_key(now=date(2026, 7, 16), extension=extension, seed="fixed")


@pytest.mark.parametrize(
    "url",
    [
        "http://cdn.example.test/narrato/api/a.mp4",
        "file:///etc/passwd",
        "https://user@cdn.example.test/narrato/api/a.mp4",
        "https://127.0.0.1/narrato/api/a.mp4",
        "https://cdn.example.test/narrato/api/../private/a.mp4",
        "https://cdn.example.test/narrato/api/%2e%2e/private/a.mp4",
        "https://cdn.example.test/narrato/api/%252e%252e/private/a.mp4",
        "https://cdn.example.test/narrato/api/a%2fb.mp4",
        "https://cdn.example.test/narrato/api/a\\b.mp4",
        "https://evil.example.test/narrato/api/a.mp4",
        "https://cdn.example.test/narrato/api/a.mp4#fragment",
    ],
)
def test_cdn_url_policy_rejects_ssrf_and_traversal(url):
    policy = CdnUrlPolicy({"cdn.example.test"})
    with pytest.raises(InputSecurityError):
        policy.validate(url)


def test_cdn_url_policy_accepts_exact_https_business_prefix():
    policy = CdnUrlPolicy({"cdn.example.test"})
    assert (
        policy.validate("https://cdn.example.test/narrato/api/2026/07/a.mp4?x=1")
        == "https://cdn.example.test/narrato/api/2026/07/a.mp4?x=1"
    )


@pytest.mark.parametrize("depth", range(1, 9))
@pytest.mark.parametrize("dangerous", ["..", "/", "\\", "%"])
def test_cdn_url_policy_rejects_recursively_encoded_path_ambiguity(depth, dangerous):
    encoded = dangerous
    for _ in range(depth):
        encoded = "".join(f"%{byte:02x}" for byte in encoded.encode("utf-8"))
    policy = CdnUrlPolicy({"cdn.example.test"})
    with pytest.raises(InputSecurityError):
        policy.validate(f"https://cdn.example.test/narrato/api/{encoded}private.mp4")


def test_downloader_sends_only_the_canonical_validated_path(tmp_path):
    observed: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        observed.append(request.url.raw_path.decode("ascii"))
        return httpx.Response(200, content=b"ok")

    downloader = HttpCdnDownloader(
        CdnUrlPolicy({"CDN.Example.Test."}), transport=httpx.MockTransport(respond)
    )
    downloader.download(
        "https://cdn.example.test.:443/narrato/api/video.mp4",
        tmp_path / "input.mp4",
        max_bytes=2,
    )
    assert observed == ["/narrato/api/video.mp4"]


def test_cdn_policy_canonicalizes_idna_host_and_keeps_exact_allowlist():
    policy = CdnUrlPolicy({"例子.测试"})
    assert policy.validate("https://例子.测试/narrato/api/a.mp4") == (
        "https://xn--fsqu00a.xn--0zwm56d/narrato/api/a.mp4"
    )
    with pytest.raises(InputSecurityError):
        policy.validate("https://例子.公司/narrato/api/a.mp4")


def test_downloader_revalidates_redirect_target(tmp_path):
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://evil.test/private"})

    downloader = HttpCdnDownloader(
        CdnUrlPolicy({"cdn.example.test"}), transport=httpx.MockTransport(respond)
    )
    with pytest.raises(InputSecurityError):
        downloader.download(
            "https://cdn.example.test/narrato/api/a.mp4",
            tmp_path / "input.mp4",
            max_bytes=32,
        )


def test_downloader_rejects_deeply_encoded_redirect_target(tmp_path):
    target = ".."
    for _ in range(6):
        target = "".join(f"%{byte:02x}" for byte in target.encode())

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={
                "Location": f"https://cdn.example.test/narrato/api/{target}/private"
            },
        )

    downloader = HttpCdnDownloader(
        CdnUrlPolicy({"cdn.example.test"}), transport=httpx.MockTransport(respond)
    )
    with pytest.raises(InputSecurityError):
        downloader.download(
            "https://cdn.example.test/narrato/api/a.mp4",
            tmp_path / "input.mp4",
            max_bytes=32,
        )


@pytest.mark.parametrize("advertised", [True, False])
def test_downloader_rejects_oversize_and_removes_partial_file(tmp_path, advertised):
    def respond(request: httpx.Request) -> httpx.Response:
        headers = {"Content-Length": "64"} if advertised else {}
        return httpx.Response(200, headers=headers, content=b"x" * 64)

    destination = tmp_path / "input.mp4"
    downloader = HttpCdnDownloader(
        CdnUrlPolicy({"cdn.example.test"}), transport=httpx.MockTransport(respond)
    )
    with pytest.raises(DownloadTooLargeError):
        downloader.download(
            "https://cdn.example.test/narrato/api/a.mp4",
            destination,
            max_bytes=32,
        )
    assert not destination.exists()


@pytest.mark.parametrize(
    ("endpoint", "public_url"),
    [
        ("http://oss.example.test", "https://cdn.example.test"),
        ("https://oss.example.test", "http://cdn.example.test"),
    ],
)
def test_production_oss_adapter_requires_https(endpoint, public_url):
    with pytest.raises(ValueError):
        Oss2Client(
            endpoint=endpoint,
            bucket="bucket",
            access_key_id="id",
            access_key_secret="secret",
            public_base_url=public_url,
        )


def test_attempt_workspace_isolated_and_never_reuses_dirty_attempt(tmp_path):
    first = CoreTaskWorkspace.create(tmp_path, "ctask_01ABC", 1)
    second = CoreTaskWorkspace.create(tmp_path, "ctask_01ABC", 2)

    assert first.input_dir != second.input_dir
    assert first.input_dir.is_dir() and first.temp_dir.is_dir() and first.output_dir.is_dir()
    with pytest.raises(FileExistsError):
        CoreTaskWorkspace.create(tmp_path, "ctask_01ABC", 1)


@pytest.mark.parametrize("task_id", ["../escape", "ctask_a/b", "bad", "ctask_.."])
def test_workspace_rejects_invalid_task_ids(tmp_path, task_id):
    with pytest.raises(WorkspaceSecurityError):
        CoreTaskWorkspace.create(tmp_path, task_id, 1)

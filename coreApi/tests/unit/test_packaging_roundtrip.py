from __future__ import annotations

import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


LEGACY_FILES = {
    "app/__init__.py",
    "app/services/__init__.py",
    "app/services/fun_asr_subtitle.py",
    "app/services/media_probe.py",
}


def test_vendored_legacy_sources_match_monorepo_source():
    core_root = Path(__file__).resolve().parents[2]
    repository_root = core_root.parent
    vendor_root = core_root / "vendor_legacy"
    for relative in LEGACY_FILES:
        assert (vendor_root / relative).read_bytes() == (
            repository_root / relative
        ).read_bytes()


def test_sdist_roundtrip_preserves_selective_legacy_runtime(tmp_path):
    source = Path(__file__).resolve().parents[2]
    checkout = tmp_path / "source"
    shutil.copytree(
        source,
        checkout,
        ignore=shutil.ignore_patterns(
            ".venv", "build", "dist", "*.egg-info", "__pycache__"
        ),
    )
    subprocess.run(
        [sys.executable, "-m", "build", "--sdist", "--no-isolation"],
        cwd=checkout,
        check=True,
        capture_output=True,
        text=True,
    )
    archive = next((checkout / "dist").glob("*.tar.gz"))
    with tarfile.open(archive) as value:
        legacy_in_sdist = {
            "/".join(Path(name).parts[1:])
            for name in value.getnames()
            if "vendor_legacy/app/" in name and name.endswith(".py")
        }
        value.extractall(tmp_path / "release", filter="data")
    assert legacy_in_sdist == {f"vendor_legacy/{item}" for item in LEGACY_FILES}

    release = next((tmp_path / "release").iterdir())
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--no-isolation"],
        cwd=release,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next((release / "dist").glob("*.whl"))
    with zipfile.ZipFile(wheel) as value:
        legacy_in_wheel = {name for name in value.namelist() if name.startswith("app/")}
    assert legacy_in_wheel == LEGACY_FILES

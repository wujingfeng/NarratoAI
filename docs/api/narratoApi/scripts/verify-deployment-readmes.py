#!/usr/bin/env python3
"""Check that both API deployment guides retain executable safety guidance."""

from __future__ import annotations

import sys
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = SERVICE_ROOT.parents[2]
README_PATHS = (
    SERVICE_ROOT / "README.md",
    REPOSITORY_ROOT / "coreApi" / "README.md",
)
REQUIRED_FRAGMENTS = (
    'export REPO_ROOT="$(git rev-parse --show-toplevel)"',
    "verify-supervisor-config.py",
    "verify-nginx-config.py",
    'nginx -t -c "$REPO_ROOT/docs/api/narratoApi/deploy/nginx.conf"',
    "/etc/narrato-api/narrato-api.toml",
    "/etc/narrato-core-api/core-api.toml",
    "supervisorctl start",
    "supervisorctl stop",
    "supervisorctl reread",
    "/var/log/narrato-api",
    "/var/log/narrato-core-api",
    "Range",
    "GET",
    "HEAD",
)
CORE_QUEUE_REQUIREMENTS = (
    "narrato.core.default",
    "single",
    "task_routes",
    "queue isolation",
)


def main() -> int:
    """Report missing deployment instructions without running deployment tools."""

    failures: list[str] = []
    contents: dict[Path, str] = {}
    for readme_path in README_PATHS:
        try:
            content = readme_path.read_text(encoding="utf-8")
        except OSError as error:
            failures.append(f"{readme_path}: cannot read ({error})")
            continue
        contents[readme_path] = content
        for fragment in REQUIRED_FRAGMENTS:
            if fragment not in content:
                failures.append(f"{readme_path}: missing {fragment!r}")

    core_readme = README_PATHS[1]
    for fragment in CORE_QUEUE_REQUIREMENTS:
        if fragment not in contents.get(core_readme, ""):
            failures.append(f"{core_readme}: missing Core queue explanation {fragment!r}")

    if failures:
        print("Deployment README validation failed:", file=sys.stderr)
        print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        return 1
    print(f"Deployment README validation passed: {len(README_PATHS)} guides")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

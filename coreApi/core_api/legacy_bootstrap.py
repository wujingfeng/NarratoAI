from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def bootstrap_legacy_app() -> Path | None:
    """Load the packaged legacy adapter modules or an explicit dev fallback."""

    dev_fallback = os.environ.get("NARRATO_CORE_ENABLE_MONOREPO_FALLBACK") == "1"
    if not dev_fallback and importlib.util.find_spec("app") is not None:
        return None
    if not dev_fallback:
        raise RuntimeError(
            "NARRATO_LEGACY_PACKAGE_MISSING: install the Core API wheel with its "
            "packaged app modules, or explicitly enable the monorepo dev fallback"
        )

    repository_root = Path(__file__).resolve().parents[2]
    if not (repository_root / "app" / "__init__.py").is_file():
        raise RuntimeError(
            "NARRATO_LEGACY_PACKAGE_MISSING: monorepo fallback was enabled but "
            "the legacy app package was not found"
        )
    root = str(repository_root)
    if root not in sys.path:
        sys.path.insert(0, root)
    return repository_root

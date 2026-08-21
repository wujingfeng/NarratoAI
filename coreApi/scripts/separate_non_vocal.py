#!/usr/bin/env python3
"""Run Demucs two-stem separation and materialize one non-vocal WAV.

This wrapper is intentionally a separate process: the Core worker can keep its
small runtime while production points ``audio_separation_command`` at a
dedicated Python environment containing Demucs and Torch.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="htdemucs")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--jobs", default=2, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.input.resolve()
    target = args.output.resolve()
    if not source.is_file() or args.jobs < 1:
        return 2

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="narrato-demucs-") as temp:
        work = Path(temp)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "demucs",
                "-n",
                args.model,
                "--two-stems",
                "vocals",
                "--shifts",
                "0",
                "-d",
                args.device,
                "-j",
                str(args.jobs),
                "-o",
                str(work),
                str(source),
            ],
            check=False,
        )
        if result.returncode != 0:
            return result.returncode
        stems = list(work.glob("*/**/no_vocals.wav"))
        if len(stems) != 1 or stems[0].stat().st_size <= 44:
            return 3
        shutil.copyfile(stems[0], target)
    return 0 if target.is_file() and target.stat().st_size > 44 else 3


if __name__ == "__main__":
    raise SystemExit(main())

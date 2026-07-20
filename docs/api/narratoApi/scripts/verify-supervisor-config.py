#!/usr/bin/env python3
"""Statically validate the Narrato Business API Supervisor definitions.

This checker reads configuration only.  It never invokes Supervisor or any
configured program, so it is safe to run in a development checkout.
"""

from __future__ import annotations

import configparser
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProgramSpec:
    """Required static properties for one Supervisor program."""

    filename: str
    section: str
    command_fragments: tuple[str, ...]
    forbidden_command_fragments: tuple[str, ...] = ()


SERVICE_ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR_DIR = SERVICE_ROOT / "supervisor"
PROGRAMS = (
    ProgramSpec(
        filename="narrato-api-web.conf",
        section="program:narrato-api-web",
        command_fragments=(".venv/bin/uvicorn", "narrato_api.main:create_app", "--factory"),
    ),
    ProgramSpec(
        filename="narrato-api-worker.conf",
        section="program:narrato-api-worker",
        command_fragments=(
            ".venv/bin/celery",
            "worker",
            "--queues=narrato.business.default",
        ),
    ),
    ProgramSpec(
        filename="narrato-api-scheduler.conf",
        section="program:narrato-api-scheduler",
        command_fragments=(".venv/bin/celery", "beat"),
        forbidden_command_fragments=(" worker", "--queues="),
    ),
)


def _read_program(path: Path, section: str) -> configparser.SectionProxy:
    parser = configparser.ConfigParser(interpolation=None)
    with path.open(encoding="utf-8") as config_file:
        parser.read_file(config_file)
    if parser.sections() != [section]:
        found = ", ".join(parser.sections()) or "no program sections"
        raise ValueError(f"{path.name}: expected [{section}], found {found}")
    return parser[section]


def _require_nonempty(program: configparser.SectionProxy, option: str, label: str) -> str:
    value = program.get(option, "").strip()
    if not value:
        raise ValueError(f"{label}: missing {option}")
    return value


def _require_true(program: configparser.SectionProxy, option: str, label: str) -> None:
    try:
        value = program.getboolean(option)
    except ValueError as error:
        raise ValueError(f"{label}: {option} must be true") from error
    if value is not True:
        raise ValueError(f"{label}: {option} must be true")


def _verify_program(spec: ProgramSpec) -> None:
    path = SUPERVISOR_DIR / spec.filename
    if not path.is_file():
        raise ValueError(f"missing Supervisor configuration: {path}")

    label = path.name
    program = _read_program(path, spec.section)
    command = _require_nonempty(program, "command", label)
    directory = _require_nonempty(program, "directory", label)
    environment = _require_nonempty(program, "environment", label)

    if ".venv/bin/" not in command:
        raise ValueError(f"{label}: command must use the service .venv")
    if not directory.startswith("/"):
        raise ValueError(f"{label}: directory must be an absolute service path")
    if "NARRATO_API_CONFIG=" not in environment or ".toml" not in environment:
        raise ValueError(f"{label}: environment must provide NARRATO_API_CONFIG TOML")
    for fragment in spec.command_fragments:
        if fragment not in command:
            raise ValueError(f"{label}: command is missing {fragment!r}")
    for fragment in spec.forbidden_command_fragments:
        if fragment in command:
            raise ValueError(f"{label}: command must not include {fragment!r}")

    for option in ("autostart", "autorestart", "stopasgroup", "killasgroup"):
        _require_true(program, option, label)

    if _require_nonempty(program, "stopsignal", label).upper() not in {"TERM", "INT", "QUIT"}:
        raise ValueError(f"{label}: stopsignal must be a graceful signal")
    stopwaitsecs = _require_nonempty(program, "stopwaitsecs", label)
    try:
        if int(stopwaitsecs) < 10:
            raise ValueError
    except ValueError as error:
        raise ValueError(f"{label}: stopwaitsecs must be an integer of at least 10") from error

    stdout_log = _require_nonempty(program, "stdout_logfile", label)
    stderr_log = _require_nonempty(program, "stderr_logfile", label)
    if not stdout_log.startswith("/") or not stderr_log.startswith("/"):
        raise ValueError(f"{label}: log paths must be absolute")
    if stdout_log == stderr_log:
        raise ValueError(f"{label}: stdout_logfile and stderr_logfile must differ")


def main() -> int:
    """Validate every Business API process definition without starting it."""

    try:
        for spec in PROGRAMS:
            _verify_program(spec)
    except (OSError, ValueError, configparser.Error) as error:
        print(f"Supervisor configuration invalid: {error}", file=sys.stderr)
        return 1
    print(f"Supervisor configuration valid: {len(PROGRAMS)} Business API programs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

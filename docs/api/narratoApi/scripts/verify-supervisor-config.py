#!/usr/bin/env python3
"""Statically validate the Narrato API platform Supervisor definitions.

This checker reads configuration only.  It never invokes Supervisor or any
configured program, so it is safe to run in a development checkout.

Core currently routes every durable ``core.tasks.wake`` message to
``narrato.core.default``.  The role-named Core workers therefore verify that
they consume that real queue rather than claiming unimplemented role queues.
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
    supervisor_dir: Path | None = None
    environment_key: str = "NARRATO_API_CONFIG"
    required_pythonpath: str | None = None


SERVICE_ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR_DIR = SERVICE_ROOT / "supervisor"
REPOSITORY_ROOT = SERVICE_ROOT.parents[2]
CORE_SERVICE_ROOT = REPOSITORY_ROOT / "coreApi"
CORE_SUPERVISOR_DIR = CORE_SERVICE_ROOT / "supervisor"
CORE_DEFAULT_QUEUE = "narrato.core.default"
PROGRAMS = (
    ProgramSpec(
        filename="narrato-api-web.conf",
        section="program:narrato-api-web",
        command_fragments=(
            ".venv/bin/uvicorn",
            "narrato_api.main:create_app",
            "--factory",
        ),
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
    ProgramSpec(
        filename="core-api-web.conf",
        section="program:core-api-web",
        command_fragments=(
            "coreApi/.venv/bin/uvicorn",
            "core_api.main:create_app",
            "--factory",
        ),
        supervisor_dir=CORE_SUPERVISOR_DIR,
        environment_key="CORE_API_CONFIG",
        required_pythonpath="/srv/narrato/NarratoAI",
    ),
    ProgramSpec(
        filename="core-api-scheduler.conf",
        section="program:core-api-scheduler",
        command_fragments=(
            "coreApi/.venv/bin/celery",
            "-A core_api.celery_app:celery_app",
            "beat",
        ),
        forbidden_command_fragments=(" worker", "--queues="),
        supervisor_dir=CORE_SUPERVISOR_DIR,
        environment_key="CORE_API_CONFIG",
        required_pythonpath="/srv/narrato/NarratoAI",
    ),
    ProgramSpec(
        filename="core-worker-analysis.conf",
        section="program:core-worker-analysis",
        command_fragments=(
            "coreApi/.venv/bin/celery",
            "-A core_api.celery_app:celery_app",
            "worker",
            f"--queues={CORE_DEFAULT_QUEUE}",
            "--hostname=core-analysis@",
        ),
        supervisor_dir=CORE_SUPERVISOR_DIR,
        environment_key="CORE_API_CONFIG",
        required_pythonpath="/srv/narrato/NarratoAI",
    ),
    ProgramSpec(
        filename="core-worker-asr.conf",
        section="program:core-worker-asr",
        command_fragments=(
            "coreApi/.venv/bin/celery",
            "-A core_api.celery_app:celery_app",
            "worker",
            f"--queues={CORE_DEFAULT_QUEUE}",
            "--hostname=core-asr@",
        ),
        supervisor_dir=CORE_SUPERVISOR_DIR,
        environment_key="CORE_API_CONFIG",
        required_pythonpath="/srv/narrato/NarratoAI",
    ),
    ProgramSpec(
        filename="core-worker-tts.conf",
        section="program:core-worker-tts",
        command_fragments=(
            "coreApi/.venv/bin/celery",
            "-A core_api.celery_app:celery_app",
            "worker",
            f"--queues={CORE_DEFAULT_QUEUE}",
            "--hostname=core-tts@",
        ),
        supervisor_dir=CORE_SUPERVISOR_DIR,
        environment_key="CORE_API_CONFIG",
        required_pythonpath="/srv/narrato/NarratoAI",
    ),
    ProgramSpec(
        filename="core-worker-render.conf",
        section="program:core-worker-render",
        command_fragments=(
            "coreApi/.venv/bin/celery",
            "-A core_api.celery_app:celery_app",
            "worker",
            f"--queues={CORE_DEFAULT_QUEUE}",
            "--hostname=core-render@",
        ),
        supervisor_dir=CORE_SUPERVISOR_DIR,
        environment_key="CORE_API_CONFIG",
        required_pythonpath="/srv/narrato/NarratoAI",
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


def _require_nonempty(
    program: configparser.SectionProxy, option: str, label: str
) -> str:
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


def _verify_program(spec: ProgramSpec) -> tuple[str, str]:
    path = (spec.supervisor_dir or SUPERVISOR_DIR) / spec.filename
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
    if f"{spec.environment_key}=" not in environment or ".toml" not in environment:
        raise ValueError(
            f"{label}: environment must provide {spec.environment_key} TOML"
        )
    if (
        spec.required_pythonpath is not None
        and f'PYTHONPATH="{spec.required_pythonpath}"' not in environment
    ):
        raise ValueError(
            f"{label}: environment must provide repository-root PYTHONPATH"
        )
    for fragment in spec.command_fragments:
        if fragment not in command:
            raise ValueError(f"{label}: command is missing {fragment!r}")
    for fragment in spec.forbidden_command_fragments:
        if fragment in command:
            raise ValueError(f"{label}: command must not include {fragment!r}")

    for option in ("autostart", "autorestart", "stopasgroup", "killasgroup"):
        _require_true(program, option, label)

    if _require_nonempty(program, "stopsignal", label).upper() not in {
        "TERM",
        "INT",
        "QUIT",
    }:
        raise ValueError(f"{label}: stopsignal must be a graceful signal")
    stopwaitsecs = _require_nonempty(program, "stopwaitsecs", label)
    try:
        if int(stopwaitsecs) < 10:
            raise ValueError
    except ValueError as error:
        raise ValueError(
            f"{label}: stopwaitsecs must be an integer of at least 10"
        ) from error

    stdout_log = _require_nonempty(program, "stdout_logfile", label)
    stderr_log = _require_nonempty(program, "stderr_logfile", label)
    if not stdout_log.startswith("/") or not stderr_log.startswith("/"):
        raise ValueError(f"{label}: log paths must be absolute")
    if stdout_log == stderr_log:
        raise ValueError(f"{label}: stdout_logfile and stderr_logfile must differ")
    return stdout_log, stderr_log


def main() -> int:
    """Validate every API-platform process definition without starting it."""

    try:
        seen_logs: set[str] = set()
        for spec in PROGRAMS:
            stdout_log, stderr_log = _verify_program(spec)
            for log_path in (stdout_log, stderr_log):
                if log_path in seen_logs:
                    raise ValueError(
                        f"{spec.filename}: log path must be unique: {log_path}"
                    )
                seen_logs.add(log_path)
    except (OSError, ValueError, configparser.Error) as error:
        print(f"Supervisor configuration invalid: {error}", file=sys.stderr)
        return 1
    print(f"Supervisor configuration valid: {len(PROGRAMS)} API platform programs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

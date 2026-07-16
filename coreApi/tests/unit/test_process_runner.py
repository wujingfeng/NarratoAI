from __future__ import annotations

import subprocess
import sys
import time
from unittest.mock import patch

import pytest

from core_api.runtime.process_runner import ProcessRunner


def test_process_runner_returns_success_and_nonzero_output():
    """Runner 返回成功与非零退出的受限输出。"""

    runner = ProcessRunner(output_limit_bytes=1024)
    success = runner.run([sys.executable, "-c", "print('ok')"])
    failure = runner.run(
        [sys.executable, "-c", "import sys; print('bad', file=sys.stderr); sys.exit(7)"]
    )
    assert (success.exit_code, success.stdout.strip(), success.timed_out) == (0, "ok", False)
    assert (failure.exit_code, failure.stderr.strip(), failure.timed_out) == (7, "bad", False)


def test_process_runner_heartbeats_and_times_out_process_group():
    """Runner 周期心跳并在超时后终止进程组。"""

    beats: list[float] = []
    runner = ProcessRunner(
        output_limit_bytes=1024,
        heartbeat_interval_seconds=0.02,
        terminate_grace_seconds=0.05,
    )
    result = runner.run(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        timeout_seconds=0.08,
        heartbeat=lambda: beats.append(time.monotonic()),
    )
    assert result.timed_out is True
    assert result.exit_code != 0
    assert len(beats) >= 2


def test_process_runner_truncates_stdout_and_stderr():
    """Runner 分别限制 stdout 与 stderr，且显式标记截断。"""

    runner = ProcessRunner(output_limit_bytes=32)
    result = runner.run(
        [
            sys.executable,
            "-c",
            "import sys; print('x'*200); print('y'*200, file=sys.stderr)",
        ]
    )
    assert len(result.stdout.encode()) <= 32
    assert len(result.stderr.encode()) <= 32
    assert result.stdout_truncated is True
    assert result.stderr_truncated is True


def test_process_runner_drains_large_stdout_and_stderr_without_deadlock():
    """双流同时超过 pipe buffer 时仍持续 drain 且内存有界。"""

    runner = ProcessRunner(output_limit_bytes=1024)
    result = runner.run(
        [
            sys.executable,
            "-c",
            "import os; data=b'x'*(2*1024*1024); "
            "os.write(1,data); os.write(2,data)",
        ],
        timeout_seconds=2,
    )
    assert result.exit_code == 0
    assert result.timed_out is False
    assert len(result.stdout.encode()) == 1024
    assert len(result.stderr.encode()) == 1024
    assert result.stdout_truncated is True
    assert result.stderr_truncated is True


def test_process_runner_uses_argument_list_and_new_session():
    """Runner 禁止 shell 拼接并创建独立 session。"""

    real_popen = subprocess.Popen
    observed: dict[str, object] = {}

    def recording_popen(*args, **kwargs):
        observed.update(kwargs)
        return real_popen(*args, **kwargs)

    with patch("core_api.runtime.process_runner.subprocess.Popen", recording_popen):
        ProcessRunner().run([sys.executable, "-c", "pass"])
    assert observed["shell"] is False
    assert observed["start_new_session"] is True


def test_process_runner_reclaims_child_when_heartbeat_fails():
    """心跳回调异常时也终止并回收子进程。"""

    runner = ProcessRunner(heartbeat_interval_seconds=0.01)
    with patch.object(runner, "_terminate_group", wraps=runner._terminate_group) as stop:
        with pytest.raises(RuntimeError, match="heartbeat failed"):
            runner.run(
                [sys.executable, "-c", "import time; time.sleep(5)"],
                heartbeat=lambda: (_ for _ in ()).throw(
                    RuntimeError("heartbeat failed")
                ),
            )
    stop.assert_called_once()


def test_process_runner_rejects_command_string():
    """Runner 只接受参数序列，不把整条命令当作可拆分字符串。"""

    with pytest.raises(ValueError, match="argv"):
        ProcessRunner().run("echo unsafe")


def test_timeout_kills_descendant_that_ignores_term_and_holds_pipe():
    """leader 退出后仍忽略 TERM 的后代必须在宽限后被整组 KILL。"""

    child = "import time; time.sleep(3)"
    parent = (
        "import signal,subprocess,sys,time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
        "signal.signal(signal.SIGTERM, signal.SIG_DFL); "
        "print('child-ready', flush=True); "
        "time.sleep(3)"
    )
    started = time.monotonic()
    result = ProcessRunner(
        heartbeat_interval_seconds=0.01,
        terminate_grace_seconds=0.05,
    ).run([sys.executable, "-c", parent], timeout_seconds=0.1)
    elapsed = time.monotonic() - started
    assert result.timed_out is True
    assert result.exit_code != 0
    assert "child-ready" in result.stdout
    assert elapsed < 0.8

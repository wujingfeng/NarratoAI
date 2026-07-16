from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """受治理子进程的有界执行结果。"""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    stdout_truncated: bool
    stderr_truncated: bool


class _BoundedCollector:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.data = bytearray()
        self.truncated = False

    def consume(self, stream) -> None:
        while chunk := stream.read(8192):
            remaining = self.limit - len(self.data)
            if remaining > 0:
                self.data.extend(chunk[:remaining])
            if len(chunk) > remaining:
                self.truncated = True
        stream.close()


class ProcessRunner:
    """以独立进程组执行参数列表，并提供心跳、超时和有界输出。"""

    def __init__(
        self,
        *,
        output_limit_bytes: int = 1_048_576,
        heartbeat_interval_seconds: float = 5,
        terminate_grace_seconds: float = 5,
    ) -> None:
        if output_limit_bytes < 0:
            raise ValueError("output_limit_bytes 不能小于零")
        if heartbeat_interval_seconds <= 0 or terminate_grace_seconds < 0:
            raise ValueError("心跳间隔必须为正数且终止宽限不能为负数")
        self.output_limit_bytes = output_limit_bytes
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.terminate_grace_seconds = terminate_grace_seconds

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float | None = None,
        heartbeat: Callable[[], None] | None = None,
        cwd: str | os.PathLike[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> ProcessResult:
        """安全执行 argv，并在超时时终止整个进程组。"""

        if (
            isinstance(argv, (str, bytes))
            or not argv
            or any(not isinstance(item, str) for item in argv)
        ):
            raise ValueError("argv 必须是非空字符串列表")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须大于零")

        process = subprocess.Popen(
            list(argv),
            cwd=cwd,
            env=env,
            shell=False,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert process.stdout is not None and process.stderr is not None
        stdout = _BoundedCollector(self.output_limit_bytes)
        stderr = _BoundedCollector(self.output_limit_bytes)
        readers = [
            threading.Thread(target=stdout.consume, args=(process.stdout,), daemon=True),
            threading.Thread(target=stderr.consume, args=(process.stderr,), daemon=True),
        ]
        for reader in readers:
            reader.start()

        started = time.monotonic()
        next_heartbeat = started
        timed_out = False
        try:
            while process.poll() is None:
                now = time.monotonic()
                if heartbeat is not None and now >= next_heartbeat:
                    heartbeat()
                    next_heartbeat = now + self.heartbeat_interval_seconds
                if timeout_seconds is not None and now - started >= timeout_seconds:
                    timed_out = True
                    self._terminate_group(process)
                    break
                time.sleep(min(self.heartbeat_interval_seconds, 0.02))
        except BaseException:
            # 心跳或宿主逻辑异常也必须回收独立进程组，不能遗留孤儿进程。
            self._terminate_group(process)
            process.wait()
            self._finish_readers(process, readers)
            raise

        process.wait()
        if not self._finish_readers(process, readers, close_on_timeout=False):
            # leader 正常退出但后代仍持有 pipe 时，同样治理整个进程组。
            self._terminate_group(process)
            self._finish_readers(process, readers)
        return ProcessResult(
            exit_code=process.returncode,
            stdout=stdout.data.decode("utf-8", errors="replace"),
            stderr=stderr.data.decode("utf-8", errors="replace"),
            timed_out=timed_out,
            stdout_truncated=stdout.truncated,
            stderr_truncated=stderr.truncated,
        )

    def _terminate_group(self, process: subprocess.Popen[bytes]) -> None:
        """先 TERM 整个进程组，宽限后仍存活则 KILL。"""

        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + self.terminate_grace_seconds
        while time.monotonic() < deadline:
            process.poll()
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                return
            time.sleep(min(0.01, max(0, deadline - time.monotonic())))
        # 宽限针对整个进程组；leader 已退出也必须清理仍存活的后代。
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        process.wait()

    def _finish_readers(
        self,
        process: subprocess.Popen[bytes],
        readers: list[threading.Thread],
        *,
        close_on_timeout: bool = True,
    ) -> bool:
        """在有界时间内回收输出线程，必要时关闭本端 pipe。"""

        deadline = time.monotonic() + max(self.terminate_grace_seconds, 0.1)
        for reader in readers:
            reader.join(timeout=max(0, deadline - time.monotonic()))
        if all(not reader.is_alive() for reader in readers):
            return True
        if not close_on_timeout:
            return False
        for stream in (process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()
        for reader in readers:
            reader.join(timeout=0.1)
        return all(not reader.is_alive() for reader in readers)

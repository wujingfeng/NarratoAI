"""Crash-safe reconciliation of OSS objects whose DB commit outcome is unknown."""

from __future__ import annotations

from core_api.type_coercion import as_float, as_int, as_mapping, as_sequence

import json
import fcntl
import hashlib
import os
import secrets
import stat
import re
import threading
import time
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.runtime.artifact_store import ArtifactRef, ArtifactStore
from core_api.tasks.models import (
    AttemptStatus,
    CoreArtifact,
    CoreTask,
    CoreTaskAttempt,
    CoreTaskStatus,
)

_DIRECTORY = ".artifact_reconciliation"
_MAX_FILE_SIZE = 1024 * 1024
_MAX_ARTIFACTS = 16
_TASK_ID = re.compile(r"^ctask_[A-Za-z0-9_-]{1,64}$")
_ARTIFACT_ID = re.compile(r"^art_[A-Za-z0-9_-]{1,64}$")
_CHECKSUM = re.compile(r"^sha256:[0-9a-f]{64}$")
_PHASES = {"uploading", "uploaded", "cleanup_tombstone"}
_DEFAULT_UPLOAD_PROTECTION_SECONDS = 90.0
_DEFAULT_SETTLEMENT_SECONDS = 24 * 60 * 60.0
_DEFAULT_SETTLEMENT_CONFIRMATIONS = 3
_MIN_ABSENCE_CONFIRM_INTERVAL = 15.0
_MAX_RECONCILE_BACKOFF = 3600.0
_MAX_ACTIVE_ENTRIES = 10_000
_MAX_ACTIVE_BYTES = 64 * 1024 * 1024
_MAX_AUXILIARY_ENTRIES = 20_000
_MAX_AUXILIARY_BYTES = 64 * 1024 * 1024
_MAX_QUARANTINE_ENTRIES = 1_000
_MAX_QUARANTINE_BYTES = 32 * 1024 * 1024
_LOCAL_OPERATION_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class ReconciliationArtifact:
    """持久化补偿日志中的单个 OSS Artifact 安全事实。"""

    artifact_id: str
    kind: str
    object_key: str
    content_type: str
    size: int
    checksum: str
    bucket: str | None = None
    url: str | None = None


class ReconciliationSecurityError(RuntimeError):
    """Journal root is not a controlled private directory."""


class InvalidJournalError(ReconciliationSecurityError):
    """One untrusted journal entry failed structural or schema validation."""


class ReconciliationCapacityError(RuntimeError):
    """Active durable cleanup capacity is full; PUT must fail closed."""


class ArtifactReconciliationJournal:
    """Persist immutable reconciliation facts using dirfd/no-follow operations."""

    def __init__(self, work_root: str | Path, *, clock=time.time) -> None:
        self.work_root = Path(work_root)
        self.clock = clock

    def _open_directory(self) -> int:
        flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
        try:
            root_fd = os.open(self.work_root, flags)
        except OSError as exc:
            raise ReconciliationSecurityError("RECONCILIATION_ROOT_REJECTED") from exc
        try:
            try:
                os.mkdir(_DIRECTORY, 0o700, dir_fd=root_fd)
                os.fsync(root_fd)
            except FileExistsError:
                pass
            info = os.stat(_DIRECTORY, dir_fd=root_fd, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
                raise ReconciliationSecurityError("RECONCILIATION_DIRECTORY_REJECTED")
            if stat.S_IMODE(info.st_mode) & 0o077:
                os.chmod(_DIRECTORY, 0o700, dir_fd=root_fd, follow_symlinks=False)
            return os.open(_DIRECTORY, flags, dir_fd=root_fd)
        except (OSError, ReconciliationSecurityError) as exc:
            if isinstance(exc, ReconciliationSecurityError):
                raise
            raise ReconciliationSecurityError(
                "RECONCILIATION_DIRECTORY_REJECTED"
            ) from exc
        finally:
            os.close(root_fd)

    @staticmethod
    def _write_all(fd: int, value: bytes) -> None:
        offset = 0
        while offset < len(value):
            offset += os.write(fd, value[offset:])

    def _acquire_operation_lock(self) -> int:
        flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        with _LOCAL_OPERATION_LOCK:
            descriptor = -1
            for _ in range(40):
                directory_fd = self._open_directory()
                try:
                    try:
                        descriptor = os.open(
                            ".operation.lock",
                            flags | os.O_CREAT | os.O_EXCL,
                            0o600,
                            dir_fd=directory_fd,
                        )
                    except FileExistsError:
                        try:
                            descriptor = os.open(
                                ".operation.lock", flags, dir_fd=directory_fd
                            )
                        except FileNotFoundError:
                            descriptor = -1
                    except FileNotFoundError:
                        descriptor = -1
                finally:
                    os.close(directory_fd)
                if descriptor >= 0:
                    break
                time.sleep(0.005)
            if descriptor < 0:
                raise ReconciliationSecurityError(
                    "RECONCILIATION_LOCK_INITIALIZATION_FAILED"
                )
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            os.close(descriptor)
            raise ReconciliationSecurityError("RECONCILIATION_LOCK_REJECTED")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        return descriptor

    @staticmethod
    def _release_operation_lock(descriptor: int) -> None:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)

    @staticmethod
    def _fact_lock_name(name: str) -> str:
        original = name.split(".claim-", 1)[0].split(".transition-", 1)[0]
        return f".fact-lock-{hashlib.sha256(original.encode()).hexdigest()[:32]}"

    @classmethod
    def _lock_entry(cls, directory_fd: int, name: str) -> int:
        lock_name = cls._fact_lock_name(name)
        descriptor = os.open(
            lock_name,
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=directory_fd,
        )
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            os.close(descriptor)
            raise InvalidJournalError("RECONCILIATION_FILE_REJECTED")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        return descriptor

    @classmethod
    def _cleanup_fact_lock(cls, directory_fd: int, original: str) -> None:
        lock_name = cls._fact_lock_name(original)
        try:
            descriptor = os.open(
                lock_name,
                os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
                dir_fd=directory_fd,
            )
        except FileNotFoundError:
            return
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            if any(
                name == original
                or name.startswith(f"{original}.claim-")
                or name.startswith(f"{original}.transition-")
                for name in os.listdir(directory_fd)
            ):
                return
            try:
                os.unlink(lock_name, dir_fd=directory_fd)
                os.fsync(directory_fd)
            except FileNotFoundError:
                pass
        finally:
            os.close(descriptor)

    def record(
        self,
        task_id: str,
        attempt_no: int,
        artifacts: Sequence[ArtifactRef],
        *,
        known_orphan: bool = False,
    ) -> str:
        """Atomically persist task/attempt/artifact identities before returning."""
        if (
            not task_id
            or type(attempt_no) is not int
            or attempt_no <= 0
            or not artifacts
        ):
            raise ValueError("RECONCILIATION_FACT_INVALID")
        return self._record_payload(
            task_id,
            attempt_no,
            [item.to_dict() for item in artifacts],
            known_orphan=known_orphan,
            phase="uploaded",
            upload_protected_until=None,
            cleanup_settle_after=None,
            cleanup_confirmations=0,
        )

    def record_intent(
        self,
        task_id: str,
        attempt_no: int,
        *,
        artifact_id: str,
        kind: str,
        object_key: str,
        content_type: str,
        size: int,
        checksum: str,
        upload_protection_seconds: float = _DEFAULT_UPLOAD_PROTECTION_SECONDS,
    ) -> str:
        """Durably record object identity before an OSS PUT is attempted."""
        if (
            type(upload_protection_seconds) not in {int, float}
            or not math.isfinite(upload_protection_seconds)
            or not 0 < upload_protection_seconds <= 3600
        ):
            raise ValueError("RECONCILIATION_UPLOAD_PROTECTION_INVALID")
        return self._record_payload(
            task_id,
            attempt_no,
            [
                asdict(
                    ReconciliationArtifact(
                        artifact_id=artifact_id,
                        kind=kind,
                        object_key=object_key,
                        content_type=content_type,
                        size=size,
                        checksum=checksum,
                    )
                )
            ],
            known_orphan=False,
            phase="uploading",
            upload_protected_until=self.clock() + upload_protection_seconds,
            cleanup_settle_after=None,
            cleanup_confirmations=0,
        )

    def _find_intent_name(self, directory_fd: int, intent_name: str) -> str | None:
        for name in os.listdir(directory_fd):
            if (
                name == intent_name
                or name.startswith(f"{intent_name}.claim-")
                or name.startswith(f"{intent_name}.transition-")
            ):
                return name
        return None

    def update_reference(
        self,
        intent_name: str,
        artifact: ArtifactRef,
        *,
        task_id: str,
        attempt_no: int,
    ) -> str | None:
        """Atomically transition the exact intent after any active scanner finishes."""
        directory_fd = self._open_directory()
        entry_lock = -1
        try:
            name = self._find_intent_name(directory_fd, intent_name)
            if name is None:
                return None
            entry_lock = self._lock_entry(directory_fd, name)
            name = self._find_intent_name(directory_fd, intent_name)
            if name is None:
                return None
            payload = ArtifactReconciliationScanner._read_claim(directory_fd, name)
            identity = (artifact.artifact_id, artifact.object_key)
            recorded = {
                (str(item["artifact_id"]), str(item["object_key"]))
                for item in as_sequence(payload["artifacts"])
            }
            if (
                payload["task_id"] != task_id
                or payload["attempt_no"] != attempt_no
                or identity not in recorded
                or payload["phase"] == "cleanup_tombstone"
            ):
                return None
            payload.update(
                phase="uploaded",
                upload_protected_until=None,
                cleanup_settle_after=None,
                cleanup_confirmations=0,
                known_orphan=False,
                artifacts=[artifact.to_dict()],
            )
            ArtifactReconciliationScanner._validate_payload(payload)
            self._replace_claim_payload(directory_fd, name, payload)
            if name != intent_name:
                os.replace(
                    name,
                    intent_name,
                    src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd,
                )
            os.fsync(directory_fd)
            return intent_name
        finally:
            if entry_lock >= 0:
                fcntl.flock(entry_lock, fcntl.LOCK_UN)
                os.close(entry_lock)
            os.close(directory_fd)

    def heartbeat_upload(self, intent_name: str, *, protection_seconds: float) -> bool:
        """Durably extend a live synchronous PUT protection lease."""
        directory_fd = self._open_directory()
        entry_lock = -1
        try:
            name = self._find_intent_name(directory_fd, intent_name)
            if name is None:
                return False
            entry_lock = self._lock_entry(directory_fd, name)
            name = self._find_intent_name(directory_fd, intent_name)
            if name is None:
                return False
            payload = ArtifactReconciliationScanner._read_claim(directory_fd, name)
            if payload["phase"] != "uploading":
                return False
            payload["upload_protected_until"] = max(
                as_float(payload["upload_protected_until"]),
                self.clock() + protection_seconds,
            )
            self._replace_claim_payload(directory_fd, name, payload)
            return True
        finally:
            if entry_lock >= 0:
                fcntl.flock(entry_lock, fcntl.LOCK_UN)
                os.close(entry_lock)
            os.close(directory_fd)

    def ensure_cleanup_tombstone(
        self, task_id: str, attempt_no: int, artifact: ArtifactRef
    ) -> str:
        """Recreate durable cleanup ownership before attempting direct DELETE."""
        return self._record_payload(
            task_id,
            attempt_no,
            [artifact.to_dict()],
            known_orphan=True,
            phase="cleanup_tombstone",
            upload_protected_until=None,
            cleanup_settle_after=self.clock() + _DEFAULT_SETTLEMENT_SECONDS,
            cleanup_confirmations=0,
        )

    def discard_artifacts(
        self,
        task_id: str,
        attempt_no: int,
        artifacts: Sequence[ArtifactRef],
        *,
        exclude: set[str] | None = None,
    ) -> None:
        """Remove durable facts after exact objects were deleted or coalesced."""
        identities = {(item.artifact_id, item.object_key) for item in artifacts}
        excluded = exclude or set()
        directory_fd = self._open_directory()
        try:
            changed = False
            removed: list[str] = []
            for name in os.listdir(directory_fd):
                if name in excluded or not (
                    name.startswith("pending-") and name.endswith(".json")
                ):
                    continue
                try:
                    payload = ArtifactReconciliationScanner._read_claim(
                        directory_fd, name
                    )
                except (
                    OSError,
                    ValueError,
                    ReconciliationSecurityError,
                    json.JSONDecodeError,
                ):
                    continue
                recorded = {
                    (str(item["artifact_id"]), str(item["object_key"]))
                    for item in as_sequence(payload["artifacts"])
                }
                if (
                    payload["task_id"] == task_id
                    and payload["attempt_no"] == attempt_no
                    and recorded <= identities
                ):
                    try:
                        os.unlink(name, dir_fd=directory_fd)
                        changed = True
                        removed.append(name)
                    except FileNotFoundError:
                        pass
            if changed:
                os.fsync(directory_fd)
                for name in removed:
                    self._cleanup_fact_lock(directory_fd, name)
        finally:
            os.close(directory_fd)

    def _record_payload(
        self,
        task_id: str,
        attempt_no: int,
        artifacts: Sequence[dict[str, object]],
        *,
        known_orphan: bool,
        phase: str,
        upload_protected_until: float | None,
        cleanup_settle_after: float | None,
        cleanup_confirmations: int,
    ) -> str:
        payload_value = {
            "version": 1,
            "task_id": task_id,
            "attempt_no": attempt_no,
            "known_orphan": known_orphan,
            "phase": phase,
            "upload_protected_until": upload_protected_until,
            "cleanup_settle_after": cleanup_settle_after,
            "cleanup_confirmations": cleanup_confirmations,
            "delete_attempts": 0,
            "absent_streak": 0,
            "last_absent_at": None,
            "last_checked_at": None,
            "next_check_at": self.clock(),
            "artifacts": list(artifacts),
        }
        ArtifactReconciliationScanner._validate_payload(payload_value)
        payload = json.dumps(payload_value, separators=(",", ":")).encode()
        if len(payload) > _MAX_FILE_SIZE:
            raise ValueError("RECONCILIATION_FACT_TOO_LARGE")
        capacity_lock = self._acquire_operation_lock()
        directory_fd = self._open_directory()
        temporary = f".tmp-{secrets.token_hex(24)}"
        target = f"pending-{secrets.token_hex(24)}.json"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = -1
        try:
            active_count = 0
            active_bytes = 0
            auxiliary_count = 0
            auxiliary_bytes = 0
            for name in os.listdir(directory_fd):
                try:
                    info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                if not stat.S_ISREG(info.st_mode):
                    continue
                if name.startswith("pending-"):
                    active_count += 1
                    active_bytes += info.st_size
                elif name.startswith((".tmp-", ".fact-lock-", "quarantine-")):
                    auxiliary_count += 1
                    auxiliary_bytes += info.st_size
            if (
                active_count >= _MAX_ACTIVE_ENTRIES
                or active_bytes + len(payload) > _MAX_ACTIVE_BYTES
                or auxiliary_count >= _MAX_AUXILIARY_ENTRIES
                or auxiliary_bytes > _MAX_AUXILIARY_BYTES
            ):
                raise ReconciliationCapacityError("RECONCILIATION_CAPACITY_EXCEEDED")
            descriptor = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
            self._write_all(descriptor, payload)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(
                temporary,
                target,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
            os.fsync(directory_fd)
            return target
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            os.close(directory_fd)
            self._release_operation_lock(capacity_lock)

    @classmethod
    def _replace_claim_payload(
        cls, directory_fd: int, claim: str, payload: dict[str, object]
    ) -> None:
        value = json.dumps(payload, separators=(",", ":")).encode()
        temporary = f".tmp-{secrets.token_hex(24)}"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        try:
            cls._write_all(descriptor, value)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.replace(
                temporary, claim, src_dir_fd=directory_fd, dst_dir_fd=directory_fd
            )
            os.fsync(directory_fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass

    def pending_count(self) -> int:
        """Return pending facts; claimed files remain pending until completed."""
        directory_fd = self._open_directory()
        try:
            return sum(
                name.startswith("pending-")
                and (
                    name.endswith(".json")
                    or ".claim-" in name
                    or ".transition-" in name
                )
                for name in os.listdir(directory_fd)
            )
        finally:
            os.close(directory_fd)


class ArtifactReconciliationScanner:
    """Resolve journal entries against exact DB artifact and attempt facts."""

    def __init__(
        self,
        session: Session,
        journal: ArtifactReconciliationJournal,
        artifact_store: ArtifactStore | None,
        *,
        stale_claim_seconds: float = 300.0,
        settlement_seconds: float = _DEFAULT_SETTLEMENT_SECONDS,
        settlement_confirmations: int = _DEFAULT_SETTLEMENT_CONFIRMATIONS,
        clock=time.time,
    ) -> None:
        self.session = session
        self.journal = journal
        self.artifact_store = artifact_store
        self.stale_claim_seconds = stale_claim_seconds
        self.settlement_seconds = settlement_seconds
        self.settlement_confirmations = settlement_confirmations
        self.clock = clock

    def _restore_stale_claims(self, directory_fd: int) -> None:
        now = time.time()
        for name in os.listdir(directory_fd):
            if not name.startswith("pending-") or not (
                ".json.claim-" in name or ".json.transition-" in name
            ):
                continue
            try:
                info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if now - info.st_mtime < self.stale_claim_seconds:
                    continue
                marker = ".claim-" if ".claim-" in name else ".transition-"
                original = name.split(marker, 1)[0]
                os.rename(
                    name, original, src_dir_fd=directory_fd, dst_dir_fd=directory_fd
                )
                os.fsync(directory_fd)
            except (FileNotFoundError, FileExistsError):
                continue

    def _cleanup_auxiliary(self, directory_fd: int) -> None:
        """Bound stale temp/quarantine/sidecar inode growth without racing users."""
        names = os.listdir(directory_fd)
        active_locks = {
            self.journal._fact_lock_name(name)
            for name in names
            if name.startswith("pending-")
        }
        for name in names:
            if name.startswith(".fact-lock-") and name not in active_locks:
                try:
                    descriptor = os.open(
                        name,
                        os.O_RDWR
                        | getattr(os, "O_NOFOLLOW", 0)
                        | getattr(os, "O_CLOEXEC", 0),
                        dir_fd=directory_fd,
                    )
                except OSError:
                    continue
                try:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        continue
                    try:
                        os.unlink(name, dir_fd=directory_fd)
                    except FileNotFoundError:
                        pass
                finally:
                    os.close(descriptor)
            elif name.startswith(".tmp-"):
                try:
                    info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    if time.time() - info.st_mtime >= self.stale_claim_seconds:
                        os.unlink(name, dir_fd=directory_fd)
                except (FileNotFoundError, OSError):
                    pass
        quarantine: list[tuple[float, str, int]] = []
        for name in os.listdir(directory_fd):
            if not name.startswith("quarantine-"):
                continue
            try:
                info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if stat.S_ISREG(info.st_mode):
                    quarantine.append((info.st_mtime, name, info.st_size))
            except FileNotFoundError:
                pass
        quarantine.sort()
        quarantine_bytes = sum(size for _mtime, _name, size in quarantine)
        while quarantine and (
            len(quarantine) > _MAX_QUARANTINE_ENTRIES
            or quarantine_bytes > _MAX_QUARANTINE_BYTES
        ):
            _mtime, name, size = quarantine.pop(0)
            try:
                os.unlink(name, dir_fd=directory_fd)
                quarantine_bytes -= size
            except FileNotFoundError:
                pass
        os.fsync(directory_fd)

    @staticmethod
    def _read_claim(directory_fd: int, name: str) -> dict[str, object]:
        try:
            before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as exc:
            raise InvalidJournalError("RECONCILIATION_FILE_REJECTED") from exc
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) & 0o077
            or before.st_size <= 0
            or before.st_size > _MAX_FILE_SIZE
        ):
            raise InvalidJournalError("RECONCILIATION_FILE_REJECTED")
        flags = (
            os.O_RDONLY
            | os.O_NONBLOCK
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(name, flags, dir_fd=directory_fd)
        except OSError as exc:
            raise InvalidJournalError("RECONCILIATION_FILE_REJECTED") from exc
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) & 0o077
                or info.st_size <= 0
                or info.st_size > _MAX_FILE_SIZE
                or (info.st_dev, info.st_ino, info.st_size)
                != (before.st_dev, before.st_ino, before.st_size)
            ):
                raise InvalidJournalError("RECONCILIATION_FILE_REJECTED")
            chunks: list[bytes] = []
            remaining = info.st_size
            while remaining:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    raise InvalidJournalError("RECONCILIATION_FILE_SHORT_READ")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise InvalidJournalError("RECONCILIATION_FILE_GREW")
            try:
                value = json.loads(b"".join(chunks))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise InvalidJournalError("RECONCILIATION_FACT_INVALID") from exc
            return ArtifactReconciliationScanner._validate_payload(value)
        finally:
            os.close(descriptor)

    @staticmethod
    def _validate_payload(value: object) -> dict[str, object]:
        if not isinstance(value, dict) or set(value) != {
            "version",
            "task_id",
            "attempt_no",
            "known_orphan",
            "phase",
            "upload_protected_until",
            "cleanup_settle_after",
            "cleanup_confirmations",
            "delete_attempts",
            "absent_streak",
            "last_absent_at",
            "last_checked_at",
            "next_check_at",
            "artifacts",
        }:
            raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
        if value["version"] != 1 or type(value["known_orphan"]) is not bool:
            raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
        if value["phase"] not in _PHASES:
            raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
        for field in ("upload_protected_until", "cleanup_settle_after"):
            if value[field] is not None and (
                type(value[field]) not in {int, float}
                or not math.isfinite(value[field])
            ):
                raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
        if (
            type(value["cleanup_confirmations"]) is not int
            or value["cleanup_confirmations"] < 0
        ):
            raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
        for field in ("delete_attempts", "absent_streak"):
            if type(value[field]) is not int or value[field] < 0:
                raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
        for field in ("last_absent_at", "last_checked_at"):
            if value[field] is not None and (
                type(value[field]) not in {int, float}
                or not math.isfinite(value[field])
            ):
                raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
        if type(value["next_check_at"]) not in {int, float} or not math.isfinite(
            value["next_check_at"]
        ):
            raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
        if value["phase"] == "uploading" and value["upload_protected_until"] is None:
            raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
        if (
            value["phase"] == "cleanup_tombstone"
            and value["cleanup_settle_after"] is None
        ):
            raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
        if value["phase"] == "uploading" and (
            value["cleanup_settle_after"] is not None
            or value["cleanup_confirmations"] != 0
            or value["delete_attempts"] != 0
            or value["absent_streak"] != 0
        ):
            raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
        if value["phase"] == "uploaded" and (
            value["upload_protected_until"] is not None
            or value["cleanup_settle_after"] is not None
            or value["cleanup_confirmations"] != 0
            or value["delete_attempts"] != 0
            or value["absent_streak"] != 0
        ):
            raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
        if (
            value["phase"] == "cleanup_tombstone"
            and value["upload_protected_until"] is not None
        ):
            raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
        task_id, attempt_no, items = (
            value["task_id"],
            value["attempt_no"],
            value["artifacts"],
        )
        if not isinstance(task_id, str) or not _TASK_ID.fullmatch(task_id):
            raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
        if type(attempt_no) is not int or not 1 <= attempt_no <= 1_000_000:
            raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
        if not isinstance(items, list) or not 1 <= len(items) <= _MAX_ARTIFACTS:
            raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
        allowed = {
            "artifact_id",
            "kind",
            "bucket",
            "object_key",
            "url",
            "content_type",
            "size",
            "checksum",
        }
        required = {
            "artifact_id",
            "kind",
            "object_key",
            "content_type",
            "size",
            "checksum",
        }
        for item in items:
            if not isinstance(item, dict) or not required <= set(item) <= allowed:
                raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
            aid, key = item["artifact_id"], item["object_key"]
            if not isinstance(aid, str) or not _ARTIFACT_ID.fullmatch(aid):
                raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
            if (
                not isinstance(key, str)
                or len(key) > 1024
                or not key.startswith("narrato/coreApi/")
                or "\\" in key
                or any(part in {"", ".", ".."} for part in key.split("/"))
            ):
                raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
            if not isinstance(item["kind"], str) or not 1 <= len(item["kind"]) <= 80:
                raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
            if (
                not isinstance(item["content_type"], str)
                or not 1 <= len(item["content_type"]) <= 255
            ):
                raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
            if type(item["size"]) is not int or not 1 <= item["size"] <= 10**12:
                raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
            if not isinstance(item["checksum"], str) or not _CHECKSUM.fullmatch(
                item["checksum"]
            ):
                raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
            for optional, maximum in (("bucket", 255), ("url", 2048)):
                if (
                    optional in item
                    and item[optional] is not None
                    and (
                        not isinstance(item[optional], str)
                        or not 1 <= len(item[optional]) <= maximum
                    )
                ):
                    raise InvalidJournalError("RECONCILIATION_FACT_INVALID")
        return value

    def _resolve(self, payload: dict[str, object]) -> bool:
        task_id = str(payload["task_id"])
        attempt_no = as_int(payload["attempt_no"])
        artifacts = [
            ReconciliationArtifact(**as_mapping(item))
            for item in as_sequence(payload["artifacts"])
        ]
        now = self.clock()
        payload["last_checked_at"] = now
        if payload["phase"] == "uploading" and now < as_float(
            payload["upload_protected_until"]
        ):
            payload["next_check_at"] = min(
                as_float(payload["upload_protected_until"]), now + 60.0
            )
            return False
        task = self.session.get(CoreTask, task_id, populate_existing=True)
        attempt = self.session.scalar(
            select(CoreTaskAttempt).where(
                CoreTaskAttempt.core_task_id == task_id,
                CoreTaskAttempt.attempt_no == attempt_no,
            )
        )
        registered = {
            (item.id, item.object_key)
            for item in self.session.scalars(
                select(CoreArtifact).where(
                    CoreArtifact.core_task_id == task_id,
                    CoreArtifact.attempt_no == attempt_no,
                )
            )
        }
        unmatched = [
            item
            for item in artifacts
            if (item.artifact_id, item.object_key) not in registered
        ]
        if not unmatched:
            return True
        terminal = task is None or task.status in {
            CoreTaskStatus.SUCCEEDED,
            CoreTaskStatus.FAILED,
        }
        old_failed_attempt = (
            task is not None
            and attempt is not None
            and attempt.status in {AttemptStatus.FAILED, AttemptStatus.EXPIRED}
            and task.current_attempt_no != attempt_no
        )
        cleanup = (
            payload["phase"] == "cleanup_tombstone"
            or payload.get("known_orphan") is True
            or terminal
            or old_failed_attempt
        )
        if not cleanup:
            payload["next_check_at"] = now + 60.0
            return False
        if self.artifact_store is None:
            payload["next_check_at"] = now + 60.0
            return False
        if payload["phase"] != "cleanup_tombstone":
            payload["phase"] = "cleanup_tombstone"
            payload["upload_protected_until"] = None
            payload["cleanup_settle_after"] = now + self.settlement_seconds
            payload["cleanup_confirmations"] = 0
            payload["absent_streak"] = 0
            payload["last_absent_at"] = None
        payload["delete_attempts"] = as_int(payload["delete_attempts"]) + 1
        backoff = min(
            _MAX_RECONCILE_BACKOFF,
            15.0 * (2 ** min(as_int(payload["delete_attempts"]) - 1, 8)),
        )
        payload["next_check_at"] = now + backoff
        for artifact in unmatched:
            self.artifact_store.delete_reconciled_artifact(
                ArtifactRef(
                    artifact_id=artifact.artifact_id,
                    kind=artifact.kind,
                    bucket=artifact.bucket or "",
                    object_key=artifact.object_key,
                    url=artifact.url or "",
                    content_type=artifact.content_type,
                    size=artifact.size,
                    checksum=artifact.checksum,
                )
            )
        confirm_absent = getattr(
            self.artifact_store, "is_reconciled_artifact_absent", None
        )
        try:
            absent = callable(confirm_absent) and all(
                confirm_absent(artifact) for artifact in unmatched
            )
        except BaseException:
            payload["absent_streak"] = 0
            payload["cleanup_confirmations"] = 0
            payload["last_absent_at"] = None
            raise
        if not absent:
            payload["absent_streak"] = 0
            payload["cleanup_confirmations"] = 0
            payload["last_absent_at"] = None
            return False
        last_absent = payload["last_absent_at"]
        if (
            last_absent is None
            or now - as_float(last_absent) >= _MIN_ABSENCE_CONFIRM_INTERVAL
        ):
            payload["absent_streak"] = as_int(payload["absent_streak"]) + 1
            payload["cleanup_confirmations"] = as_int(payload["absent_streak"])
            payload["last_absent_at"] = now
        return (
            now >= as_float(payload["cleanup_settle_after"])
            and as_int(payload["absent_streak"]) >= self.settlement_confirmations
        )

    def scan(self, *, limit: int = 100) -> int:
        """Claim and resolve pending facts; DB/OSS failures restore the journal."""
        if self.artifact_store is None:
            return 0
        directory_fd = self.journal._open_directory()
        completed = 0
        try:
            self._restore_stale_claims(directory_fd)
            self._cleanup_auxiliary(directory_fd)
            candidates: list[tuple[float, str]] = []
            for name in os.listdir(directory_fd):
                if not (name.startswith("pending-") and name.endswith(".json")):
                    continue
                try:
                    preview = self._read_claim(directory_fd, name)
                except InvalidJournalError:
                    quarantine = f"quarantine-{secrets.token_hex(24)}.bad"
                    try:
                        os.rename(
                            name,
                            quarantine,
                            src_dir_fd=directory_fd,
                            dst_dir_fd=directory_fd,
                        )
                        os.fsync(directory_fd)
                        self.journal._cleanup_fact_lock(directory_fd, name)
                    except FileNotFoundError:
                        pass
                    continue
                due = as_float(preview["next_check_at"])
                if due <= self.clock():
                    candidates.append((due, name))
            self._cleanup_auxiliary(directory_fd)
            names = [name for _due, name in sorted(candidates)[:limit]]
            for original in names:
                cleanup_lock = False
                claim = f"{original}.claim-{os.getpid()}-{secrets.token_hex(12)}"
                try:
                    os.rename(
                        original,
                        claim,
                        src_dir_fd=directory_fd,
                        dst_dir_fd=directory_fd,
                    )
                except FileNotFoundError:
                    continue
                os.utime(claim, None, dir_fd=directory_fd, follow_symlinks=False)
                os.fsync(directory_fd)
                try:
                    entry_lock = self.journal._lock_entry(directory_fd, claim)
                except (OSError, InvalidJournalError):
                    try:
                        os.rename(
                            claim,
                            original,
                            src_dir_fd=directory_fd,
                            dst_dir_fd=directory_fd,
                        )
                    except FileNotFoundError:
                        pass
                    continue
                stop = threading.Event()
                interval = max(0.02, min(5.0, self.stale_claim_seconds / 3))

                def heartbeat() -> None:
                    while not stop.wait(interval):
                        try:
                            os.utime(
                                claim, None, dir_fd=directory_fd, follow_symlinks=False
                            )
                        except FileNotFoundError:
                            return

                lease = threading.Thread(target=heartbeat, daemon=True)
                lease.start()
                payload: dict[str, object] | None = None
                try:
                    try:
                        payload = self._read_claim(directory_fd, claim)
                    except InvalidJournalError:
                        stop.set()
                        lease.join()
                        quarantine = f"quarantine-{secrets.token_hex(24)}.bad"
                        try:
                            os.rename(
                                claim,
                                quarantine,
                                src_dir_fd=directory_fd,
                                dst_dir_fd=directory_fd,
                            )
                            os.fsync(directory_fd)
                            cleanup_lock = True
                        except FileNotFoundError:
                            pass
                        continue
                    if not self._resolve(payload):
                        stop.set()
                        lease.join()
                        self.journal._replace_claim_payload(
                            directory_fd, claim, payload
                        )
                        os.rename(
                            claim,
                            original,
                            src_dir_fd=directory_fd,
                            dst_dir_fd=directory_fd,
                        )
                        os.fsync(directory_fd)
                        continue
                    os.unlink(claim, dir_fd=directory_fd)
                    os.fsync(directory_fd)
                    completed += 1
                    cleanup_lock = True
                except BaseException:
                    stop.set()
                    lease.join()
                    self.session.rollback()
                    try:
                        if payload is not None:
                            self.journal._replace_claim_payload(
                                directory_fd, claim, payload
                            )
                        os.rename(
                            claim,
                            original,
                            src_dir_fd=directory_fd,
                            dst_dir_fd=directory_fd,
                        )
                        os.fsync(directory_fd)
                    except FileNotFoundError:
                        pass
                finally:
                    stop.set()
                    lease.join()
                    fcntl.flock(entry_lock, fcntl.LOCK_UN)
                    os.close(entry_lock)
                    if cleanup_lock:
                        self.journal._cleanup_fact_lock(directory_fd, original)
            return completed
        finally:
            os.close(directory_fd)

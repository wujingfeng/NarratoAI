import json
import multiprocessing
import os
import threading
import time
import socket
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
import core_api.tasks.artifact_reconciliation as reconciliation

from core_api.infrastructure.oss_client import CdnUrlPolicy
from core_api.runtime.artifact_store import ArtifactRef, ArtifactStore
from core_api.runtime.workspace import CoreTaskWorkspace
from core_api.tasks.artifact_reconciliation import (
    ArtifactReconciliationJournal,
    ArtifactReconciliationScanner,
    ReconciliationSecurityError,
)
from core_api.tasks.models import AttemptStatus, CoreTaskStatus
from core_api.tasks.service import TaskService
from core_api.tasks.handlers import AtomicTaskHandler


class DeleteStore:
    def __init__(self):
        self.deleted = []
        self.fail = False

    def delete_reconciled_artifact(self, artifact):
        if self.fail:
            raise RuntimeError("oss unavailable")
        self.deleted.append(artifact.object_key)

    def is_reconciled_artifact_absent(self, _artifact):
        return True


def settled_scanner(session, journal, store):
    return ArtifactReconciliationScanner(
        session,
        journal,
        store,
        settlement_seconds=0,
        settlement_confirmations=1,
    )


def force_pending_due(tmp_path):
    path = next((tmp_path / ".artifact_reconciliation").glob("pending-*.json"))
    payload = json.loads(path.read_text())
    payload["next_check_at"] = 0
    path.write_text(json.dumps(payload, separators=(",", ":")))
    path.chmod(0o600)


def artifact(attempt_no=1, suffix="video"):
    return ArtifactRef(
        artifact_id=f"art_{attempt_no}_{suffix}",
        kind=suffix,
        bucket="bucket",
        object_key=f"narrato/coreApi/task/{attempt_no}/{suffix}.bin",
        url=f"https://cdn.example.test/narrato/coreApi/task/{attempt_no}/{suffix}.bin",
        content_type="application/octet-stream",
        size=1,
        checksum="sha256:" + "a" * 64,
    )


def create_running(service, key="reconcile"):
    task = service.create_core_task(
        caller="test",
        route="/test",
        task_type="video_render",
        idempotency_key=key,
        input_snapshot={"value": key},
    )
    attempt = service.claim_dispatched_task(
        task.id,
        expected_state_version=task.state_version,
        not_before=task.updated_at,
        lease_seconds=60,
    )
    return task, attempt


def test_journal_is_concurrent_durable_and_contains_attempt_identity(tmp_path):
    journal = ArtifactReconciliationJournal(tmp_path)
    item = artifact()
    with ThreadPoolExecutor(max_workers=50) as pool:
        names = list(
            pool.map(lambda _: journal.record("ctask_test", 1, [item]), range(50))
        )
    assert len(set(names)) == 50
    payloads = [
        json.loads((tmp_path / ".artifact_reconciliation" / name).read_text())
        for name in names
    ]
    assert all(p["task_id"] == "ctask_test" and p["attempt_no"] == 1 for p in payloads)
    assert all(p["artifacts"][0]["artifact_id"] == item.artifact_id for p in payloads)
    assert all(p["artifacts"][0]["object_key"] == item.object_key for p in payloads)


def test_journal_rejects_symlink_directory(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".artifact_reconciliation").symlink_to(
        outside, target_is_directory=True
    )
    with pytest.raises(ReconciliationSecurityError):
        ArtifactReconciliationJournal(tmp_path).record("ctask_test", 1, [artifact()])
    assert list(outside.iterdir()) == []


def test_scanner_preserves_running_and_retry_wait(session, tmp_path):
    service = TaskService(session)
    task, attempt = create_running(service)
    journal = ArtifactReconciliationJournal(tmp_path)
    store = DeleteStore()
    journal.record(task.id, attempt.attempt_no, [artifact()])
    scanner = ArtifactReconciliationScanner(session, journal, store)
    assert scanner.scan() == 0 and store.deleted == []
    task.status = CoreTaskStatus.RETRY_WAIT
    session.commit()
    assert scanner.scan() == 0 and store.deleted == []


def test_scanner_retries_known_rollback_delete_even_while_task_running(
    session, tmp_path
):
    service = TaskService(session)
    task, attempt = create_running(service, "known-rollback")
    journal = ArtifactReconciliationJournal(tmp_path)
    journal.record(task.id, attempt.attempt_no, [artifact()], known_orphan=True)
    store = DeleteStore()
    assert settled_scanner(session, journal, store).scan() == 1
    assert store.deleted == [artifact().object_key]


def test_scanner_matches_each_registered_artifact_and_deletes_old_retry_orphan(
    session, tmp_path
):
    service = TaskService(session)
    task, attempt = create_running(service, "retry-old")
    old = artifact(1)
    journal = ArtifactReconciliationJournal(tmp_path)
    journal.record(task.id, 1, [old])
    attempt.status = AttemptStatus.FAILED
    task.current_attempt_no = 2
    task.status = CoreTaskStatus.SUCCEEDED
    session.commit()
    store = DeleteStore()
    scanner = settled_scanner(session, journal, store)
    assert scanner.scan() == 1
    assert store.deleted == [old.object_key]


def test_scanner_preserves_exact_registered_artifact_but_not_unregistered_succeeded(
    session, tmp_path
):
    service = TaskService(session)
    task, attempt = create_running(service, "partial-success")
    kept, orphan = artifact(1, "video"), artifact(1, "voice")
    result = {"artifacts": [kept.to_dict()]}
    service.complete_attempt(
        attempt.id, attempt.lease_token, result, lease_version=attempt.lease_version
    )
    journal = ArtifactReconciliationJournal(tmp_path)
    journal.record(task.id, 1, [kept, orphan])
    store = DeleteStore()
    scanner = settled_scanner(session, journal, store)
    assert scanner.scan() == 1
    assert store.deleted == [orphan.object_key]


def test_two_scanners_claim_once_and_oss_failure_restores_journal(session, tmp_path):
    service = TaskService(session)
    task, attempt = create_running(service, "claim")
    attempt.status = AttemptStatus.FAILED
    task.current_attempt_no = 2
    task.status = CoreTaskStatus.FAILED
    session.commit()
    journal = ArtifactReconciliationJournal(tmp_path)
    journal.record(task.id, 1, [artifact()])
    store = DeleteStore()
    store.fail = True
    assert settled_scanner(session, journal, store).scan() == 0
    assert journal.pending_count() == 1
    store.fail = False
    force_pending_due(tmp_path)
    assert settled_scanner(session, journal, store).scan() == 1
    assert journal.pending_count() == 0


def test_two_concurrent_scanners_claim_one_journal_once(session, tmp_path):
    journal = ArtifactReconciliationJournal(tmp_path)
    journal.record("ctask_test", 1, [artifact()], known_orphan=True)
    scanners = [
        ArtifactReconciliationScanner(session, journal, DeleteStore()) for _ in range(2)
    ]
    for scanner in scanners:
        scanner._resolve = lambda _payload: True
    with ThreadPoolExecutor(max_workers=2) as pool:
        processed = list(pool.map(lambda scanner: scanner.scan(), scanners))
    assert sum(processed) == 1
    assert journal.pending_count() == 0


def test_database_failure_restores_claim_for_periodic_retry(
    session, tmp_path, monkeypatch
):
    journal = ArtifactReconciliationJournal(tmp_path)
    journal.record("ctask_test", 1, [artifact()])
    scanner = ArtifactReconciliationScanner(session, journal, DeleteStore())
    monkeypatch.setattr(
        scanner,
        "_resolve",
        lambda _payload: (_ for _ in ()).throw(RuntimeError("db unavailable")),
    )
    assert scanner.scan() == 0
    assert journal.pending_count() == 1


class ObservedOss:
    public_base_url = "https://cdn.example.test"

    def __init__(self, journal, *, crash=False):
        self.journal = journal
        self.crash = crash
        self.puts = []

    def upload_stream(self, handle, object_key, **_kwargs):
        assert self.journal.pending_count() >= 1
        self.puts.append((object_key, handle.read()))
        if self.crash:
            raise SystemExit("SIGKILL boundary")
        return SimpleNamespace(
            object_key=object_key,
            bucket="bucket",
            url=f"https://cdn.example.test/{object_key}",
        )


def _upload_fixture(tmp_path, *, crash=False):
    workspace = CoreTaskWorkspace.create(tmp_path, "ctask_writeahead", 1)
    output = workspace.output_dir / "video.mp4"
    output.write_bytes(b"artifact")
    journal = ArtifactReconciliationJournal(tmp_path)
    oss = ObservedOss(journal, crash=crash)
    store = ArtifactStore(
        oss,
        CdnUrlPolicy({"cdn.example.test"}, prefix="/narrato/coreApi/"),
    )
    return workspace, output, journal, oss, store


def test_artifact_store_records_intent_before_put_and_updates_full_reference(tmp_path):
    workspace, output, journal, oss, store = _upload_fixture(tmp_path)
    ref = store.upload(
        workspace=workspace,
        local_path=output,
        core_task_id="ctask_writeahead",
        attempt_no=1,
        kind="video",
    )
    assert len(oss.puts) == 1 and journal.pending_count() == 1
    name = next((tmp_path / ".artifact_reconciliation").glob("pending-*.json"))
    payload = json.loads(name.read_text())
    assert payload["artifacts"][0]["artifact_id"] == ref.artifact_id
    assert payload["artifacts"][0]["bucket"] == "bucket"
    assert payload["artifacts"][0]["url"] == ref.url


def test_crash_after_oss_put_leaves_exact_write_ahead_intent(tmp_path):
    workspace, output, journal, oss, store = _upload_fixture(tmp_path, crash=True)
    with pytest.raises(SystemExit):
        store.upload(
            workspace=workspace,
            local_path=output,
            core_task_id="ctask_writeahead",
            attempt_no=1,
            kind="video",
        )
    assert len(oss.puts) == 1 and journal.pending_count() == 1
    payload = json.loads(
        next((tmp_path / ".artifact_reconciliation").glob("pending-*.json")).read_text()
    )
    assert payload["task_id"] == "ctask_writeahead"
    assert payload["artifacts"][0]["object_key"] == oss.puts[0][0]


def test_journal_failure_prevents_oss_put(tmp_path, monkeypatch):
    workspace, output, _journal, oss, store = _upload_fixture(tmp_path)
    monkeypatch.setattr(
        ArtifactReconciliationJournal,
        "record_intent",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(OSError, match="disk full"):
        store.upload(
            workspace=workspace,
            local_path=output,
            core_task_id="ctask_writeahead",
            attempt_no=1,
            kind="video",
        )
    assert oss.puts == []


def test_scanner_quarantines_hardlink_and_invalid_known_orphan_schema(
    session, tmp_path
):
    journal = ArtifactReconciliationJournal(tmp_path)
    name = journal.record("ctask_test", 1, [artifact()], known_orphan=True)
    directory = tmp_path / ".artifact_reconciliation"
    os.link(directory / name, directory / "attacker-link")
    store = DeleteStore()
    assert ArtifactReconciliationScanner(session, journal, store).scan() == 0
    assert store.deleted == []
    assert list(directory.glob("quarantine-*.bad"))

    invalid = directory / "pending-invalid.json"
    invalid.write_text(
        json.dumps(
            {
                "version": 1,
                "task_id": "ctask_test",
                "attempt_no": 1,
                "known_orphan": "yes",
                "artifacts": [artifact().to_dict()],
            }
        )
    )
    invalid.chmod(0o600)
    assert ArtifactReconciliationScanner(session, journal, store).scan() == 0
    assert store.deleted == []
    assert len(list(directory.glob("quarantine-*.bad"))) == 2


def test_active_claim_heartbeat_prevents_second_scanner_from_stealing_old_pending(
    session, tmp_path
):
    journal = ArtifactReconciliationJournal(tmp_path)
    name = journal.record("ctask_test", 1, [artifact()], known_orphan=True)
    directory = tmp_path / ".artifact_reconciliation"
    old = time.time() - 60
    os.utime(directory / name, (old, old))
    calls = []
    entered = threading.Event()

    first = ArtifactReconciliationScanner(
        session, journal, DeleteStore(), stale_claim_seconds=0.12
    )
    second = ArtifactReconciliationScanner(
        session, journal, DeleteStore(), stale_claim_seconds=0.12
    )

    def slow(_payload):
        calls.append("first")
        entered.set()
        time.sleep(0.35)
        return True

    first._resolve = slow
    second._resolve = lambda _payload: calls.append("second") or True
    thread = threading.Thread(target=first.scan)
    thread.start()
    assert entered.wait(1)
    time.sleep(0.2)
    assert second.scan() == 0
    thread.join()
    assert calls == ["first"]


def test_uploading_protection_and_cleanup_tombstone_delete_late_remote_commit(
    session, tmp_path
):
    now = [100.0]

    def clock():
        return now[0]

    journal = ArtifactReconciliationJournal(tmp_path, clock=clock)
    item = artifact()
    journal.record_intent(
        "ctask_missing",
        1,
        artifact_id=item.artifact_id,
        kind=item.kind,
        object_key=item.object_key,
        content_type=item.content_type,
        size=item.size,
        checksum=item.checksum,
        upload_protection_seconds=10,
    )

    class RemoteStore(DeleteStore):
        def __init__(self):
            super().__init__()
            self.objects = {item.object_key}

        def delete_reconciled_artifact(self, reference):
            self.deleted.append(reference.object_key)
            self.objects.discard(reference.object_key)

        def is_reconciled_artifact_absent(self, reference):
            return reference.object_key not in self.objects

    store = RemoteStore()
    scanner = ArtifactReconciliationScanner(
        session,
        journal,
        store,
        clock=clock,
        settlement_seconds=30,
        settlement_confirmations=3,
    )
    now[0] = 105
    assert scanner.scan() == 0 and store.deleted == []
    now[0] = 111
    assert scanner.scan() == 0 and store.objects == set()
    store.objects.add(item.object_key)  # remote PUT commits after first DELETE
    assert (
        journal.update_reference("ignored", item, task_id="ctask_missing", attempt_no=1)
        is None
    )
    now[0] = 126
    assert scanner.scan() == 0 and store.objects == set()
    now[0] = 156
    assert scanner.scan() == 1
    assert store.objects == set() and journal.pending_count() == 0
    assert store.deleted.count(item.object_key) == 3


def test_resolver_value_error_restores_fact_instead_of_quarantine(session, tmp_path):
    journal = ArtifactReconciliationJournal(tmp_path)
    journal.record("ctask_test", 1, [artifact()], known_orphan=True)
    store = DeleteStore()
    store.fail = True
    store.delete_reconciled_artifact = lambda _item: (_ for _ in ()).throw(
        ValueError("temporary provider error")
    )
    scanner = settled_scanner(session, journal, store)
    assert scanner.scan() == 0 and journal.pending_count() == 1
    assert not list((tmp_path / ".artifact_reconciliation").glob("quarantine-*.bad"))
    store.delete_reconciled_artifact = lambda item: store.deleted.append(
        item.object_key
    )
    force_pending_due(tmp_path)
    assert scanner.scan() == 1 and journal.pending_count() == 0


def test_fifo_socket_and_symlink_are_quarantined_without_blocking_valid_fact(
    session, tmp_path
):
    journal = ArtifactReconciliationJournal(tmp_path)
    journal.pending_count()
    directory = tmp_path / ".artifact_reconciliation"
    os.mkfifo(directory / "pending-00-fifo.json", 0o600)
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    (directory / "pending-01-link.json").symlink_to(outside)
    sock = socket.socket(socket.AF_UNIX)
    short_socket = f"/tmp/narrato-{os.getpid()}-{time.time_ns()}.sock"
    expected_quarantine = 2
    try:
        sock.bind(short_socket)
        os.rename(short_socket, directory / "pending-02-socket.json")
        expected_quarantine = 3
    except OSError:
        # Some CI sandboxes deny AF_UNIX bind; production branch is the same
        # lstat non-regular rejection already exercised by FIFO.
        pass
    try:
        journal.record("ctask_test", 1, [artifact()], known_orphan=True)
        store = DeleteStore()
        started = time.monotonic()
        settled_scanner(session, journal, store).scan(limit=10)
        assert time.monotonic() - started < 1
        assert store.deleted == [artifact().object_key]
        assert len(list(directory.glob("quarantine-*.bad"))) == expected_quarantine
    finally:
        sock.close()


def test_synchronous_upload_joins_intent_heartbeat_and_leaves_no_detached_put(
    tmp_path,
):
    workspace = CoreTaskWorkspace.create(tmp_path, "ctask_syncput", 1)
    output = workspace.output_dir / "video.mp4"
    output.write_bytes(b"artifact")
    started, release = threading.Event(), threading.Event()

    class BlockingOss(ObservedOss):
        def upload_stream(self, handle, object_key, **kwargs):
            started.set()
            assert release.wait(2)
            return super().upload_stream(handle, object_key, **kwargs)

    journal = ArtifactReconciliationJournal(tmp_path)
    oss = BlockingOss(journal)
    store = ArtifactStore(
        oss,
        CdnUrlPolicy({"cdn.example.test"}, prefix="/narrato/coreApi/"),
        upload_protection_seconds=30,
    )
    baseline = {thread.ident for thread in threading.enumerate()}
    result = []
    caller = threading.Thread(
        target=lambda: result.append(
            store.upload(
                workspace=workspace,
                local_path=output,
                core_task_id="ctask_syncput",
                attempt_no=1,
                kind="video",
            )
        )
    )
    caller.start()
    assert started.wait(1) and caller.is_alive()
    release.set()
    caller.join(2)
    assert len(result) == 1 and not caller.is_alive()
    assert {thread.ident for thread in threading.enumerate()} == baseline


def test_update_reference_waits_for_slow_scanner_claim_instead_of_misdeleting(
    session, tmp_path
):
    journal = ArtifactReconciliationJournal(tmp_path)
    item = artifact()
    intent = journal.record_intent(
        "ctask_test",
        1,
        artifact_id=item.artifact_id,
        kind=item.kind,
        object_key=item.object_key,
        content_type=item.content_type,
        size=item.size,
        checksum=item.checksum,
        upload_protection_seconds=30,
    )
    entered = threading.Event()
    scanner = ArtifactReconciliationScanner(session, journal, DeleteStore())

    def slow(_payload):
        entered.set()
        time.sleep(0.8)
        return False

    scanner._resolve = slow
    thread = threading.Thread(target=scanner.scan)
    thread.start()
    assert entered.wait(1)
    started = time.monotonic()
    assert (
        journal.update_reference(intent, item, task_id="ctask_test", attempt_no=1)
        == intent
    )
    assert time.monotonic() - started >= 0.7
    thread.join()
    payload = json.loads((tmp_path / ".artifact_reconciliation" / intent).read_text())
    assert payload["phase"] == "uploaded"


def test_tombstone_without_remote_head_is_never_retired(session, tmp_path):
    journal = ArtifactReconciliationJournal(tmp_path)
    journal.record("ctask_test", 1, [artifact()], known_orphan=True)

    class NoHeadStore:
        def __init__(self):
            self.deleted = 0

        def delete_reconciled_artifact(self, _artifact):
            self.deleted += 1

    store = NoHeadStore()
    scanner = ArtifactReconciliationScanner(
        session,
        journal,
        store,
        settlement_seconds=0,
        settlement_confirmations=1,
    )
    assert [scanner.scan() for _ in range(3)] == [0, 0, 0]
    assert store.deleted == 1 and journal.pending_count() == 1


def test_missing_intent_and_direct_delete_failure_recreates_durable_tombstone(
    tmp_path, monkeypatch
):
    workspace, output, journal, oss, store = _upload_fixture(tmp_path)
    monkeypatch.setattr(
        ArtifactReconciliationJournal, "update_reference", lambda *_a, **_k: None
    )
    oss.delete_object = lambda _key: (_ for _ in ()).throw(
        RuntimeError("delete unavailable")
    )
    with pytest.raises(RuntimeError, match="delete unavailable"):
        store.upload(
            workspace=workspace,
            local_path=output,
            core_task_id="ctask_writeahead",
            attempt_no=1,
            kind="video",
        )
    payloads = [
        json.loads(path.read_text())
        for path in (tmp_path / ".artifact_reconciliation").glob("pending-*.json")
    ]
    assert any(payload["phase"] == "cleanup_tombstone" for payload in payloads)


def test_upload_heartbeat_never_shortens_protection_across_wall_clock_jumps(tmp_path):
    now = [100.0]

    def clock():
        return now[0]

    journal = ArtifactReconciliationJournal(tmp_path, clock=clock)
    item = artifact()
    intent = journal.record_intent(
        "ctask_test",
        1,
        artifact_id=item.artifact_id,
        kind=item.kind,
        object_key=item.object_key,
        content_type=item.content_type,
        size=item.size,
        checksum=item.checksum,
        upload_protection_seconds=30,
    )
    now[0] = 50
    assert journal.heartbeat_upload(intent, protection_seconds=30)
    payload = json.loads((tmp_path / ".artifact_reconciliation" / intent).read_text())
    assert payload["upload_protected_until"] == 130
    now[0] = 1000
    assert journal.heartbeat_upload(intent, protection_seconds=30)
    payload = json.loads((tmp_path / ".artifact_reconciliation" / intent).read_text())
    assert payload["upload_protected_until"] == 1030


def test_claim_replace_failure_cleans_temporary_file(tmp_path, monkeypatch):
    journal = ArtifactReconciliationJournal(tmp_path)
    name = journal.record("ctask_test", 1, [artifact()])
    directory_fd = journal._open_directory()
    payload = ArtifactReconciliationScanner._read_claim(directory_fd, name)
    real_replace = os.replace

    def fail_replace(src, dst, **kwargs):
        if dst == name:
            raise OSError("replace failed")
        return real_replace(src, dst, **kwargs)

    monkeypatch.setattr(os, "replace", fail_replace)
    try:
        with pytest.raises(OSError, match="replace failed"):
            journal._replace_claim_payload(directory_fd, name, payload)
        assert not [
            entry for entry in os.listdir(directory_fd) if entry.startswith(".tmp-")
        ]
    finally:
        os.close(directory_fd)


def test_due_time_rotation_prevents_limit_head_starvation(session, tmp_path):
    now = [100.0]

    def clock():
        return now[0]

    journal = ArtifactReconciliationJournal(tmp_path, clock=clock)
    items = [artifact(1, suffix) for suffix in ("first", "second", "third")]
    for item in items:
        journal.record("ctask_test", 1, [item], known_orphan=True)
    store = DeleteStore()
    scanner = ArtifactReconciliationScanner(
        session, journal, store, clock=clock, settlement_seconds=3600
    )
    assert scanner.scan(limit=2) == 0
    assert len(set(store.deleted)) == 2
    assert scanner.scan(limit=2) == 0
    assert set(store.deleted) == {item.object_key for item in items}


def test_retirement_requires_consecutive_spaced_absent_head_confirmations(
    session, tmp_path
):
    now = [100.0]

    def clock():
        return now[0]

    journal = ArtifactReconciliationJournal(tmp_path, clock=clock)
    journal.record("ctask_test", 1, [artifact()], known_orphan=True)

    class EventuallyConsistentStore(DeleteStore):
        # True means HEAD confirms absent. A single false-negative is followed
        # by exists=True and must not contribute to retirement.
        absent = iter([False, False, True, False, True, True, True])

        def is_reconciled_artifact_absent(self, _artifact):
            return next(self.absent)

    store = EventuallyConsistentStore()
    scanner = ArtifactReconciliationScanner(
        session,
        journal,
        store,
        clock=clock,
        settlement_seconds=0,
        settlement_confirmations=3,
    )
    results = []
    for _ in range(7):
        results.append(scanner.scan())
        now[0] += 4000
    assert results[:-1] == [0] * 6 and results[-1] == 1
    assert journal.pending_count() == 0


@pytest.mark.parametrize("mode,hardlink", [(0o666, False), (0o600, True)])
def test_operation_lock_rejects_weak_mode_and_hardlink(tmp_path, mode, hardlink):
    journal = ArtifactReconciliationJournal(tmp_path)
    journal.pending_count()
    lock = tmp_path / ".artifact_reconciliation" / ".operation.lock"
    outside = tmp_path / "outside.lock"
    outside.write_bytes(b"")
    outside.chmod(mode)
    if hardlink:
        os.link(outside, lock)
    else:
        os.rename(outside, lock)
    with pytest.raises(ReconciliationSecurityError):
        journal._acquire_operation_lock()


def test_slow_fact_does_not_block_other_scanner_fact(session, tmp_path):
    journal = ArtifactReconciliationJournal(tmp_path)
    first = journal.record("ctask_test", 1, [artifact(1, "slow")], known_orphan=True)
    second = journal.record("ctask_test", 1, [artifact(1, "fast")], known_orphan=True)
    directory = tmp_path / ".artifact_reconciliation"
    os.rename(directory / first, directory / "pending-00.json")
    os.rename(directory / second, directory / "pending-01.json")
    entered, release, fast_done = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    slow_scanner = ArtifactReconciliationScanner(session, journal, DeleteStore())
    fast_scanner = ArtifactReconciliationScanner(session, journal, DeleteStore())

    def slow(_payload):
        entered.set()
        assert release.wait(2)
        return True

    slow_scanner._resolve = slow
    fast_scanner._resolve = lambda _payload: fast_done.set() or True
    slow_thread = threading.Thread(target=lambda: slow_scanner.scan(limit=1))
    slow_thread.start()
    assert entered.wait(1)
    fast_thread = threading.Thread(target=lambda: fast_scanner.scan(limit=10))
    fast_thread.start()
    assert fast_done.wait(0.5)
    release.set()
    slow_thread.join(2)
    fast_thread.join(2)
    assert journal.pending_count() == 0


def test_journal_capacity_fails_closed_before_new_fact(tmp_path, monkeypatch):
    journal = ArtifactReconciliationJournal(tmp_path)
    monkeypatch.setattr(reconciliation, "_MAX_ACTIVE_ENTRIES", 1)
    journal.record("ctask_test", 1, [artifact(1, "first")])
    with pytest.raises(reconciliation.ReconciliationCapacityError):
        journal.record("ctask_test", 1, [artifact(1, "second")])


def test_delete_failure_persists_attempt_and_backoff_before_retry(session, tmp_path):
    now = [100.0]

    def clock():
        return now[0]

    journal = ArtifactReconciliationJournal(tmp_path, clock=clock)
    journal.record("ctask_test", 1, [artifact()], known_orphan=True)
    store = DeleteStore()
    calls = []
    store.delete_reconciled_artifact = lambda _item: (
        calls.append(now[0]),
        (_ for _ in ()).throw(RuntimeError("oss down")),
    )[1]
    scanner = ArtifactReconciliationScanner(session, journal, store, clock=clock)
    assert scanner.scan() == 0 and calls == [100]
    payload = json.loads(
        next((tmp_path / ".artifact_reconciliation").glob("pending-*.json")).read_text()
    )
    assert payload["delete_attempts"] == 1
    assert payload["next_check_at"] == 115
    assert scanner.scan() == 0 and calls == [100]
    now[0] = 115
    assert scanner.scan() == 0 and calls == [100, 115]


def test_capacity_reservation_is_atomic_for_concurrent_writers(tmp_path, monkeypatch):
    journal = ArtifactReconciliationJournal(tmp_path)
    monkeypatch.setattr(reconciliation, "_MAX_ACTIVE_ENTRIES", 1)

    def write(suffix):
        try:
            return journal.record("ctask_test", 1, [artifact(1, suffix)])
        except reconciliation.ReconciliationCapacityError:
            return "capacity"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ("one", "two")))
    assert results.count("capacity") == 1
    assert journal.pending_count() == 1


def test_completed_fact_sidecars_and_temps_are_bounded_and_collected(session, tmp_path):
    journal = ArtifactReconciliationJournal(tmp_path)
    for index in range(20):
        journal.record(
            "ctask_test", 1, [artifact(1, f"item{index}")], known_orphan=True
        )
    store = DeleteStore()
    assert settled_scanner(session, journal, store).scan(limit=20) == 20
    directory = tmp_path / ".artifact_reconciliation"
    assert journal.pending_count() == 0
    assert not list(directory.glob(".fact-lock-*"))
    assert not list(directory.glob(".tmp-*"))


def test_operation_lock_cold_start_is_reliable_across_fork_workers(tmp_path):
    context = multiprocessing.get_context("fork")
    for round_no in range(3):
        root = tmp_path / f"cold-{round_no}"
        root.mkdir()
        barrier = context.Barrier(6)
        results = context.Queue()

        def worker(index):
            try:
                barrier.wait(timeout=5)
                ArtifactReconciliationJournal(root).record(
                    "ctask_test", 1, [artifact(1, f"worker{index}")]
                )
                results.put("ok")
            except BaseException as exc:
                results.put(f"{type(exc).__name__}:{exc}")

        processes = [
            context.Process(target=worker, args=(index,)) for index in range(6)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            assert process.exitcode == 0
        outcomes = [results.get(timeout=2) for _ in processes]
        assert outcomes == ["ok"] * 6
        assert ArtifactReconciliationJournal(root).pending_count() == 6


def test_quarantine_gc_enforces_byte_budget_and_restores_write_capacity(
    session, tmp_path, monkeypatch
):
    journal = ArtifactReconciliationJournal(tmp_path)
    journal.pending_count()
    directory = tmp_path / ".artifact_reconciliation"
    for index in range(3):
        path = directory / f"quarantine-{index}.bad"
        path.write_bytes(b"x" * 6)
        path.chmod(0o600)
        os.utime(path, (100 + index, 100 + index))
    monkeypatch.setattr(reconciliation, "_MAX_QUARANTINE_ENTRIES", 1000)
    monkeypatch.setattr(reconciliation, "_MAX_QUARANTINE_BYTES", 10)
    monkeypatch.setattr(reconciliation, "_MAX_AUXILIARY_BYTES", 12)
    ArtifactReconciliationScanner(session, journal, DeleteStore()).scan()
    remaining = list(directory.glob("quarantine-*.bad"))
    assert sum(path.stat().st_size for path in remaining) <= 10
    assert journal.record("ctask_test", 1, [artifact(1, "aftergc")])


@pytest.mark.parametrize(
    "adapter_name",
    ["asr_adapter", "short_drama_adapter", "tts_adapter", "render_adapter"],
)
def test_handler_uses_one_generic_store_for_every_artifact_task_type(
    tmp_path, adapter_name
):
    store = DeleteStore()
    handler = AtomicTaskHandler(
        task_service=SimpleNamespace(session=None),
        work_root=tmp_path,
        **{adapter_name: SimpleNamespace(artifact_store=store)},
    )
    assert handler._compensate_result({"artifacts": [artifact().to_dict()]}) is True
    assert store.deleted == [artifact().object_key]

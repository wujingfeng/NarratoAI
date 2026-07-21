from __future__ import annotations

import concurrent.futures

from redis.cluster import key_slot

from narrato_api.auth import redis_store
from narrato_api.auth.service import InMemorySessionStore, SingleSessionTokens


def test_second_login_revokes_first_token_and_raw_token_is_not_stored() -> None:
    store = InMemorySessionStore()
    tokens = SingleSessionTokens(store, ttl_seconds=2_592_000)
    first = tokens.issue("usr_01", password_version=1)
    second = tokens.issue("usr_01", password_version=1)
    assert tokens.resolve(first) is None
    identity = tokens.resolve(second)
    assert identity is not None
    assert (identity.user_id, identity.password_version) == ("usr_01", 1)
    assert first not in repr(store.snapshot())
    assert second not in repr(store.snapshot())


def test_session_ttl_is_fixed_and_resolve_does_not_refresh_it() -> None:
    store = InMemorySessionStore()
    tokens = SingleSessionTokens(store, ttl_seconds=2_592_000)
    token = tokens.issue("usr_01", password_version=7)
    assert 2_591_999 <= store.ttl_for_token(token) <= 2_592_000
    store.advance(120)
    before = store.ttl_for_token(token)
    identity = tokens.resolve(token)
    assert identity is not None and identity.password_version == 7
    assert store.ttl_for_token(token) == before


def test_old_token_logout_does_not_delete_new_session() -> None:
    store = InMemorySessionStore()
    tokens = SingleSessionTokens(store, ttl_seconds=2_592_000)
    old = tokens.issue("usr_01", password_version=1)
    new = tokens.issue("usr_01", password_version=1)
    tokens.revoke(old)
    assert tokens.resolve(new) is not None


def test_concurrent_logins_leave_exactly_one_valid_session() -> None:
    store = InMemorySessionStore()
    tokens = SingleSessionTokens(store, ttl_seconds=2_592_000)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        issued = list(
            executor.map(
                lambda version: tokens.issue("usr_01", password_version=version),
                range(1, 21),
            )
        )
    valid = [token for token in issued if tokens.resolve(token) is not None]
    assert len(valid) == 1


def test_auth_redis_keys_share_cluster_slot_and_lua_uses_only_keys() -> None:
    store = redis_store.RedisSessionStore(object(), prefix="narrato:test:")  # type: ignore[arg-type]
    keys = (
        store.user_key("usr_01"),
        store.session_key("a" * 64),
        store.session_key("b" * 64),
        redis_store.RedisEmailCodeStore(object(), prefix="narrato:test:").key(  # type: ignore[arg-type]
            "register", "c" * 64
        ),
    )
    assert len({key_slot(key.encode()) for key in keys}) == 1
    for script in redis_store.AUTH_LUA_SCRIPTS:
        assert "ARGV[1] .." not in script
        assert "ARGV[2] .." not in script


def test_code_fsm_lua_uses_redis_time_not_client_epoch() -> None:
    import inspect

    source = inspect.getsource(redis_store.RedisEmailCodeStore)
    assert "time.time" not in source
    clocked = [script for script in redis_store.AUTH_LUA_SCRIPTS if "now_ms" in script]
    assert clocked and all("redis.call('TIME')" in script for script in clocked)


def test_code_owner_transition_requires_an_active_redis_time_lease() -> None:
    """完成发送不能让已过期的 owner 以旧 generation 提交状态。"""

    assert "redis.call('TIME')" in redis_store._TRANSITION_CODE
    assert "lease_until_ms" in redis_store._TRANSITION_CODE
    assert "<= now_ms" in redis_store._TRANSITION_CODE

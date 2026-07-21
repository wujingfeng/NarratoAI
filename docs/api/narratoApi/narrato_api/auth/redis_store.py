from __future__ import annotations

import json
from dataclasses import dataclass

from redis import Redis
from redis.exceptions import RedisError

from narrato_api.api.errors import ApiError
from narrato_api.auth.service import (
    CodePurpose,
    EmailCodeStore,
    SessionIdentity,
    SessionStore,
    decode_session_identity,
    encode_session_identity,
)

_ROTATE_CODE = """
local clock = redis.call('TIME')
local now_ms = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local current = redis.call('GET', KEYS[1])
if current then
  local decoded = cjson.decode(current)
  if decoded['status'] == 'sending' and tonumber(decoded['lease_until_ms'] or 0) > now_ms then return 0 end
end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
return 1
"""

_CONSUME_CODE = """
local current = redis.call('GET', KEYS[1])
if current then
  local decoded = cjson.decode(current)
  if decoded['digest'] == ARGV[1] then
    redis.call('DEL', KEYS[1])
    return 1
  end
end
return 0
"""

_DISCARD_CODE = """
local current = redis.call('GET', KEYS[1])
if current then
  local decoded = cjson.decode(current)
  if decoded['generation'] == ARGV[1] and decoded['digest'] == ARGV[2] then
    redis.call('DEL', KEYS[1])
    return 1
  end
end
return 0
"""

_CLAIM_CODE = """
local clock = redis.call('TIME')
local now_ms = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local current = redis.call('GET', KEYS[1])
if not current then return {0, 0} end
local decoded = cjson.decode(current)
if decoded['generation'] ~= ARGV[1] or decoded['digest'] ~= ARGV[2] then return {0, 0} end
if decoded['status'] == 'sending' and tonumber(decoded['lease_until_ms'] or 0) > now_ms then
  return {2, math.ceil((tonumber(decoded['lease_until_ms']) - now_ms) / 1000)}
end
if decoded['status'] ~= 'pending' and decoded['status'] ~= 'sending' then return {0, 0} end
decoded['status'] = 'sending'
decoded['claim_id'] = ARGV[3]
decoded['lease_until_ms'] = now_ms + tonumber(ARGV[4])
redis.call('SET', KEYS[1], cjson.encode(decoded), 'KEEPTTL')
return {1, 0}
"""

_TRANSITION_CODE = """
local clock = redis.call('TIME')
local now_ms = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local current = redis.call('GET', KEYS[1])
if not current then return 0 end
local decoded = cjson.decode(current)
if decoded['generation'] ~= ARGV[1] or decoded['digest'] ~= ARGV[2] or decoded['claim_id'] ~= ARGV[3] or decoded['status'] ~= ARGV[4] then return 0 end
if tonumber(decoded['lease_until_ms'] or 0) <= now_ms then return 0 end
decoded['status'] = ARGV[5]
decoded['claim_id'] = cjson.null
decoded['lease_until_ms'] = 0
redis.call('SET', KEYS[1], cjson.encode(decoded), 'KEEPTTL')
return 1
"""

_RENEW_CODE = """
local clock = redis.call('TIME')
local now_ms = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local current = redis.call('GET', KEYS[1])
if not current then return 0 end
local decoded = cjson.decode(current)
if decoded['generation'] ~= ARGV[1] or decoded['digest'] ~= ARGV[2] or decoded['claim_id'] ~= ARGV[3] or decoded['status'] ~= 'sending' then return 0 end
decoded['lease_until_ms'] = now_ms + tonumber(ARGV[4])
redis.call('SET', KEYS[1], cjson.encode(decoded), 'KEEPTTL')
return 1
"""

_COMPARE_DELETE = """
local current = redis.call('GET', KEYS[1])
if current and current == ARGV[1] then
  redis.call('DEL', KEYS[1])
  return 1
end
return 0
"""

_REPLACE_SESSION_CAS = """
local current = redis.call('GET', KEYS[1])
if not current then current = '' end
if current ~= ARGV[1] then return 0 end
if ARGV[1] ~= '' then redis.call('DEL', KEYS[3]) end
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3])
redis.call('SET', KEYS[1], ARGV[4], 'EX', ARGV[3])
return 1
"""

_RESOLVE_SESSION = """
local identity = redis.call('GET', KEYS[1])
if not identity then return false end
local current = redis.call('GET', KEYS[2])
if current and current == ARGV[1] then return identity end
return false
"""

_REVOKE_SESSION = """
local identity = redis.call('GET', KEYS[1])
if not identity then return 0 end
redis.call('DEL', KEYS[1])
local current = redis.call('GET', KEYS[2])
if current and current == ARGV[1] then redis.call('DEL', KEYS[2]) end
return 1
"""

_REVOKE_USER_CAS = """
local current = redis.call('GET', KEYS[1])
if not current then current = '' end
if current ~= ARGV[1] then return 0 end
redis.call('DEL', KEYS[1])
if ARGV[1] ~= '' then redis.call('DEL', KEYS[2]) end
return 1
"""

AUTH_LUA_SCRIPTS = (
    _ROTATE_CODE,
    _CONSUME_CODE,
    _DISCARD_CODE,
    _CLAIM_CODE,
    _TRANSITION_CODE,
    _RENEW_CODE,
    _COMPARE_DELETE,
    _REPLACE_SESSION_CAS,
    _RESOLVE_SESSION,
    _REVOKE_SESSION,
    _REVOKE_USER_CAS,
)


def _redis_unavailable(_error: RedisError | None = None) -> ApiError:
    """将 Redis 故障或并发重试耗尽收敛为稳定 503。"""

    return ApiError(
        "AUTH_SERVICE_UNAVAILABLE", "Authentication service unavailable", 503
    )


def _text(value: object | None) -> str | None:
    """将 redis-py 字节响应安全转换为文本。"""

    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


class RedisEmailCodeStore(EmailCodeStore):
    """使用同一 Cluster hash tag 保存验证码 HMAC 摘要。"""

    def __init__(self, client: Redis, *, prefix: str) -> None:
        self.client = client
        self.prefix = f"{{narrato-auth}}:{prefix}auth:code:"

    def key(self, purpose: CodePurpose, email_hash: str) -> str:
        """返回不包含明文邮箱和验证码的同槽键。"""

        return f"{self.prefix}{purpose}:{email_hash}"

    @staticmethod
    def _value(generation: str, digest: str, status: str = "pending") -> str:
        return json.dumps(
            {"digest": digest, "generation": generation, "status": status},
            separators=(",", ":"),
            sort_keys=True,
        )

    def rotate(
        self,
        purpose: CodePurpose,
        email_hash: str,
        generation: str,
        digest: str,
        ttl_seconds: int,
    ) -> bool:
        """pending/sent 原子替换并重置 TTL；sending generation 暂不旋转。"""

        try:
            return bool(
                self.client.eval(
                    _ROTATE_CODE,
                    1,
                    self.key(purpose, email_hash),
                    self._value(generation, digest),
                    str(ttl_seconds),
                )
            )
        except RedisError as error:
            raise _redis_unavailable(error) from None

    def consume(self, purpose: CodePurpose, email_hash: str, digest: str) -> bool:
        """Lua 比较删除保证并发消费只有一个成功。"""

        try:
            return bool(
                self.client.eval(
                    _CONSUME_CODE, 1, self.key(purpose, email_hash), digest
                )
            )
        except RedisError as error:
            raise _redis_unavailable(error) from None

    def discard(
        self, purpose: CodePurpose, email_hash: str, generation: str, digest: str
    ) -> bool:
        """仅删除显式 KEYS 中仍匹配 generation 的验证码。"""

        try:
            return bool(
                self.client.eval(
                    _DISCARD_CODE,
                    1,
                    self.key(purpose, email_hash),
                    generation,
                    digest,
                )
            )
        except RedisError as error:
            raise _redis_unavailable(error) from None

    def invalidate(self, purpose: CodePurpose, email_hash: str) -> None:
        """删除不再可使用的用途键。"""

        try:
            self.client.delete(self.key(purpose, email_hash))
        except RedisError as error:
            raise _redis_unavailable(error) from None

    def claim(
        self,
        purpose: CodePurpose,
        email_hash: str,
        generation: str,
        digest: str,
        *,
        claim_id: str,
        lease_seconds: int,
    ) -> CodeClaim:
        """邮件 Worker 在 SMTP 前原子 claim 精确 generation。"""

        try:
            raw = self.client.eval(
                _CLAIM_CODE,
                1,
                self.key(purpose, email_hash),
                generation,
                digest,
                claim_id,
                str(lease_seconds * 1000),
            )
            if not isinstance(raw, (list, tuple)) or len(raw) != 2:
                raise _redis_unavailable()
            status, retry_after = int(raw[0]), int(raw[1])
            return CodeClaim(
                claimed=status == 1,
                busy=status == 2,
                retry_after_seconds=max(1, retry_after) if status == 2 else 0,
            )
        except RedisError as error:
            raise _redis_unavailable(error) from None

    def _transition(
        self,
        purpose: CodePurpose,
        email_hash: str,
        generation: str,
        digest: str,
        claim_id: str,
        source: str,
        target: str,
    ) -> bool:
        try:
            return bool(
                self.client.eval(
                    _TRANSITION_CODE,
                    1,
                    self.key(purpose, email_hash),
                    generation,
                    digest,
                    claim_id,
                    source,
                    target,
                )
            )
        except RedisError as error:
            raise _redis_unavailable(error) from None

    def renew(
        self,
        purpose: CodePurpose,
        email_hash: str,
        generation: str,
        digest: str,
        claim_id: str,
        lease_seconds: int,
    ) -> bool:
        """使用 Redis TIME 为当前 owner 原子续租。"""

        try:
            return bool(
                self.client.eval(
                    _RENEW_CODE,
                    1,
                    self.key(purpose, email_hash),
                    generation,
                    digest,
                    claim_id,
                    str(lease_seconds * 1000),
                )
            )
        except RedisError as error:
            raise _redis_unavailable(error) from None

    def mark_sent(
        self,
        purpose: CodePurpose,
        email_hash: str,
        generation: str,
        digest: str,
        claim_id: str,
    ) -> bool:
        return self._transition(
            purpose, email_hash, generation, digest, claim_id, "sending", "sent"
        )

    def release(
        self,
        purpose: CodePurpose,
        email_hash: str,
        generation: str,
        digest: str,
        claim_id: str,
    ) -> bool:
        return self._transition(
            purpose, email_hash, generation, digest, claim_id, "sending", "pending"
        )


@dataclass(frozen=True, slots=True)
class CodeClaim:
    """Worker claim 结果；busy 必须延迟重试而不能成功 ACK。"""

    claimed: bool
    busy: bool
    retry_after_seconds: int


class RedisSessionStore(SessionStore):
    """用同槽显式 KEYS 与有限 CAS 重试维护单点会话。"""

    _MAX_CAS_ATTEMPTS = 16

    def __init__(self, client: Redis, *, prefix: str) -> None:
        self.client = client
        self.prefix = f"{{narrato-auth}}:{prefix}auth:"

    def user_key(self, user_id: str) -> str:
        """返回用户当前 Token 摘要映射键。"""

        return f"{self.prefix}user-session:{user_id}"

    def session_key(self, token_hash: str) -> str:
        """返回只包含 Token 摘要的会话事实键。"""

        return f"{self.prefix}session:{token_hash}"

    def _get(self, key: str) -> str | None:
        try:
            return _text(self.client.get(key))
        except RedisError as error:
            raise _redis_unavailable(error) from None

    def replace(
        self,
        user_id: str,
        password_version: int,
        token_hash: str,
        ttl_seconds: int,
    ) -> None:
        """乐观读取旧摘要后以三显式 KEYS 原子 CAS 替换会话。"""

        user_key = self.user_key(user_id)
        new_session_key = self.session_key(token_hash)
        identity = encode_session_identity(user_id, password_version)
        for _attempt in range(self._MAX_CAS_ATTEMPTS):
            old_hash = self._get(user_key) or ""
            old_session_key = self.session_key(old_hash or "__none__")
            try:
                changed = self.client.eval(
                    _REPLACE_SESSION_CAS,
                    3,
                    user_key,
                    new_session_key,
                    old_session_key,
                    old_hash,
                    identity,
                    str(ttl_seconds),
                    token_hash,
                )
            except RedisError as error:
                raise _redis_unavailable(error) from None
            if bool(changed):
                return
        raise _redis_unavailable()

    def resolve(self, token_hash: str) -> SessionIdentity | None:
        """只读解析且不刷新 TTL；映射竞态由两 KEYS Lua 收口。"""

        session_key = self.session_key(token_hash)
        raw_identity = self._get(session_key)
        if raw_identity is None:
            return None
        try:
            identity = decode_session_identity(raw_identity)
        except ValueError:
            self.revoke(token_hash)
            return None
        try:
            value = self.client.eval(
                _RESOLVE_SESSION,
                2,
                session_key,
                self.user_key(identity.user_id),
                token_hash,
            )
        except RedisError as error:
            raise _redis_unavailable(error) from None
        rendered = _text(value)
        if rendered is None:
            return None
        try:
            return decode_session_identity(rendered)
        except ValueError:
            self.revoke(token_hash)
            return None

    def revoke(self, token_hash: str) -> None:
        """用两个显式同槽 KEYS 删除会话及仍匹配的用户映射。"""

        session_key = self.session_key(token_hash)
        raw_identity = self._get(session_key)
        if raw_identity is None:
            return
        try:
            identity = decode_session_identity(raw_identity)
        except ValueError:
            try:
                self.client.delete(session_key)
            except RedisError as error:
                raise _redis_unavailable(error) from None
            return
        try:
            self.client.eval(
                _REVOKE_SESSION,
                2,
                session_key,
                self.user_key(identity.user_id),
                token_hash,
            )
        except RedisError as error:
            raise _redis_unavailable(error) from None

    def revoke_user(self, user_id: str) -> None:
        """乐观读取当前摘要后以两个显式 KEYS 原子 CAS 撤销。"""

        user_key = self.user_key(user_id)
        for _attempt in range(self._MAX_CAS_ATTEMPTS):
            token_hash = self._get(user_key) or ""
            if not token_hash:
                return
            try:
                changed = self.client.eval(
                    _REVOKE_USER_CAS,
                    2,
                    user_key,
                    self.session_key(token_hash),
                    token_hash,
                )
            except RedisError as error:
                raise _redis_unavailable(error) from None
            if bool(changed):
                return
        raise _redis_unavailable()

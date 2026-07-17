from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from email_validator import EmailNotValidError, validate_email

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from narrato_api.api.errors import ApiError
from narrato_api.auth.models import User
from narrato_api.integrations.mail_client import MailDispatcher

CodePurpose = Literal["register", "password_reset"]


def normalize_email(value: str) -> str:
    """去除首尾空白并返回无歧义的小写邮箱。"""

    value = value.strip()
    if not value or len(value) > 254 or not value.isascii():
        raise ValueError("invalid email")
    try:
        result = validate_email(
            value,
            allow_smtputf8=False,
            check_deliverability=False,
            allow_quoted_local=False,
        )
    except EmailNotValidError as error:
        raise ValueError("invalid email") from error
    normalized = result.normalized.lower()
    if not normalized.isascii() or len(normalized) > 254:
        raise ValueError("invalid email")
    return normalized


def validate_password(value: str) -> None:
    """限制密码长度并要求字母与数字同时存在。"""

    encoded = value.encode("utf-8")
    if (
        len(encoded) < 12
        or len(encoded) > 128
        or not any(char.isalpha() for char in value)
        or not any(char.isdigit() for char in value)
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError("password does not satisfy policy")


def _email_hash(email: str) -> str:
    """生成不泄漏邮箱的固定键摘要。"""

    return hashlib.sha256(normalize_email(email).encode()).hexdigest()


def _token_hash(token: str) -> str:
    """生成 Redis 会话事实使用的 Token 摘要。"""

    return hashlib.sha256(token.encode()).hexdigest()


def encode_session_identity(user_id: str, password_version: int) -> str:
    """编码无敏感值且可严格验证的会话版本元数据。"""

    if "|" in user_id or password_version < 1:
        raise ValueError("invalid session identity")
    return f"{user_id}|{password_version}"


def decode_session_identity(value: str) -> SessionIdentity:
    """严格解析 Redis 会话版本元数据。"""

    user_id, separator, version = value.rpartition("|")
    if separator != "|" or not user_id or not version.isascii() or not version.isdigit():
        raise ValueError("invalid session identity")
    parsed = int(version)
    if parsed < 1:
        raise ValueError("invalid session identity")
    return SessionIdentity(user_id=user_id, password_version=parsed)


def _new_user_id() -> str:
    """生成带前缀、时间有序且不可解析的用户 ID。"""

    return f"usr_{time.time_ns():016x}{secrets.token_hex(8)}"


class EmailCodeStore(Protocol):
    """验证码原子替换和一次消费协议。"""

    def rotate(
        self,
        purpose: CodePurpose,
        email_hash: str,
        generation: str,
        digest: str,
        ttl_seconds: int,
    ) -> bool: ...

    def consume(self, purpose: CodePurpose, email_hash: str, digest: str) -> bool: ...

    def discard(
        self, purpose: CodePurpose, email_hash: str, generation: str, digest: str
    ) -> bool: ...

    def invalidate(self, purpose: CodePurpose, email_hash: str) -> None: ...


@dataclass(frozen=True, slots=True)
class SessionIdentity:
    """Redis 会话绑定的用户和密码版本快照。"""

    user_id: str
    password_version: int


class SessionStore(Protocol):
    """单用户单会话原子存储协议。"""

    def replace(
        self,
        user_id: str,
        password_version: int,
        token_hash: str,
        ttl_seconds: int,
    ) -> None: ...

    def resolve(self, token_hash: str) -> SessionIdentity | None: ...

    def revoke(self, token_hash: str) -> None: ...

    def revoke_user(self, user_id: str) -> None: ...

    def session_key(self, token_hash: str) -> str: ...


class PasswordHasher:
    """使用 Argon2id 不可逆保存和验证密码。"""

    def __init__(
        self, *, time_cost: int = 3, memory_cost_kib: int = 65_536, parallelism: int = 2
    ) -> None:
        """绑定明确且可配置的 Argon2id 参数。"""

        self._hasher = Argon2PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost_kib,
            parallelism=parallelism,
            hash_len=32,
            salt_len=16,
        )
        self._dummy_hash = self._hasher.hash("narrato-dummy-password-0000")

    def hash(self, password: str) -> str:
        """校验策略后生成带随机盐的 Argon2id 哈希。"""

        validate_password(password)
        return self._hasher.hash(password)

    def verify(self, stored_hash: str | None, password: str) -> bool:
        """不存在用户也执行一次等价哈希验证以降低明显时序差。"""

        candidate = stored_hash or self._dummy_hash
        try:
            matched: bool = self._hasher.verify(candidate, password)
        except (VerificationError, InvalidHashError):
            matched = False
        return bool(matched and stored_hash is not None)


@dataclass(frozen=True, slots=True)
class EmailCodeIssue:
    """一次验证码 generation 的原子创建结果。"""

    purpose: CodePurpose
    email_hash: str
    digest: str
    generation: str
    code: str
    created: bool


class EmailCodeManager:
    """生成高熵六位码并仅向存储层提交 HMAC 摘要。"""

    def __init__(self, store: EmailCodeStore, *, secret: str, ttl_seconds: int) -> None:
        """绑定用途隔离存储、HMAC 密钥和固定 TTL。"""

        if not secret:
            raise ValueError("verification code HMAC secret is required")
        self.store = store
        self._secret = secret.encode()
        self.ttl_seconds = ttl_seconds

    def _digest(self, purpose: CodePurpose, email_hash: str, code: str) -> str:
        payload = f"{purpose}:{email_hash}:{code}".encode()
        return hmac.new(self._secret, payload, hashlib.sha256).hexdigest()

    def coordinates(
        self, email: str, code: str, *, purpose: CodePurpose
    ) -> tuple[str, str]:
        """返回 Worker 状态机使用的邮箱摘要和 code HMAC。"""

        hashed_email = _email_hash(email)
        return hashed_email, self._digest(purpose, hashed_email, code)

    def issue(self, email: str, *, purpose: CodePurpose) -> EmailCodeIssue:
        """仅在不存在当前 generation 时原子创建验证码。"""

        hashed_email = _email_hash(email)
        code = f"{secrets.randbelow(1_000_000):06d}"
        digest = self._digest(purpose, hashed_email, code)
        generation = secrets.token_urlsafe(18)
        created = self.store.rotate(
            purpose, hashed_email, generation, digest, self.ttl_seconds
        )
        return EmailCodeIssue(
            purpose=purpose,
            email_hash=hashed_email,
            digest=digest,
            generation=generation,
            code=code,
            created=created,
        )

    def cancel(self, issue: EmailCodeIssue) -> bool:
        """Broker 拒绝时仅删除本次成功创建的 generation。"""

        if not issue.created:
            return False
        return self.store.discard(
            issue.purpose, issue.email_hash, issue.generation, issue.digest
        )

    def invalidate(self, email: str, *, purpose: CodePurpose) -> None:
        """删除不再具有业务意义的当前用途验证码。"""

        self.store.invalidate(purpose, _email_hash(email))

    def consume(self, email: str, code: str, *, purpose: CodePurpose) -> bool:
        """以原子比较删除保证验证码最多成功一次。"""

        if len(code) != 6 or not code.isascii() or not code.isdigit():
            return False
        hashed_email = _email_hash(email)
        return self.store.consume(
            purpose, hashed_email, self._digest(purpose, hashed_email, code)
        )


class SingleSessionTokens:
    """生成原始随机 Token，并只把 SHA-256 摘要交给存储层。"""

    def __init__(self, store: SessionStore, *, ttl_seconds: int) -> None:
        """绑定原子会话存储和固定过期时间。"""

        self.store = store
        self.ttl_seconds = ttl_seconds

    def issue(self, user_id: str, *, password_version: int) -> str:
        """原子撤销旧会话并返回只展示一次的新原始 Token。"""

        token = secrets.token_urlsafe(48)
        self.store.replace(
            user_id, password_version, _token_hash(token), self.ttl_seconds
        )
        return token

    def resolve(self, token: str) -> SessionIdentity | None:
        """只读解析 Token，不刷新固定 TTL。"""

        if not token or len(token) > 512:
            return None
        return self.store.resolve(_token_hash(token))

    def revoke(self, token: str) -> None:
        """仅撤销该 Token，旧 Token 不会误删当前映射。"""

        if token and len(token) <= 512:
            self.store.revoke(_token_hash(token))

    def revoke_user(self, user_id: str) -> None:
        """立即撤销用户当前会话。"""

        self.store.revoke_user(user_id)

    def session_key(self, token: str) -> str:
        """返回测试与运维 TTL 探针使用的摘要会话键。"""

        return self.store.session_key(_token_hash(token))


@dataclass(slots=True)
class _ExpiringValue:
    value: str
    expires_at: float


@dataclass(slots=True)
class _CodeValue:
    digest: str
    generation: str
    status: Literal["pending", "sending", "sent"]
    expires_at: float


class InMemoryEmailCodeStore:
    """真实模拟 TTL 和原子语义的测试验证码存储。"""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], _CodeValue] = {}
        self._offset = 0.0
        self._lock = threading.Lock()

    def _now(self) -> float:
        return time.monotonic() + self._offset

    def rotate(
        self,
        purpose: CodePurpose,
        email_hash: str,
        generation: str,
        digest: str,
        ttl_seconds: int,
    ) -> bool:
        with self._lock:
            key = (purpose, email_hash)
            current = self._values.get(key)
            if (
                current is not None
                and current.expires_at > self._now()
                and current.status == "sending"
            ):
                return False
            self._values[key] = _CodeValue(
                digest, generation, "pending", self._now() + ttl_seconds
            )
            return True

    def consume(self, purpose: CodePurpose, email_hash: str, digest: str) -> bool:
        with self._lock:
            key = (purpose, email_hash)
            item = self._values.get(key)
            if item is None or item.expires_at <= self._now():
                self._values.pop(key, None)
                return False
            if not hmac.compare_digest(item.digest, digest):
                return False
            del self._values[key]
            return True

    def discard(
        self, purpose: CodePurpose, email_hash: str, generation: str, digest: str
    ) -> bool:
        """仅在 generation 摘要仍匹配时删除。"""

        with self._lock:
            key = (purpose, email_hash)
            item = self._values.get(key)
            if item is None:
                return False
            if item.generation != generation or not hmac.compare_digest(item.digest, digest):
                return False
            del self._values[key]
            return True

    def invalidate(self, purpose: CodePurpose, email_hash: str) -> None:
        """无条件删除指定用途当前 generation。"""

        with self._lock:
            self._values.pop((purpose, email_hash), None)

    def ttl_for(self, purpose: CodePurpose, email: str) -> int:
        with self._lock:
            item = self._values[(purpose, _email_hash(email))]
            return max(-1, int(item.expires_at - self._now()))

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._offset += seconds

    def snapshot(self) -> dict[tuple[str, str], str]:
        with self._lock:
            return {key: value.digest for key, value in self._values.items()}


class AccountLockRegistry:
    """FastAPI app 作用域的 SQLite 测试兼容锁；生产正确性依赖数据库行锁。"""

    def __init__(self, stripes: int = 64) -> None:
        self._locks = tuple(threading.RLock() for _ in range(stripes))

    def for_email(self, normalized_email: str) -> threading.RLock:
        index = int(hashlib.sha256(normalized_email.encode()).hexdigest()[:8], 16)
        return self._locks[index % len(self._locks)]


class InMemorySessionStore:
    """真实模拟单会话替换、匹配删除和固定 TTL 的测试存储。"""

    def __init__(self) -> None:
        self._sessions: dict[str, _ExpiringValue] = {}
        self._users: dict[str, _ExpiringValue] = {}
        self._offset = 0.0
        self._lock = threading.Lock()

    def _now(self) -> float:
        return time.monotonic() + self._offset

    def _purge(self, token_hash: str) -> None:
        item = self._sessions.get(token_hash)
        if item is not None and item.expires_at <= self._now():
            self._sessions.pop(token_hash, None)
            try:
                user_id = decode_session_identity(item.value).user_id
            except ValueError:
                return
            current = self._users.get(user_id)
            if current is not None and current.value == token_hash:
                self._users.pop(user_id, None)

    def replace(
        self,
        user_id: str,
        password_version: int,
        token_hash: str,
        ttl_seconds: int,
    ) -> None:
        with self._lock:
            previous = self._users.get(user_id)
            if previous is not None:
                self._sessions.pop(previous.value, None)
            expires = self._now() + ttl_seconds
            self._sessions[token_hash] = _ExpiringValue(
                encode_session_identity(user_id, password_version), expires
            )
            self._users[user_id] = _ExpiringValue(token_hash, expires)

    def resolve(self, token_hash: str) -> SessionIdentity | None:
        with self._lock:
            self._purge(token_hash)
            item = self._sessions.get(token_hash)
            if item is None:
                return None
            try:
                identity = decode_session_identity(item.value)
            except ValueError:
                self._sessions.pop(token_hash, None)
                return None
            current = self._users.get(identity.user_id)
            if current is None or current.value != token_hash:
                return None
            return identity

    def revoke(self, token_hash: str) -> None:
        with self._lock:
            item = self._sessions.pop(token_hash, None)
            if item is not None:
                try:
                    user_id = decode_session_identity(item.value).user_id
                except ValueError:
                    return
                current = self._users.get(user_id)
                if current is not None and current.value == token_hash:
                    self._users.pop(user_id, None)

    def revoke_user(self, user_id: str) -> None:
        with self._lock:
            current = self._users.pop(user_id, None)
            if current is not None:
                self._sessions.pop(current.value, None)

    def ttl_for_token(self, token: str) -> int:
        with self._lock:
            item = self._sessions[_token_hash(token)]
            return max(-1, int(item.expires_at - self._now()))

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._offset += seconds

    def snapshot(self) -> tuple[dict[str, str], dict[str, str]]:
        with self._lock:
            return (
                {key: value.value for key, value in self._sessions.items()},
                {key: value.value for key, value in self._users.items()},
            )

    def session_key(self, token_hash: str) -> str:
        """返回不含原始 Token 的内存会话键。"""

        return token_hash


@dataclass(frozen=True, slots=True)
class LoginResult:
    """登录后仅向调用方展示一次的 Token 和账户快照。"""

    token: str
    user: User


class AuthService:
    """协调账户、验证码、密码、邮件与单点会话。"""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        password_hasher: PasswordHasher,
        codes: EmailCodeManager,
        tokens: SingleSessionTokens,
        mail_dispatcher: MailDispatcher,
        account_locks: AccountLockRegistry | None = None,
    ) -> None:
        """注入可独立测试的数据库和外部依赖。"""

        self.session_factory = session_factory
        self.password_hasher = password_hasher
        self.codes = codes
        self.tokens = tokens
        self.mail_dispatcher = mail_dispatcher
        self.account_locks = account_locks or AccountLockRegistry()

    def _account_lock(self, normalized_email: str) -> threading.RLock:
        """返回进程内固定条带锁；跨进程一致性仍由数据库行锁保证。"""

        return self.account_locks.for_email(normalized_email)

    def send_register_code(self, email: str) -> str | None:
        """以统一公开工作量创建唯一未过期注册码 generation。"""

        normalized = normalize_email(email)
        with self.session_factory() as session:
            exists = session.scalar(select(User.id).where(User.email == normalized))
        issue = self.codes.issue(normalized, purpose="register")
        deliver = exists is None
        try:
            self.mail_dispatcher.enqueue(
                normalized,
                issue.code,
                purpose="register",
                generation=issue.generation,
                deliver=deliver,
                ttl_seconds=self.codes.ttl_seconds,
            )
        except BaseException:
            self.codes.cancel(issue)
            raise
        return issue.code

    def send_password_reset_code(self, email: str) -> None:
        """找回密码始终走一次 Redis 与 Broker，且仅有效账户真实投递。"""

        normalized = normalize_email(email)
        with self.session_factory() as session:
            user = session.scalar(select(User).where(User.email == normalized))
        issue = self.codes.issue(normalized, purpose="password_reset")
        deliver = user is not None and user.status == "active"
        try:
            self.mail_dispatcher.enqueue(
                normalized,
                issue.code,
                purpose="password_reset",
                generation=issue.generation,
                deliver=deliver,
                ttl_seconds=self.codes.ttl_seconds,
            )
        except BaseException:
            self.codes.cancel(issue)
            raise

    def register(self, email: str, password: str, verification_code: str) -> User:
        """一次消费验证码并以数据库唯一约束收口并发注册。"""

        normalized = normalize_email(email)
        validate_password(password)
        if not self.codes.consume(
            normalized, verification_code, purpose="register"
        ):
            raise ApiError("INVALID_VERIFICATION_CODE", "Verification code is invalid", 400)
        user = User(
            id=_new_user_id(),
            email=normalized,
            password_hash=self.password_hasher.hash(password),
            status="active",
        )
        with self.session_factory() as session:
            session.add(user)
            try:
                session.commit()
            except IntegrityError as error:
                session.rollback()
                raise ApiError(
                    "EMAIL_ALREADY_REGISTERED", "Email already registered", 409
                ) from error
            session.refresh(user)
            session.expunge(user)
        return user

    def login(self, email: str, password: str) -> LoginResult:
        """持有账户行锁验证密码并签发绑定版本的单点会话。"""

        normalized = normalize_email(email)
        with self._account_lock(normalized):
            with self.session_factory() as session:
                with session.begin():
                    user = session.scalar(
                        select(User)
                        .where(User.email == normalized)
                        .with_for_update()
                    )
                    stored = user.password_hash if user is not None else None
                    verified = self.password_hasher.verify(stored, password)
                    if user is None or not verified or user.status != "active":
                        if user is not None and user.status != "active":
                            self.tokens.revoke_user(user.id)
                        raise authentication_required()
                    token = self.tokens.issue(
                        user.id, password_version=user.password_version
                    )
                session.expunge(user)
        return LoginResult(token=token, user=user)

    def resolve(self, token: str) -> User:
        """按执行计划稳定接口解析当前用户。"""

        return self.resolve_user(token)

    def resolve_user(self, token: str) -> User:
        """解析会话并核对数据库 active 状态和当前密码版本。"""

        identity = self.tokens.resolve(token)
        if identity is None:
            raise authentication_required()
        with self.session_factory() as session:
            user = session.get(User, identity.user_id)
            if (
                user is None
                or user.status != "active"
                or user.password_version != identity.password_version
            ):
                self.tokens.revoke(token)
                raise authentication_required()
            session.expunge(user)
        return user

    def logout(self, token: str) -> None:
        """撤销当前原始 Token 对应的摘要事实。"""

        self.tokens.revoke(token)

    def session_key(self, token: str) -> str:
        """返回不含原始 Token 的会话事实键。"""

        return self.tokens.session_key(token)

    def reset_password(
        self, email: str, verification_code: str, new_password: str
    ) -> None:
        """一次消费找回码、更新密码并立即撤销当前会话。"""

        normalized = normalize_email(email)
        validate_password(new_password)
        if not self.codes.consume(
            normalized, verification_code, purpose="password_reset"
        ):
            raise ApiError("INVALID_VERIFICATION_CODE", "Verification code is invalid", 400)
        with self._account_lock(normalized):
            with self.session_factory() as session:
                with session.begin():
                    user = session.scalar(
                        select(User)
                        .where(User.email == normalized)
                        .with_for_update()
                    )
                    if user is None or user.status != "active":
                        raise ApiError(
                            "INVALID_VERIFICATION_CODE",
                            "Verification code is invalid",
                            400,
                        )
                    # Redis 撤销失败必须先中止事务，禁止提交新密码。
                    self.tokens.revoke_user(user.id)
                    user.password_hash = self.password_hasher.hash(new_password)
                    user.password_version += 1

    def disable_user(self, user_id: str) -> None:
        """禁用账户并立即撤销当前 Redis 会话。"""

        with self.session_factory() as session:
            with session.begin():
                user = session.scalar(
                    select(User).where(User.id == user_id).with_for_update()
                )
                if user is None:
                    return
                self.tokens.revoke_user(user_id)
                user.status = "disabled"
                user.password_version += 1


def authentication_required() -> ApiError:
    """返回所有认证失败共用的安全 401。"""

    return ApiError("AUTHENTICATION_REQUIRED", "Authentication required", 401)

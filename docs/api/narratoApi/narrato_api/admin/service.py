from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from narrato_api.admin.models import (
    AdminPermission,
    AdminRole,
    AdminRolePermission,
    AdminUser,
    AdminUserRole,
)
from narrato_api.auth.service import PasswordHasher, validate_password
from narrato_api.config import Settings


def new_id(prefix: str) -> str:
    return f"{prefix}_{time.time_ns():x}{secrets.token_hex(8)}"


def normalize_username(value: str) -> str:
    value = value.strip()
    if (
        not value
        or len(value) > 64
        or not value.isascii()
        or not all(c.isalnum() or c in "._-" for c in value)
    ):
        raise ValueError("invalid username")
    return value


@dataclass(frozen=True, slots=True)
class AdminIdentity:
    id: str
    password_version: int


class AdminTokenService:
    """无状态、独立密钥签名的短期管理端令牌。"""

    def __init__(self, *, secret: str, ttl_seconds: int) -> None:
        if len(secret) < 32:
            raise ValueError("admin session secret unavailable")
        self._key = secret.encode()
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _b64(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

    @staticmethod
    def _unb64(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

    def issue(self, admin: AdminUser) -> str:
        payload = json.dumps(
            {
                "sub": admin.id,
                "pv": admin.password_version,
                "exp": int(time.time()) + self.ttl_seconds,
                "typ": "admin",
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        encoded = self._b64(payload)
        signature = hmac.new(self._key, encoded.encode(), hashlib.sha256).digest()
        return f"adm1.{encoded}.{self._b64(signature)}"

    def resolve(self, token: str) -> AdminIdentity | None:
        try:
            prefix, encoded, signature = token.split(".")
            if prefix != "adm1" or len(token) > 2048:
                return None
            expected = self._b64(
                hmac.new(self._key, encoded.encode(), hashlib.sha256).digest()
            )
            if not hmac.compare_digest(signature, expected):
                return None
            payload = json.loads(self._unb64(encoded))
            if payload.get("typ") != "admin" or int(payload["exp"]) < int(time.time()):
                return None
            admin_id, version = payload["sub"], int(payload["pv"])
            if not isinstance(admin_id, str) or not admin_id or version < 1:
                return None
            return AdminIdentity(admin_id, version)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None


def password_hasher(settings: Settings) -> PasswordHasher:
    return PasswordHasher(
        time_cost=settings.password_argon2_time_cost,
        memory_cost_kib=settings.password_argon2_memory_cost_kib,
        parallelism=settings.password_argon2_parallelism,
    )


def ensure_bootstrap_admin(session: Session, settings: Settings) -> bool:
    """仅首次在显式提供强密码时创建不可自动删除的 Admin 超管。"""
    if session.scalar(select(AdminUser.id).limit(1)) is not None:
        return False
    password = settings.admin_bootstrap_password
    if not password:
        return False
    validate_password(password)
    username = normalize_username(settings.admin_bootstrap_username)
    admin = AdminUser(
        id=new_id("adm"),
        username=username,
        display_name=settings.admin_bootstrap_display_name.strip() or username,
        password_hash=password_hasher(settings).hash(password),
        is_superuser=True,
    )
    session.add(admin)
    session.flush()
    session.add(AdminUserRole(admin_id=admin.id, role_id="role_super_admin"))
    session.commit()
    return True


def permissions_for(session: Session, admin: AdminUser) -> set[str]:
    if admin.is_superuser:
        return {"*"}
    statement = (
        select(AdminPermission.code)
        .join(
            AdminRolePermission, AdminRolePermission.permission_id == AdminPermission.id
        )
        .join(AdminUserRole, AdminUserRole.role_id == AdminRolePermission.role_id)
        .where(AdminUserRole.admin_id == admin.id)
    )
    return set(session.scalars(statement))


def roles_for(session: Session, admin_id: str) -> list[str]:
    statement = (
        select(AdminRole.code)
        .join(AdminUserRole, AdminUserRole.role_id == AdminRole.id)
        .where(AdminUserRole.admin_id == admin_id)
        .order_by(AdminRole.code)
    )
    return list(session.scalars(statement))


def require_permission(permissions: Iterable[str], code: str) -> bool:
    available = set(permissions)
    return "*" in available or code in available

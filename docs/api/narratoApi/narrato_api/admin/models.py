from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from narrato_api.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AdminUser(Base):
    """独立于普通用户的管理端账户。"""

    __tablename__ = "admin_users"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'disabled')", name="ck_admin_users_status"
        ),
        Index("ix_admin_users_username", "username", unique=True),
        {"comment": "管理后台账户，和 users 完全隔离。"},
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    password_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class AdminRole(Base):
    __tablename__ = "admin_roles"
    __table_args__ = (Index("ix_admin_roles_code", "code", unique=True),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512))
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class AdminPermission(Base):
    __tablename__ = "admin_permissions"
    __table_args__ = (Index("ix_admin_permissions_code", "code", unique=True),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AdminMenu(Base):
    __tablename__ = "admin_menus"
    __table_args__ = (
        CheckConstraint(
            "menu_type IN ('directory', 'menu', 'button')", name="ck_admin_menus_type"
        ),
        Index("ix_admin_menus_parent_sort", "parent_id", "sort_order"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("admin_menus.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    path: Mapped[str | None] = mapped_column(String(256))
    icon: Mapped[str | None] = mapped_column(String(64))
    menu_type: Mapped[str] = mapped_column(String(16), nullable=False, default="menu")
    permission_code: Mapped[str | None] = mapped_column(String(128))
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class AdminUserRole(Base):
    __tablename__ = "admin_user_roles"
    admin_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("admin_users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("admin_roles.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AdminRolePermission(Base):
    __tablename__ = "admin_role_permissions"
    role_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("admin_roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("admin_permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AdminOperationLog(Base):
    __tablename__ = "admin_operation_logs"
    __table_args__ = (
        Index("ix_admin_operation_logs_created", "created_at"),
        Index("ix_admin_operation_logs_admin", "admin_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    admin_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    username: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128))
    request_id: Mapped[str | None] = mapped_column(String(128))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    method: Mapped[str | None] = mapped_column(String(8))
    path: Mapped[str | None] = mapped_column(String(512))
    before_data: Mapped[dict | None] = mapped_column(JSON)
    after_data: Mapped[dict | None] = mapped_column(JSON)
    result: Mapped[str] = mapped_column(String(16), nullable=False, default="success")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class SystemConfig(Base):
    __tablename__ = "system_configs"
    __table_args__ = (Index("ix_system_configs_key", "config_key", unique=True),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    config_key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(String(512))
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

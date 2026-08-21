"""Add independent management-console authentication and RBAC.

Revision ID: 0036_admin_rbac
Revises: 0035_allow_legacy_task_charge_usd_null
Create Date: 2026-08-17
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision: str = "0036_admin_rbac"
down_revision: str | None = "0035_allow_legacy_task_charge_usd_null"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = (
    ("perm_admin_users_read", "admin:users:read", "查看用户"),
    ("perm_admin_users_manage", "admin:users:manage", "管理用户状态"),
    ("perm_admin_tasks_read", "admin:tasks:read", "查看任务"),
    ("perm_admin_models_read", "admin:models:read", "查看模型配置"),
    ("perm_admin_models_manage", "admin:models:manage", "管理模型和玩法"),
    ("perm_admin_configs_read", "admin:configs:read", "查看系统配置"),
    ("perm_admin_configs_manage", "admin:configs:manage", "管理系统配置"),
    ("perm_admin_rbac_read", "admin:rbac:read", "查看权限配置"),
    ("perm_admin_rbac_manage", "admin:rbac:manage", "管理权限配置"),
    ("perm_admin_logs_read", "admin:logs:read", "查看日志"),
    ("perm_admin_dashboard_read", "admin:overview:read", "查看运营总览"),
)


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column(
            "is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("password_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')", name="ck_admin_users_status"
        ),
        comment="管理后台账户，和 users 完全隔离。",
    )
    op.create_index("ix_admin_users_username", "admin_users", ["username"], unique=True)
    op.create_table(
        "admin_roles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(512)),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_roles_code", "admin_roles", ["code"], unique=True)
    op.create_table(
        "admin_permissions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(512)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_admin_permissions_code", "admin_permissions", ["code"], unique=True
    )
    op.create_table(
        "admin_menus",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "parent_id",
            sa.String(64),
            sa.ForeignKey("admin_menus.id", ondelete="RESTRICT"),
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("code", sa.String(128), nullable=False, unique=True),
        sa.Column("path", sa.String(256)),
        sa.Column("icon", sa.String(64)),
        sa.Column("menu_type", sa.String(16), nullable=False, server_default="menu"),
        sa.Column("permission_code", sa.String(128)),
        sa.Column("is_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "menu_type IN ('directory', 'menu', 'button')", name="ck_admin_menus_type"
        ),
    )
    op.create_index(
        "ix_admin_menus_parent_sort", "admin_menus", ["parent_id", "sort_order"]
    )
    op.create_table(
        "admin_user_roles",
        sa.Column(
            "admin_id",
            sa.String(64),
            sa.ForeignKey("admin_users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "role_id",
            sa.String(64),
            sa.ForeignKey("admin_roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "admin_role_permissions",
        sa.Column(
            "role_id",
            sa.String(64),
            sa.ForeignKey("admin_roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_id",
            sa.String(64),
            sa.ForeignKey("admin_permissions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "admin_operation_logs",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "admin_id",
            sa.String(64),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
        ),
        sa.Column("username", sa.String(64)),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128)),
        sa.Column("request_id", sa.String(128)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("method", sa.String(8)),
        sa.Column("path", sa.String(512)),
        sa.Column("before_data", sa.JSON()),
        sa.Column("after_data", sa.JSON()),
        sa.Column("result", sa.String(16), nullable=False, server_default="success"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_admin_operation_logs_created", "admin_operation_logs", ["created_at"]
    )
    op.create_index(
        "ix_admin_operation_logs_admin",
        "admin_operation_logs",
        ["admin_id", "created_at"],
    )
    op.create_table(
        "system_configs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("config_key", sa.String(128), nullable=False),
        sa.Column("value", sa.Text()),
        sa.Column("description", sa.String(512)),
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "updated_by",
            sa.String(64),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_system_configs_key", "system_configs", ["config_key"], unique=True
    )
    # 运营总览与时间范围筛选使用这些单列索引，避免全表扫描历史数据。
    op.create_index("ix_users_created_at", "users", ["created_at"])
    op.create_index("ix_model_tasks_created_at", "model_tasks", ["created_at"])
    op.create_index("ix_workflows_created_at", "workflows", ["created_at"])
    op.create_index("ix_credit_ledger_created_at", "credit_ledger", ["created_at"])

    now = datetime.now(timezone.utc)
    op.bulk_insert(
        sa.table(
            "admin_roles",
            sa.column("id"),
            sa.column("code"),
            sa.column("name"),
            sa.column("description"),
            sa.column("is_system"),
            sa.column("created_at"),
            sa.column("updated_at"),
        ),
        [
            {
                "id": "role_super_admin",
                "code": "super_admin",
                "name": "超级管理员",
                "description": "拥有所有后台权限",
                "is_system": True,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    op.bulk_insert(
        sa.table(
            "admin_permissions",
            sa.column("id"),
            sa.column("code"),
            sa.column("name"),
            sa.column("created_at"),
        ),
        [
            {"id": i, "code": code, "name": name, "created_at": now}
            for i, code, name in PERMISSIONS
        ],
    )
    op.bulk_insert(
        sa.table(
            "admin_role_permissions",
            sa.column("role_id"),
            sa.column("permission_id"),
            sa.column("created_at"),
        ),
        [
            {"role_id": "role_super_admin", "permission_id": i, "created_at": now}
            for i, _, _ in PERMISSIONS
        ],
    )
    menus = [
        (
            "menu_dashboard",
            None,
            "运营总览",
            "dashboard",
            "/overview",
            "menu",
            "admin:overview:read",
            10,
        ),
        ("menu_users", None, "用户管理", "users", None, "directory", None, 20),
        (
            "menu_users_list",
            "menu_users",
            "用户列表",
            "users.list",
            "/users",
            "menu",
            "admin:users:read",
            10,
        ),
        ("menu_tasks", None, "任务管理", "tasks", None, "directory", None, 30),
        (
            "menu_tasks_drama",
            "menu_tasks",
            "短剧解说",
            "tasks.short-drama",
            "/tasks/short-drama",
            "menu",
            "admin:tasks:read",
            10,
        ),
        (
            "menu_tasks_translation",
            "menu_tasks",
            "视频翻译",
            "tasks.video-translation",
            "/tasks/video-translation",
            "menu",
            "admin:tasks:read",
            20,
        ),
        (
            "menu_tasks_ai",
            "menu_tasks",
            "AI 视频",
            "tasks.ai-video",
            "/tasks/ai-video",
            "menu",
            "admin:tasks:read",
            30,
        ),
        ("menu_configs", None, "配置管理", "configs", None, "directory", None, 40),
        (
            "menu_models",
            "menu_configs",
            "模型相关配置管理",
            "configs.models",
            "/config/models",
            "menu",
            "admin:models:read",
            10,
        ),
        (
            "menu_rbac",
            "menu_configs",
            "管理后台权限配置",
            "configs.rbac",
            "/rbac/admins",
            "menu",
            "admin:rbac:read",
            20,
        ),
        (
            "menu_system",
            "menu_configs",
            "系统配置",
            "configs.system",
            "/config/system",
            "menu",
            "admin:configs:read",
            30,
        ),
        ("menu_logs", None, "日志", "logs", None, "directory", None, 50),
        (
            "menu_operation_logs",
            "menu_logs",
            "后台操作日志",
            "logs.operations",
            "/logs/operations",
            "menu",
            "admin:logs:read",
            10,
        ),
        (
            "menu_credit_logs",
            "menu_logs",
            "用户积分日志",
            "logs.credit",
            "/logs/credits",
            "menu",
            "admin:logs:read",
            20,
        ),
    ]
    op.bulk_insert(
        sa.table(
            "admin_menus",
            sa.column("id"),
            sa.column("parent_id"),
            sa.column("name"),
            sa.column("code"),
            sa.column("path"),
            sa.column("menu_type"),
            sa.column("permission_code"),
            sa.column("sort_order"),
            sa.column("created_at"),
            sa.column("updated_at"),
        ),
        [
            {
                "id": i,
                "parent_id": parent,
                "name": name,
                "code": code,
                "path": path,
                "menu_type": typ,
                "permission_code": perm,
                "sort_order": order,
                "created_at": now,
                "updated_at": now,
            }
            for i, parent, name, code, path, typ, perm, order in menus
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_credit_ledger_created_at", table_name="credit_ledger")
    op.drop_index("ix_workflows_created_at", table_name="workflows")
    op.drop_index("ix_model_tasks_created_at", table_name="model_tasks")
    op.drop_index("ix_users_created_at", table_name="users")
    for table in (
        "system_configs",
        "admin_operation_logs",
        "admin_role_permissions",
        "admin_user_roles",
        "admin_menus",
        "admin_permissions",
        "admin_roles",
        "admin_users",
    ):
        op.drop_table(table)

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from narrato_api.admin.models import AdminRole, AdminUser, AdminUserRole
from narrato_api.admin.service import AdminTokenService, ensure_bootstrap_admin
from narrato_api.config import Settings
from narrato_api.database import Base


def _settings() -> Settings:
    return Settings(
        database_url="sqlite://",
        verification_code_hmac_secret="v" * 32,
        admin_session_hmac_secret="a" * 32,
        admin_bootstrap_password="AdminPass123",
        smtp_timeout_seconds=1,
        smtp_total_deadline_seconds=2,
        verification_code_send_lease_seconds=10,
        verification_code_ttl_seconds=60,
    )


def test_bootstrap_admin_is_idempotent_and_issues_independent_token() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    settings = _settings()
    with Session(engine) as session:
        session.add(AdminRole(id="role_super_admin", code="super_admin", name="超级管理员", is_system=True))
        session.commit()
        assert ensure_bootstrap_admin(session, settings) is True
        assert ensure_bootstrap_admin(session, settings) is False
        admin = session.scalar(select(AdminUser).where(AdminUser.username == "Admin"))
        assert admin is not None
        assert session.get(AdminUserRole, {"admin_id": admin.id, "role_id": "role_super_admin"}) is not None
        token = AdminTokenService(secret=settings.admin_session_hmac_secret, ttl_seconds=300).issue(admin)
        identity = AdminTokenService(secret=settings.admin_session_hmac_secret, ttl_seconds=300).resolve(token)
        assert identity is not None
        assert identity.id == admin.id
        assert AdminTokenService(secret=settings.admin_session_hmac_secret, ttl_seconds=300).resolve(token + "x") is None

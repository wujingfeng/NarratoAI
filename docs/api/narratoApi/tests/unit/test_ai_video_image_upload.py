from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from narrato_api.assets.models import Asset
from narrato_api.assets.service import UploadService
from narrato_api.auth.models import User
from narrato_api.database import Base
from narrato_api.integrations.oss_client import OssObject
from narrato_api.projects.models import Project


class _Oss:
    def head_object(self, bucket: str, object_key: str) -> OssObject:
        assert bucket == "bucket" and object_key == "narrato/api/reference.png"
        return OssObject(size_bytes=3, content_type="image/png")


class _Core:
    def probe_media(self, **kwargs: object) -> object:
        raise AssertionError("image uploads must not be relayed to Core media probe")


def test_verified_image_upload_is_marked_ready_without_core_probe() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with Session(engine) as session:
        session.add(User(id="usr_img_ready", email="ready@example.com", password_hash="hash"))
        session.flush()
        session.add(Project(id="prj_img_ready", user_id="usr_img_ready", product="ai_video"))
        session.commit()
    service = UploadService(session_factory=factory, oss_client=_Oss(), core_client=_Core(), oss_bucket="bucket")
    service.reserve(user_id="usr_img_ready", project_id="prj_img_ready", asset_type="image", filename="reference.png", size_bytes=3, object_key="narrato/api/reference.png", cdn_url="https://cdn.example/reference.png")
    asset = service.complete(user_id="usr_img_ready", project_id="prj_img_ready", asset_type="image", filename="reference.png", size_bytes=3, content_type="image/png", object_key="narrato/api/reference.png")
    assert asset.status == "ready"
    with Session(engine) as session:
        assert session.scalar(select(Asset.status).where(Asset.id == asset.id)) == "ready"

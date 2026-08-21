from __future__ import annotations


def test_task_events_are_authenticated_ordered_and_in_openapi(app, client, settings):
    """事件接口只读、鉴权并按 state_version 单调返回。"""

    from sqlalchemy.orm import Session
    from core_api.api.dependencies import get_database_session
    from core_api.database import Base, get_engine
    from core_api.tasks.service import TaskService

    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    database_session = Session(engine, expire_on_commit=False)
    task_service = TaskService(database_session)
    task = task_service.create_core_task(
        caller="narrato-api",
        route="/probe",
        task_type="asr",
        idempotency_key="events-probe",
        input_snapshot={"asset": "one"},
    )
    attempt = task_service.start_attempt(task.id)
    task_service.complete_attempt(
        attempt.id, attempt.lease_token, [], lease_version=attempt.lease_version
    )

    app.dependency_overrides[get_database_session] = lambda: database_session
    path = f"/api/v1/tasks/{task.id}/events"
    assert (
        path.replace(task.id, "{core_task_id}")
        in client.get("/openapi.json").json()["paths"]
    )
    assert client.get(path).status_code == 401
    response = client.get(path, headers={"Authorization": "Bearer test-service-token"})
    assert response.status_code == 200
    events = response.json()["data"]["events"]
    assert [event["sequence"] for event in events] == [1, 2]
    assert events[0]["artifacts"] == []
    assert all(
        set(event)
        == {
            "event_id",
            "sequence",
            "event_type",
            "time",
            "status",
            "phase",
            "progress",
            "attempt",
            "error",
            "artifacts",
        }
        for event in events
    )
    assert (
        client.post(
            path, headers={"Authorization": "Bearer test-service-token"}
        ).status_code
        == 405
    )


def test_task_events_unknown_task_returns_safe_404(app, client, settings):
    from sqlalchemy.orm import Session
    from core_api.api.dependencies import get_database_session
    from core_api.database import Base, get_engine

    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    database_session = Session(engine, expire_on_commit=False)
    app.dependency_overrides[get_database_session] = lambda: database_session
    response = client.get(
        "/api/v1/tasks/ctask_unknown/events",
        headers={"Authorization": "Bearer test-service-token"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "CORE_TASK_NOT_FOUND"


def test_task_query_exposes_completed_media_probe_result(app, client, settings):
    """Business API 轮询任务时必须能读取媒体探测的时长结果。"""

    from sqlalchemy.orm import Session

    from core_api.api.dependencies import get_database_session
    from core_api.database import Base, get_engine
    from core_api.tasks.service import TaskService

    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    database_session = Session(engine, expire_on_commit=False)
    service = TaskService(database_session)
    task = service.create_core_task(
        caller="narrato-api",
        route="/media-probe",
        task_type="media_probe",
        idempotency_key="media-probe-result",
        input_snapshot={"media_type": "video"},
    )
    attempt = service.start_attempt(task.id)
    result = {"media_type": "video", "duration_seconds": 20.053333}
    service.complete_attempt(
        attempt.id, attempt.lease_token, result, lease_version=attempt.lease_version
    )

    app.dependency_overrides[get_database_session] = lambda: database_session
    response = client.get(
        f"/api/v1/tasks/{task.id}",
        headers={"Authorization": "Bearer test-service-token"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["result"] == result
    assert response.json()["data"]["state_version"] == task.state_version


def test_task_query_openapi_publishes_versionable_dto_schema(client):
    """Task 与 Event 200 响应必须发布固定 Envelope/DTO，而非任意对象。"""

    document = client.get("/openapi.json").json()
    task_schema = document["paths"]["/api/v1/tasks/{core_task_id}"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]
    event_schema = document["paths"]["/api/v1/tasks/{core_task_id}/events"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    assert "$ref" in task_schema
    assert "$ref" in event_schema
    schemas = document["components"]["schemas"]
    for name in (
        "CoreTaskArtifactDTO",
        "CoreTaskDTO",
        "CoreTaskEventDTO",
        "CoreTaskEventsDTO",
    ):
        assert schemas[name].get("additionalProperties") is False
        assert schemas[name]["properties"]
    event_properties = schemas["CoreTaskEventDTO"]["properties"]
    assert set(event_properties) == {
        "event_id",
        "sequence",
        "event_type",
        "time",
        "status",
        "phase",
        "progress",
        "attempt",
        "error",
        "artifacts",
    }
    assert "state_version" in schemas["CoreTaskDTO"]["properties"]

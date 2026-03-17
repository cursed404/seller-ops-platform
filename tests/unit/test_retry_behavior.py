from sqlalchemy import select

from app.dependencies import build_incident_service, build_workflow_engine
from app.infrastructure.db.models import RetryAttempt, WorkflowRun


def test_sync_timeout_records_retries_and_completes(
    db_session,
    fake_publisher,
    fake_idempotency,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.dependencies.get_publisher", lambda: fake_publisher)
    monkeypatch.setattr("app.dependencies.get_idempotency_store", lambda: fake_idempotency)

    incident_service = build_incident_service(db_session)
    created = incident_service.create_incident(
        title="Ошибка синхронизации по таймауту",
        description="Синхронизация каталога с партнерским источником завершилась временной ошибкой по таймауту.",
        order_id=None,
        sku=None,
        sync_job_id="sync_cat_2002",
        metadata={"source": "test"},
    )

    engine = build_workflow_engine(db_session)
    engine.run_initial(created["workflow_id"])

    workflow = db_session.get(WorkflowRun, created["workflow_id"])
    attempts = db_session.scalars(
        select(RetryAttempt).where(RetryAttempt.workflow_id == created["workflow_id"]).order_by(RetryAttempt.id.asc())
    ).all()

    assert workflow is not None
    assert workflow.status == "completed"
    assert len(attempts) == 2
    assert attempts[0].outcome == "retryable_failure"
    assert attempts[1].outcome == "success"

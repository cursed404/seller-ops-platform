from sqlalchemy import select

from app.dependencies import build_incident_service, build_workflow_engine
from app.infrastructure.db.models import ActionExecution, WorkflowRun


def test_approval_resumes_repricing_workflow(
    db_session,
    fake_publisher,
    fake_idempotency,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.dependencies.get_publisher", lambda: fake_publisher)
    monkeypatch.setattr("app.dependencies.get_idempotency_store", lambda: fake_idempotency)

    incident_service = build_incident_service(db_session)
    created = incident_service.create_incident(
        title="Аномальное изменение цены",
        description="Цена по SKU-9921 упала на 38 процентов, а маржа ушла ниже допустимого порога.",
        order_id=None,
        sku="SKU-9921",
        sync_job_id=None,
        metadata={"source": "test"},
    )

    engine = build_workflow_engine(db_session)
    engine.run_initial(created["workflow_id"])
    incident_service.approve_workflow(
        workflow_id=created["workflow_id"],
        approved=True,
        decided_by="tester",
        note="Можно выполнять.",
    )
    engine.run_resume(created["workflow_id"])

    workflow = db_session.get(WorkflowRun, created["workflow_id"])
    action_execution = db_session.scalars(
        select(ActionExecution).where(ActionExecution.workflow_id == created["workflow_id"])
    ).first()

    assert workflow is not None
    assert workflow.status == "completed"
    assert action_execution is not None
    assert action_execution.status == "executed"
    assert action_execution.external_reference == "reprice-SKU-9921"

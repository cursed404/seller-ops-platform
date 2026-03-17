from sqlalchemy import select

from app.dependencies import build_workflow_engine
from app.infrastructure.db.models import ApprovalRequest, WorkflowRun


def test_inventory_mismatch_waits_for_approval(db_session, fake_publisher, fake_idempotency, monkeypatch) -> None:
    monkeypatch.setattr("app.dependencies.get_publisher", lambda: fake_publisher)
    monkeypatch.setattr("app.dependencies.get_idempotency_store", lambda: fake_idempotency)

    from app.dependencies import build_incident_service

    incident_service = build_incident_service(db_session)
    created = incident_service.create_incident(
        title="Обнаружено расхождение остатков",
        description="Остаток по SKU-1042 на витрине отличается от внутреннего на 17 единиц.",
        order_id=None,
        sku="SKU-1042",
        sync_job_id=None,
        metadata={"source": "test"},
    )

    engine = build_workflow_engine(db_session)
    engine.run_initial(created["workflow_id"])

    workflow = db_session.get(WorkflowRun, created["workflow_id"])
    approval = db_session.scalars(
        select(ApprovalRequest).where(ApprovalRequest.workflow_id == created["workflow_id"])
    ).first()

    assert workflow is not None
    assert workflow.status == "waiting_for_approval"
    assert approval is not None
    assert approval.status == "pending"

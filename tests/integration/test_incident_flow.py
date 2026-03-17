from app.dependencies import build_workflow_engine


def test_order_stuck_end_to_end(client, db_session, fake_publisher, fake_idempotency, monkeypatch) -> None:
    monkeypatch.setattr("app.dependencies.get_publisher", lambda: fake_publisher)
    monkeypatch.setattr("app.dependencies.get_idempotency_store", lambda: fake_idempotency)

    response = client.post(
        "/api/v1/incidents",
        json={
            "title": "Заказ завис в обработке после подтверждения оплаты",
            "description": "Заказ находится в обработке уже 45 минут после подтверждения оплаты.",
            "order_id": "ord_1001",
            "metadata": {"source": "integration-test"},
        },
    )
    assert response.status_code == 202
    created = response.json()

    engine = build_workflow_engine(db_session)
    engine.run_initial(created["workflow_id"])

    workflow_response = client.get(f"/api/v1/workflows/{created['workflow_id']}")
    assert workflow_response.status_code == 200
    workflow = workflow_response.json()

    assert workflow["workflow"]["status"] == "completed"
    event_types = [event["event_type"] for event in workflow["events"]]
    assert "incident.classified" in event_types
    assert "context.collected" in event_types
    assert "runbook.selected" in event_types
    assert "action.executed" in event_types
    assert "workflow.completed" in event_types

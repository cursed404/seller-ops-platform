from __future__ import annotations

import structlog
from prometheus_client import start_http_server

from app.dependencies import build_workflow_engine, get_app_settings
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.messaging.redpanda import KafkaWorkflowConsumer
from app.logging import configure_logging

configure_logging()
logger = structlog.get_logger(__name__)


def main() -> None:
    settings = get_app_settings()
    start_http_server(settings.worker_metrics_port)
    consumer = KafkaWorkflowConsumer(settings, group_id="ops-copilot-worker")
    logger.info("worker.started", metrics_port=settings.worker_metrics_port)
    try:
        while True:
            processed = False
            for event in consumer.poll():
                processed = True
                logger.info(
                    "worker.event_received",
                    event_type=event.event_type,
                    workflow_id=event.workflow_id,
                    incident_id=event.incident_id,
                )
                if event.event_type not in {"incident.received", "approval.received"}:
                    continue
                if event.workflow_id is None:
                    continue
                with SessionLocal() as session:
                    engine = build_workflow_engine(session)
                    workflow = session.get(
                        __import__("app.infrastructure.db.models", fromlist=["WorkflowRun"]).WorkflowRun,
                        event.workflow_id,
                    )
                    if workflow is None:
                        logger.warning("worker.workflow_missing", workflow_id=event.workflow_id)
                        continue
                    if event.event_type == "incident.received":
                        if workflow.status != "pending":
                            logger.info(
                                "worker.skip_incident",
                                workflow_id=event.workflow_id,
                                status=workflow.status,
                            )
                            continue
                        engine.run_initial(event.workflow_id)
                    elif event.event_type == "approval.received":
                        if event.payload.get("status") != "approved":
                            logger.info(
                                "worker.skip_rejected_approval",
                                workflow_id=event.workflow_id,
                                approval_status=event.payload.get("status"),
                            )
                            continue
                        if workflow.status not in {"running", "waiting_for_approval"}:
                            logger.info(
                                "worker.skip_resume",
                                workflow_id=event.workflow_id,
                                status=workflow.status,
                            )
                            continue
                        engine.run_resume(event.workflow_id)
            if not processed:
                continue
    finally:
        consumer.close()


if __name__ == "__main__":
    main()

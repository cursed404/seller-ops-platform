from __future__ import annotations

from functools import lru_cache

from redis import Redis
from sqlalchemy.orm import Session

from app.application.services.audit import AuditTrailService
from app.application.services.incidents import IncidentService
from app.application.services.queries import OperationsQueryService
from app.application.services.toolbox import Toolbox
from app.application.workflows.engine import WorkflowEngine
from app.infrastructure.llm.base import ChatModel
from app.infrastructure.llm.factory import build_chat_model
from app.infrastructure.messaging.redpanda import KafkaEventPublisher
from app.infrastructure.redis.client import build_redis_client
from app.infrastructure.redis.idempotency import IdempotencyStore
from app.infrastructure.tools.marketplace import MarketplaceGateway
from app.infrastructure.tools.ticketing import TicketGateway
from app.settings import Settings, get_settings


@lru_cache
def get_publisher() -> KafkaEventPublisher:
    return KafkaEventPublisher(get_settings())


@lru_cache
def get_redis() -> Redis:
    return build_redis_client(get_settings())


@lru_cache
def get_idempotency_store() -> IdempotencyStore:
    return IdempotencyStore(get_redis())


@lru_cache
def get_marketplace_gateway() -> MarketplaceGateway:
    return MarketplaceGateway()


@lru_cache
def get_ticket_gateway() -> TicketGateway:
    return TicketGateway()


@lru_cache
def get_chat_provider() -> ChatModel:
    return build_chat_model(get_settings())


def build_query_service(session: Session) -> OperationsQueryService:
    return OperationsQueryService(session)


def build_audit_service(session: Session, publisher: KafkaEventPublisher | None = None) -> AuditTrailService:
    return AuditTrailService(session, publisher or get_publisher())


def build_toolbox(session: Session) -> Toolbox:
    return Toolbox(
        session=session,
        query_service=build_query_service(session),
        audit=build_audit_service(session),
        marketplace_gateway=get_marketplace_gateway(),
        ticket_gateway=get_ticket_gateway(),
        idempotency_store=get_idempotency_store(),
    )


def build_incident_service(session: Session) -> IncidentService:
    queries = build_query_service(session)
    return IncidentService(session=session, audit=build_audit_service(session), queries=queries)


def build_workflow_engine(session: Session) -> WorkflowEngine:
    queries = build_query_service(session)
    audit = build_audit_service(session)
    incidents = IncidentService(session=session, audit=audit, queries=queries)
    toolbox = Toolbox(
        session=session,
        query_service=queries,
        audit=audit,
        marketplace_gateway=get_marketplace_gateway(),
        ticket_gateway=get_ticket_gateway(),
        idempotency_store=get_idempotency_store(),
    )
    return WorkflowEngine(
        session=session,
        audit=audit,
        incidents=incidents,
        queries=queries,
        toolbox=toolbox,
        chat_model=get_chat_provider(),
    )


def get_app_settings() -> Settings:
    return get_settings()

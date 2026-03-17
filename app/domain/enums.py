from enum import StrEnum


class IncidentType(StrEnum):
    ORDER_PROCESSING_DELAY = "order_processing_delay"
    INVENTORY_MISMATCH = "inventory_mismatch"
    PRICE_ANOMALY = "price_anomaly"
    SYNC_FAILURE = "sync_failure"
    DELIVERY_INCONSISTENCY = "delivery_inconsistency"
    CATALOG_CONFLICT = "catalog_conflict"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WorkflowStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING = "waiting"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ActionStatus(StrEnum):
    PENDING = "pending"
    EXECUTED = "executed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ActionType(StrEnum):
    RETRY_SYNC = "retry_sync"
    CREATE_TICKET = "create_ticket"
    REQUEST_RECONCILIATION = "request_reconciliation"
    REQUEST_REPRICING = "request_repricing"
    REVIEW_ORDER = "review_order"


class ToolStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


from abc import ABC, abstractmethod
from typing import Any

from app.domain.schemas import IncidentClassification, ProposedAction, VerificationResult


class ChatModel(ABC):
    @abstractmethod
    def classify_incident(
        self,
        *,
        title: str,
        description: str,
        metadata: dict[str, Any] | None,
    ) -> IncidentClassification:
        raise NotImplementedError

    @abstractmethod
    def plan_action(
        self,
        *,
        incident_type: str,
        severity: str,
        context_summary: dict[str, Any],
        runbooks: list[dict[str, Any]],
    ) -> ProposedAction:
        raise NotImplementedError

    @abstractmethod
    def verify_execution(
        self,
        *,
        incident_type: str,
        action: dict[str, Any],
        execution_result: dict[str, Any],
    ) -> VerificationResult:
        raise NotImplementedError


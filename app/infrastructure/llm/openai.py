from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.domain.schemas import IncidentClassification, ProposedAction, VerificationResult
from app.infrastructure.llm.base import ChatModel


class OpenAIChatModel(ChatModel):
    def __init__(self, *, base_url: str, api_key: str, model: str, timeout_seconds: int) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds

    def _call(self, *, system_prompt: str, user_prompt: str, schema: type[BaseModel]) -> Any:
        payload = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        with httpx.Client(timeout=self._timeout_seconds) as client:
            response = client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        try:
            return schema.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError("OpenAI-compatible provider returned invalid JSON for the expected schema") from exc

    def classify_incident(
        self,
        *,
        title: str,
        description: str,
        metadata: dict[str, Any] | None,
    ) -> IncidentClassification:
        return self._call(
            system_prompt="Classify operational e-commerce incidents into the provided JSON schema.",
            user_prompt=json.dumps({"title": title, "description": description, "metadata": metadata or {}}),
            schema=IncidentClassification,
        )

    def plan_action(
        self,
        *,
        incident_type: str,
        severity: str,
        context_summary: dict[str, Any],
        runbooks: list[dict[str, Any]],
    ) -> ProposedAction:
        return self._call(
            system_prompt="Choose the safest operational action plan and include citations in the provided JSON schema.",
            user_prompt=json.dumps(
                {
                    "incident_type": incident_type,
                    "severity": severity,
                    "context_summary": context_summary,
                    "runbooks": runbooks,
                }
            ),
            schema=ProposedAction,
        )

    def verify_execution(
        self,
        *,
        incident_type: str,
        action: dict[str, Any],
        execution_result: dict[str, Any],
    ) -> VerificationResult:
        return self._call(
            system_prompt="Verify if the workflow outcome is complete and grounded in the result payload.",
            user_prompt=json.dumps(
                {
                    "incident_type": incident_type,
                    "action": action,
                    "execution_result": execution_result,
                }
            ),
            schema=VerificationResult,
        )


from __future__ import annotations

from datetime import UTC, datetime


class TransientToolError(RuntimeError):
    pass


class MarketplaceGateway:
    def retry_sync_job(
        self,
        *,
        sync_job_id: str,
        current_attempts: int,
        failure_code: str | None,
    ) -> dict[str, str]:
        if failure_code == "transient_timeout" and current_attempts < 1:
            raise TransientToolError("Повторная попытка снова уперлась в таймаут со стороны витрины.")
        return {
            "status": "success",
            "sync_job_id": sync_job_id,
            "external_reference": f"sync-{sync_job_id}",
            "completed_at": datetime.now(UTC).isoformat(),
        }

    def request_reconciliation(self, *, sku: str, difference: int) -> dict[str, str | int]:
        return {
            "status": "success",
            "request_id": f"reconcile-{sku}",
            "sku": sku,
            "difference": difference,
        }

    def request_repricing(self, *, sku: str, price: float) -> dict[str, str | float]:
        return {
            "status": "success",
            "request_id": f"reprice-{sku}",
            "sku": sku,
            "approved_price": price,
        }

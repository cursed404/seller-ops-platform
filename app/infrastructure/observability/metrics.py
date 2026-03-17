from time import perf_counter

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

http_requests_total = Counter(
    "http_requests_total",
    "HTTP requests processed by the API.",
    ["method", "path", "status_code"],
)
http_request_latency_seconds = Histogram(
    "http_request_latency_seconds",
    "Latency of HTTP requests.",
    ["method", "path"],
)
workflow_runs_total = Counter(
    "workflow_runs_total",
    "Workflow runs grouped by incident type and final status.",
    ["incident_type", "status"],
)
workflow_duration_seconds = Histogram(
    "workflow_duration_seconds",
    "End-to-end workflow duration in seconds.",
)
approval_wait_seconds = Histogram(
    "approval_wait_seconds",
    "Time spent waiting for human approval.",
)
workflow_retries_total = Counter(
    "workflow_retries_total",
    "Retry attempts by target and outcome.",
    ["target", "outcome"],
)
tool_invocations_total = Counter(
    "tool_invocations_total",
    "Tool invocation outcomes.",
    ["tool", "status"],
)
workflow_errors_total = Counter(
    "workflow_errors_total",
    "Workflow errors by step and error type.",
    ["step", "error_type"],
)


def metrics_response() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


class RequestTimer:
    def __init__(self) -> None:
        self._started_at = perf_counter()

    def observe(self, *, method: str, path: str, status_code: int) -> None:
        duration = perf_counter() - self._started_at
        http_requests_total.labels(method=method, path=path, status_code=str(status_code)).inc()
        http_request_latency_seconds.labels(method=method, path=path).observe(duration)


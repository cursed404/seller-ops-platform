# API

Базовый адрес локально: `http://localhost:8000`

## Технические ручки

### `GET /health`

Просто проверка, что API живое.

Пример ответа:

```json
{
  "status": "ok"
}
```

### `GET /ready`

Проверяет, что доступны:

- Postgres
- Redis
- Kafka producer

### `GET /metrics`

Метрики API в формате Prometheus.

## Инциденты

### `POST /api/v1/incidents`

Создает новый инцидент и процесс обработки.

Пример запроса:

```json
{
  "title": "Обнаружено расхождение остатков по SKU-1042",
  "description": "Остаток на маркетплейсе по SKU-1042 отличается от внутреннего остатка на 17 единиц. Нужно проверить причину и решить, запускать ли сверку.",
  "sku": "SKU-1042",
  "metadata": {
    "source": "inventory-monitor"
  }
}
```

Пример ответа:

```json
{
  "incident_id": "uuid",
  "workflow_id": "uuid"
}
```

### `GET /api/v1/incidents/{incident_id}`

Возвращает сам инцидент и связанный процесс.

## Процессы

### `GET /api/v1/workflows/{workflow_id}`

Главная ручка для просмотра, что вообще происходило.

В ответе есть:

- данные самого процесса
- incident
- шаги
- события
- tool invocations
- action executions
- approval requests

### `GET /api/v1/workflows/{workflow_id}/events`

Только лента событий процесса.

### `POST /api/v1/workflows/{workflow_id}/approve`

Подтверждает или отклоняет рискованное действие.

Пример запроса:

```json
{
  "approved": true,
  "decided_by": "ops-manager",
  "note": "Можно выполнять"
}
```

Пример ответа:

```json
{
  "workflow_id": "uuid",
  "approval_id": "uuid",
  "status": "approved"
}
```

## Ручки с данными

### `GET /api/v1/orders/{order_id}`

Возвращает заказ и его позиции.

### `GET /api/v1/inventory/{sku}`

Возвращает снимки остатков по SKU.

### `GET /api/v1/pricing/{sku}`

Возвращает историю цен по SKU.

### `GET /api/v1/runbooks`

Возвращает регламенты и инструкции из базы.

### `GET /api/v1/tools`

Показывает, какие инструменты использует процесс.

## Примеры событий

### `incident.classified`

```json
{
  "event_type": "incident.classified",
  "payload": {
    "incident_type": "price_anomaly",
    "severity": "high"
  }
}
```

### `approval.required`

```json
{
  "event_type": "approval.required",
  "payload": {
    "requires_approval": true,
    "approval_status": "pending"
  }
}
```

### `workflow.completed`

```json
{
  "event_type": "workflow.completed",
  "payload": {
    "verification": {
      "workflow_status": "completed"
    }
  }
}
```
```

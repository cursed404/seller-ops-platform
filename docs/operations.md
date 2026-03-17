# Операционка

## Как поднять проект

```bash
docker compose up --build -d
make migrate-docker
make seed-docker
```

## Как сбросить все заново

```bash
docker compose down -v
docker compose up --build -d
make migrate-docker
make seed-docker
```

## Как прогнать демо

```bash
make demo-docker
```

## Как смотреть логи

```bash
make logs
docker compose logs -f postgres redpanda
```

## Как смотреть метрики

- API: `http://localhost:8000/metrics`
- Worker: `http://localhost:9100`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

## Как посмотреть Kafka-события

```bash
docker compose exec redpanda rpk topic consume operations.events --brokers=redpanda:9092
```

## Как вручную отправить инцидент

```bash
curl -X POST http://localhost:8000/api/v1/incidents \
  -H "Content-Type: application/json" \
  --data @examples/incidents/inventory_mismatch.json
```

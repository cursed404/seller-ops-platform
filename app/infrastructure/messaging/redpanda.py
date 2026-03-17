from __future__ import annotations

import json
from collections.abc import Iterator

from kafka import KafkaConsumer, KafkaProducer

from app.domain.events import EventEnvelope
from app.settings import Settings


class KafkaEventPublisher:
    def __init__(self, settings: Settings) -> None:
        self._topic = settings.kafka_topic
        self._producer = KafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda payload: json.dumps(payload).encode("utf-8"),
        )

    def publish(self, event: EventEnvelope) -> None:
        self._producer.send(self._topic, value=event.model_dump(mode="json"))
        self._producer.flush(timeout=5)

    def is_connected(self) -> bool:
        return self._producer.bootstrap_connected()

    def close(self) -> None:
        self._producer.close()


class KafkaWorkflowConsumer:
    def __init__(self, settings: Settings, group_id: str) -> None:
        self._consumer = KafkaConsumer(
            settings.kafka_topic,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            consumer_timeout_ms=1000,
            value_deserializer=lambda payload: json.loads(payload.decode("utf-8")),
        )

    def poll(self) -> Iterator[EventEnvelope]:
        for message in self._consumer:
            yield EventEnvelope.model_validate(message.value)

    def close(self) -> None:
        self._consumer.close()

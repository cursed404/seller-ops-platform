from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.db.base import Base
from app.infrastructure.db.session import get_session
from app.main import app
from seed.demo_data import seed_demo


class FakePublisher:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def publish(self, event) -> None:
        self.events.append(event.model_dump(mode="json"))

    def is_connected(self) -> bool:
        return True


class FakeIdempotencyStore:
    def __init__(self) -> None:
        self._keys: set[str] = set()

    def acquire(self, key: str, ttl_seconds: int = 3600) -> bool:
        if key in self._keys:
            return False
        self._keys.add(key)
        return True


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session_local() as session:
        seed_demo(session)
        yield session


@pytest.fixture
def fake_publisher() -> FakePublisher:
    return FakePublisher()


@pytest.fixture
def fake_idempotency() -> FakeIdempotencyStore:
    return FakeIdempotencyStore()


@pytest.fixture
def client(
    db_session: Session,
    fake_publisher: FakePublisher,
    fake_idempotency: FakeIdempotencyStore,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    def override_get_session() -> Generator[Session, None, None]:
        yield db_session

    monkeypatch.setattr("app.dependencies.get_publisher", lambda: fake_publisher)
    monkeypatch.setattr("app.dependencies.get_idempotency_store", lambda: fake_idempotency)
    monkeypatch.setattr("app.api.endpoints.health.get_publisher", lambda: fake_publisher)

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

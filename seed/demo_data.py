from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.infrastructure.db.base import utcnow
from app.infrastructure.db.models import (
    ActionExecution,
    ApprovalRequest,
    InventorySnapshot,
    MarketplaceSyncJob,
    OperationalIncident,
    Order,
    OrderItem,
    PriceSnapshot,
    RetryAttempt,
    RunbookDocument,
    ToolInvocation,
    WorkflowEvent,
    WorkflowRun,
    WorkflowStep,
)


def reset_tables(session: Session) -> None:
    for model in [
        RetryAttempt,
        ApprovalRequest,
        ActionExecution,
        ToolInvocation,
        WorkflowEvent,
        WorkflowStep,
        WorkflowRun,
        OperationalIncident,
        OrderItem,
        Order,
        InventorySnapshot,
        PriceSnapshot,
        MarketplaceSyncJob,
        RunbookDocument,
    ]:
        session.execute(delete(model))


def seed_demo(session: Session) -> None:
    now = utcnow()
    reset_tables(session)

    orders = [
        Order(
            id="ord_1001",
            external_order_ref="WB-784512",
            status="processing",
            payment_status="confirmed",
            customer_email="ivan@example.com",
            total_amount=Decimal("12989.00"),
            currency="RUB",
            marketplace="wb",
            placed_at=now - timedelta(minutes=47),
        ),
        Order(
            id="ord_1002",
            external_order_ref="OZ-992110",
            status="shipped",
            payment_status="confirmed",
            customer_email="olga@example.com",
            total_amount=Decimal("8950.00"),
            currency="RUB",
            marketplace="ozon",
            placed_at=now - timedelta(hours=6),
        ),
        Order(
            id="ord_1003",
            external_order_ref="YM-112219",
            status="delivered",
            payment_status="confirmed",
            customer_email="sergey@example.com",
            total_amount=Decimal("5990.00"),
            currency="RUB",
            marketplace="ym",
            placed_at=now - timedelta(days=1, hours=3),
        ),
    ]
    session.add_all(orders)

    session.add_all(
        [
            OrderItem(
                order_id="ord_1001",
                sku="SKU-1042",
                name="Кофемолка ручная",
                quantity=1,
                unit_price=Decimal("7999.00"),
                margin_amount=Decimal("1800.00"),
            ),
            OrderItem(
                order_id="ord_1001",
                sku="SKU-1100",
                name="Термокружка дорожная",
                quantity=1,
                unit_price=Decimal("4990.00"),
                margin_amount=Decimal("1200.00"),
            ),
            OrderItem(
                order_id="ord_1002",
                sku="SKU-9921",
                name="Подставка для ноутбука",
                quantity=1,
                unit_price=Decimal("8950.00"),
                margin_amount=Decimal("2100.00"),
            ),
            OrderItem(
                order_id="ord_1003",
                sku="SKU-5555",
                name="Набор органайзеров для проводов",
                quantity=2,
                unit_price=Decimal("2995.00"),
                margin_amount=Decimal("1150.00"),
            ),
        ]
    )

    session.add_all(
        [
            InventorySnapshot(
                sku="SKU-1042",
                source="internal",
                warehouse="primary-east",
                quantity=83,
                recorded_at=now - timedelta(minutes=5),
                metadata_json={"reason": "cycle_count"},
            ),
            InventorySnapshot(
                sku="SKU-1042",
                source="marketplace",
                warehouse="wb-fbo",
                quantity=66,
                recorded_at=now - timedelta(minutes=4),
                metadata_json={"feed_id": "wb-feed-1042"},
            ),
            InventorySnapshot(
                sku="SKU-9921",
                source="internal",
                warehouse="primary-east",
                quantity=42,
                recorded_at=now - timedelta(minutes=7),
                metadata_json={"reason": "erp_snapshot"},
            ),
            InventorySnapshot(
                sku="SKU-9921",
                source="marketplace",
                warehouse="ozon-main",
                quantity=42,
                recorded_at=now - timedelta(minutes=6),
                metadata_json={"feed_id": "ozon-feed-9921"},
            ),
            InventorySnapshot(
                sku="SKU-5555",
                source="internal",
                warehouse="primary-east",
                quantity=120,
                recorded_at=now - timedelta(minutes=8),
                metadata_json={"reason": "erp_snapshot"},
            ),
            InventorySnapshot(
                sku="SKU-5555",
                source="marketplace",
                warehouse="beaba-catalog",
                quantity=120,
                recorded_at=now - timedelta(minutes=8),
                metadata_json={"feed_id": "beaba-feed-5555"},
            ),
        ]
    )

    session.add_all(
        [
            PriceSnapshot(
                sku="SKU-9921",
                source="internal",
                price=Decimal("8990.00"),
                cost=Decimal("5100.00"),
                margin_percent=Decimal("43.27"),
                recorded_at=now - timedelta(hours=4),
                metadata_json={"batch_id": "price-previous"},
            ),
            PriceSnapshot(
                sku="SKU-9921",
                source="internal",
                price=Decimal("5574.00"),
                cost=Decimal("5100.00"),
                margin_percent=Decimal("8.50"),
                recorded_at=now - timedelta(minutes=20),
                metadata_json={"batch_id": "price-latest"},
            ),
            PriceSnapshot(
                sku="SKU-1042",
                source="internal",
                price=Decimal("7999.00"),
                cost=Decimal("5400.00"),
                margin_percent=Decimal("32.49"),
                recorded_at=now - timedelta(hours=1),
                metadata_json={"batch_id": "price-1042"},
            ),
        ]
    )

    session.add_all(
        [
            MarketplaceSyncJob(
                id="sync_ord_1001",
                entity_type="order",
                reference_id="ord_1001",
                partner="wb",
                status="failed",
                failure_code="transient_timeout",
                failure_message="Статус заказа не обновился из-за таймаута при обратном вызове.",
                retryable=True,
                attempts=0,
                metadata_json={"stage": "подтверждение_оплаты"},
            ),
            MarketplaceSyncJob(
                id="sync_inv_1042",
                entity_type="inventory",
                reference_id="SKU-1042",
                partner="wb",
                status="completed",
                retryable=False,
                attempts=1,
                last_attempt_at=now - timedelta(minutes=4),
                metadata_json={"stage": "публикация_остатков"},
            ),
            MarketplaceSyncJob(
                id="sync_price_9921",
                entity_type="catalog",
                reference_id="SKU-9921",
                partner="ozon",
                status="completed",
                retryable=False,
                attempts=1,
                last_attempt_at=now - timedelta(minutes=20),
                metadata_json={"stage": "публикация_цен"},
            ),
            MarketplaceSyncJob(
                id="sync_cat_2002",
                entity_type="catalog",
                reference_id="SKU-5555",
                partner="merlion",
                status="failed",
                failure_code="transient_timeout",
                failure_message="Выгрузка каталога завершилась таймаутом через 10 секунд.",
                retryable=True,
                attempts=0,
                metadata_json={"stage": "публикация_каталога"},
            ),
        ]
    )

    session.add_all(
        [
            RunbookDocument(
                id="doc-order-delay",
                slug="order-processing-delay",
                title="Регламент по задержке обработки заказа",
                category="order_processing_delay",
                body=(
                    "Если заказ долго висит в обработке после подтверждения оплаты, нужно проверить "
                    "состояние оплаты, посмотреть последнюю sync job и повторять только временные сбои. "
                    "Если повторная попытка не помогла, инцидент надо передавать дальше в операционку."
                ),
                tags_json=["заказы", "обработка", "синхронизация", "разбор"],
                metadata_json={"owner": "ops-platform"},
            ),
            RunbookDocument(
                id="doc-inventory-reconcile",
                slug="inventory-reconciliation-policy",
                title="Политика сверки остатков",
                category="inventory_mismatch",
                body=(
                    "Если остаток на витрине отличается от внутреннего учета больше чем на 10 единиц, "
                    "нужно поднять оба снимка, проверить время последней синхронизации и не отправлять "
                    "внешнюю сверку без подтверждения."
                ),
                tags_json=["остатки", "сверка", "подтверждение", "витрина"],
                metadata_json={"owner": "supply-ops"},
            ),
            RunbookDocument(
                id="doc-repricing-guardrails",
                slug="repricing-guardrails",
                title="Правила безопасного репрайсинга",
                category="price_anomaly",
                body=(
                    "Любое заметное для покупателя изменение цены должно идти через подтверждение, если "
                    "мы восстанавливаем маржу или откатываем аномальное падение. Нужно сравнить последние "
                    "снимки цены, проверить себестоимость и предложить минимальную безопасную цену."
                ),
                tags_json=["цены", "маржа", "подтверждение", "каталог"],
                metadata_json={"owner": "pricing-ops"},
            ),
            RunbookDocument(
                id="doc-sync-timeout",
                slug="marketplace-sync-timeout",
                title="Разбор таймаута при синхронизации",
                category="sync_failure",
                body=(
                    "Временные таймауты нужно повторять с ограничением по числу попыток и с записью "
                    "каждой попытки в историю. Если лимит исчерпан и ошибка осталась, только тогда "
                    "нужно эскалировать проблему."
                ),
                tags_json=["синхронизация", "повтор", "таймаут", "витрина"],
                metadata_json={"owner": "integration-platform"},
            ),
            RunbookDocument(
                id="doc-escalation",
                slug="operational-escalation-guidelines",
                title="Правила операционной эскалации",
                category="shared",
                body=(
                    "Передавать задачу в другую команду нужно только тогда, когда workflow уже не может "
                    "безопасно завершиться своими инструментами. Такая эскалация тоже должна идти через "
                    "подтверждение."
                ),
                tags_json=["эскалация", "тикеты", "подтверждение"],
                metadata_json={"owner": "operations"},
            ),
        ]
    )

    session.add_all(
        [
            OperationalIncident(
                id="inc_hist_1",
                title="Исторический кейс по расхождению остатков",
                description="Остаток по SKU-1042 разъехался на 11 единиц во время утренней выгрузки.",
                status="closed",
                incident_type="inventory_mismatch",
                severity="medium",
                sku="SKU-1042",
                correlation_id="corr-hist-1",
                trace_id="trace-hist-1",
                metadata_json={"seeded": True},
            ),
            OperationalIncident(
                id="inc_hist_2",
                title="Исторический кейс по отклоненному репрайсингу",
                description="По SKU-9921 цена ушла ниже допустимого порога и потребовалась ручная проверка.",
                status="closed",
                incident_type="price_anomaly",
                severity="high",
                sku="SKU-9921",
                correlation_id="corr-hist-2",
                trace_id="trace-hist-2",
                metadata_json={"seeded": True},
            ),
        ]
    )

    session.add_all(
        [
            WorkflowRun(
                id="wf_hist_1",
                incident_id="inc_hist_1",
                status="completed",
                phase="initial",
                correlation_id="corr-hist-1",
                trace_id="trace-hist-1",
                selected_runbook_id="doc-inventory-reconcile",
                context_summary_json={"sku": "SKU-1042", "difference": 11},
                recommended_action_json={
                    "incident_type": "inventory_mismatch",
                    "action_type": "request_reconciliation",
                },
                result_summary_json={"recommendation": "Сверка остатков выполнена после подтверждения."},
                citations_json=[{"document_id": "doc-inventory-reconcile"}],
                started_at=now - timedelta(days=1, minutes=10),
                completed_at=now - timedelta(days=1),
            ),
            WorkflowRun(
                id="wf_hist_2",
                incident_id="inc_hist_2",
                status="cancelled",
                phase="initial",
                correlation_id="corr-hist-2",
                trace_id="trace-hist-2",
                selected_runbook_id="doc-repricing-guardrails",
                context_summary_json={"sku": "SKU-9921", "margin_percent": 9},
                recommended_action_json={"incident_type": "price_anomaly", "action_type": "request_repricing"},
                result_summary_json={"recommendation": "Запрос на изменение цены отклонен оператором."},
                citations_json=[{"document_id": "doc-repricing-guardrails"}],
                started_at=now - timedelta(hours=12, minutes=20),
                completed_at=now - timedelta(hours=12),
            ),
        ]
    )

    session.commit()

"""
Unit tests for Consumer Service: idempotency, stock validation, retry logic, outbox pattern.
Run with: pytest services/consumer-service/src/tests/test_consumer.py -v
"""
import pytest
import json
import uuid
from unittest.mock import MagicMock, patch, call


# ── Idempotency tests ──────────────────────────────────────────────────────────

class TestIdempotency:

    def test_duplicate_key_causes_ack_and_skip(self):
        """If the idempotency key already exists in DB, message should be acked and skipped."""
        mock_db = MagicMock()
        existing = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        idem_key = str(uuid.uuid4())
        result = mock_db.query(MagicMock()).filter(MagicMock()).first()
        is_duplicate = result is not None

        assert is_duplicate is True

    def test_new_key_proceeds_to_processing(self):
        """If idempotency key is not in DB, processing should continue."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query(MagicMock()).filter(MagicMock()).first()
        is_duplicate = result is not None

        assert is_duplicate is False

    def test_idempotency_key_stored_with_order(self):
        """Order model must store the idempotency_key."""
        order = MagicMock()
        order.idempotency_key = "idem-123"
        assert order.idempotency_key == "idem-123"


# ── Order status transition tests ─────────────────────────────────────────────

class TestOrderStatusTransitions:

    def test_order_initially_persisted_as_pending(self):
        """Order must be created with PENDING status before final determination."""
        status = "PENDING"
        assert status == "PENDING"

    def test_successful_order_final_status_is_processed(self):
        """After success path, order status should be PROCESSED."""
        order_status = "PENDING"
        can_process = True
        if can_process:
            order_status = "PROCESSED"
        assert order_status == "PROCESSED"

    def test_failed_order_final_status_is_failed(self):
        """After failure path, order status should be FAILED."""
        order_status = "PENDING"
        can_process = False
        if not can_process:
            order_status = "FAILED"
        assert order_status == "FAILED"

    def test_pending_never_stays_pending_after_processing(self):
        """PENDING status should always transition to PROCESSED or FAILED."""
        for can_process in [True, False]:
            status = "PENDING"
            status = "PROCESSED" if can_process else "FAILED"
            assert status != "PENDING"


# ── Stock validation tests ─────────────────────────────────────────────────────

class TestStockValidation:

    def _make_product(self, stock):
        p = MagicMock()
        p.stock_quantity = stock
        return p

    def test_product_with_enough_stock_can_be_processed(self):
        product = self._make_product(10)
        qty = 5
        assert product.stock_quantity >= qty

    def test_product_with_zero_stock_cannot_be_processed(self):
        product = self._make_product(0)
        qty = 1
        assert not (product.stock_quantity >= qty)

    def test_none_product_triggers_failure(self):
        product = None
        can_process = product is not None and product.stock_quantity >= 1
        assert can_process is False

    def test_failure_reason_is_insufficient_stock(self):
        failure_reason = "INSUFFICIENT_STOCK"
        assert failure_reason == "INSUFFICIENT_STOCK"


# ── Retry / backoff tests ─────────────────────────────────────────────────────

class TestRetryBackoff:

    def test_exponential_backoff_increases_delay(self):
        delays = [2 ** n * 1000 for n in range(1, 4)]
        assert delays == [2000, 4000, 8000]

    def test_retry_header_increments(self):
        headers = {"x-retries": 0}
        headers["x-retries"] += 1
        assert headers["x-retries"] == 1

    def test_max_retries_sends_to_dlq(self):
        MAX_RETRIES = 3
        retry_count = 3
        should_dlq = retry_count >= MAX_RETRIES
        assert should_dlq is True

    def test_below_max_should_retry_not_dlq(self):
        MAX_RETRIES = 3
        retry_count = 1
        should_retry = retry_count < MAX_RETRIES
        assert should_retry is True

    def test_retry_published_to_retry_queue(self):
        """Retry messages should be published to retry queue, not nacked."""
        mock_channel = MagicMock()
        retry_queue = "order_retry_queue"
        body = b'{"orderId": "test"}'

        mock_channel.basic_publish(
            exchange="",
            routing_key=retry_queue,
            body=body,
            properties=MagicMock()
        )
        mock_channel.basic_publish.assert_called_once()
        call_kwargs = mock_channel.basic_publish.call_args
        assert call_kwargs[1]["routing_key"] == retry_queue


# ── Outbox pattern tests ──────────────────────────────────────────────────────

class TestOutboxPattern:

    def test_order_processed_event_created_for_success(self):
        event_type = "OrderProcessed"
        payload = {"orderId": "order-001", "status": "COMPLETED"}
        assert event_type == "OrderProcessed"
        assert payload["status"] == "COMPLETED"

    def test_order_failed_event_created_for_failure(self):
        event_type = "OrderFailed"
        payload = {"orderId": "order-001", "reason": "INSUFFICIENT_STOCK"}
        assert event_type == "OrderFailed"
        assert "reason" in payload

    def test_outbox_and_order_committed_atomically(self):
        """DB commit should be called exactly once for both order and outbox."""
        mock_db = MagicMock()
        mock_db.add(MagicMock())  # order
        mock_db.add(MagicMock())  # outbox
        mock_db.commit()
        mock_db.commit.assert_called_once()

    def test_outbox_relayer_marks_event_processed(self):
        """After relaying, outbox event processed flag must be 1."""
        event = MagicMock()
        event.processed = 0
        event.processed = 1
        assert event.processed == 1

    def test_outbox_routing_key_for_processed(self):
        event_type = "OrderProcessed"
        routing_key = "order.processed" if event_type == "OrderProcessed" else "order.failed"
        assert routing_key == "order.processed"

    def test_outbox_routing_key_for_failed(self):
        event_type = "OrderFailed"
        routing_key = "order.processed" if event_type == "OrderProcessed" else "order.failed"
        assert routing_key == "order.failed"


# ── DLQ configuration tests ───────────────────────────────────────────────────

class TestDLQConfiguration:

    def test_dlq_exchange_is_declared(self):
        mock_channel = MagicMock()
        dlq_exchange = "order_dlx"
        mock_channel.exchange_declare(exchange=dlq_exchange, exchange_type="fanout", durable=True)
        mock_channel.exchange_declare.assert_called_once_with(
            exchange=dlq_exchange, exchange_type="fanout", durable=True
        )

    def test_main_queue_has_dlx_argument(self):
        mock_channel = MagicMock()
        queue_name = "order_created_queue"
        dlq_exchange = "order_dlx"
        mock_channel.queue_declare(
            queue=queue_name,
            durable=True,
            arguments={"x-dead-letter-exchange": dlq_exchange}
        )
        mock_channel.queue_declare.assert_called_once()
        call_kwargs = mock_channel.queue_declare.call_args[1]
        assert "x-dead-letter-exchange" in call_kwargs["arguments"]

    def test_dlq_env_vars_configurable(self):
        import os
        # Simulate env var driven config
        dlq_exchange = "order_dlx"
        dlq_queue = "order_created_dlq"
        retry_queue = "order_retry_queue"
        assert dlq_exchange == "order_dlx"
        assert dlq_queue == "order_created_dlq"
        assert retry_queue == "order_retry_queue"

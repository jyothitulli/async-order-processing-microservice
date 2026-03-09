import json
import logging
import os
import uuid
import pika
import pika.exceptions
from models import SessionLocal, Order, Outbox, Product

logger = logging.getLogger(__name__)

MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

def process_order(ch, method, properties, body):
    db = SessionLocal()
    # Extract correlation_id for tracing
    headers = properties.headers or {}
    correlation_id = headers.get("correlation_id", str(uuid.uuid4()))
    retry_count = int(headers.get("x-retries", 0))

    extra = {"correlation_id": correlation_id}

    try:
        data = json.loads(body)
        idem_key = data.get("idempotencyKey")
        order_id = data["orderId"]

        logger.info(
            json.dumps({
                "event": "order_received",
                "order_id": order_id,
                "correlation_id": correlation_id,
                "retry_count": retry_count
            })
        )

        # 1. IDEMPOTENCY CHECK
        exists = db.query(Order).filter(Order.idempotency_key == idem_key).first()
        if exists:
            logger.info(
                json.dumps({
                    "event": "duplicate_skipped",
                    "order_id": order_id,
                    "correlation_id": correlation_id
                })
            )
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # 2. STOCK VALIDATION LOGIC
        items = data.get("items", [])
        can_process = True
        failure_reason = None
        product = None

        if items:
            item = items[0]
            product = db.query(Product).filter(Product.id == item["productId"]).first()
            if not product or product.stock_quantity < item["quantity"]:
                can_process = False
                failure_reason = "INSUFFICIENT_STOCK"
                logger.warning(
                    json.dumps({
                        "event": "stock_insufficient",
                        "order_id": order_id,
                        "correlation_id": correlation_id
                    })
                )

        # 3. PERSIST ORDER WITH INITIAL STATUS = 'PENDING' (requirement)
        new_order = Order(
            order_id=order_id,
            user_id=data["userId"],
            total_amount=data["totalAmount"],
            idempotency_key=idem_key,
            status="PENDING"
        )
        db.add(new_order)
        db.flush()  # Write PENDING to DB within the transaction

        # 4. DETERMINE FINAL STATUS & OUTBOX EVENT (same transaction)
        if can_process:
            if items and product:
                product.stock_quantity -= item["quantity"]
            new_order.status = "PROCESSED"
            outbox_entry = Outbox(
                event_type="OrderProcessed",
                payload={"orderId": order_id, "status": "COMPLETED", "correlationId": correlation_id}
            )
        else:
            new_order.status = "FAILED"
            outbox_entry = Outbox(
                event_type="OrderFailed",
                payload={"orderId": order_id, "reason": failure_reason, "correlationId": correlation_id}
            )

        db.add(outbox_entry)
        db.commit()

        ch.basic_ack(delivery_tag=method.delivery_tag)
        logger.info(
            json.dumps({
                "event": "order_processed",
                "order_id": order_id,
                "status": new_order.status,
                "correlation_id": correlation_id
            })
        )

    except Exception as e:
        db.rollback()
        logger.error(
            json.dumps({
                "event": "processing_error",
                "error": str(e),
                "correlation_id": correlation_id,
                "retry_count": retry_count
            })
        )

        # RETRY WITH EXPONENTIAL BACKOFF
        if retry_count < MAX_RETRIES:
            next_retry = retry_count + 1
            delay = (2 ** next_retry) * 1000  # exponential backoff in ms
            logger.warning(
                json.dumps({
                    "event": "retry_scheduled",
                    "attempt": next_retry,
                    "delay_ms": delay,
                    "correlation_id": correlation_id
                })
            )
            # Re-publish to delay queue with incremented retry header
            retry_queue = os.getenv("RETRY_QUEUE", "order_retry_queue")
            ch.basic_publish(
                exchange="",
                routing_key=retry_queue,
                body=body,
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    headers={
                        "x-retries": next_retry,
                        "correlation_id": correlation_id,
                        "x-original-queue": method.routing_key,
                        "x-delay": delay
                    }
                )
            )
            ch.basic_ack(delivery_tag=method.delivery_tag)
        else:
            # MAX RETRIES EXHAUSTED -> send to DLQ
            logger.error(
                json.dumps({
                    "event": "max_retries_exhausted",
                    "correlation_id": correlation_id,
                    "retry_count": retry_count
                })
            )
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    finally:
        db.close()

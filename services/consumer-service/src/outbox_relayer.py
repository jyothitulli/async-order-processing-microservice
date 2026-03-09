import time
import json
import logging
import pika
import os
from models import SessionLocal, Outbox

# Structured JSON logging
class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        })

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger("outbox-relayer")


def run_relayer():
    mq_host = os.getenv("MQ_HOST", "rabbitmq")

    # Retry RabbitMQ connection
    connection = None
    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=mq_host))
            break
        except pika.exceptions.AMQPConnectionError:
            logger.warning(json.dumps({"event": "rabbitmq_not_ready", "attempt": i + 1}))
            time.sleep(5)

    if not connection:
        logger.error(json.dumps({"event": "rabbitmq_connection_failed"}))
        return

    channel = connection.channel()
    channel.exchange_declare(exchange="order_events", exchange_type="topic", durable=True)
    logger.info(json.dumps({"event": "relayer_started"}))

    while True:
        db = SessionLocal()
        try:
            events = db.query(Outbox).filter(Outbox.processed == 0).limit(10).all()

            for event in events:
                routing_key = "order.processed" if event.event_type == "OrderProcessed" else "order.failed"
                payload = event.payload if isinstance(event.payload, dict) else json.loads(event.payload)
                correlation_id = payload.get("correlationId", "")

                channel.basic_publish(
                    exchange="order_events",
                    routing_key=routing_key,
                    body=json.dumps(payload),
                    properties=pika.BasicProperties(
                        delivery_mode=2,
                        headers={"correlation_id": correlation_id}
                    )
                )
                event.processed = 1
                db.commit()
                logger.info(json.dumps({
                    "event": "outbox_event_relayed",
                    "outbox_id": event.id,
                    "event_type": event.event_type,
                    "correlation_id": correlation_id
                }))

        except Exception as e:
            logger.error(json.dumps({"event": "relayer_error", "error": str(e)}))
            db.rollback()
        finally:
            db.close()

        time.sleep(5)


if __name__ == "__main__":
    run_relayer()

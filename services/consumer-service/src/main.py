import time
import json
import pika
import logging
import os
from order_consumer import process_order

# Structured JSON logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("consumer-service")

def connect_to_rabbitmq():
    mq_host = os.getenv("MQ_HOST", "rabbitmq")
    queue_name = os.getenv("INCOMING_ORDER_QUEUE", "order_created_queue")
    dlq_exchange = os.getenv("DLQ_EXCHANGE", "order_dlx")
    dlq_queue = os.getenv("DLQ_QUEUE", "order_created_dlq")
    retry_queue = os.getenv("RETRY_QUEUE", "order_retry_queue")

    for i in range(10):
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=mq_host, heartbeat=600)
            )
            channel = connection.channel()

            # --- Dead-Letter Exchange & Queue ---
            channel.exchange_declare(exchange=dlq_exchange, exchange_type="fanout", durable=True)
            channel.queue_declare(queue=dlq_queue, durable=True)
            channel.queue_bind(exchange=dlq_exchange, queue=dlq_queue)

            # --- Retry queue (messages re-published here before re-delivery) ---
            channel.queue_declare(queue=retry_queue, durable=True)

            # --- Main queue wired to DLX ---
            channel.queue_declare(
                queue=queue_name,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": dlq_exchange,
                    "x-dead-letter-routing-key": queue_name
                }
            )

            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=queue_name, on_message_callback=process_order)

            logger.info(json.dumps({
                "event": "consumer_started",
                "queue": queue_name,
                "dlq": dlq_queue,
                "retry_queue": retry_queue
            }))
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError:
            logger.warning(json.dumps({
                "event": "rabbitmq_not_ready",
                "attempt": i + 1
            }))
            time.sleep(5)
        except Exception as e:
            logger.error(json.dumps({"event": "unexpected_error", "error": str(e)}))
            break

if __name__ == "__main__":
    connect_to_rabbitmq()

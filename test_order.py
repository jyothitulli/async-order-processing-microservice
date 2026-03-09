import pika
import json
import uuid

# Connection to RabbitMQ
connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()

# Must match the DLQ arguments used by consumer-service
channel.queue_declare(
    queue='order_created_queue',
    durable=True,
    arguments={
        'x-dead-letter-exchange': 'order_dlx',
        'x-dead-letter-routing-key': 'order_created_queue'
    }
)

order_id = str(uuid.uuid4())
order_event = {
    "orderId": order_id,
    "userId": "user-123",
    "items": [
        {"productId": "prod-101", "quantity": 1}
    ],
    "totalAmount": 1200.0,
    "idempotencyKey": str(uuid.uuid4())
}

channel.basic_publish(
    exchange='',
    routing_key='order_created_queue',
    body=json.dumps(order_event),
    properties=pika.BasicProperties(delivery_mode=2)
)

print(f" [x] Sent Order Event: {order_id}")
connection.close()

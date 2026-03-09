# Questionnaire Responses – Asynchronous Order Processing Microservice

---

## Type A – Implementation Questions (past tense, specific file/function references)

### Q1: How did you implement the Transactional Outbox pattern?

I implemented the Transactional Outbox pattern in `services/consumer-service/src/order_consumer.py` inside the `process_order` function. After the idempotency check and stock validation, I opened a single SQLAlchemy transaction, created the `Order` record first with an initial status of `PENDING` using `db.flush()`, determined the final outcome (PROCESSED or FAILED), updated the order status, and inserted an `Outbox` record (either `OrderProcessed` or `OrderFailed`) — all before calling `db.commit()`. This ensured atomicity: either both the order and its outbox event were persisted together, or neither was, preventing ghost events or missing events.

The outbox records are picked up by a separate service (`services/consumer-service/src/outbox_relayer.py`) that polls `SELECT * FROM outbox WHERE processed = 0 LIMIT 10` every 5 seconds and publishes them to the `order_events` RabbitMQ topic exchange, then marks each record `processed = 1`.

### Q2: How did you implement idempotency?

I implemented idempotency at two levels. First, in `sql/init.sql`, the `orders` table has `idempotency_key VARCHAR(255) UNIQUE NOT NULL`, which creates a database-level unique constraint. Second, at the application level in `services/consumer-service/src/order_consumer.py:process_order`, before any processing I queried `db.query(Order).filter(Order.idempotency_key == idem_key).first()`. If a record was found, I immediately called `ch.basic_ack` and returned, skipping all processing. This prevents duplicate order creation even if a message is delivered more than once.

### Q3: How did you implement the retry mechanism with exponential backoff?

I implemented retry logic in `services/consumer-service/src/order_consumer.py:process_order` inside the `except` block. I read the `x-retries` header from `properties.headers` (defaulting to 0). If `retry_count < MAX_RETRIES` (configured via the `MAX_RETRIES` environment variable, default 3), I calculated the delay as `2 ** next_retry * 1000` milliseconds and re-published the original message body to `order_retry_queue` with an updated `x-retries` header, then acknowledged the original message. If `retry_count >= MAX_RETRIES`, I called `ch.basic_nack(requeue=False)` to route the message to the Dead-Letter Queue.

### Q4: How did you configure the Dead-Letter Queue?

I configured the DLQ in `services/consumer-service/src/main.py:connect_to_rabbitmq`. I declared a `fanout` exchange named `order_dlx` (configurable via `DLQ_EXCHANGE` env var) and a durable queue named `order_created_dlq` (configurable via `DLQ_QUEUE`), then bound the queue to the exchange. When declaring the main `order_created_queue`, I passed `arguments={"x-dead-letter-exchange": dlq_exchange}` so that any message nacked with `requeue=False` is automatically routed to `order_created_dlq` for later inspection and manual reprocessing.

### Q5: How did you implement health checks?

In `services/api-service/src/main.py`, the `GET /health` endpoint performs two real checks. For the database, it executes `db.execute(text("SELECT 1"))` and catches any exception, reporting `database: DOWN: <error>` if it fails. For RabbitMQ, it attempts `pika.BlockingConnection(pika.ConnectionParameters(...))` and catches `pika.exceptions.AMQPConnectionError`, reporting `rabbitmq: DOWN: <error>`. The overall `status` is `UP` only when both checks pass; otherwise it returns HTTP 503.

### Q6: How did you implement structured logging and correlation IDs?

I implemented a `JsonFormatter` class in both `services/api-service/src/main.py` and `services/consumer-service/src/outbox_relayer.py` that overrides `logging.Formatter.format()` to return `json.dumps({...})` for every log record. In `services/api-service/src/main.py`, the HTTP middleware extracts `X-Correlation-ID` from the request header (or generates a new UUID4 if absent) and attaches it to `request.state.correlation_id`, also echoing it back in the response header. In `services/consumer-service/src/order_consumer.py`, the `correlation_id` is read from `properties.headers` (or generated fresh) and included in every `logger.info/warning/error` call as a JSON field, ensuring full end-to-end traceability.

---

## Type B – Hypothetical / Scaling Questions (conditional tense)

### Q7: How would you scale this system to handle 10× the current load?

To handle 10× load, I would horizontally scale the consumer service by increasing the number of replicas in `docker-compose.yml` (or a Kubernetes Deployment). Each consumer instance would compete for messages on `order_created_queue`, naturally distributing load. I would also increase `prefetch_count` per consumer to allow batching. For the database, I would introduce read replicas and consider partitioning the `orders` table by `created_at`. The outbox relayer could be parallelized by sharding the outbox table or adding a distributed lock (e.g., using MySQL `GET_LOCK`) to prevent multiple relayers from publishing the same event.

### Q8: How would you improve the retry mechanism in production?

In production, instead of re-publishing to a plain `order_retry_queue`, I would use the **RabbitMQ Delayed Message Exchange plugin** (`x-delayed-message`) to enforce true time-delayed redelivery. This would prevent the retry queue from being consumed immediately and allows the delay to match the exponential formula precisely. I would also add a `x-first-death-queue` header inspection in the DLQ consumer to surface actionable alerts (e.g., PagerDuty notification) when messages exceed the retry threshold.

### Q9: How would you add schema validation for incoming events?

I would introduce a **JSON Schema** or **Pydantic model** for the `OrderCreated` event payload. In `services/consumer-service/src/order_consumer.py`, before processing, I would validate `data` against the schema using `pydantic.BaseModel.model_validate(data)`. Invalid schema messages would be immediately nacked with `requeue=False` (no retries, since retrying a malformed message is pointless) and routed to a separate `schema_error_dlq` for developer inspection. I would also consider a schema registry (e.g., Confluent Schema Registry) if migrating to Kafka in the future.

### Q10: How would you add end-to-end distributed tracing?

I would integrate **OpenTelemetry** across both services. Each service would initialize an OTLP exporter pointing to a Jaeger or Zipkin collector. The API service middleware would create a root `Span` for each HTTP request, injecting the `traceparent` header into RabbitMQ message properties. The consumer service would extract the trace context from `properties.headers` and create a child span for `process_order`. The outbox relayer would similarly propagate the trace context. This would give full end-to-end visibility from HTTP request → queue message → DB write → outbox relay in a single trace.


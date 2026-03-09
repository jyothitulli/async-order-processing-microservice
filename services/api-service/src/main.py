import logging
import json
import os
import uuid
import pika
import pika.exceptions
from fastapi import FastAPI, Request, Response, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from models import SessionLocal, engine, Base
from utils.rate_limiter import RateLimiter
from routes.order_routes import router as order_router
from routes.product_routes import router as product_router

# ── Structured JSON logging ────────────────────────────────────────────────────
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "correlation_id"):
            log_record["correlation_id"] = record.correlation_id
        return json.dumps(log_record)

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger("api-service")

app = FastAPI(title="Order Processing API")
rate_limiter = RateLimiter(limit=10, window_seconds=60)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ── Middleware: attach correlation_id to every request ────────────────────────
@app.middleware("http")
async def global_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id

    client_ip = request.client.host
    if not rate_limiter.allow_request(client_ip):
        logger.warning(json.dumps({
            "event": "rate_limit_exceeded",
            "ip": client_ip,
            "correlation_id": correlation_id
        }))
        return Response(content="Rate limit exceeded", status_code=429)

    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response
    except Exception as e:
        logger.error(json.dumps({
            "event": "unhandled_error",
            "error": str(e),
            "correlation_id": correlation_id
        }))
        return Response(content="Internal Server Error", status_code=500)

# ── Health endpoint: real DB + real RabbitMQ checks ──────────────────────────
@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    health_status = {
        "status": "UP",
        "database": "CONNECTED",
        "rabbitmq": "CONNECTED"
    }

    # 1. Real Database Check
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        health_status["database"] = f"DOWN: {str(e)}"
        health_status["status"] = "DOWN"

    # 2. Real RabbitMQ Check
    try:
        mq_host = os.getenv("MQ_HOST", "rabbitmq")
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=mq_host, heartbeat=60,
                                      blocked_connection_timeout=5)
        )
        connection.close()
    except pika.exceptions.AMQPConnectionError as e:
        health_status["rabbitmq"] = f"DOWN: {str(e)}"
        health_status["status"] = "DOWN"
    except Exception as e:
        health_status["rabbitmq"] = f"DOWN: {str(e)}"
        health_status["status"] = "DOWN"

    status_code = 200 if health_status["status"] == "UP" else 503
    return Response(
        content=json.dumps(health_status),
        status_code=status_code,
        media_type="application/json"
    )

app.include_router(order_router, prefix="/api/v1")
app.include_router(product_router, prefix="/api/v1")

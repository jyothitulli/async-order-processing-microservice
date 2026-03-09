from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import os

Base = declarative_base()

class Order(Base):
    __tablename__ = "orders"
    order_id = Column(String(255), primary_key=True)
    user_id = Column(String(255), nullable=False)
    total_amount = Column(Float, nullable=False)
    status = Column(String(50), default="PENDING")
    idempotency_key = Column(String(255), unique=True, nullable=False) # For Idempotency
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Outbox(Base):
    __tablename__ = "outbox"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(255), nullable=False)
    payload = Column(JSON, nullable=False) # Store the event data here
    processed = Column(Integer, default=0) # 0 = Pending, 1 = Sent
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# Database Connection
DB_URL = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}"
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
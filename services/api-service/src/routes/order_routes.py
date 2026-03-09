from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models import SessionLocal, Order  # Ensure these are imported correctly
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

# Dependency to get the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Schema for response (Optional but good practice)
class OrderResponse(BaseModel):
    order_id: str
    user_id: str
    total_amount: float
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

@router.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: str, db: Session = Depends(get_db)):
    # CRITICAL: We query using order_id to match the DB
    order = db.query(Order).filter(Order.order_id == order_id).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return order
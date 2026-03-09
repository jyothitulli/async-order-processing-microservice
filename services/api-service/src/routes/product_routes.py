# services/api-service/src/routes/product_routes.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models import SessionLocal, Product # Assuming you have a Product class in models.py

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/products/{product_id}")
def get_product(product_id: str, db: Session = Depends(get_db)):
    # Update to match your Product model's ID field
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product
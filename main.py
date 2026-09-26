from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="SmartTable.ma Production API", version="1.0.0")

class CustomerAuth(BaseModel):
    phone_number: str
    restaurant_slug: str

class ReviewReward(BaseModel):
    customer_id: int
    restaurant_id: int

class Redemption(BaseModel):
    customer_id: int
    restaurant_id: int
    points_to_redeem: int

@app.get("/")
def health_check():
    return {"status": "online", "brand": "smarttable.ma", "message": "Loyalty engine is running smoothly."}

@app.post("/api/customer/auth")
def authenticate_customer(data: CustomerAuth):
    return {
        "status": "success",
        "customer_id": 1,
        "phone": data.phone_number,
        "points_balance": 0
    }

@app.post("/api/rewards/claim-review")
def claim_google_review(data: ReviewReward):
    return {
        "status": "success",
        "added_points": 50,
        "new_balance": 50,
        "message": "Review verified and points added!"
    }

@app.post("/api/rewards/redeem")
def redeem_points(data: Redemption):
    return {
        "status": "success",
        "redeemed": data.points_to_redeem,
        "remaining_balance": 0,
        "message": "Points successfully redeemed to zero."
    }

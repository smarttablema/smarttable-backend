import os
import random
import re
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_7aYbfrQdjcq6@ep-cold-lake-b1djlrzp-pooler.c-5.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

app = FastAPI(title="SmartTable.ma SaaS Engine", version="9.0.0")

# Setup templates directory
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
def startup_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_referrals (
            id SERIAL PRIMARY KEY,
            referrer_phone VARCHAR(20),
            referred_phone VARCHAR(20) UNIQUE,
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS redemption_queue (
            id SERIAL PRIMARY KEY,
            restaurant_slug VARCHAR(50),
            table_number VARCHAR(20),
            customer_name VARCHAR(100),
            customer_phone VARCHAR(20),
            reward_item VARCHAR(100),
            security_pin VARCHAR(4),
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS active_vouchers (
            id SERIAL PRIMARY KEY,
            code VARCHAR(10),
            phone_number VARCHAR(20),
            reward_title VARCHAR(100),
            image_url TEXT,
            status VARCHAR(20) DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

class CustomerAuth(BaseModel):
    phone_number: str
    restaurant_slug: str = "default-restaurant"

class ReviewReward(BaseModel):
    phone_number: str
    restaurant_slug: str = "default-restaurant"

class ReferralCreate(BaseModel):
    referrer_phone: str
    friend_phone: str
    restaurant_slug: str = "default-restaurant"

class MenuItemCreate(BaseModel):
    restaurant_slug: str = "default-restaurant"
    category: str
    name: str
    price: str
    image_url: str = ""

class MenuPriceUpdate(BaseModel):
    price: str

class RewardCreate(BaseModel):
    restaurant_slug: str = "default-restaurant"
    title: str
    points_required: int
    image_url: str = ""

class TierCreate(BaseModel):
    restaurant_slug: str = "default-restaurant"
    name: str
    min_points: int

class SettingsUpdate(BaseModel):
    restaurant_slug: str = "default-restaurant"
    review_points: int
    referral_points: int

class VoucherValidate(BaseModel):
    code: str

@app.get("/api/health")
def health_check():
    return {"status": "online", "database": "neon-postgres", "brand": "smarttable.ma"}

@app.post("/api/customer/auth")
def authenticate_customer(data: CustomerAuth):
    phone = data.phone_number.strip()
    clean_phone = re.sub(r'[\s\-\(\)]', '', phone)
    if not re.match(r'^\+?\d{8,15}$', clean_phone):
        raise HTTPException(status_code=400, detail="Invalid phone number format.")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (clean_phone,))
        customer = cur.fetchone()
        if not customer:
            cur.execute("INSERT INTO customers (phone_number, points_balance, has_purchased) VALUES (%s, 0, FALSE) RETURNING *;", (clean_phone,))
            customer = cur.fetchone()
            conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "points_balance": customer["points_balance"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/customers")
def get_customers():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT phone_number, points_balance, created_at FROM customers ORDER BY id DESC;")
        customers = cur.fetchall()
        cur.close()
        conn.close()
        return customers or []
    except Exception:
        return []

@app.get("/api/settings/{slug}")
def get_restaurant_settings(slug: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM restaurant_settings WHERE restaurant_slug = %s;", (slug,))
        settings = cur.fetchone()
        cur.close()
        conn.close()
        if not settings:
            return {"review_points": 50, "referral_points": 50}
        return {"review_points": settings["review_points"], "referral_points": settings["referral_points"]}
    except Exception:
        return {"review_points": 50, "referral_points": 50}

@app.post("/api/admin/settings/update")
def update_restaurant_settings(data: SettingsUpdate):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM restaurant_settings WHERE restaurant_slug = %s;", (data.restaurant_slug,))
        exists = cur.fetchone()
        if exists:
            cur.execute("UPDATE restaurant_settings SET review_points = %s, referral_points = %s WHERE restaurant_slug = %s;", 
                        (data.review_points, data.referral_points, data.restaurant_slug))
        else:
            cur.execute("INSERT INTO restaurant_settings (restaurant_slug, review_points, referral_points) VALUES (%s, %s, %s);", 
                        (data.restaurant_slug, data.review_points, data.referral_points))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Campaign settings updated!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/menu/{slug}")
def get_menu(slug: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM menu_items WHERE restaurant_slug = %s ORDER BY id DESC;", (slug,))
        items = cur.fetchall()
        cur.close()
        conn.close()
        return items or []
    except Exception:
        return []

@app.post("/api/admin/menu/add")
def add_menu_item(item: MenuItemCreate):
    try:
        price_str = item.price.strip()
        if price_str.isdigit():
            price_str += " MAD"
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO menu_items (restaurant_slug, category, name, price, image_url) VALUES (%s, %s, %s, %s, %s);",
            (item.restaurant_slug, item.category, item.name, price_str, item.image_url)
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Menu item added!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/admin/menu/{item_id}")
def update_menu_price(item_id: int, data: MenuPriceUpdate):
    try:
        new_price = data.price.strip()
        if new_price.isdigit():
            new_price += " MAD"
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE menu_items SET price = %s WHERE id = %s;", (new_price, item_id))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Price updated!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/admin/menu/{item_id}")
def delete_menu_item(item_id: int):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM menu_items WHERE id = %s;", (item_id,))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Menu item removed!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/rewards/{slug}")
def get_rewards(slug: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM custom_rewards WHERE restaurant_slug = %s ORDER BY points_required ASC;", (slug,))
        rewards = cur.fetchall()
        cur.close()
        conn.close()
        if not rewards:
            return [
                {"id": 1, "title": "Free Espresso / Coffee", "points_required": 50, "image_url": "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=500"},
                {"id": 2, "title": "Free Gourmet Dessert", "points_required": 100, "image_url": "https://images.unsplash.com/photo-1551024709-8f23befc6f87?w=500"},
                {"id": 3, "title": "100 MAD Off Total Bill", "points_required": 250, "image_url": "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=500"}
            ]
        return rewards
    except Exception:
        return []

@app.post("/api/admin/rewards/add")
def add_reward(reward: RewardCreate):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO custom_rewards (restaurant_slug, title, points_required, image_url) VALUES (%s, %s, %s, %s);",
            (reward.restaurant_slug, reward.title, reward.points_required, reward.image_url)
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Reward created!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/admin/rewards/{reward_id}")
def delete_reward(reward_id: int):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM custom_rewards WHERE id = %s;", (reward_id,))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Reward removed!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tiers/{slug}")
def get_tiers(slug: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM restaurant_tiers WHERE restaurant_slug = %s ORDER BY min_points ASC;", (slug,))
        tiers = cur.fetchall()
        cur.close()
        conn.close()
        if not tiers:
            return [
                {"id": 1, "name": "Classic Member", "min_points": 0},
                {"id": 2, "name": "Silver VIP", "min_points": 100},
                {"id": 3, "name": "Gold VIP", "min_points": 300}
            ]
        return tiers
    except Exception:
        return []

@app.post("/api/admin/tiers/add")
def add_tier(tier: TierCreate):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO restaurant_tiers (restaurant_slug, name, min_points) VALUES (%s, %s, %s);",
            (tier.restaurant_slug, tier.name, tier.min_points)
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Tier created!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/admin/tiers/{tier_id}")
def delete_tier(tier_id: int):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM restaurant_tiers WHERE id = %s;", (tier_id,))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Tier removed!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rewards/redeem")
def redeem_reward(data: dict):
    phone = data.get("phone_number")
    reward_id = data.get("reward_id")
    slug = data.get("restaurant_slug", "default-restaurant")
    table_number = data.get("table_number", "1")
    customer_name = data.get("customer_name", "Guest")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (phone,))
        customer = cur.fetchone()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found.")
        
        cur.execute("SELECT * FROM custom_rewards WHERE id = %s;", (reward_id,))
        reward = cur.fetchone()
        cost = reward["points_required"] if reward else 50
        title = reward["title"] if reward else "Free Item"
        img = reward.get("image_url") or "https://images.unsplash.com/photo-1551024709-8f23befc6f87?w=500"

        if customer["points_balance"] < cost:
            raise HTTPException(status_code=400, detail="Insufficient points balance.")

        new_balance = customer["points_balance"] - cost
        cur.execute("UPDATE customers SET points_balance = %s WHERE phone_number = %s;", (new_balance, phone))
        
        v_code = str(random.randint(1000, 9999))
        cur.execute("INSERT INTO active_vouchers (code, phone_number, reward_title, image_url) VALUES (%s, %s, %s, %s);", (v_code, phone, title, img))
        cur.execute(
            """INSERT INTO redemption_queue 
               (restaurant_slug, table_number, customer_name, customer_phone, reward_item, security_pin) 
               VALUES (%s, %s, %s, %s, %s, %s);""",
            (slug, str(table_number), customer_name, phone, title, v_code)
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "new_balance": new_balance, "voucher_code": v_code, "reward_title": title, "image_url": img}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/{slug}/redemptions")
async def get_redemption_queue(slug: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT id, table_number, customer_name, reward_item, security_pin, created_at 
               FROM redemption_queue 
               WHERE restaurant_slug = %s AND status = 'pending' 
               ORDER BY created_at ASC;""",
            (slug,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        queue = []
        for r in rows:
            queue.append({
                "id": r["id"],
                "table_number": r["table_number"],
                "customer_name": r["customer_name"],
                "reward_item": r["reward_item"],
                "security_pin": r["security_pin"],
                "time": r["created_at"].strftime("%H:%M:%S")
            })
        return {"queue": queue}
    except Exception:
        return {"queue": []}

@app.post("/api/admin/redemptions/fulfill/{redemption_id}")
async def fulfill_redemption(redemption_id: int):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE redemption_queue SET status = 'fulfilled' WHERE id = %s;", (redemption_id,))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Fulfilled!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/validate-voucher")
def validate_voucher(data: VoucherValidate):
    try:
        code_input = data.code.strip()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM active_vouchers WHERE code = %s AND status = 'active';", (code_input,))
        voucher = cur.fetchone()
        if not voucher:
            raise HTTPException(status_code=404, detail="Invalid voucher.")
        
        cur.execute("UPDATE active_vouchers SET status = 'redeemed' WHERE code = %s;", (code_input,))
        conn.commit()
        cur.close()
        conn.close()
        return {
            "status": "success",
            "reward_title": voucher["reward_title"],
            "image_url": voucher["image_url"],
            "phone_number": voucher["phone_number"]
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rewards/claim-review")
def claim_google_review(data: ReviewReward):
    slug = data.restaurant_slug or "default-restaurant"
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT review_points FROM restaurant_settings WHERE restaurant_slug = %s;", (slug,))
        s = cur.fetchone()
        review_pts = s["review_points"] if s else 50

        cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (data.phone_number,))
        customer = cur.fetchone()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found.")
        new_balance = customer["points_balance"] + review_pts
        cur.execute("UPDATE customers SET points_balance = %s WHERE phone_number = %s;", (new_balance, data.phone_number))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "new_balance": new_balance, "message": f"{review_pts} points added!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rewards/refer-friend")
def refer_friend(data: ReferralCreate):
    friend = data.friend_phone.strip()
    clean_friend = re.sub(r'[\s\-\(\)]', '', friend)
    if not re.match(r'^\+?\d{8,15}$', clean_friend):
        raise HTTPException(status_code=400, detail="Invalid phone format.")
    try:
        if data.referrer_phone == clean_friend:
            raise HTTPException(status_code=400, detail="Cannot refer yourself.")
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (clean_friend,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Friend already registered.")
        
        cur.execute(
            "INSERT INTO customers (phone_number, points_balance, referred_by, has_purchased) VALUES (%s, 0, %s, FALSE);",
            (clean_friend, data.referrer_phone)
        )
        cur.execute(
            "INSERT INTO pending_referrals (referrer_phone, referred_phone) VALUES (%s, %s) ON CONFLICT (referred_phone) DO NOTHING;",
            (data.referrer_phone, clean_friend)
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Friend linked! Reward unlocks on first purchase."}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
def serve_mobile_frontend(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)

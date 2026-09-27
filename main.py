import os
import random
import re
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_7aYbfrQdjcq6@ep-cold-lake-b1djlrzp-pooler.c-5.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

app = FastAPI(title="SmartTable.ma Enterprise POS & Loyalty Engine", version="10.2.0")

@app.on_event("startup")
def startup_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Ensure customers table and pin_code column exist safely
    cur.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id SERIAL PRIMARY KEY,
            phone_number VARCHAR(20) UNIQUE,
            pin_code VARCHAR(10) DEFAULT '1234',
            points_balance INT DEFAULT 0,
            has_purchased BOOLEAN DEFAULT FALSE,
            referred_by VARCHAR(20),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    try:
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS pin_code VARCHAR(10) DEFAULT '1234';")
    except Exception:
        conn.rollback()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cashback_audit_log (
            id SERIAL PRIMARY KEY,
            restaurant_slug VARCHAR(50),
            customer_phone VARCHAR(20),
            bill_amount DECIMAL(10,2),
            earned_points INT,
            status VARCHAR(20) DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pos_orders (
            id SERIAL PRIMARY KEY,
            restaurant_slug VARCHAR(50),
            items_summary TEXT,
            total_amount DECIMAL(10,2),
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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS restaurant_settings (
            id SERIAL PRIMARY KEY,
            restaurant_slug VARCHAR(50) UNIQUE,
            review_points INT DEFAULT 50,
            referral_points INT DEFAULT 50,
            cashback_percentage DECIMAL(5,2) DEFAULT 10.00,
            open_time VARCHAR(10) DEFAULT '07:00',
            close_time VARCHAR(10) DEFAULT '00:00'
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

def normalize_phone(phone: str) -> str:
    return re.sub(r'[\s\-\(\)]', '', phone.strip())

class CustomerAuth(BaseModel):
    phone_number: str
    pin_code: str = "1234"
    restaurant_slug: str = "default-restaurant"

class CashbackProcess(BaseModel):
    phone_number: str
    bill_amount: float
    restaurant_slug: str = "default-restaurant"

class POSOrderCreate(BaseModel):
    restaurant_slug: str = "default-restaurant"
    items_summary: str
    total_amount: float

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
    cashback_percentage: float
    open_time: str
    close_time: str

class VoucherValidate(BaseModel):
    code: str

@app.get("/api/health")
def health_check():
    return {"status": "online", "database": "neon-postgres", "brand": "smarttable.ma"}

@app.post("/api/customer/auth")
def authenticate_customer(data: CustomerAuth):
    clean_phone = normalize_phone(data.phone_number)
    pin = data.pin_code.strip() if data.pin_code else "1234"
    if not re.match(r'^\+?\d{8,15}$', clean_phone):
        raise HTTPException(status_code=400, detail="Invalid phone number format.")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (clean_phone,))
        customer = cur.fetchone()
        
        if not customer:
            cur.execute(
                "INSERT INTO customers (phone_number, pin_code, points_balance, has_purchased) VALUES (%s, %s, 0, FALSE) RETURNING *;",
                (clean_phone, pin)
            )
            customer = cur.fetchone()
            conn.commit()
        else:
            if not customer.get("pin_code"):
                cur.execute("UPDATE customers SET pin_code = %s WHERE phone_number = %s;", (pin, clean_phone))
                conn.commit()
            elif str(customer.get("pin_code", "1234")) != pin:
                raise HTTPException(status_code=401, detail="Incorrect PIN code.")

        cur.close()
        conn.close()
        return {"status": "success", "points_balance": customer["points_balance"]}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
            return {"review_points": 50, "referral_points": 50, "cashback_percentage": 10.0, "open_time": "07:00", "close_time": "00:00"}
        return {
            "review_points": settings["review_points"],
            "referral_points": settings["referral_points"],
            "cashback_percentage": float(settings["cashback_percentage"]),
            "open_time": settings["open_time"] or "07:00",
            "close_time": settings["close_time"] or "00:00"
        }
    except Exception:
        return {"review_points": 50, "referral_points": 50, "cashback_percentage": 10.0, "open_time": "07:00", "close_time": "00:00"}

@app.post("/api/admin/settings/update")
def update_restaurant_settings(data: SettingsUpdate):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM restaurant_settings WHERE restaurant_slug = %s;", (data.restaurant_slug,))
        exists = cur.fetchone()
        if exists:
            cur.execute("""
                UPDATE restaurant_settings 
                SET review_points = %s, referral_points = %s, cashback_percentage = %s, open_time = %s, close_time = %s 
                WHERE restaurant_slug = %s;
            """, (data.review_points, data.referral_points, data.cashback_percentage, data.open_time, data.close_time, data.restaurant_slug))
        else:
            cur.execute("""
                INSERT INTO restaurant_settings (restaurant_slug, review_points, referral_points, cashback_percentage, open_time, close_time) 
                VALUES (%s, %s, %s, %s, %s, %s);
            """, (data.restaurant_slug, data.review_points, data.referral_points, data.cashback_percentage, data.open_time, data.close_time))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Settings updated successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/cashback/process")
def process_cashback(data: CashbackProcess):
    clean_phone = normalize_phone(data.phone_number)
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT cashback_percentage FROM restaurant_settings WHERE restaurant_slug = %s;", (data.restaurant_slug,))
        s = cur.fetchone()
        cb_rate = float(s["cashback_percentage"]) if s and s["cashback_percentage"] is not None else 10.0

        earned_points = int(data.bill_amount * (cb_rate / 100.0))

        cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (clean_phone,))
        customer = cur.fetchone()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer phone not found.")
        
        new_balance = customer["points_balance"] + earned_points
        cur.execute("UPDATE customers SET points_balance = %s, has_purchased = TRUE WHERE phone_number = %s;", (new_balance, clean_phone))
        cur.execute(
            "INSERT INTO cashback_audit_log (restaurant_slug, customer_phone, bill_amount, earned_points) VALUES (%s, %s, %s, %s);",
            (data.restaurant_slug, clean_phone, data.bill_amount, earned_points)
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "earned_points": earned_points, "new_balance": new_balance, "message": f"Successfully credited {earned_points} points ({cb_rate}% cashback)!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/{slug}/cashback/log")
def get_cashback_log(slug: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM cashback_audit_log WHERE restaurant_slug = %s ORDER BY id DESC LIMIT 20;", (slug,))
        logs = cur.fetchall()
        cur.close()
        conn.close()
        formatted = []
        for l in logs:
            formatted.append({
                "id": l["id"],
                "customer_phone": l["customer_phone"],
                "bill_amount": float(l["bill_amount"]),
                "earned_points": l["earned_points"],
                "status": l["status"],
                "time": l["created_at"].strftime("%H:%M:%S")
            })
        return {"logs": formatted}
    except Exception:
        return {"logs": []}

@app.post("/api/admin/cashback/reverse/{log_id}")
def reverse_cashback(log_id: int):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM cashback_audit_log WHERE id = %s;", (log_id,))
        log = cur.fetchone()
        if not log or log["status"] == 'reversed':
            raise HTTPException(status_code=404, detail="Transaction not found or already reversed.")
        
        phone = log["customer_phone"]
        pts = log["earned_points"]

        cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (phone,))
        cust = cur.fetchone()
        if cust:
            new_bal = max(0, cust["points_balance"] - pts)
            cur.execute("UPDATE customers SET points_balance = %s WHERE phone_number = %s;", (new_bal, phone))

        cur.execute("UPDATE cashback_audit_log SET status = 'reversed' WHERE id = %s;", (log_id,))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Transaction reversed successfully."}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/pos/order")
def create_pos_order(data: POSOrderCreate):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO pos_orders (restaurant_slug, items_summary, total_amount) VALUES (%s, %s, %s);",
            (data.restaurant_slug, data.items_summary, data.total_amount)
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Order confirmed and logged!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/{slug}/reports/daily")
def get_daily_report(slug: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(SUM(total_amount), 0) as revenue, COUNT(*) as orders_count FROM pos_orders WHERE restaurant_slug = %s AND created_at >= CURRENT_DATE;", (slug,))
        summary = cur.fetchone()
        
        cur.execute("SELECT COALESCE(SUM(earned_points), 0) as pts, COUNT(*) as tx_count FROM cashback_audit_log WHERE restaurant_slug = %s AND status = 'active' AND created_at >= CURRENT_DATE;", (slug,))
        cb = cur.fetchone()
        cur.close()
        conn.close()
        return {
            "total_revenue": float(summary["revenue"]),
            "orders_count": summary["orders_count"],
            "cashback_points_issued": cb["pts"],
            "cashback_transactions": cb["tx_count"]
        }
    except Exception:
        return {"total_revenue": 0.0, "orders_count": 0, "cashback_points_issued": 0, "cashback_transactions": 0}

@app.post("/api/admin/{slug}/reports/clear")
def clear_daily_reports(slug: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM pos_orders WHERE restaurant_slug = %s;", (slug,))
        cur.execute("DELETE FROM cashback_audit_log WHERE restaurant_slug = %s;", (slug,))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "All reports and logs cleared successfully."}
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
        return {"status": "success", "message": "Menu item added successfully!"}
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
        return {"status": "success", "message": "Reward created successfully!"}
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

@app.post("/api/rewards/redeem")
def redeem_reward(data: dict):
    phone = normalize_phone(data.get("phone_number", ""))
    reward_id = data.get("reward_id")
    slug = data.get("restaurant_slug", "default-restaurant")
    table_number = data.get("table_number", "1")
    customer_name = data.get("customer_name", "Valued Guest").strip()
    
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
        return {"status": "success", "message": "Reward fulfilled."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rewards/claim-review")
def claim_google_review(data: ReviewReward):
    clean_phone = normalize_phone(data.phone_number)
    slug = data.restaurant_slug or "default-restaurant"
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT review_points FROM restaurant_settings WHERE restaurant_slug = %s;", (slug,))
        s = cur.fetchone()
        review_pts = s["review_points"] if s else 50

        cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (clean_phone,))
        customer = cur.fetchone()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found.")
        new_balance = customer["points_balance"] + review_pts
        cur.execute("UPDATE customers SET points_balance = %s WHERE phone_number = %s;", (new_balance, clean_phone))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "new_balance": new_balance, "message": f"{review_pts} points added successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rewards/refer-friend")
def refer_friend(data: ReferralCreate):
    ref_phone = normalize_phone(data.referrer_phone)
    friend_phone = normalize_phone(data.friend_phone)
    if not re.match(r'^\+?\d{8,15}$', friend_phone):
        raise HTTPException(status_code=400, detail="Invalid friend phone format.")
    try:
        if ref_phone == friend_phone:
            raise HTTPException(status_code=400, detail="You cannot refer your own number.")
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (friend_phone,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="This friend already has an account.")
        
        cur.execute(
            "INSERT INTO customers (phone_number, pin_code, points_balance, referred_by, has_purchased) VALUES (%s, '1234', 0, %s, FALSE);",
            (friend_phone, ref_phone)
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Friend registered!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- FRONTEND UI WITH CORRECT TAB ORDER & SHIFT CONTROLS ---
@app.get("/", response_class=HTMLResponse)
def serve_mobile_frontend():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SmartTable.ma | Enterprise POS & Loyalty</title>
    <link rel="icon" type="image/png" href="https://img.icons8.com/color/48/qr-code.png">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-deep: #090d16;
            --surface: #131c31;
            --surface-card: #1a2642;
            --accent: #f59e0b;
            --accent-glow: rgba(245, 158, 11, 0.2);
            --primary: #38bdf8;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --success: #10b981;
            --danger: #ef4444;
            --border: #2a3a5e;
            --radius: 20px;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
        body { background-color: var(--bg-deep); color: var(--text-main); display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 1rem; background-image: radial-gradient(circle at 50% 0%, #1e293b 0%, var(--bg-deep) 70%); }
        
        .app-frame { width: 100%; max-width: 440px; background: var(--surface); border-radius: var(--radius); padding: 1.5rem; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7); border: 1px solid var(--border); position: relative; overflow: hidden; }
        
        .brand-header { text-align: center; margin-bottom: 1.25rem; }
        .logo { font-size: 1.65rem; font-weight: 800; color: var(--text-main); letter-spacing: -0.5px; }
        .logo span { color: var(--accent); }
        .brand-tag { font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 2px; margin-top: 2px; font-weight: 600; }
        
        .nav-tabs { display: flex; background: var(--bg-deep); border-radius: 14px; padding: 5px; margin-bottom: 1.25rem; border: 1px solid var(--border); }
        .tab-btn { flex: 1; padding: 0.5rem; text-align: center; border-radius: 10px; font-size: 0.75rem; font-weight: 600; color: var(--text-muted); cursor: pointer; border: none; background: transparent; transition: all 0.3s; }
        .tab-btn.active { background: var(--surface-card); color: var(--text-main); box-shadow: 0 4px 12px rgba(0,0,0,0.3); border: 1px solid var(--border); }
        
        .card { background: var(--surface-card); border-radius: 16px; padding: 1.25rem; margin-bottom: 1rem; border: 1px solid var(--border); }
        
        label { display: block; font-size: 0.75rem; font-weight: 600; color: var(--text-muted); margin-bottom: 0.4rem; text-transform: uppercase; letter-spacing: 0.5px; }
        input, textarea { width: 100%; padding: 0.8rem 1rem; border-radius: 12px; border: 1px solid var(--border); background: var(--bg-deep); color: white; font-size: 0.9rem; margin-bottom: 0.85rem; outline: none; transition: border-color 0.2s; resize: none; }
        input:focus, textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
        
        .btn-main { width: 100%; padding: 0.8rem; border-radius: 12px; border: none; background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: #090d16; font-weight: 700; font-size: 0.95rem; cursor: pointer; transition: transform 0.1s; box-shadow: 0 4px 14px var(--accent-glow); }
        .btn-main:active { transform: scale(0.98); }
        
        .hidden { display: none !important; }
        
        .points-display { text-align: center; padding: 0.2rem 0; }
        .points-label { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }
        .points-number { font-size: 2.75rem; font-weight: 800; color: var(--success); letter-spacing: -1px; margin: 0.2rem 0; }
        .tier-badge { display: inline-block; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); color: var(--accent); padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 700; margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 0.5px; }
        .cashback-badge { display: inline-block; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); color: var(--success); padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; margin-bottom: 0.75rem; }

        .rewards-list { display: flex; flex-direction: column; gap: 0.5rem; max-height: 150px; overflow-y: auto; margin-top: 0.5rem; padding-right: 2px; }
        .reward-item { display: flex; align-items: center; justify-content: space-between; background: var(--bg-deep); padding: 0.5rem 0.75rem; border-radius: 12px; border: 1px solid var(--border); gap: 0.5rem; }
        .reward-thumb { width: 40px; height: 40px; border-radius: 8px; object-fit: cover; background: var(--surface); }
        .reward-info { flex: 1; }
        .reward-title { font-size: 0.82rem; font-weight: 700; color: var(--text-main); }
        .reward-cost { font-size: 0.7rem; color: var(--accent); font-weight: 700; }
        .redeem-btn { background: var(--success); color: white; border: none; padding: 6px 10px; border-radius: 8px; font-weight: 700; font-size: 0.72rem; cursor: pointer; }

        .review-link { display: flex; align-items: center; justify-content: center; gap: 8px; text-align: center; margin-top: 0.75rem; padding: 0.75rem; background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.3); color: var(--accent); border-radius: 12px; text-decoration: none; font-weight: 700; font-size: 0.8rem; }

        .pos-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; max-height: 200px; overflow-y: auto; margin-bottom: 1rem; padding-right: 2px; }
        .pos-item-card { background: var(--bg-deep); border: 1px solid var(--border); border-radius: 10px; padding: 8px; text-align: center; cursor: pointer; transition: all 0.2s; }
        .pos-item-card:hover { border-color: var(--accent); background: var(--surface); }
        .pos-img { width: 40px; height: 40px; border-radius: 8px; object-fit: cover; margin-bottom: 4px; }
        .pos-title { font-size: 0.75rem; font-weight: 700; color: var(--text-main); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .pos-price { font-size: 0.7rem; font-weight: 800; color: var(--accent); }

        .cart-box { background: var(--bg-deep); border: 1px solid var(--border); border-radius: 12px; padding: 10px; margin-bottom: 0.85rem; max-height: 120px; overflow-y: auto; font-size: 0.8rem; }
        .cart-row { display: flex; justify-content: space-between; margin-bottom: 4px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 2px; }

        .menu-grid { display: flex; flex-direction: column; gap: 0.75rem; max-height: 360px; overflow-y: auto; padding-right: 2px; }
        .menu-card { display: flex; align-items: center; background: var(--bg-deep); border-radius: 14px; padding: 0.75rem; border: 1px solid var(--border); gap: 0.85rem; cursor: pointer; }
        .menu-img { width: 55px; height: 55px; border-radius: 10px; object-fit: cover; background: var(--surface); }
        .menu-info { flex: 1; }
        .menu-name { font-size: 0.95rem; font-weight: 700; color: var(--text-main); margin-bottom: 2px; }
        .menu-cat { font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700; }
        .menu-price { font-size: 0.9rem; font-weight: 800; color: var(--accent); }

        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(9, 13, 22, 0.85); backdrop-filter: blur(8px); justify-content: center; align-items: center; padding: 1.5rem; }
        .modal-content { background: var(--surface); padding: 1.5rem; border-radius: 24px; max-width: 360px; width: 100%; text-align: center; border: 1px solid var(--border); box-shadow: 0 25px 50px rgba(0,0,0,0.8); animation: modalPop 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
        @keyframes modalPop { from { transform: scale(0.9); opacity: 0; } to { transform: scale(1); opacity: 1; } }
        .modal-img { width: 100%; height: 160px; border-radius: 16px; object-fit: cover; margin-bottom: 1rem; border: 1px solid var(--border); }
        .close-modal { background: var(--border); color: var(--text-main); border: none; padding: 0.75rem; border-radius: 12px; cursor: pointer; font-weight: 700; width: 100%; transition: background 0.2s; margin-top: 0.5rem; }
        .close-modal:hover { background: var(--danger); }

        .voucher-code-box { font-size: 2.2rem; font-weight: 800; color: var(--accent); background: var(--bg-deep); padding: 0.75rem; border-radius: 12px; border: 1px dashed var(--accent); margin: 0.75rem 0; letter-spacing: 2px; }

        .admin-item-row { display: flex; justify-content: space-between; align-items: center; background: var(--bg-deep); padding: 0.75rem; border-radius: 12px; margin-bottom: 0.5rem; font-size: 0.85rem; border: 1px solid var(--border); }
        .danger-btn { background: rgba(239, 68, 68, 0.15); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); padding: 6px 10px; border-radius: 8px; cursor: pointer; font-weight: 700; }
        .edit-btn { background: rgba(56, 189, 248, 0.15); color: var(--primary); border: 1px solid rgba(56, 189, 248, 0.3); padding: 6px 10px; border-radius: 8px; cursor: pointer; font-weight: 700; margin-right: 6px; }

        #toast-banner { position: fixed; bottom: 25px; left: 50%; transform: translateX(-50%) translateY(120px); background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 12px 24px; border-radius: 30px; font-weight: 700; font-size: 0.85rem; box-shadow: 0 15px 30px rgba(16, 185, 129, 0.4); z-index: 9999; transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1); display: flex; align-items: center; gap: 8px; border: 1px solid rgba(255,255,255,0.2); }
        #toast-banner.show { transform: translateX(-50%) translateY(0); }
        #toast-banner.error { background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%); box-shadow: 0 15px 30px rgba(239, 68, 68, 0.4); }

        /* EXACT TAB ORDER: Queue, Menu, Reports, Rewards, Cashback, POS, Settings */
        .admin-subnav { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; background: var(--bg-deep); padding: 4px; border-radius: 14px; margin-bottom: 1.25rem; border: 1px solid var(--border); }
        .admin-sub-btn { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 50px; padding: 2px 1px; text-align: center; border-radius: 8px; font-size: 0.52rem; font-weight: 700; color: var(--text-muted); cursor: pointer; border: none; background: transparent; transition: all 0.2s ease; }
        .admin-sub-btn span.nav-icon { font-size: 1rem; margin-bottom: 2px; display: block; line-height: 1; }
        .admin-sub-btn span.nav-text { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 100%; display: block; }
        .admin-sub-btn.active { background: var(--surface-card); color: var(--accent); border: 1px solid var(--border); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
        
        .queue-grid { display: grid; grid-template-columns: 1fr; gap: 12px; margin-top: 10px; }
        .redemption-card { background: var(--bg-deep); border-left: 4px solid var(--accent); padding: 12px; border-radius: 10px; border: 1px solid var(--border); }
        .pin-display { background: var(--surface); padding: 8px; text-align: center; font-size: 1.3rem; font-weight: 800; color: var(--success); letter-spacing: 3px; border-radius: 6px; margin: 8px 0; border: 1px dashed var(--border); }
    </style>
</head>
<body>
    <div id="toast-banner">✓ Action completed successfully!</div>

    <div class="app-frame">
        <div class="brand-header">
            <div class="logo">SmartTable<span>.ma</span></div>
            <div class="brand-tag" id="app-subtitle">Enterprise POS & Loyalty</div>
        </div>
        
        <!-- CLIENT TABS -->
        <div class="nav-tabs" id="client-nav">
            <button class="tab-btn active" onclick="switchTab('rewards')">🏆 Rewards</button>
            <button class="tab-btn" onclick="switchTab('menu')">📖 Menu</button>
        </div>

        <!-- CLIENT: REWARDS TAB WITH PIN LOGIN -->
        <div id="tab-rewards" class="client-view">
            <div id="login-section" class="card">
                <h3 style="margin-bottom: 0.85rem; font-size: 1rem; font-weight: 700;">Customer Portal</h3>
                <label>Phone Number</label>
                <input type="tel" id="phone-input" placeholder="e.g., 0612345678" />
                <label>Security PIN (4-Digits)</label>
                <input type="password" id="pin-input" placeholder="e.g., 1234" maxlength="4" />
                <button class="btn-main" onclick="loginCustomer()">Access / Register My Account</button>
            </div>
            
            <div id="dashboard-section" class="card hidden">
                <div class="points-display">
                    <div class="tier-badge" id="customer-tier-badge">Classic Member</div>
                    <div class="points-label">Your Balance</div>
                    <div class="points-number" id="points-val">0</div>
                    <div class="cashback-badge" id="client-cashback-badge">⚡ 10% Bill Cashback Active</div>
                </div>
                
                <div style="margin-top: 0.5rem;">
                    <label>🎁 Redeemable Rewards</label>
                    <div id="customer-rewards-list" class="rewards-list">
                        <div style="text-align:center; color:var(--text-muted); font-size:0.75rem;">Loading rewards...</div>
                    </div>
                </div>

                <div style="border-top: 1px solid var(--border); margin-top: 0.85rem; padding-top: 0.75rem;">
                    <label id="referral-label-text">👥 Refer a Friend (+50 pts on 1st visit)</label>
                    <input type="tel" id="friend-phone" placeholder="Friend's Phone Number" />
                    <button class="btn-main" onclick="referFriend()" style="background: linear-gradient(135deg, #38bdf8 0%, #0284c7 100%); color: #090d16; padding: 0.6rem; font-size: 0.85rem;">Register Friend</button>
                </div>

                <a href="https://maps.google.com" target="_blank" class="review-link" id="review-link-btn" onclick="claimReview()">
                    ⭐ Leave Google Review (+50 Points)
                </a>
            </div>
        </div>

        <!-- CLIENT: MENU TAB -->
        <div id="tab-menu" class="client-view hidden">
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.85rem;">
                    <h3 style="font-size: 1rem; font-weight: 700; color: var(--accent);">Live Menu</h3>
                    <span style="font-size: 0.7rem; color: var(--text-muted);">Tap to zoom</span>
                </div>
                <div id="menu-container" class="menu-grid">
                    <div style="text-align:center; color:var(--text-muted); font-size:0.85rem; padding: 2rem 0;">Loading menu...</div>
                </div>
            </div>
        </div>

        <!-- OWNER CONTROL CENTER (EXACT TAB ORDER REQUESTED) -->
        <div id="tab-admin" class="hidden">
            <div class="admin-subnav">
                <button class="admin-sub-btn active" onclick="switchAdminSub('queue')" id="sub-btn-queue">
                    <span class="nav-icon">🔥</span><span class="nav-text">Queue</span>
                </button>
                <button class="admin-sub-btn" onclick="switchAdminSub('menu')" id="sub-btn-menu">
                    <span class="nav-icon">📖</span><span class="nav-text">Menu</span>
                </button>
                <button class="admin-sub-btn" onclick="switchAdminSub('reports')" id="sub-btn-reports">
                    <span class="nav-icon">📊</span><span class="nav-text">Reports</span>
                </button>
                <button class="admin-sub-btn" onclick="switchAdminSub('rewards')" id="sub-btn-rewards">
                    <span class="nav-icon">🎁</span><span class="nav-text">Rewards</span>
                </button>
                <button class="admin-sub-btn" onclick="switchAdminSub('cashback')" id="sub-btn-cashback">
                    <span class="nav-icon">⚡</span><span class="nav-text">Cashback</span>
                </button>
                <button class="admin-sub-btn" onclick="switchAdminSub('pos')" id="sub-btn-pos">
                    <span class="nav-icon">🛒</span><span class="nav-text">POS</span>
                </button>
                <button class="admin-sub-btn" onclick="switchAdminSub('settings')" id="sub-btn-settings">
                    <span class="nav-icon">⚙️</span><span class="nav-text">Settings</span>
                </button>
            </div>

            <!-- 1. QUEUE -->
            <div id="admin-sub-queue" class="admin-section">
                <div class="card">
                    <h3 style="margin-bottom: 0.4rem; font-size: 0.95rem; font-weight: 700; color: var(--accent);">⚡ Live Redemption Queue</h3>
                    <p style="font-size: 0.7rem; color: var(--text-muted); margin-bottom: 0.75rem;">Active redemptions with customer names</p>
                    <div id="admin-queue-container" class="queue-grid">
                        <div style="text-align:center; color:var(--text-muted); font-size:0.75rem;">No pending redemptions right now.</div>
                    </div>
                </div>
            </div>

            <!-- 2. MENU -->
            <div id="admin-sub-menu" class="admin-section hidden">
                <div class="card">
                    <h3 style="margin-bottom: 0.75rem; font-size: 0.95rem; font-weight: 700; color: var(--accent);">📖 Menu Management</h3>
                    <label>Category</label>
                    <input type="text" id="admin-cat" placeholder="e.g., Burgers, Drinks" />
                    <label>Item Name</label>
                    <input type="text" id="admin-name" placeholder="Item Name" />
                    <label>Price (MAD)</label>
                    <input type="text" id="admin-price" placeholder="e.g. 65" />
                    <label>Image URL (Optional)</label>
                    <input type="text" id="admin-img" placeholder="https://..." />
                    <button class="btn-main" onclick="addAdminMenu()" style="margin-bottom: 1rem; padding: 0.6rem; font-size: 0.8rem;">+ Add Menu Item</button>
                    
                    <label>Existing Items:</label>
                    <div id="admin-menu-list" style="max-height: 150px; overflow-y: auto;"></div>
                </div>
            </div>

            <!-- 3. REPORTS (WITH SHIFT INFO & CLEAR BUTTON) -->
            <div id="admin-sub-reports" class="admin-section hidden">
                <div class="card" style="text-align: center;">
                    <h3 style="margin-bottom: 0.4rem; font-size: 0.95rem; font-weight: 700; color: var(--accent);">📊 Daily Shift Z-Report</h3>
                    <div id="shift-label-display" style="font-size: 0.7rem; color: var(--success); margin-bottom: 0.85rem; font-weight: 700;">Active Shift: 07:00 - 00:00</div>
                    
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 1rem;">
                        <div style="background: var(--bg-deep); padding: 10px; border-radius: 12px; border: 1px solid var(--border);">
                            <div style="font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase;">Total Revenue</div>
                            <div id="rep-revenue" style="font-size: 1.2rem; font-weight: 800; color: var(--success);">0 MAD</div>
                        </div>
                        <div style="background: var(--bg-deep); padding: 10px; border-radius: 12px; border: 1px solid var(--border);">
                            <div style="font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase;">Orders Sold</div>
                            <div id="rep-orders" style="font-size: 1.2rem; font-weight: 800; color: var(--primary);">0</div>
                        </div>
                    </div>

                    <div style="background: var(--bg-deep); padding: 10px; border-radius: 12px; border: 1px solid var(--border); margin-bottom: 1rem;">
                        <div style="font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase;">Cashback Points Issued</div>
                        <div id="rep-cb-pts" style="font-size: 1rem; font-weight: 800; color: var(--accent);">0 pts</div>
                    </div>

                    <button class="danger-btn" onclick="clearReports()" style="width: 100%; padding: 0.6rem; font-size: 0.8rem; border-radius: 10px;">🗑️ Clear / Reset Shift Data</button>
                </div>
            </div>

            <!-- 4. REWARDS -->
            <div id="admin-sub-rewards" class="admin-section hidden">
                <div class="card">
                    <h3 style="margin-bottom: 0.75rem; font-size: 0.95rem; font-weight: 700; color: var(--accent);">🎁 Rewards Builder</h3>
                    <label>Reward Title</label>
                    <input type="text" id="reward-title-input" placeholder="e.g. Free Gourmet Dessert" />
                    <label>Points Required</label>
                    <input type="number" id="reward-cost-input" placeholder="e.g. 100" />
                    <label>Image URL (Optional)</label>
                    <input type="text" id="reward-img-input" placeholder="https://..." />
                    <button class="btn-main" onclick="addRewardTier()" style="background: #3b82f6; color: white; padding: 0.6rem; font-size: 0.8rem; margin-bottom: 1rem;">+ Create Reward</button>
                    
                    <label>Configured Rewards:</label>
                    <div id="admin-rewards-list" style="max-height: 150px; overflow-y: auto;"></div>
                </div>
            </div>

            <!-- 5. CASHBACK -->
            <div id="admin-sub-cashback" class="admin-section hidden">
                <div class="card">
                    <h3 style="margin-bottom: 0.4rem; font-size: 0.95rem; font-weight: 700; color: var(--success);">⚡ Cashback POS & Audit Log</h3>
                    <p style="font-size: 0.7rem; color: var(--text-muted); margin-bottom: 0.75rem;">Calculates cashback based on active settings percentage.</p>
                    
                    <label>Customer Phone Number</label>
                    <input type="tel" id="cb-phone" placeholder="e.g. 0612345678" />
                    
                    <label>Total Bill Amount (MAD)</label>
                    <input type="number" id="cb-amount" placeholder="e.g. 250" />
                    
                    <button class="btn-main" onclick="submitCashback()" style="background: var(--success); color: white; padding: 0.6rem; font-size: 0.8rem; margin-bottom: 1rem;">Credit Cashback Points ✓</button>
                    
                    <label>Recent Transactions & Reversals:</label>
                    <div id="cashback-log-container" style="max-height: 120px; overflow-y: auto;"></div>
                </div>
            </div>

            <!-- 6. POS -->
            <div id="admin-sub-pos" class="admin-section hidden">
                <div class="card">
                    <h3 style="margin-bottom: 0.4rem; font-size: 0.95rem; font-weight: 700; color: var(--accent);">🛒 Touchscreen POS Builder</h3>
                    <p style="font-size: 0.7rem; color: var(--text-muted); margin-bottom: 0.75rem;">Tap item cards to add quantities to order cart</p>
                    
                    <div id="pos-menu-grid" class="pos-grid">
                        <div style="text-align:center; color:var(--text-muted); font-size:0.7rem; grid-column: span 2;">Loading items...</div>
                    </div>

                    <label>Order Cart:</label>
                    <div id="pos-cart-box" class="cart-box">
                        <div style="text-align: center; color: var(--text-muted);">Cart is empty</div>
                    </div>

                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.85rem; font-weight: 800; font-size: 0.95rem;">
                        <span>Total:</span>
                        <span id="pos-total-val" style="color: var(--accent);">0.00 MAD</span>
                    </div>

                    <button class="btn-main" onclick="confirmPOSOrder()" style="background: var(--success); color: white; padding: 0.7rem; font-size: 0.85rem;">Confirm & Submit Order ✓</button>
                </div>
            </div>

            <!-- 7. SETTINGS (WITH CASHBACK % & SHIFT HOURS) -->
            <div id="admin-sub-settings" class="admin-section hidden">
                <div class="card">
                    <h3 style="margin-bottom: 0.75rem; font-size: 0.95rem; font-weight: 700; color: var(--accent);">⚙️ Campaign & Shift Settings</h3>
                    
                    <label>Google Review Points</label>
                    <input type="number" id="setting-review-pts" placeholder="e.g. 50" />
                    
                    <label>Friend Referral Points</label>
                    <input type="number" id="setting-referral-pts" placeholder="e.g. 50" />
                    
                    <label>Cashback Percentage (%)</label>
                    <input type="number" step="0.5" id="setting-cb-pct" placeholder="e.g. 10" />

                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                        <div>
                            <label>Shift Open Time</label>
                            <input type="time" id="setting-open-time" value="07:00" />
                        </div>
                        <div>
                            <label>Shift Close Time</label>
                            <input type="time" id="setting-close-time" value="00:00" />
                        </div>
                    </div>

                    <button class="btn-main" onclick="saveCampaignSettings()" style="background: var(--accent); color: #090d16; padding: 0.7rem; font-size: 0.85rem; margin-top: 0.5rem;">Save All Settings ✓</button>
                </div>
            </div>
        </div>
    </div>

    <!-- MODALS -->
    <div id="redeem-name-modal" class="modal">
        <div class="modal-content">
            <h3 style="font-size: 1rem; font-weight: 700; color: var(--accent); margin-bottom: 0.4rem;">Claim Reward</h3>
            <p style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 1rem;">Please enter your name for the waiter:</p>
            <input type="text" id="customer-name-input" placeholder="e.g., Mohammed Daou" style="margin-bottom: 1rem;" />
            <button class="btn-main" onclick="confirmRedeem()" style="margin-bottom: 0.5rem;">Confirm & Get PIN</button>
            <button class="close-modal" onclick="document.getElementById('redeem-name-modal').style.display='none'">Cancel</button>
        </div>
    </div>

    <div id="voucher-modal" class="modal">
        <div class="modal-content">
            <h3 style="font-size: 1rem; font-weight: 700; color: var(--success); margin-bottom: 0.25rem;">Reward Unlocked!</h3>
            <p style="font-size: 0.75rem; color: var(--text-muted);">Show PIN to waiter:</p>
            <div id="modal-voucher-code" class="voucher-code-box">----</div>
            <img id="modal-voucher-img" class="modal-img" src="" style="height: 120px; margin-bottom: 0.5rem;" />
            <div id="modal-voucher-title" style="font-size: 0.85rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.75rem;"></div>
            <button class="close-modal" onclick="closeVoucherModal()">Done</button>
        </div>
    </div>

    <div id="image-modal" class="modal">
        <div class="modal-content">
            <img id="modal-img-tag" class="modal-img" src="" />
            <h3 id="modal-title" style="font-size: 1.1rem; font-weight: 700; margin-bottom: 0.25rem; color: var(--text-main);"></h3>
            <div id="modal-price" style="font-size: 1rem; font-weight: 800; color: var(--accent); margin-bottom: 0.5rem;"></div>
            <button class="close-modal" onclick="closeModal()">Close Preview</button>
        </div>
    </div>

    <script>
        let currentPhone = '';
        const currentSlug = 'default-restaurant';
        let selectedRewardId = null;
        let posCart = {};
        let menuItemsCache = [];
        
        window.onload = function() {
            loadRestaurantSettings();
            const urlParams = new URLSearchParams(window.location.search);
            if(urlParams.get('mode') === 'admin') {
                document.getElementById('client-nav').classList.add('hidden');
                document.getElementById('tab-rewards').classList.add('hidden');
                document.getElementById('tab-admin').classList.remove('hidden');
                document.getElementById('app-subtitle').innerText = "Owner Control Center";
                loadAdminQueue();
                loadPOSMenu();
                loadCashbackLog();
                loadDailyReport();
                loadAdminMenu();
                loadAdminRewards();
                setInterval(loadAdminQueue, 5000);
            } else {
                loadMenu();
            }
        };

        async function loadRestaurantSettings() {
            try {
                const res = await fetch('/api/settings/' + currentSlug);
                const data = await res.json();
                if(res.ok) {
                    document.getElementById('setting-review-pts').value = data.review_points;
                    document.getElementById('setting-referral-pts').value = data.referral_points;
                    document.getElementById('setting-cb-pct').value = data.cashback_percentage;
                    document.getElementById('setting-open-time').value = data.open_time;
                    document.getElementById('setting-close-time').value = data.close_time;
                    document.getElementById('client-cashback-badge').innerText = `⚡ ${data.cashback_percentage}% Bill Cashback Active`;
                    document.getElementById('shift-label-display').innerText = `Active Shift: ${data.open_time} - ${data.close_time}`;
                }
            } catch(e) {}
        }

        async function saveCampaignSettings() {
            const review_points = parseInt(document.getElementById('setting-review-pts').value);
            const referral_points = parseInt(document.getElementById('setting-referral-pts').value);
            const cashback_percentage = parseFloat(document.getElementById('setting-cb-pct').value);
            const open_time = document.getElementById('setting-open-time').value;
            const close_time = document.getElementById('setting-close-time').value;

            try {
                const res = await fetch('/api/admin/settings/update', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ restaurant_slug: currentSlug, review_points, referral_points, cashback_percentage, open_time, close_time })
                });
                const data = await res.json();
                if(res.ok) {
                    showToast(data.message);
                    loadRestaurantSettings();
                }
            } catch(e) {
                showToast('Connection error', true);
            }
        }

        function showToast(text, isError = false) {
            const t = document.getElementById('toast-banner');
            t.innerText = text;
            if(isError) t.classList.add('error'); else t.classList.remove('error');
            t.classList.add('show');
            setTimeout(() => t.classList.remove('show'), 3500);
        }

        function switchTab(tabName) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('tab-rewards').classList.add('hidden');
            document.getElementById('tab-menu').classList.add('hidden');
            
            if(tabName === 'rewards') {
                document.querySelectorAll('.tab-btn')[0].classList.add('active');
                document.getElementById('tab-rewards').classList.remove('hidden');
                if(currentPhone) loadCustomerData();
            } else if(tabName === 'menu') {
                document.querySelectorAll('.tab-btn')[1].classList.add('active');
                document.getElementById('tab-menu').classList.remove('hidden');
                loadMenu();
            }
        }

        function switchAdminSub(subName) {
            ['queue', 'menu', 'reports', 'rewards', 'cashback', 'pos', 'settings'].forEach(s => {
                const btn = document.getElementById('sub-btn-' + s);
                const sec = document.getElementById('admin-sub-' + s);
                if(btn) btn.classList.remove('active');
                if(sec) sec.classList.add('hidden');
            });
            const targetBtn = document.getElementById('sub-btn-' + subName);
            const targetSec = document.getElementById('admin-sub-' + subName);
            if(targetBtn) targetBtn.classList.add('active');
            if(targetSec) targetSec.classList.remove('hidden');
            if(subName === 'queue') loadAdminQueue();
            if(subName === 'pos') loadPOSMenu();
            if(subName === 'cashback') loadCashbackLog();
            if(subName === 'reports') loadDailyReport();
        }

        async function loadPOSMenu() {
            try {
                const res = await fetch('/api/menu/' + currentSlug);
                menuItemsCache = await res.json();
                const container = document.getElementById('pos-menu-grid');
                if(!menuItemsCache || menuItemsCache.length === 0) {
                    container.innerHTML = '<div style="grid-column: span 2; text-align:center; color:var(--text-muted); font-size:0.75rem;">No items found.</div>';
                    return;
                }
                container.innerHTML = menuItemsCache.map(item => `
                    <div class="pos-item-card" onclick="addToPOSCart(${item.id})">
                        <img src="${item.image_url || 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=500'}" class="pos-img" />
                        <div class="pos-title">${item.name}</div>
                        <div class="pos-price">${item.price}</div>
                    </div>
                `).join('');
            } catch(e) {}
        }

        function addToPOSCart(id) {
            const item = menuItemsCache.find(i => i.id === id);
            if(!item) return;
            if(!posCart[id]) {
                posCart[id] = { name: item.name, priceNum: parseFloat(item.price) || 50, qty: 0 };
            }
            posCart[id].qty++;
            renderPOSCart();
        }

        function renderPOSCart() {
            const box = document.getElementById('pos-cart-box');
            const keys = Object.keys(posCart);
            if(keys.length === 0) {
                box.innerHTML = '<div style="text-align: center; color: var(--text-muted);">Cart is empty</div>';
                document.getElementById('pos-total-val').innerText = '0.00 MAD';
                return;
            }
            let total = 0;
            box.innerHTML = keys.map(k => {
                const c = posCart[k];
                const lineTotal = c.priceNum * c.qty;
                total += lineTotal;
                return `<div class="cart-row"><span>${c.qty}x ${c.name}</span><span>${lineTotal.toFixed(2)} MAD</span></div>`;
            }).join('');
            document.getElementById('pos-total-val').innerText = total.toFixed(2) + ' MAD';
        }

        async function confirmPOSOrder() {
            const keys = Object.keys(posCart);
            if(keys.length === 0) { showToast('Cart is empty.', true); return; }
            let summaryParts = [];
            let total = 0;
            keys.forEach(k => {
                const c = posCart[k];
                summaryParts.push(`${c.qty}x ${c.name}`);
                total += c.priceNum * c.qty;
            });
            try {
                const res = await fetch('/api/admin/pos/order', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ restaurant_slug: currentSlug, items_summary: summaryParts.join(', '), total_amount: total })
                });
                if(res.ok) {
                    showToast('Order confirmed and logged!');
                    posCart = {};
                    renderPOSCart();
                    loadDailyReport();
                }
            } catch(e) {
                showToast('Error submitting order', true);
            }
        }

        async function loadDailyReport() {
            try {
                const res = await fetch('/api/admin/' + currentSlug + '/reports/daily');
                const data = await res.json();
                document.getElementById('rep-revenue').innerText = data.total_revenue.toFixed(2) + ' MAD';
                document.getElementById('rep-orders').innerText = data.orders_count;
                document.getElementById('rep-cb-pts').innerText = data.cashback_points_issued + ' pts';
            } catch(e) {}
        }

        async function clearReports() {
            if(!confirm('Clear all shift report data and logs?')) return;
            try {
                const res = await fetch('/api/admin/' + currentSlug + '/reports/clear', { method: 'POST' });
                if(res.ok) {
                    showToast('Shift data cleared!');
                    loadDailyReport();
                    loadCashbackLog();
                }
            } catch(e) {
                showToast('Error clearing data', true);
            }
        }

        async function submitCashback() {
            const phone = document.getElementById('cb-phone').value.trim();
            const amount = parseFloat(document.getElementById('cb-amount').value);
            if(!phone || isNaN(amount) || amount <= 0) {
                showToast('Please enter valid phone and amount.', true);
                return;
            }
            try {
                const res = await fetch('/api/admin/cashback/process', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ phone_number: phone, bill_amount: amount, restaurant_slug: currentSlug })
                });
                const data = await res.json();
                if(res.ok) {
                    showToast(data.message);
                    document.getElementById('cb-phone').value = '';
                    document.getElementById('cb-amount').value = '';
                    loadCashbackLog();
                } else {
                    showToast(data.detail || 'Failed', true);
                }
            } catch(e) {
                showToast('Connection error', true);
            }
        }

        async function loadCashbackLog() {
            try {
                const res = await fetch('/api/admin/' + currentSlug + '/cashback/log');
                const data = await res.json();
                const container = document.getElementById('cashback-log-container');
                if(!data.logs || data.logs.length === 0) {
                    container.innerHTML = '<div style="color:var(--text-muted); font-size:0.75rem;">No recent transactions.</div>';
                    return;
                }
                container.innerHTML = data.logs.map(l => `
                    <div class="admin-item-row" style="${l.status === 'reversed' ? 'opacity: 0.5; text-decoration: line-through;' : ''}">
                        <div>
                            <div style="font-weight: 700;">${l.customer_phone} - ${l.bill_amount} MAD</div>
                            <div style="font-size: 0.65rem; color: var(--success);">+${l.earned_points} pts (${l.time})</div>
                        </div>
                        ${l.status === 'active' ? `<button class="danger-btn" onclick="reverseCashback(${l.id})" style="padding:2px 6px; font-size:0.7rem;">Reverse</button>` : '<span style="font-size:0.7rem; color:var(--danger);">Reversed</span>'}
                    </div>
                `).join('');
            } catch(e) {}
        }

        async function reverseCashback(id) {
            if(!confirm('Reverse transaction?')) return;
            try {
                const res = await fetch('/api/admin/cashback/reverse/' + id, { method: 'POST' });
                if(res.ok) {
                    showToast('Reversed successfully.');
                    loadCashbackLog();
                }
            } catch(e) {}
        }

        async function loadAdminQueue() {
            try {
                const res = await fetch('/api/admin/' + currentSlug + '/redemptions');
                const data = await res.json();
                const container = document.getElementById('admin-queue-container');
                if(!data.queue || data.queue.length === 0) {
                    container.innerHTML = '<div style="text-align:center; color:var(--text-muted); font-size:0.75rem; padding: 1rem 0;">☕ All quiet! No pending redemptions.</div>';
                    return;
                }
                container.innerHTML = data.queue.map(item => `
                    <div class="redemption-card">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                            <span style="background: var(--primary); color: #090d16; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.75rem;">Table ${item.table_number}</span>
                            <span style="font-size: 0.65rem; color: var(--text-muted);">${item.time}</span>
                        </div>
                        <div style="font-weight: 700; font-size: 0.95rem; color: var(--accent); margin-bottom: 2px;">👤 Customer: ${item.customer_name}</div>
                        <div style="font-weight: 700; font-size: 0.9rem; color: var(--text-main);">${item.reward_item}</div>
                        <div class="pin-display">PIN: ${item.security_pin}</div>
                        <button class="btn-main" onclick="fulfillRedemption(${item.id})" style="background: var(--success); color: white; padding: 8px; font-size: 0.8rem;">Mark Handed Out ✓</button>
                    </div>
                `).join('');
            } catch(e) {}
        }

        async function fulfillRedemption(id) {
            await fetch('/api/admin/redemptions/fulfill/' + id, { method: 'POST' });
            showToast('Reward fulfilled!');
            loadAdminQueue();
        }

        async function loadMenu() {
            try {
                const res = await fetch('/api/menu/' + currentSlug);
                const items = await res.json();
                const container = document.getElementById('menu-container');
                if(!items || items.length === 0) {
                    container.innerHTML = '<div style="text-align:center; color:var(--text-muted); padding: 2rem 0;">No items available.</div>';
                    return;
                }
                container.innerHTML = items.map(item => `
                    <div class="menu-card" onclick="openModal('${item.image_url || 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=500'}', '${item.name.replace(/'/g, "\\\\'")}', '${item.price}')">
                        <img src="${item.image_url || 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=500'}" class="menu-img" />
                        <div class="menu-info">
                            <div class="menu-cat">${item.category}</div>
                            <div class="menu-name">${item.name}</div>
                            <div class="menu-price">${item.price}</div>
                        </div>
                    </div>
                `).join('');
            } catch(e) {}
        }

        async function loginCustomer() {
            const phone = document.getElementById('phone-input').value.trim();
            const pin = document.getElementById('pin-input').value.trim();
            if(!phone || !pin) { showToast('Please enter phone and PIN code', true); return; }
            currentPhone = phone;
            try {
                const res = await fetch('/api/customer/auth', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ phone_number: phone, pin_code: pin, restaurant_slug: currentSlug })
                });
                const data = await res.json();
                if(res.ok) {
                    document.getElementById('points-val').innerText = data.points_balance;
                    document.getElementById('login-section').classList.add('hidden');
                    document.getElementById('dashboard-section').classList.remove('hidden');
                    loadCustomerData();
                    showToast('Welcome!');
                } else {
                    showToast(data.detail || 'Login failed', true);
                }
            } catch(e) {
                showToast('Connection error', true);
            }
        }

        async function loadCustomerData() {
            try {
                const res = await fetch('/api/rewards/' + currentSlug);
                const rewards = await res.json();
                const container = document.getElementById('customer-rewards-list');
                if(!rewards || rewards.length === 0) {
                    container.innerHTML = '<div style="color:var(--text-muted); font-size:0.75rem; text-align:center;">No rewards.</div>';
                    return;
                }
                container.innerHTML = rewards.map(r => `
                    <div class="reward-item">
                        <img src="${r.image_url || 'https://images.unsplash.com/photo-1551024709-8f23befc6f87?w=500'}" class="reward-thumb" />
                        <div class="reward-info">
                            <div class="reward-title">${r.title}</div>
                            <div class="reward-cost">${r.points_required} pts</div>
                        </div>
                        <button class="redeem-btn" onclick="openRedeemModal(${r.id})">Redeem</button>
                    </div>
                `).join('');
            } catch(e) {}
        }

        function openRedeemModal(rewardId) {
            selectedRewardId = rewardId;
            document.getElementById('customer-name-input').value = '';
            document.getElementById('redeem-name-modal').style.display = 'flex';
        }

        async function confirmRedeem() {
            const customerName = document.getElementById('customer-name-input').value.trim();
            if(!customerName) { showToast('Please enter your name.', true); return; }
            document.getElementById('redeem-name-modal').style.display = 'none';

            try {
                const res = await fetch('/api/rewards/redeem', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ phone_number: currentPhone, reward_id: selectedRewardId, restaurant_slug: currentSlug, customer_name: customerName })
                });
                const data = await res.json();
                if(res.ok) {
                    document.getElementById('points-val').innerText = data.new_balance;
                    document.getElementById('modal-voucher-code').innerText = data.voucher_code;
                    document.getElementById('modal-voucher-title').innerText = data.reward_title;
                    document.getElementById('modal-voucher-img').src = data.image_url;
                    document.getElementById('voucher-modal').style.display = 'flex';
                    loadCustomerData();
                    showToast('Reward unlocked successfully!');
                }
            } catch(e) {}
        }

        function closeVoucherModal() { document.getElementById('voucher-modal').style.display = 'none'; }

        async function claimReview() {
            const res = await fetch('/api/rewards/claim-review', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ phone_number: currentPhone, restaurant_slug: currentSlug })
            });
            const data = await res.json();
            document.getElementById('points-val').innerText = data.new_balance;
            loadCustomerData();
            showToast(data.message);
        }

        async function referFriend() {
            const friendPhone = document.getElementById('friend-phone').value.trim();
            if(!friendPhone) { showToast('Enter friend phone', true); return; }
            const res = await fetch('/api/rewards/refer-friend', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ referrer_phone: currentPhone, friend_phone: friendPhone, restaurant_slug: currentSlug })
            });
            const data = await res.json();
            if(res.ok) {
                showToast(data.message);
                document.getElementById('friend-phone').value = '';
            }
        }

        async function addAdminMenu() {
            const category = document.getElementById('admin-cat').value;
            const name = document.getElementById('admin-name').value;
            const price = document.getElementById('admin-price').value;
            const image_url = document.getElementById('admin-img').value;
            if(!category || !name || !price) { showToast('Fill all fields', true); return; }
            await fetch('/api/admin/menu/add', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ restaurant_slug: currentSlug, category, name, price, image_url })
            });
            showToast('Menu item added!');
            document.getElementById('admin-cat').value = '';
            document.getElementById('admin-name').value = '';
            document.getElementById('admin-price').value = '';
            document.getElementById('admin-img').value = '';
            loadAdminMenu();
            loadPOSMenu();
        }

        async function loadAdminMenu() {
            const res = await fetch('/api/menu/' + currentSlug);
            const items = await res.json();
            const container = document.getElementById('admin-menu-list');
            if(!items || items.length === 0) { container.innerHTML = '<div style="color:var(--text-muted); font-size:0.75rem;">No items.</div>'; return; }
            container.innerHTML = items.map(item => `
                <div class="admin-item-row">
                    <span><b>${item.name}</b> (${item.price})</span>
                    <button class="danger-btn" onclick="deleteItem(${item.id})">Delete</button>
                </div>
            `).join('');
        }

        async function deleteItem(id) {
            if(!confirm('Delete item?')) return;
            await fetch('/api/admin/menu/' + id, { method: 'DELETE' });
            loadAdminMenu();
            loadPOSMenu();
            showToast('Item removed.');
        }

        async function addRewardTier() {
            const title = document.getElementById('reward-title-input').value;
            const points_required = document.getElementById('reward-cost-input').value;
            const image_url = document.getElementById('reward-img-input').value;
            if(!title || !points_required) { showToast('Fill title and points', true); return; }
            await fetch('/api/admin/rewards/add', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ restaurant_slug: currentSlug, title, points_required: parseInt(points_required), image_url })
            });
            showToast('Reward added!');
            loadAdminRewards();
        }

        async function loadAdminRewards() {
            const res = await fetch('/api/rewards/' + currentSlug);
            const rewards = await res.json();
            const container = document.getElementById('admin-rewards-list');
            if(!rewards || rewards.length === 0) { container.innerHTML = '<div style="color:var(--text-muted); font-size:0.75rem;">No rewards.</div>'; return; }
            container.innerHTML = rewards.map(r => `
                <div class="admin-item-row">
                    <span><b>${r.title}</b> (${r.points_required} pts)</span>
                    <button class="danger-btn" onclick="deleteReward(${r.id})" style="padding:2px 6px; font-size:0.7rem;">Delete</button>
                </div>
            `).join('');
        }

        async function deleteReward(id) {
            if(!confirm('Delete reward?')) return;
            await fetch('/api/admin/rewards/' + id, { method: 'DELETE' });
            loadAdminRewards();
            showToast('Reward removed.');
        }

        function openModal(imgUrl, name, price) {
            document.getElementById('modal-img-tag').src = imgUrl;
            document.getElementById('modal-title').innerText = name;
            document.getElementById('modal-price').innerText = price;
            document.getElementById('image-modal').style.display = 'flex';
        }
        function closeModal() { document.getElementById('image-modal').style.display = 'none'; }
    </script>
</body>
</html>
    """

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)

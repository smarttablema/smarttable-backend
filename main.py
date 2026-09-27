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

app = FastAPI(title="SmartTable.ma Enterprise POS & Loyalty Engine", version="11.7.0")

@app.on_event("startup")
def startup_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id SERIAL PRIMARY KEY,
            phone_number VARCHAR(20) UNIQUE,
            password VARCHAR(100),
            recovery_pin VARCHAR(10),
            points_balance INT DEFAULT 0,
            has_purchased BOOLEAN DEFAULT FALSE,
            referred_by VARCHAR(20),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    try:
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS password VARCHAR(100);")
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS recovery_pin VARCHAR(10);")
    except Exception:
        conn.rollback()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS owner_admin (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE,
            password VARCHAR(100),
            recovery_pin VARCHAR(10)
        );
    """)
    cur.execute("INSERT INTO owner_admin (username, password, recovery_pin) VALUES ('admin', 'admin123', '9999') ON CONFLICT (username) DO NOTHING;")

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

class CustomerRegister(BaseModel):
    phone_number: str
    password: str
    recovery_pin: str
    restaurant_slug: str = "default-restaurant"

class CustomerLogin(BaseModel):
    phone_number: str
    password: str
    restaurant_slug: str = "default-restaurant"

class CustomerPinRecover(BaseModel):
    phone_number: str
    recovery_pin: str
    new_password: str
    restaurant_slug: str = "default-restaurant"

class CustomerPasswordChange(BaseModel):
    phone_number: str
    old_password: str
    new_password: str
    restaurant_slug: str = "default-restaurant"

class AdminLogin(BaseModel):
    username: str
    password: str

class AdminPasswordChange(BaseModel):
    username: str = "admin"
    old_password: str
    new_password: str

class CashbackProcess(BaseModel):
    phone_number: str
    bill_amount: float
    restaurant_slug: str = "default-restaurant"

class POSOrderCreate(BaseModel):
    restaurant_slug: str = "default-restaurant"
    items_summary: str
    total_amount: float
    table_number: str = "1"
    customer_phone: str = ""

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

class RewardCreate(BaseModel):
    restaurant_slug: str = "default-restaurant"
    title: str
    points_required: int
    image_url: str = ""

class SettingsUpdate(BaseModel):
    restaurant_slug: str = "default-restaurant"
    review_points: int
    referral_points: int
    cashback_percentage: float
    open_time: str
    close_time: str

@app.get("/api/health")
def health_check():
    return {"status": "online", "database": "neon-postgres", "brand": "smarttable.ma"}

@app.post("/api/customer/register")
def register_customer(data: CustomerRegister):
    clean_phone = normalize_phone(data.phone_number)
    pwd = data.password.strip()
    pin = data.recovery_pin.strip()
    
    if not re.match(r'^\+?\d{8,15}$', clean_phone):
        raise HTTPException(status_code=400, detail="Invalid phone number format.")
    if len(pwd) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters.")
    if len(pin) != 4 or not pin.isdigit():
        raise HTTPException(status_code=400, detail="Recovery PIN must be exactly 4 digits.")

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (clean_phone,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="An account with this phone number already exists.")
        
        cur.execute(
            "INSERT INTO customers (phone_number, password, recovery_pin, points_balance, has_purchased) VALUES (%s, %s, %s, 0, FALSE) RETURNING *;",
            (clean_phone, pwd, pin)
        )
        customer = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "points_balance": customer["points_balance"], "message": "Account registered successfully!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/customer/login")
def login_customer(data: CustomerLogin):
    clean_phone = normalize_phone(data.phone_number)
    pwd = data.password.strip()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (clean_phone,))
        customer = cur.fetchone()
        cur.close()
        conn.close()

        if not customer:
            raise HTTPException(status_code=404, detail="Account not found. Please register first.")
        
        if customer.get("password") != pwd:
            raise HTTPException(status_code=401, detail="Incorrect password. Use 'Forgot Password?' with your PIN.")

        return {"status": "success", "points_balance": customer["points_balance"]}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/customer/recover")
def recover_customer_password(data: CustomerPinRecover):
    clean_phone = normalize_phone(data.phone_number)
    pin = data.recovery_pin.strip()
    new_pwd = data.new_password.strip()
    
    if len(new_pwd) < 4:
        raise HTTPException(status_code=400, detail="New password must be at least 4 characters.")

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (clean_phone,))
        customer = cur.fetchone()

        if not customer:
            raise HTTPException(status_code=404, detail="Account not found.")
        
        if customer.get("recovery_pin") != pin:
            raise HTTPException(status_code=401, detail="Incorrect recovery PIN.")

        cur.execute("UPDATE customers SET password = %s WHERE phone_number = %s;", (new_pwd, clean_phone))
        conn.commit()
        cur.close()
        conn.close()

        return {"status": "success", "points_balance": customer["points_balance"], "message": "Password updated successfully!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/customer/change-password")
def change_customer_password(data: CustomerPasswordChange):
    clean_phone = normalize_phone(data.phone_number)
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (clean_phone,))
        customer = cur.fetchone()
        if not customer or customer.get("password") != data.old_password.strip():
            raise HTTPException(status_code=401, detail="Current password is incorrect.")
        
        if len(data.new_password.strip()) < 4:
            raise HTTPException(status_code=400, detail="New password must be at least 4 characters.")

        cur.execute("UPDATE customers SET password = %s WHERE phone_number = %s;", (data.new_password.strip(), clean_phone))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Password changed successfully!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/customer/refresh-balance/{phone}")
def refresh_customer_balance(phone: str):
    clean_phone = normalize_phone(phone)
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT points_balance FROM customers WHERE phone_number = %s;", (clean_phone,))
        customer = cur.fetchone()
        cur.close()
        conn.close()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found.")
        return {"status": "success", "points_balance": customer["points_balance"]}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/login")
def admin_login(data: AdminLogin):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM owner_admin WHERE username = %s;", (data.username.strip(),))
        admin = cur.fetchone()
        cur.close()
        conn.close()
        if not admin or admin["password"] != data.password.strip():
            raise HTTPException(status_code=401, detail="Invalid owner credentials.")
        return {"status": "success", "message": "Owner login authorized."}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/change-password")
def admin_change_password(data: AdminPasswordChange):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM owner_admin WHERE username = %s;", (data.username,))
        admin = cur.fetchone()
        if not admin or admin["password"] != data.old_password.strip():
            raise HTTPException(status_code=401, detail="Current admin password is incorrect.")
        
        cur.execute("UPDATE owner_admin SET password = %s WHERE username = %s;", (data.new_password.strip(), data.username))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Admin password updated successfully!"}
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

        cur.execute(
            """INSERT INTO redemption_queue 
               (restaurant_slug, table_number, customer_name, customer_phone, reward_item, security_pin, status) 
               VALUES (%s, %s, %s, %s, %s, %s, 'pending');""",
            (data.restaurant_slug, str(data.table_number), "App Guest", data.customer_phone or "Walk-in", f"ORDER: {data.items_summary} ({data.total_amount:.2f} MAD)", "APP")
        )

        if data.customer_phone:
            cur.execute("SELECT cashback_percentage FROM restaurant_settings WHERE restaurant_slug = %s;", (data.restaurant_slug,))
            s = cur.fetchone()
            cb_rate = float(s["cashback_percentage"]) if s and s["cashback_percentage"] is not None else 10.0
            earned_points = int(data.total_amount * (cb_rate / 100.0))

            cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (data.customer_phone,))
            customer = cur.fetchone()
            if customer and earned_points > 0:
                new_balance = customer["points_balance"] + earned_points
                cur.execute("UPDATE customers SET points_balance = %s, has_purchased = TRUE WHERE phone_number = %s;", (new_balance, data.customer_phone))
                cur.execute(
                    "INSERT INTO cashback_audit_log (restaurant_slug, customer_phone, bill_amount, earned_points) VALUES (%s, %s, %s, %s);",
                    (data.restaurant_slug, data.customer_phone, data.total_amount, earned_points)
                )

        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Order submitted and sent to kitchen/owner successfully!"}
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
                "raw_time": r["created_at"].isoformat(),
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
            "INSERT INTO customers (phone_number, password, recovery_pin, points_balance, referred_by, has_purchased) VALUES (%s, 'default123', '1234', 0, %s, FALSE);",
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

# --- FRONTEND UI WITH PROFESSIONAL POLISHED CLIENT REWARDS & BALANCE REFRESH ---
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
        
        .card { background: var(--surface-card); border-radius: 16px; padding: 1.25rem; margin-bottom: 1rem; border: 1px solid var(--border); position: relative; }
        
        label { display: block; font-size: 0.75rem; font-weight: 600; color: var(--text-muted); margin-bottom: 0.4rem; text-transform: uppercase; letter-spacing: 0.5px; }
        input, textarea, select { width: 100%; padding: 0.8rem 1rem; border-radius: 12px; border: 1px solid var(--border); background: var(--bg-deep); color: white; font-size: 0.9rem; margin-bottom: 0.85rem; outline: none; transition: border-color 0.2s; resize: none; }
        input:focus, textarea:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
        
        .btn-main { width: 100%; padding: 0.8rem; border-radius: 12px; border: none; background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: #090d16; font-weight: 700; font-size: 0.95rem; cursor: pointer; transition: transform 0.1s; box-shadow: 0 4px 14px var(--accent-glow); }
        .btn-main:active { transform: scale(0.98); }
        
        .hidden { display: none !important; }
        
        /* PROFESSIONALLY DESIGNED BALANCE COMPONENT */
        .wallet-card { background: linear-gradient(135deg, rgba(26, 38, 66, 0.9) 0%, rgba(15, 23, 42, 0.95) 100%); border: 1px solid rgba(245, 158, 11, 0.25); border-radius: 16px; padding: 1.25rem; text-align: center; margin-bottom: 1.25rem; position: relative; box-shadow: 0 8px 24px rgba(0,0,0,0.3); }
        .wallet-top-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
        .tier-badge { background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); color: var(--accent); padding: 4px 10px; border-radius: 20px; font-size: 0.68rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; }
        .refresh-balance-btn { background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.3); color: var(--primary); padding: 4px 10px; border-radius: 20px; font-size: 0.68rem; font-weight: 700; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; transition: all 0.2s; }
        .refresh-balance-btn:hover { background: rgba(56, 189, 248, 0.25); border-color: var(--primary); transform: translateY(-1px); }
        
        .wallet-balance-label { font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1.5px; font-weight: 700; margin-top: 0.25rem; }
        .wallet-balance-number { font-size: 2.8rem; font-weight: 800; color: var(--success); letter-spacing: -1px; line-height: 1.1; margin: 0.2rem 0 0.5rem 0; text-shadow: 0 2px 10px rgba(16, 185, 129, 0.2); }
        .cashback-badge { display: inline-block; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); color: var(--success); padding: 4px 12px; border-radius: 20px; font-size: 0.72rem; font-weight: 700; }

        /* REFINED REDEEMABLE REWARDS LIST */
        .rewards-section-title { font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.6rem; display: flex; align-items: center; gap: 6px; }
        .rewards-list { display: flex; flex-direction: column; gap: 0.65rem; max-height: 180px; overflow-y: auto; margin-bottom: 1rem; padding-right: 3px; }
        
        .reward-item { display: flex; align-items: center; justify-content: space-between; background: var(--bg-deep); padding: 0.7rem 0.85rem; border-radius: 14px; border: 1px solid var(--border); gap: 0.75rem; transition: border-color 0.2s; }
        .reward-item:hover { border-color: rgba(245, 158, 11, 0.4); }
        .reward-thumb { width: 48px; height: 48px; border-radius: 10px; object-fit: cover; background: var(--surface); border: 1px solid var(--border); }
        .reward-info { flex: 1; text-align: left; }
        .reward-title { font-size: 0.88rem; font-weight: 700; color: var(--text-main); margin-bottom: 2px; }
        .reward-cost { font-size: 0.72rem; color: var(--accent); font-weight: 700; display: inline-flex; align-items: center; gap: 3px; }
        
        .redeem-btn { background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; border: none; padding: 7px 14px; border-radius: 10px; font-weight: 700; font-size: 0.75rem; cursor: pointer; box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25); transition: transform 0.1s; }
        .redeem-btn:active { transform: scale(0.95); }

        .review-link { display: flex; align-items: center; justify-content: center; gap: 8px; text-align: center; margin-top: 0.75rem; padding: 0.75rem; background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.3); color: var(--accent); border-radius: 12px; text-decoration: none; font-weight: 700; font-size: 0.8rem; }

        .pos-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; max-height: 200px; overflow-y: auto; margin-bottom: 1rem; padding-right: 2px; }
        .pos-item-card { background: var(--bg-deep); border: 1px solid var(--border); border-radius: 10px; padding: 8px; text-align: center; cursor: pointer; transition: all 0.2s; }
        .pos-item-card:hover { border-color: var(--accent); background: var(--surface); }
        .pos-img { width: 40px; height: 40px; border-radius: 8px; object-fit: cover; margin-bottom: 4px; }
        .pos-title { font-size: 0.75rem; font-weight: 700; color: var(--text-main); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .pos-price { font-size: 0.7rem; font-weight: 800; color: var(--accent); }

        .cart-box { background: var(--bg-deep); border: 1px solid var(--border); border-radius: 12px; padding: 10px; margin-bottom: 0.85rem; max-height: 120px; overflow-y: auto; font-size: 0.8rem; }
        .cart-row { display: flex; justify-content: space-between; margin-bottom: 4px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 2px; }

        .menu-grid { display: flex; flex-direction: column; gap: 0.75rem; max-height: 260px; overflow-y: auto; padding-right: 2px; margin-bottom: 1rem; }
        .menu-card { display: flex; align-items: center; background: var(--bg-deep); border-radius: 14px; padding: 0.75rem; border: 1px solid var(--border); gap: 0.85rem; cursor: pointer; transition: border-color 0.2s; }
        .menu-card:hover { border-color: var(--accent); }
        .menu-img { width: 50px; height: 50px; border-radius: 10px; object-fit: cover; background: var(--surface); }
        .menu-info { flex: 1; }
        .menu-name { font-size: 0.9rem; font-weight: 700; color: var(--text-main); margin-bottom: 2px; }
        .menu-cat { font-size: 0.62rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700; }
        .menu-price { font-size: 0.85rem; font-weight: 800; color: var(--accent); }
        .add-cart-mini { background: var(--accent); color: #090d16; border: none; padding: 6px 10px; border-radius: 8px; font-weight: 800; font-size: 0.75rem; cursor: pointer; }

        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(9, 13, 22, 0.85); backdrop-filter: blur(8px); justify-content: center; align-items: center; padding: 1.5rem; }
        .modal-content { background: var(--surface); padding: 1.5rem; border-radius: 24px; max-width: 380px; width: 100%; text-align: center; border: 1px solid var(--border); box-shadow: 0 25px 50px rgba(0,0,0,0.8); animation: modalPop 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
        @keyframes modalPop { from { transform: scale(0.9); opacity: 0; } to { transform: scale(1); opacity: 1; } }
        .modal-img { width: 100%; height: 160px; border-radius: 16px; object-fit: cover; margin-bottom: 1rem; border: 1px solid var(--border); }
        .close-modal { background: var(--border); color: var(--text-main); border: none; padding: 0.75rem; border-radius: 12px; cursor: pointer; font-weight: 700; width: 100%; transition: background 0.2s; margin-top: 0.5rem; }
        .close-modal:hover { background: var(--danger); }

        .voucher-code-box { font-size: 2.2rem; font-weight: 800; color: var(--accent); background: var(--bg-deep); padding: 0.75rem; border-radius: 12px; border: 1px dashed var(--accent); margin: 0.75rem 0; letter-spacing: 2px; }

        .admin-item-row { display: flex; justify-content: space-between; align-items: center; background: var(--bg-deep); padding: 0.75rem; border-radius: 12px; margin-bottom: 0.5rem; font-size: 0.85rem; border: 1px solid var(--border); }
        .danger-btn { background: rgba(239, 68, 68, 0.15); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); padding: 6px 10px; border-radius: 8px; cursor: pointer; font-weight: 700; }

        #toast-banner { position: fixed; bottom: 25px; left: 50%; transform: translateX(-50%) translateY(120px); background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 12px 24px; border-radius: 30px; font-weight: 700; font-size: 0.85rem; box-shadow: 0 15px 30px rgba(16, 185, 129, 0.4); z-index: 9999; transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1); display: flex; align-items: center; gap: 8px; border: 1px solid rgba(255,255,255,0.2); }
        #toast-banner.show { transform: translateX(-50%) translateY(0); }
        #toast-banner.error { background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%); box-shadow: 0 15px 30px rgba(239, 68, 68, 0.4); }

        .admin-subnav { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; background: var(--bg-deep); padding: 4px; border-radius: 14px; margin-bottom: 1.25rem; border: 1px solid var(--border); }
        .admin-sub-btn { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 50px; padding: 2px 1px; text-align: center; border-radius: 8px; font-size: 0.52rem; font-weight: 700; color: var(--text-muted); cursor: pointer; border: none; background: transparent; transition: all 0.2s ease; }
        .admin-sub-btn span.nav-icon { font-size: 1rem; margin-bottom: 2px; display: block; line-height: 1; }
        .admin-sub-btn span.nav-text { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 100%; display: block; }
        .admin-sub-btn.active { background: var(--surface-card); color: var(--accent); border: 1px solid var(--border); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
        
        .queue-grid { display: grid; grid-template-columns: 1fr; gap: 12px; margin-top: 10px; }
        
        .redemption-card { background: var(--bg-deep); border-left: 5px solid var(--success); padding: 14px; border-radius: 12px; border: 1px solid var(--border); transition: all 0.3s ease; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
        .redemption-card.urgency-normal { border-left-color: var(--success); }
        
        .redemption-card.urgency-orange { 
            border-left-color: #f97316; 
            background: linear-gradient(135deg, rgba(249, 115, 22, 0.12) 0%, rgba(26, 38, 66, 0.95) 100%);
            border-top: 1px solid rgba(249, 115, 22, 0.4);
            border-right: 1px solid rgba(249, 115, 22, 0.4);
            border-bottom: 1px solid rgba(249, 115, 22, 0.4);
            box-shadow: 0 6px 20px rgba(249, 115, 22, 0.18);
        }

        .redemption-card.urgency-red { 
            border-left-color: var(--danger); 
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.2) 0%, rgba(26, 38, 66, 0.95) 100%);
            border-top: 1px solid rgba(239, 68, 68, 0.6);
            border-right: 1px solid rgba(239, 68, 68, 0.6);
            border-bottom: 1px solid rgba(239, 68, 68, 0.6);
            box-shadow: 0 8px 25px rgba(239, 68, 68, 0.35);
        }

        .pin-display { background: var(--surface); padding: 8px; text-align: center; font-size: 1.3rem; font-weight: 800; color: var(--success); letter-spacing: 3px; border-radius: 6px; margin: 8px 0; border: 1px dashed var(--border); }
        
        .auth-sub-toggle { display: flex; gap: 8px; margin-bottom: 1rem; }
        .auth-toggle-btn { flex: 1; background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-muted); padding: 8px; border-radius: 8px; font-size: 0.75rem; font-weight: 700; cursor: pointer; }
        .auth-toggle-btn.active { background: var(--surface); color: var(--accent); border-color: var(--accent); }
        
        .forgot-link { text-align: right; margin-top: -0.4rem; margin-bottom: 0.85rem; }
        .forgot-link a { font-size: 0.72rem; color: var(--primary); text-decoration: none; font-weight: 600; cursor: pointer; }
        .forgot-link a:hover { text-decoration: underline; }

        .dashboard-actions { display: flex; justify-content: space-between; align-items: center; margin-top: 0.85rem; border-top: 1px solid var(--border); padding-top: 0.85rem; }
        .dash-action-btn { background: rgba(56, 189, 248, 0.15); color: var(--primary); border: 1px solid rgba(56, 189, 248, 0.3); padding: 6px 12px; border-radius: 8px; font-size: 0.75rem; font-weight: 700; cursor: pointer; }
        .logout-btn { background: rgba(239, 68, 68, 0.15); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); padding: 6px 14px; border-radius: 8px; font-size: 0.75rem; font-weight: 700; cursor: pointer; }
        
        .table-badge-locked { display: flex; align-items: center; justify-content: space-between; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); color: var(--primary); padding: 8px 12px; border-radius: 10px; font-size: 0.8rem; font-weight: 700; margin-bottom: 0.75rem; }
    </style>
</head>
<body>
    <div id="toast-banner">✓ Action completed successfully!</div>

    <!-- OWNER ADMIN LOGIN GATE -->
    <div id="admin-login-modal" class="modal" style="display: none;">
        <div class="modal-content">
            <div class="logo" style="margin-bottom: 0.5rem;">SmartTable<span>.ma</span></div>
            <h3 style="font-size: 1.1rem; font-weight: 700; color: var(--accent); margin-bottom: 0.25rem;">Owner Control Center</h3>
            <p style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 1.25rem;">Enter manager username (admin) & password</p>
            
            <label>Username</label>
            <input type="text" id="owner-user" placeholder="admin" value="admin" />
            
            <label>Password</label>
            <input type="password" id="owner-pass" placeholder="admin123" />
            
            <button class="btn-main" onclick="loginOwner()" style="margin-top: 0.5rem;">Authorize & Open Dashboard</button>
        </div>
    </div>

    <div class="app-frame">
        <div class="brand-header">
            <div class="logo">SmartTable<span>.ma</span></div>
            <div class="brand-tag" id="app-subtitle">Enterprise POS & Loyalty</div>
        </div>
        
        <!-- CLIENT TABS -->
        <div class="nav-tabs" id="client-nav">
            <button class="tab-btn active" onclick="switchTab('rewards')">🏆 Rewards</button>
            <button class="tab-btn" onclick="switchTab('menu')">📖 Menu & Order</button>
        </div>

        <!-- CLIENT: REWARDS TAB -->
        <div id="tab-rewards" class="client-view">
            <div id="login-section" class="card">
                <div class="auth-sub-toggle">
                    <button class="auth-toggle-btn active" id="btn-toggle-signin" onclick="switchAuthMode('signin')">Sign In</button>
                    <button class="auth-toggle-btn" id="btn-toggle-register" onclick="switchAuthMode('register')">Register</button>
                </div>

                <!-- SIGN IN FORM -->
                <div id="form-signin">
                    <h3 style="margin-bottom: 0.85rem; font-size: 0.95rem; font-weight: 700;">Customer Sign In</h3>
                    <label>Phone Number</label>
                    <input type="tel" id="signin-phone" placeholder="e.g., 0612345678" />
                    <label>Password</label>
                    <input type="password" id="signin-password" placeholder="Your password" />
                    <div class="forgot-link">
                        <a onclick="switchAuthMode('recover')">Forgot Password?</a>
                    </div>
                    <button class="btn-main" onclick="loginCustomer()">Sign In to Account</button>
                </div>

                <!-- REGISTER FORM -->
                <div id="form-register" class="hidden">
                    <h3 style="margin-bottom: 0.85rem; font-size: 0.95rem; font-weight: 700; color: var(--accent);">Create New Account</h3>
                    <label>Phone Number</label>
                    <input type="tel" id="reg-phone" placeholder="e.g., 0612345678" />
                    <label>Password</label>
                    <input type="password" id="reg-password" placeholder="Create a password" />
                    <label>Recovery PIN (4-Digits for Reset)</label>
                    <input type="password" id="reg-pin" placeholder="e.g., 1234" maxlength="4" />
                    <button class="btn-main" onclick="registerCustomer()" style="background: linear-gradient(135deg, #38bdf8 0%, #0284c7 100%); color: #090d16; margin-top: 0.5rem;">Register & Create Account</button>
                </div>

                <!-- RECOVER FORM -->
                <div id="form-recover" class="hidden">
                    <h3 style="margin-bottom: 0.85rem; font-size: 0.95rem; font-weight: 700; color: var(--primary);">PIN Recovery & Reset</h3>
                    <label>Phone Number</label>
                    <input type="tel" id="recover-phone" placeholder="e.g., 0612345678" />
                    <label>4-Digit Recovery PIN</label>
                    <input type="password" id="recover-pin" placeholder="e.g., 1234" maxlength="4" />
                    <label>New Password</label>
                    <input type="password" id="recover-new-pass" placeholder="Enter new password" />
                    <button class="btn-main" onclick="recoverCustomer()" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; margin-top: 0.5rem;">Reset Password & Login ✓</button>
                    <div style="text-align: center; margin-top: 0.75rem;">
                        <a onclick="switchAuthMode('signin')" style="font-size: 0.75rem; color: var(--text-muted); cursor: pointer;">Back to Sign In</a>
                    </div>
                </div>
            </div>
            
            <div id="dashboard-section" class="card hidden" style="padding: 1rem;">
                <!-- PROFESSIONAL WALLET & BALANCE CARD -->
                <div class="wallet-card">
                    <div class="wallet-top-row">
                        <span class="tier-badge" id="customer-tier-badge">Classic Member</span>
                        <button class="refresh-balance-btn" onclick="triggerRefreshBalance()">🔄 Refresh</button>
                    </div>
                    <div class="wallet-balance-label">Your Balance</div>
                    <div class="wallet-balance-number" id="points-val">0</div>
                    <div class="cashback-badge" id="client-cashback-badge">⚡ 10% Bill Cashback Active</div>
                </div>
                
                <div>
                    <div class="rewards-section-title">🎁 Redeemable Rewards</div>
                    <div id="customer-rewards-list" class="rewards-list">
                        <div style="text-align:center; color:var(--text-muted); font-size:0.75rem; padding: 1rem 0;">Loading rewards...</div>
                    </div>
                </div>

                <div style="border-top: 1px solid var(--border); margin-top: 0.5rem; padding-top: 0.75rem;">
                    <label id="referral-label-text">👥 Refer a Friend (+50 pts on 1st visit)</label>
                    <input type="tel" id="friend-phone" placeholder="Friend's Phone Number" />
                    <button class="btn-main" onclick="referFriend()" style="background: linear-gradient(135deg, #38bdf8 0%, #0284c7 100%); color: #090d16; padding: 0.6rem; font-size: 0.85rem;">Register Friend</button>
                </div>

                <a href="https://maps.google.com" target="_blank" class="review-link" id="review-link-btn" onclick="claimReview()">
                    ⭐ Leave Google Review (+50 Points)
                </a>

                <div class="dashboard-actions">
                    <button class="dash-action-btn" onclick="openClientPasswordModal()">🔒 Password</button>
                    <button class="logout-btn" onclick="logoutCustomer()">🚪 Log Out</button>
                </div>
            </div>
        </div>

        <!-- CLIENT: MENU & NFC AUTOMATED ORDERING TAB -->
        <div id="tab-menu" class="client-view hidden">
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                    <h3 style="font-size: 1rem; font-weight: 700; color: var(--accent);">📖 Interactive Menu & Order</h3>
                </div>

                <!-- NFC Locked Table Banner or Dropdown -->
                <div id="table-selection-container">
                    <!-- Populated dynamically via JS based on URL param -->
                </div>

                <div id="menu-container" class="menu-grid">
                    <div style="text-align:center; color:var(--text-muted); font-size:0.85rem; padding: 2rem 0;">Loading menu...</div>
                </div>

                <label>🛒 Your App Order Cart:</label>
                <div id="app-cart-box" class="cart-box">
                    <div style="text-align: center; color: var(--text-muted);">Cart is empty. Tap items above to add!</div>
                </div>

                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; font-weight: 800; font-size: 0.95rem;">
                    <span>Total Bill:</span>
                    <span id="app-total-val" style="color: var(--accent);">0.00 MAD</span>
                </div>

                <button class="btn-main" onclick="submitAppOrder()" style="background: var(--success); color: white; padding: 0.75rem; font-size: 0.9rem;">Place App Order & Earn Cashback ✓</button>
            </div>
        </div>

        <!-- OWNER CONTROL CENTER -->
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
                    <h3 style="margin-bottom: 0.4rem; font-size: 0.95rem; font-weight: 700; color: var(--accent);">⚡ Live Orders & Redemptions Queue</h3>
                    <p style="font-size: 0.7rem; color: var(--text-muted); margin-bottom: 0.75rem;">Oldest orders dynamically shift Amber / Red</p>
                    <div id="admin-queue-container" class="queue-grid">
                        <div style="text-align:center; color:var(--text-muted); font-size:0.75rem;">No active orders right now.</div>
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

            <!-- 3. REPORTS -->
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

                    <button class="danger-btn" onclick="openClearReportsModal()" style="width: 100%; padding: 0.6rem; font-size: 0.8rem; border-radius: 10px;">🗑️ Clear / Reset Shift Data</button>
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

            <!-- 7. SETTINGS -->
            <div id="admin-sub-settings" class="admin-section hidden">
                <div class="card">
                    <h3 style="margin-bottom: 0.75rem; font-size: 0.95rem; font-weight: 700; color: var(--accent);">⚙️ Campaign & Shift Settings</h3>
                    
                    <label>Google Review Points</label>
                    <input type="number" id="setting-review-pts" placeholder="e.g. 50" />
                    
                    <label>Friend Referral Points</label>
                    <input type="number" id="setting-referral-pts" placeholder="e.g. 50" />
                    
                    <label>Cashback Percentage (%)</label>
                    <input type="number" step="0.5" id="setting-cb-pct" placeholder="e.g. 10" />

                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 0.85rem;">
                        <div>
                            <label>Shift Open Time</label>
                            <input type="time" id="setting-open-time" value="07:00" />
                        </div>
                        <div>
                            <label>Shift Close Time</label>
                            <input type="time" id="setting-close-time" value="00:00" />
                        </div>
                    </div>

                    <button class="btn-main" onclick="saveCampaignSettings()" style="background: var(--accent); color: #090d16; padding: 0.7rem; font-size: 0.85rem; margin-bottom: 1rem;">Save Campaign Settings ✓</button>

                    <div style="border-top: 1px solid var(--border); padding-top: 0.75rem;">
                        <label style="color: var(--primary);">🔒 Change Owner Password</label>
                        <input type="password" id="admin-old-pass" placeholder="Current Admin Password" />
                        <input type="password" id="admin-new-pass" placeholder="New Admin Password" />
                        <button class="btn-main" onclick="changeAdminPassword()" style="background: var(--primary); color: #090d16; padding: 0.6rem; font-size: 0.8rem;">Update Admin Password</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- MODALS -->
    <div id="client-password-modal" class="modal">
        <div class="modal-content">
            <h3 style="font-size: 1.1rem; font-weight: 700; color: var(--accent); margin-bottom: 0.4rem;">Change Password</h3>
            <p style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 1rem;">Update your account password securely:</p>
            <label style="text-align: left;">Current Password</label>
            <input type="password" id="client-old-pass" placeholder="Current password" />
            <label style="text-align: left;">New Password</label>
            <input type="password" id="client-new-pass" placeholder="New password" />
            <label style="text-align: left;">Repeat New Password</label>
            <input type="password" id="client-repeat-pass" placeholder="Confirm new password" />
            <button class="btn-main" onclick="submitClientPasswordChange()" style="margin-bottom: 0.5rem; margin-top: 0.5rem;">Save New Password ✓</button>
            <button class="close-modal" onclick="document.getElementById('client-password-modal').style.display='none'">Cancel</button>
        </div>
    </div>

    <div id="clear-reports-modal" class="modal">
        <div class="modal-content">
            <h3 style="font-size: 1.1rem; font-weight: 700; color: var(--danger); margin-bottom: 0.4rem;">Reset Shift Data?</h3>
            <p style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 1.25rem;">This will permanently wipe all daily orders and cashback logs for the current shift. Are you sure?</p>
            <button class="btn-main" onclick="executeClearReports()" style="background: var(--danger); color: white; margin-bottom: 0.5rem;">Yes, Clear Shift Data</button>
            <button class="close-modal" onclick="document.getElementById('clear-reports-modal').style.display='none'">Cancel</button>
        </div>
    </div>

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
        let appCart = {};
        let menuItemsCache = [];
        let lockedTableNumber = '1';
        
        window.onload = function() {
            loadRestaurantSettings();
            
            const urlParams = new URLSearchParams(window.location.search);
            const tableParam = urlParams.get('table');
            const tableContainer = document.getElementById('table-selection-container');
            
            if(tableParam) {
                lockedTableNumber = tableParam.trim();
                tableContainer.innerHTML = `
                    <div class="table-badge-locked">
                        <span>📍 NFC Scanned Table:</span>
                        <span style="font-size: 0.95rem; font-weight: 800; color: white; background: var(--primary); padding: 2px 10px; border-radius: 6px;">Table ${lockedTableNumber}</span>
                    </div>
                `;
            } else {
                tableContainer.innerHTML = `
                    <label>Select Your Table #</label>
                    <select id="app-table-num" style="padding: 8px; font-size: 0.85rem; margin-bottom: 0.85rem;">
                        <option value="1">Table 1</option>
                        <option value="2">Table 2</option>
                        <option value="3">Table 3</option>
                        <option value="4">Table 4</option>
                        <option value="VIP">VIP Table</option>
                    </select>
                `;
            }

            if(urlParams.get('mode') === 'admin') {
                document.getElementById('admin-login-modal').style.display = 'flex';
            } else {
                loadMenu();
            }
        };

        function switchAuthMode(mode) {
            document.getElementById('form-signin').classList.add('hidden');
            document.getElementById('form-register').classList.add('hidden');
            document.getElementById('form-recover').classList.add('hidden');
            document.getElementById('btn-toggle-signin').classList.remove('active');
            document.getElementById('btn-toggle-register').classList.remove('active');

            if(mode === 'signin') {
                document.getElementById('btn-toggle-signin').classList.add('active');
                document.getElementById('form-signin').classList.remove('hidden');
            } else if(mode === 'register') {
                document.getElementById('btn-toggle-register').classList.add('active');
                document.getElementById('form-register').classList.remove('hidden');
            } else if(mode === 'recover') {
                document.getElementById('form-recover').classList.remove('hidden');
            }
        }

        async function loginOwner() {
            const user = document.getElementById('owner-user').value.trim();
            const pass = document.getElementById('owner-pass').value.trim();
            if(!user || !pass) { showToast('Enter username and password', true); return; }
            try {
                const res = await fetch('/api/admin/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ username: user, password: pass })
                });
                const data = await res.json();
                if(res.ok) {
                    document.getElementById('admin-login-modal').style.display = 'none';
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
                    showToast('Owner authorized successfully!');
                } else {
                    showToast(data.detail || 'Invalid login', true);
                }
            } catch(e) {
                showToast('Connection error', true);
            }
        }

        async function changeAdminPassword() {
            const oldPass = document.getElementById('admin-old-pass').value.trim();
            const newPass = document.getElementById('admin-new-pass').value.trim();
            if(!oldPass || !newPass) { showToast('Fill all password fields', true); return; }
            try {
                const res = await fetch('/api/admin/change-password', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ username: 'admin', old_password: oldPass, new_password: newPass })
                });
                const data = await res.json();
                if(res.ok) {
                    showToast(data.message);
                    document.getElementById('admin-old-pass').value = '';
                    document.getElementById('admin-new-pass').value = '';
                } else {
                    showToast(data.detail || 'Failed to update', true);
                }
            } catch(e) {
                showToast('Connection error', true);
            }
        }

        async function registerCustomer() {
            const phone = document.getElementById('reg-phone').value.trim();
            const password = document.getElementById('reg-password').value.trim();
            const pin = document.getElementById('reg-pin').value.trim();
            if(!phone || !password || !pin) { showToast('Fill all registration fields', true); return; }
            try {
                const res = await fetch('/api/customer/register', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ phone_number: phone, password: password, recovery_pin: pin, restaurant_slug: currentSlug })
                });
                const data = await res.json();
                if(res.ok) {
                    showToast('Account registered successfully! Now sign in.');
                    switchAuthMode('signin');
                    document.getElementById('signin-phone').value = phone;
                    document.getElementById('reg-phone').value = '';
                    document.getElementById('reg-password').value = '';
                    document.getElementById('reg-pin').value = '';
                } else {
                    showToast(data.detail || 'Registration failed', true);
                }
            } catch(e) {
                showToast('Connection error', true);
            }
        }

        async function loginCustomer() {
            const phone = document.getElementById('signin-phone').value.trim();
            const password = document.getElementById('signin-password').value.trim();
            if(!phone || !password) { showToast('Enter phone and password', true); return; }
            currentPhone = phone;
            try {
                const res = await fetch('/api/customer/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ phone_number: phone, password: password, restaurant_slug: currentSlug })
                });
                const data = await res.json();
                if(res.ok) {
                    document.getElementById('points-val').innerText = data.points_balance;
                    document.getElementById('login-section').classList.add('hidden');
                    document.getElementById('dashboard-section').classList.remove('hidden');
                    loadCustomerData();
                    showToast('Welcome back!');
                } else {
                    showToast(data.detail || 'Login failed', true);
                }
            } catch(e) {
                showToast('Connection error', true);
            }
        }

        async function recoverCustomer() {
            const phone = document.getElementById('recover-phone').value.trim();
            const pin = document.getElementById('recover-pin').value.trim();
            const newPassword = document.getElementById('recover-new-pass').value.trim();
            if(!phone || !pin || !newPassword) { showToast('Fill all recovery fields', true); return; }
            currentPhone = phone;
            try {
                const res = await fetch('/api/customer/recover', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ phone_number: phone, recovery_pin: pin, new_password: newPassword, restaurant_slug: currentSlug })
                });
                const data = await res.json();
                if(res.ok) {
                    document.getElementById('points-val').innerText = data.points_balance;
                    document.getElementById('login-section').classList.add('hidden');
                    document.getElementById('dashboard-section').classList.remove('hidden');
                    loadCustomerData();
                    showToast('Password reset & signed in!');
                } else {
                    showToast(data.detail || 'Recovery failed', true);
                }
            } catch(e) {
                showToast('Connection error', true);
            }
        }

        async function triggerRefreshBalance() {
            if(!currentPhone) return;
            try {
                const res = await fetch('/api/customer/refresh-balance/' + encodeURIComponent(currentPhone));
                const data = await res.json();
                if(res.ok) {
                    document.getElementById('points-val').innerText = data.points_balance;
                    showToast('Balance updated successfully!');
                } else {
                    showToast('Could not refresh balance', true);
                }
            } catch(e) {
                showToast('Connection error', true);
            }
        }

        function openClientPasswordModal() {
            document.getElementById('client-old-pass').value = '';
            document.getElementById('client-new-pass').value = '';
            document.getElementById('client-repeat-pass').value = '';
            document.getElementById('client-password-modal').style.display = 'flex';
        }

        async function submitClientPasswordChange() {
            const oldPass = document.getElementById('client-old-pass').value.trim();
            const newPass = document.getElementById('client-new-pass').value.trim();
            const repeatPass = document.getElementById('client-repeat-pass').value.trim();
            if(!oldPass || !newPass || !repeatPass) { showToast('Fill all fields', true); return; }
            if(newPass !== repeatPass) { showToast('New passwords do not match', true); return; }

            try {
                const res = await fetch('/api/customer/change-password', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ phone_number: currentPhone, old_password: oldPass, new_password: newPass, restaurant_slug: currentSlug })
                });
                const data = await res.json();
                if(res.ok) {
                    document.getElementById('client-password-modal').style.display = 'none';
                    showToast('Password updated successfully!');
                } else {
                    showToast(data.detail || 'Update failed', true);
                }
            } catch(e) {
                showToast('Connection error', true);
            }
        }

        function logoutCustomer() {
            currentPhone = '';
            document.getElementById('dashboard-section').classList.add('hidden');
            document.getElementById('login-section').classList.remove('hidden');
            document.getElementById('signin-phone').value = '';
            document.getElementById('signin-password').value = '';
            switchAuthMode('signin');
            showToast('Logged out successfully.');
        }

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
                if(currentPhone) {
                    loadCustomerData();
                    triggerRefreshBalance();
                }
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

        async function loadMenu() {
            try {
                const res = await fetch('/api/menu/' + currentSlug);
                menuItemsCache = await res.json();
                const container = document.getElementById('menu-container');
                if(!menuItemsCache || menuItemsCache.length === 0) {
                    container.innerHTML = '<div style="text-align:center; color:var(--text-muted); padding: 2rem 0;">No items available.</div>';
                    return;
                }
                container.innerHTML = menuItemsCache.map(item => `
                    <div class="menu-card">
                        <img src="${item.image_url || 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=500'}" class="menu-img" onclick="openModal('${item.image_url || 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=500'}', '${item.name.replace(/'/g, "\\\\'")}', '${item.price}')" />
                        <div class="menu-info" onclick="openModal('${item.image_url || 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=500'}', '${item.name.replace(/'/g, "\\\\'")}', '${item.price}')">
                            <div class="menu-cat">${item.category}</div>
                            <div class="menu-name">${item.name}</div>
                            <div class="menu-price">${item.price}</div>
                        </div>
                        <button class="add-cart-mini" onclick="addToAppCart(${item.id})">+ Add</button>
                    </div>
                `).join('');
            } catch(e) {}
        }

        function addToAppCart(id) {
            const item = menuItemsCache.find(i => i.id === id);
            if(!item) return;
            if(!appCart[id]) {
                appCart[id] = { name: item.name, priceNum: parseFloat(item.price) || 50, qty: 0 };
            }
            appCart[id].qty++;
            renderAppCart();
            showToast(`Added ${item.name} to cart`);
        }

        function renderAppCart() {
            const box = document.getElementById('app-cart-box');
            const keys = Object.keys(appCart);
            if(keys.length === 0) {
                box.innerHTML = '<div style="text-align: center; color: var(--text-muted);">Cart is empty. Tap items above to add!</div>';
                document.getElementById('app-total-val').innerText = '0.00 MAD';
                return;
            }
            let total = 0;
            box.innerHTML = keys.map(k => {
                const c = appCart[k];
                const lineTotal = c.priceNum * c.qty;
                total += lineTotal;
                return `<div class="cart-row"><span>${c.qty}x ${c.name}</span><span>${lineTotal.toFixed(2)} MAD</span></div>`;
            }).join('');
            document.getElementById('app-total-val').innerText = total.toFixed(2) + ' MAD';
        }

        async function submitAppOrder() {
            const keys = Object.keys(appCart);
            if(keys.length === 0) { showToast('Your order cart is empty!', true); return; }
            
            const tableSelect = document.getElementById('app-table-num');
            const tableNum = tableSelect ? tableSelect.value : lockedTableNumber;

            let summaryParts = [];
            let total = 0;
            keys.forEach(k => {
                const c = appCart[k];
                summaryParts.push(`${c.qty}x ${c.name}`);
                total += c.priceNum * c.qty;
            });

            try {
                const res = await fetch('/api/admin/pos/order', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        restaurant_slug: currentSlug,
                        items_summary: summaryParts.join(', '),
                        total_amount: total,
                        table_number: tableNum,
                        customer_phone: currentPhone
                    })
                });
                const data = await res.json();
                if(res.ok) {
                    showToast(`🎉 Order placed for Table ${tableNum}! Sent to kitchen.`);
                    appCart = {};
                    renderAppCart();
                    triggerRefreshBalance();
                } else {
                    showToast(data.detail || 'Order failed', true);
                }
            } catch(e) {
                showToast('Connection error', true);
            }
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
                    body: JSON.stringify({ restaurant_slug: currentSlug, items_summary: summaryParts.join(', '), total_amount: total, table_number: 'Counter', customer_phone: '' })
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

        function openClearReportsModal() {
            document.getElementById('clear-reports-modal').style.display = 'flex';
        }

        async function executeClearReports() {
            document.getElementById('clear-reports-modal').style.display = 'none';
            try {
                const res = await fetch('/api/admin/' + currentSlug + '/reports/clear', { method: 'POST' });
                if(res.ok) {
                    showToast('Shift data cleared successfully!');
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
                    container.innerHTML = '<div style="text-align:center; color:var(--text-muted); font-size:0.75rem; padding: 1rem 0;">☕ All quiet! No pending orders or redemptions.</div>';
                    return;
                }
                
                const now = new Date();

                container.innerHTML = data.queue.map(item => {
                    const orderDate = new Date(item.raw_time);
                    const diffMinutes = Math.floor((now - orderDate) / 60000);

                    let urgencyClass = 'urgency-normal';
                    let timeBadgeText = `${diffMinutes}m ago`;
                    let badgeColor = 'var(--text-muted)';
                    
                    if(diffMinutes >= 5 && diffMinutes < 10) {
                        urgencyClass = 'urgency-orange';
                        timeBadgeText = `⚠️ ${diffMinutes}m waiting (Attention)`;
                        badgeColor = '#f97316';
                    } else if(diffMinutes >= 10) {
                        urgencyClass = 'urgency-red';
                        timeBadgeText = `🚨 ${diffMinutes}m waiting (URGENT!)`;
                        badgeColor = 'var(--danger)';
                    }

                    return `
                        <div class="redemption-card ${urgencyClass}">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                <span style="background: var(--primary); color: #090d16; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.75rem;">Table ${item.table_number}</span>
                                <span style="font-size: 0.75rem; font-weight: 800; color: ${badgeColor};">${timeBadgeText}</span>
                            </div>
                            <div style="font-weight: 700; font-size: 0.95rem; color: var(--accent); margin-bottom: 2px;">👤 ${item.customer_name} (${item.customer_phone || 'Walk-in'})</div>
                            <div style="font-weight: 700; font-size: 0.9rem; color: var(--text-main);">${item.reward_item}</div>
                            ${item.security_pin !== 'APP' ? `<div class="pin-display">PIN: ${item.security_pin}</div>` : '<div style="font-size: 0.7rem; color: var(--success); font-weight: 700; margin: 4px 0;">⚡ NFC App Order - Automatic Cashback Applied</div>'}
                            <button class="btn-main" onclick="fulfillRedemption(${item.id})" style="background: var(--success); color: white; padding: 8px; font-size: 0.8rem; margin-top: 6px;">Mark Fulfilled ✓</button>
                        </div>
                    `;
                }).join('');
            } catch(e) {}
        }

        async function fulfillRedemption(id) {
            await fetch('/api/admin/redemptions/fulfill/' + id, { method: 'POST' });
            showToast('Order/Redemption marked fulfilled!');
            loadAdminQueue();
        }

        async function loadCustomerData() {
            try {
                const res = await fetch('/api/rewards/' + currentSlug);
                const rewards = await res.json();
                const container = document.getElementById('customer-rewards-list');
                if(!rewards || rewards.length === 0) {
                    container.innerHTML = '<div style="color:var(--text-muted); font-size:0.75rem; text-align:center;">No rewards available.</div>';
                    return;
                }
                container.innerHTML = rewards.map(r => `
                    <div class="reward-item">
                        <img src="${r.image_url || 'https://images.unsplash.com/photo-1551024709-8f23befc6f87?w=500'}" class="reward-thumb" />
                        <div class="reward-info">
                            <div class="reward-title">${r.title}</div>
                            <div class="reward-cost">⭐ ${r.points_required} Points</div>
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
            loadMenu();
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
            loadMenu();
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

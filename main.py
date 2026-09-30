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

app = FastAPI(title="smartTable Enterprise POS & Loyalty Engine", version="12.9.1")

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
        CREATE TABLE IF NOT EXISTS restaurant_workers (
            id SERIAL PRIMARY KEY,
            worker_id VARCHAR(50) UNIQUE,
            password VARCHAR(100),
            recovery_pin VARCHAR(10),
            worker_name VARCHAR(100),
            restaurant_slug VARCHAR(50) DEFAULT 'default-restaurant'
        );
    """)
    cur.execute("INSERT INTO restaurant_workers (worker_id, password, recovery_pin, worker_name, restaurant_slug) VALUES ('staff1', 'staff123', '1234', 'Default Worker', 'default-restaurant') ON CONFLICT (worker_id) DO NOTHING;")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS table_assignments (
            id SERIAL PRIMARY KEY,
            restaurant_slug VARCHAR(50),
            table_number VARCHAR(20) UNIQUE,
            worker_id VARCHAR(50),
            worker_name VARCHAR(100),
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS menu_items (
            id SERIAL PRIMARY KEY,
            restaurant_slug VARCHAR(50),
            category VARCHAR(50),
            name VARCHAR(100),
            price VARCHAR(50),
            image_url TEXT
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS custom_rewards (
            id SERIAL PRIMARY KEY,
            restaurant_slug VARCHAR(50),
            title VARCHAR(100),
            points_required INT,
            image_url TEXT
        );
    """)

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
            table_number VARCHAR(20) DEFAULT '1',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS worker_tips (
            id SERIAL PRIMARY KEY,
            restaurant_slug VARCHAR(50),
            worker_id VARCHAR(50),
            worker_name VARCHAR(100),
            tip_amount DECIMAL(10,2),
            table_number VARCHAR(20),
            customer_phone VARCHAR(20),
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

class WorkerLogin(BaseModel):
    worker_id: str
    password: str

class WorkerCreate(BaseModel):
    worker_id: str
    password: str
    recovery_pin: str
    worker_name: str
    restaurant_slug: str = "default-restaurant"

class TableClaim(BaseModel):
    restaurant_slug: str = "default-restaurant"
    table_number: str
    worker_id: str

class AdminPasswordChange(BaseModel):
    username: str = "admin"
    old_password: str
    new_password: str

class POSOrderCreate(BaseModel):
    restaurant_slug: str = "default-restaurant"
    items_summary: str
    total_amount: float
    table_number: str = "1"
    customer_phone: str = ""
    tip_amount: float = 0.00
    worker_id: str = ""

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

class ReviewReward(BaseModel):
    phone_number: str
    restaurant_slug: str = "default-restaurant"

class ReferralCreate(BaseModel):
    referrer_phone: str
    friend_phone: str
    restaurant_slug: str = "default-restaurant"

@app.get("/api/health")
def health_check():
    return {"status": "online", "database": "neon-postgres", "brand": "smartTable"}

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
            raise HTTPException(status_code=401, detail="Incorrect password.")

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
        return {"status": "success", "role": "admin", "message": "Owner login authorized."}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/change-password")
def change_admin_password(data: AdminPasswordChange):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM owner_admin WHERE username = %s;", (data.username,))
        admin = cur.fetchone()
        if not admin or admin["password"] != data.old_password.strip():
            raise HTTPException(status_code=401, detail="Current admin password incorrect.")
        
        cur.execute("UPDATE owner_admin SET password = %s WHERE username = %s;", (data.new_password.strip(), data.username))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Admin password updated successfully!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/worker/login")
def worker_login(data: WorkerLogin):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM restaurant_workers WHERE worker_id = %s;", (data.worker_id.strip(),))
        worker = cur.fetchone()
        cur.close()
        conn.close()
        if not worker or worker["password"] != data.password.strip():
            raise HTTPException(status_code=401, detail="Invalid staff credentials.")
        return {"status": "success", "role": "worker", "worker_id": worker["worker_id"], "worker_name": worker["worker_name"], "message": "Worker login authorized."}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/workers/{slug}")
def get_restaurant_workers(slug: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, worker_id, worker_name, recovery_pin FROM restaurant_workers WHERE restaurant_slug = %s ORDER BY id DESC;", (slug,))
        workers = cur.fetchall()
        cur.close()
        conn.close()
        return workers or []
    except Exception:
        return []

@app.post("/api/admin/workers/add")
def add_restaurant_worker(data: WorkerCreate):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM restaurant_workers WHERE worker_id = %s;", (data.worker_id.strip(),))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Worker ID already exists.")
        
        cur.execute(
            "INSERT INTO restaurant_workers (worker_id, password, recovery_pin, worker_name, restaurant_slug) VALUES (%s, %s, %s, %s, %s);",
            (data.worker_id.strip(), data.password.strip(), data.recovery_pin.strip(), data.worker_name.strip(), data.restaurant_slug)
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Worker account created successfully!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/admin/workers/{worker_id_str}")
def delete_restaurant_worker(worker_id_str: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM restaurant_workers WHERE worker_id = %s;", (worker_id_str,))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Worker account deleted successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/worker/claim-table")
def claim_table_worker(data: TableClaim):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT worker_name FROM restaurant_workers WHERE worker_id = %s;", (data.worker_id,))
        w = cur.fetchone()
        if not w:
            raise HTTPException(status_code=404, detail="Worker not found.")
        w_name = w["worker_name"]

        cur.execute("""
            INSERT INTO table_assignments (restaurant_slug, table_number, worker_id, worker_name, updated_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (table_number) 
            DO UPDATE SET worker_id = EXCLUDED.worker_id, worker_name = EXCLUDED.worker_name, updated_at = CURRENT_TIMESTAMP;
        """, (data.restaurant_slug, str(data.table_number), data.worker_id, w_name))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": f"Table {data.table_number} claimed by {w_name}!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/table/assigned-server/{slug}/{table_num}")
def get_table_server(slug: str, table_num: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT worker_id, worker_name FROM table_assignments WHERE restaurant_slug = %s AND table_number = %s;", (slug, str(table_num)))
        assign = cur.fetchone()
        cur.close()
        conn.close()
        if not assign:
            return {"worker_id": "", "worker_name": "General Staff"}
        return {"worker_id": assign["worker_id"], "worker_name": assign["worker_name"]}
    except Exception:
        return {"worker_id": "", "worker_name": "General Staff"}

@app.post("/api/admin/pos/order")
def create_pos_order(data: POSOrderCreate):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO pos_orders (restaurant_slug, items_summary, total_amount, table_number) VALUES (%s, %s, %s, %s);",
            (data.restaurant_slug, data.items_summary, data.total_amount, str(data.table_number))
        )

        w_id = data.worker_id.strip()
        w_name = "Walk-in Staff"
        if w_id:
            cur.execute("SELECT worker_name FROM restaurant_workers WHERE worker_id = %s;", (w_id,))
            w_row = cur.fetchone()
            if w_row:
                w_name = w_row["worker_name"]

        if data.tip_amount > 0:
            cur.execute(
                "INSERT INTO worker_tips (restaurant_slug, worker_id, worker_name, tip_amount, table_number, customer_phone) VALUES (%s, %s, %s, %s, %s, %s);",
                (data.restaurant_slug, w_id or "general", w_name, data.tip_amount, str(data.table_number), data.customer_phone)
            )

        cur.execute(
            """INSERT INTO redemption_queue 
               (restaurant_slug, table_number, customer_name, customer_phone, reward_item, security_pin, status) 
               VALUES (%s, %s, %s, %s, %s, %s, 'pending');""",
            (data.restaurant_slug, str(data.table_number), f"Server: {w_name}", data.customer_phone or "Walk-in", f"ORDER: {data.items_summary} ({data.total_amount:.2f} MAD) {f'+ Tip: {data.tip_amount:.2f} MAD' if data.tip_amount > 0 else ''}", "POS")
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
        return {"status": "success", "message": "Order submitted and sent to kitchen successfully!"}
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

        cur.execute("SELECT COALESCE(SUM(tip_amount), 0) as total_tips FROM worker_tips WHERE restaurant_slug = %s AND created_at >= CURRENT_DATE;", (slug,))
        tips_summary = cur.fetchone()

        cur.execute("""
            SELECT worker_name, COALESCE(SUM(tip_amount), 0) as worker_tips_total, COUNT(*) as tips_count 
            FROM worker_tips 
            WHERE restaurant_slug = %s AND created_at >= CURRENT_DATE 
            GROUP BY worker_name ORDER BY worker_tips_total DESC;
        """, (slug,))
        worker_tips_breakdown = cur.fetchall()

        cur.execute("""
            SELECT id, table_number, items_summary, total_amount, created_at 
            FROM pos_orders 
            WHERE restaurant_slug = %s AND created_at >= CURRENT_DATE 
            ORDER BY created_at DESC;
        """, (slug,))
        orders_history = cur.fetchall()

        cur.execute("""
            SELECT id, table_number, worker_name, tip_amount, customer_phone, created_at 
            FROM worker_tips 
            WHERE restaurant_slug = %s AND created_at >= CURRENT_DATE 
            ORDER BY created_at DESC;
        """, (slug,))
        tips_history = cur.fetchall()

        cur.close()
        conn.close()

        formatted_orders = [{
            "id": o["id"],
            "table_number": o["table_number"],
            "items_summary": o["items_summary"],
            "total_amount": float(o["total_amount"]),
            "time": o["created_at"].strftime("%H:%M:%S")
        } for o in orders_history]

        formatted_tips = [{
            "id": t["id"],
            "table_number": t["table_number"],
            "worker_name": t["worker_name"],
            "tip_amount": float(t["tip_amount"]),
            "customer_phone": t["customer_phone"] or "Walk-in",
            "time": t["created_at"].strftime("%H:%M:%S")
        } for t in tips_history]

        formatted_worker_tips = [{
            "worker_name": wt["worker_name"],
            "total_tips": float(wt["worker_tips_total"]),
            "tips_count": wt["tips_count"]
        } for wt in worker_tips_breakdown]

        return {
            "total_revenue": float(summary["revenue"]),
            "orders_count": summary["orders_count"],
            "cashback_points_issued": cb["pts"],
            "total_tips_collected": float(tips_summary["total_tips"] or 0),
            "worker_tips_breakdown": formatted_worker_tips,
            "orders_history": formatted_orders,
            "tips_history": formatted_tips
        }
    except Exception:
        return {
            "total_revenue": 0.0, "orders_count": 0, "cashback_points_issued": 0, 
            "total_tips_collected": 0.0, "worker_tips_breakdown": [], "orders_history": [], "tips_history": []
        }

@app.post("/api/admin/{slug}/reports/clear")
def clear_daily_reports(slug: str, data: dict):
    password = data.get("password", "").strip()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM owner_admin WHERE username = 'admin';")
        admin = cur.fetchone()
        if not admin or admin["password"] != password:
            raise HTTPException(status_code=401, detail="Incorrect admin password.")

        cur.execute("DELETE FROM pos_orders WHERE restaurant_slug = %s;", (slug,))
        cur.execute("DELETE FROM cashback_audit_log WHERE restaurant_slug = %s;", (slug,))
        cur.execute("DELETE FROM worker_tips WHERE restaurant_slug = %s;", (slug,))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "All shift reports, orders, and tip logs cleared successfully."}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/{slug}/analytics")
def get_analytics_insights(slug: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN date_trunc('month', created_at) = date_trunc('month', CURRENT_DATE) THEN total_amount ELSE 0 END), 0) as current_month_rev,
                COALESCE(SUM(CASE WHEN date_trunc('month', created_at) = date_trunc('month', CURRENT_DATE - INTERVAL '1 month') THEN total_amount ELSE 0 END), 0) as prev_month_rev
            FROM pos_orders 
            WHERE restaurant_slug = %s;
        """, (slug,))
        rev_data = cur.fetchone()
        
        cur.execute("SELECT phone_number, points_balance, has_purchased FROM customers ORDER BY points_balance DESC LIMIT 5;")
        vips = cur.fetchall()
        
        cur.execute("SELECT COUNT(*) as total, SUM(CASE WHEN has_purchased = TRUE THEN 1 ELSE 0 END) as buyers FROM customers;")
        cust_stats = cur.fetchone()
        cur.close()
        conn.close()
        
        curr_rev = float(rev_data["current_month_rev"] or 0)
        prev_rev = float(rev_data["prev_month_rev"] or 0)
        
        if prev_rev > 0:
            growth_pct = round(((curr_rev - prev_rev) / prev_rev) * 100, 1)
        else:
            growth_pct = 100.0 if curr_rev > 0 else 0.0

        total_cust = cust_stats["total"] or 1
        buyers = cust_stats["buyers"] or 0
        return_rate = round((buyers / total_cust) * 100, 1)
        
        vip_list = [{"phone": v["phone_number"], "points": v["points_balance"]} for v in vips]
        return {
            "monthly_revenue": curr_rev,
            "monthly_growth_percentage": growth_pct,
            "total_customers": total_cust,
            "return_rate": return_rate,
            "vip_spenders": vip_list
        }
    except Exception:
        return {"monthly_revenue": 0.0, "monthly_growth_percentage": 0.0, "total_customers": 0, "return_rate": 0.0, "vip_spenders": []}

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

@app.get("/api/settings/{slug}")
def get_restaurant_settings(slug: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM restaurant_settings WHERE restaurant_slug = %s;", (slug,))
        s = cur.fetchone()
        cur.close()
        conn.close()
        if not s:
            return {
                "review_points": 50,
                "referral_points": 50,
                "cashback_percentage": 10.00,
                "open_time": "07:00",
                "close_time": "00:00"
            }
        return {
            "review_points": s["review_points"],
            "referral_points": s["referral_points"],
            "cashback_percentage": float(s["cashback_percentage"]),
            "open_time": s["open_time"],
            "close_time": s["close_time"]
        }
    except Exception:
        return {
            "review_points": 50,
            "referral_points": 50,
            "cashback_percentage": 10.00,
            "open_time": "07:00",
            "close_time": "00:00"
        }

@app.post("/api/admin/settings/update")
def update_restaurant_settings(data: dict):
    slug = data.get("restaurant_slug", "default-restaurant")
    review_pts = data.get("review_points", 50)
    ref_pts = data.get("referral_points", 50)
    cb_pct = data.get("cashback_percentage", 10.0)
    open_t = data.get("open_time", "07:00")
    close_t = data.get("close_time", "00:00")

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO restaurant_settings (restaurant_slug, review_points, referral_points, cashback_percentage, open_time, close_time)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (restaurant_slug)
            DO UPDATE SET review_points = EXCLUDED.review_points,
                          referral_points = EXCLUDED.referral_points,
                          cashback_percentage = EXCLUDED.cashback_percentage,
                          open_time = EXCLUDED.open_time,
                          close_time = EXCLUDED.close_time;
        """, (slug, review_pts, ref_pts, cb_pct, open_t, close_t))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Campaign settings updated successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
def serve_mobile_frontend():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>smartTable | Enterprise POS & Loyalty</title>
    <link rel="icon" type="image/png" href="https://img.icons8.com/color/48/qr-code.png">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Cairo:wght@400;600;700;800&display=swap" rel="stylesheet">
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
        body.lang-ar * { font-family: 'Cairo', sans-serif !important; direction: rtl; text-align: right; }
        body { background-color: var(--bg-deep); color: var(--text-main); display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 1rem; background-image: radial-gradient(circle at 50% 0%, #1e293b 0%, var(--bg-deep) 70%); }
        
        .app-frame { width: 100%; max-width: 480px; background: var(--surface); border-radius: var(--radius); padding: 1.25rem 1.25rem 1.5rem 1.25rem; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7); border: 1px solid var(--border); position: relative; overflow: hidden; }
        
        .brand-header { text-align: center; margin-bottom: 0.85rem; }
        .logo { font-size: 1.6rem; font-weight: 800; color: var(--text-main); letter-spacing: -0.5px; }
        .logo span { color: var(--accent); }
        .brand-tag { font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 2px; margin-top: 2px; font-weight: 600; }
        
        .nav-tabs { display: flex; background: var(--bg-deep); border-radius: 12px; padding: 4px; margin-bottom: 1rem; border: 1px solid var(--border); }
        .tab-btn { flex: 1; padding: 0.45rem; text-align: center; border-radius: 9px; font-size: 0.75rem; font-weight: 600; color: var(--text-muted); cursor: pointer; border: none; background: transparent; transition: all 0.3s; }
        .tab-btn.active { background: var(--surface-card); color: var(--text-main); box-shadow: 0 4px 12px rgba(0,0,0,0.3); border: 1px solid var(--border); }
        
        .card { background: var(--surface-card); border-radius: 16px; padding: 1.15rem; margin-bottom: 0.85rem; border: 1px solid var(--border); position: relative; }
        
        label { display: block; font-size: 0.73rem; font-weight: 600; color: var(--text-muted); margin-bottom: 0.35rem; text-transform: uppercase; letter-spacing: 0.5px; }
        input, select, textarea { width: 100%; padding: 0.75rem 0.9rem; border-radius: 10px; border: 1px solid var(--border); background: var(--bg-deep); color: white; font-size: 0.88rem; margin-bottom: 0.75rem; outline: none; transition: border-color 0.2s; resize: none; }
        input:focus, select:focus, textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
        
        .btn-main { width: 100%; padding: 0.75rem; border-radius: 10px; border: none; background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: #090d16; font-weight: 700; font-size: 0.9rem; cursor: pointer; transition: transform 0.1s; box-shadow: 0 4px 14px var(--accent-glow); }
        .btn-main:active { transform: scale(0.98); }
        
        .hidden { display: none !important; }
        
        .wallet-card { background: linear-gradient(135deg, rgba(26, 38, 66, 0.9) 0%, rgba(15, 23, 42, 0.95) 100%); border: 1px solid rgba(245, 158, 11, 0.25); border-radius: 14px; padding: 1.1rem; text-align: center; margin-bottom: 1rem; position: relative; box-shadow: 0 8px 24px rgba(0,0,0,0.3); }
        .wallet-top-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem; }
        .tier-badge { background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); color: var(--accent); padding: 3px 8px; border-radius: 20px; font-size: 0.65rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; }
        .refresh-balance-btn { background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.3); color: var(--primary); padding: 3px 8px; border-radius: 20px; font-size: 0.65rem; font-weight: 700; cursor: pointer; display: inline-flex; align-items: center; gap: 3px; transition: all 0.2s; }
        .refresh-balance-btn:hover { background: rgba(56, 189, 248, 0.25); border-color: var(--primary); }
        
        .wallet-balance-label { font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1.5px; font-weight: 700; margin-top: 0.2rem; }
        .wallet-balance-number { font-size: 2.5rem; font-weight: 800; color: var(--success); letter-spacing: -1px; line-height: 1.1; margin: 0.15rem 0 0.4rem 0; text-shadow: 0 2px 10px rgba(16, 185, 129, 0.2); }
        .cashback-badge { display: inline-block; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); color: var(--success); padding: 3px 10px; border-radius: 20px; font-size: 0.7rem; font-weight: 700; }

        .rewards-section-title { font-size: 0.73rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.5rem; display: flex; align-items: center; gap: 6px; }
        .rewards-list { display: flex; flex-direction: column; gap: 0.6rem; max-height: 160px; overflow-y: auto; margin-bottom: 0.85rem; padding-right: 3px; }
        
        .reward-item { display: flex; align-items: center; justify-content: space-between; background: var(--bg-deep); padding: 0.6rem 0.75rem; border-radius: 12px; border: 1px solid var(--border); gap: 0.65rem; transition: border-color 0.2s; }
        .reward-item:hover { border-color: rgba(245, 158, 11, 0.4); }
        .reward-thumb { width: 42px; height: 42px; border-radius: 8px; object-fit: cover; background: var(--surface); border: 1px solid var(--border); }
        .reward-info { flex: 1; text-align: left; }
        .reward-title { font-size: 0.85rem; font-weight: 700; color: var(--text-main); margin-bottom: 2px; }
        .reward-cost { font-size: 0.7rem; color: var(--accent); font-weight: 700; display: inline-flex; align-items: center; gap: 3px; }
        
        .redeem-btn { background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; border: none; padding: 6px 12px; border-radius: 8px; font-weight: 700; font-size: 0.72rem; cursor: pointer; box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25); }

        .review-link { display: flex; align-items: center; justify-content: center; gap: 6px; text-align: center; margin-top: 0.65rem; padding: 0.7rem; background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.3); color: var(--accent); border-radius: 10px; text-decoration: none; font-weight: 700; font-size: 0.78rem; }

        .pos-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; max-height: 160px; overflow-y: auto; margin-bottom: 0.85rem; padding-right: 2px; }
        .pos-item-card { background: var(--bg-deep); border: 1px solid var(--border); border-radius: 10px; padding: 8px; text-align: center; cursor: pointer; transition: all 0.2s; }
        .pos-item-card:hover { border-color: var(--accent); background: var(--surface); }
        .pos-img { width: 38px; height: 38px; border-radius: 8px; object-fit: cover; margin-bottom: 4px; }
        .pos-title { font-size: 0.73rem; font-weight: 700; color: var(--text-main); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .pos-price { font-size: 0.68rem; font-weight: 800; color: var(--accent); }

        .cart-box { background: var(--bg-deep); border: 1px solid var(--border); border-radius: 10px; padding: 8px; margin-bottom: 0.75rem; max-height: 110px; overflow-y: auto; font-size: 0.78rem; }
        .cart-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 3px; }
        .cart-controls { display: flex; align-items: center; gap: 5px; }
        .cart-btn-qty { background: var(--surface); border: 1px solid var(--border); color: white; width: 20px; height: 20px; border-radius: 5px; font-weight: bold; cursor: pointer; display: flex; align-items: center; justify-content: center; }

        .menu-grid { display: flex; flex-direction: column; gap: 0.65rem; max-height: 230px; overflow-y: auto; padding-right: 2px; margin-bottom: 0.85rem; }
        .menu-card { display: flex; align-items: center; background: var(--bg-deep); border-radius: 12px; padding: 0.65rem; border: 1px solid var(--border); gap: 0.75rem; cursor: pointer; }
        .menu-img { width: 45px; height: 45px; border-radius: 9px; object-fit: cover; background: var(--surface); }
        .menu-info { flex: 1; }
        .menu-name { font-size: 0.85rem; font-weight: 700; color: var(--text-main); margin-bottom: 2px; }
        .menu-cat { font-size: 0.6rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700; }
        .menu-price { font-size: 0.8rem; font-weight: 800; color: var(--accent); }
        .add-cart-mini { background: var(--accent); color: #090d16; border: none; padding: 5px 9px; border-radius: 7px; font-weight: 800; font-size: 0.72rem; cursor: pointer; }

        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(9, 13, 22, 0.85); backdrop-filter: blur(8px); justify-content: center; align-items: center; padding: 1.5rem; }
        .modal-content { background: var(--surface); padding: 1.5rem; border-radius: 20px; max-width: 380px; width: 100%; text-align: center; border: 1px solid var(--border); box-shadow: 0 25px 50px rgba(0,0,0,0.8); }
        .modal-img { width: 100%; height: 150px; border-radius: 12px; object-fit: cover; margin-bottom: 0.85rem; border: 1px solid var(--border); }
        .close-modal { background: var(--border); color: var(--text-main); border: none; padding: 0.65rem; border-radius: 10px; cursor: pointer; font-weight: 700; width: 100%; margin-top: 0.4rem; }

        .voucher-code-box { font-size: 2rem; font-weight: 800; color: var(--accent); background: var(--bg-deep); padding: 0.65rem; border-radius: 10px; border: 1px dashed var(--accent); margin: 0.65rem 0; letter-spacing: 2px; }

        .admin-item-row { display: flex; justify-content: space-between; align-items: center; background: var(--bg-deep); padding: 0.65rem; border-radius: 10px; margin-bottom: 0.45rem; font-size: 0.8rem; border: 1px solid var(--border); }
        .danger-btn { background: rgba(239, 68, 68, 0.15); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); padding: 5px 9px; border-radius: 7px; cursor: pointer; font-weight: 700; font-size: 0.72rem; }

        #toast-banner { position: fixed; bottom: 25px; left: 50%; transform: translateX(-50%) translateY(120px); background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 10px 20px; border-radius: 30px; font-weight: 700; font-size: 0.82rem; box-shadow: 0 15px 30px rgba(16, 185, 129, 0.4); z-index: 9999; transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1); display: flex; align-items: center; gap: 8px; border: 1px solid rgba(255,255,255,0.2); }
        #toast-banner.show { transform: translateX(-50%) translateY(0); }
        #toast-banner.error { background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%); }

        /* CENTERED SUBNAV */
        .admin-subnav { display: grid; gap: 4px; background: var(--bg-deep); padding: 6px; border-radius: 14px; margin-bottom: 1rem; border: 1px solid var(--border); overflow-x: auto; box-shadow: inset 0 2px 6px rgba(0,0,0,0.4); }
        .admin-sub-btn { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 52px; padding: 4px 2px; text-align: center; border-radius: 10px; font-size: 0.58rem; font-weight: 700; color: var(--text-muted); cursor: pointer; border: none; background: transparent; transition: all 0.25s ease; }
        .admin-sub-btn span.nav-icon { font-size: 1.05rem; margin-bottom: 3px; display: block; line-height: 1; text-align: center; width: 100%; }
        .admin-sub-btn span.nav-text { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 100%; display: block; text-align: center; }
        .admin-sub-btn.active { background: var(--surface-card); color: var(--accent); border: 1px solid var(--border); box-shadow: 0 4px 14px rgba(0,0,0,0.4); }
        
        .queue-grid { display: grid; grid-template-columns: 1fr; gap: 10px; margin-top: 8px; }
        .redemption-card { background: var(--bg-deep); border-left: 5px solid var(--success); padding: 12px; border-radius: 10px; border: 1px solid var(--border); }
        .pin-display { background: var(--surface); padding: 6px; text-align: center; font-size: 1.2rem; font-weight: 800; color: var(--success); letter-spacing: 3px; border-radius: 6px; margin: 6px 0; border: 1px dashed var(--border); }
        
        .floor-card { background: var(--bg-deep); border: 1px solid var(--border); border-radius: 10px; padding: 10px; text-align: center; }
        .floor-card.status-green { border-color: rgba(16, 185, 129, 0.4); background: linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, var(--bg-deep) 100%); }
        .floor-card.status-orange { border-color: rgba(249, 115, 22, 0.5); background: linear-gradient(135deg, rgba(249, 115, 22, 0.15) 0%, var(--bg-deep) 100%); }

        .auth-sub-toggle { display: flex; gap: 6px; margin-bottom: 0.85rem; }
        .auth-toggle-btn { flex: 1; background: var(--bg-deep); border: 1px solid var(--border); color: var(--text-muted); padding: 7px; border-radius: 7px; font-size: 0.72rem; font-weight: 700; cursor: pointer; }
        .auth-toggle-btn.active { background: var(--surface); color: var(--accent); border-color: var(--accent); }
        
        .form-footer-actions { display: flex; justify-content: space-between; align-items: center; margin-top: -0.35rem; margin-bottom: 0.75rem; }
        .form-footer-actions a, .form-footer-actions span { font-size: 0.75rem; font-weight: 700; cursor: pointer; }

        .dashboard-actions { display: flex; justify-content: space-between; align-items: center; margin-top: 0.75rem; border-top: 1px solid var(--border); padding-top: 0.75rem; }
        .dash-action-btn { background: rgba(56, 189, 248, 0.15); color: var(--primary); border: 1px solid rgba(56, 189, 248, 0.3); padding: 5px 10px; border-radius: 7px; font-size: 0.72rem; font-weight: 700; cursor: pointer; }
        .logout-btn { background: rgba(239, 68, 68, 0.15); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); padding: 5px 12px; border-radius: 7px; font-size: 0.72rem; font-weight: 700; cursor: pointer; }
        
        .table-badge-locked { display: flex; align-items: center; justify-content: space-between; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); color: var(--primary); padding: 10px 14px; border-radius: 12px; font-size: 0.85rem; font-weight: 700; margin-bottom: 0.85rem; box-shadow: 0 4px 12px rgba(56, 189, 248, 0.1); }
        .table-badge-unlocked { background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); color: var(--danger); padding: 12px; border-radius: 12px; font-size: 0.82rem; font-weight: 700; text-align: center; margin-bottom: 0.85rem; line-height: 1.4; box-shadow: 0 4px 12px rgba(239, 68, 68, 0.1); }

        .app-footer-bar { display: flex; justify-content: space-between; align-items: center; width: 100%; max-width: 480px; margin-top: 1rem; padding: 0 0.5rem; font-size: 0.75rem; color: var(--text-muted); gap: 1rem; }
        .app-footer-bar a { color: var(--primary); text-decoration: none; font-weight: 700; white-space: nowrap; }
        .lang-selector { background: var(--surface); border: 1px solid var(--border); color: var(--text-main); padding: 6px 14px; border-radius: 8px; font-size: 0.78rem; font-weight: 700; outline: none; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.3); transition: border-color 0.2s; }
        .lang-selector:hover { border-color: var(--accent); }
    </style>
</head>
<body>
    <div id="toast-banner">✓ Action completed successfully!</div>

    <!-- OWNER ADMIN LOGIN MODAL -->
    <div id="admin-login-modal" class="modal">
        <div class="modal-content">
            <div class="logo" style="margin-bottom: 0.4rem;">smart<span>Table</span></div>
            <h3 style="font-size: 1.05rem; font-weight: 700; color: var(--accent); margin-bottom: 0.2rem;">Owner Control Center</h3>
            <p style="font-size: 0.72rem; color: var(--text-muted); margin-bottom: 1rem;">Enter manager username & password</p>
            
            <label>Username</label>
            <input type="text" id="owner-user" placeholder="admin" value="admin" />
            
            <label>Password</label>
            <input type="password" id="owner-pass" placeholder="admin123" />
            
            <button class="btn-main" onclick="loginOwner()" style="margin-top: 0.4rem;">Authorize & Open Dashboard</button>
            <button class="close-modal" onclick="openWorkerLoginFromAdmin()" style="margin-top: 0.4rem; background: rgba(56, 189, 248, 0.15); color: var(--primary); border: 1px solid rgba(56, 189, 248, 0.3);">Switch to Staff Portal Login</button>
            <button class="close-modal" onclick="window.location.href='/'" style="margin-top: 0.4rem;">Return to Client App</button>
        </div>
    </div>

    <!-- STAFF WORKER LOGIN MODAL -->
    <div id="worker-login-modal" class="modal">
        <div class="modal-content">
            <div class="logo" style="margin-bottom: 0.4rem;">smart<span>Table</span></div>
            <h3 style="font-size: 1.05rem; font-weight: 700; color: var(--primary); margin-bottom: 0.2rem;">Staff Worker Portal</h3>
            <p style="font-size: 0.72rem; color: var(--text-muted); margin-bottom: 1rem;">Authorized staff access only</p>
            
            <label>Worker ID</label>
            <input type="text" id="worker-id-input" placeholder="e.g. staff1" />
            
            <label>Password</label>
            <input type="password" id="worker-pass-input" placeholder="Worker password" />
            
            <button class="btn-main" onclick="loginWorker()" style="background: linear-gradient(135deg, #38bdf8 0%, #0284c7 100%); color: #090d16; margin-top: 0.4rem;">Authorize Staff Portal</button>
            <button class="close-modal" onclick="openAdminLoginFromWorker()" style="margin-top: 0.4rem; background: rgba(245, 158, 11, 0.15); color: var(--accent); border: 1px solid rgba(245, 158, 11, 0.3);">Return to Admin Login</button>
            <button class="close-modal" onclick="window.location.href='/'" style="margin-top: 0.4rem;">Return to Client App</button>
        </div>
    </div>

    <div class="app-frame">
        <div class="brand-header">
            <div class="logo">smart<span>Table</span></div>
            <div class="brand-tag" id="app-subtitle">Enterprise POS & Loyalty</div>
        </div>
        
        <!-- CLIENT TABS -->
        <div class="nav-tabs" id="client-nav">
            <button class="tab-btn active" onclick="switchTab('rewards')" id="tab-btn-rewards">🏆 Rewards</button>
            <button class="tab-btn" onclick="switchTab('menu')" id="tab-btn-menu">📖 Menu & Order</button>
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
                    <h3 style="margin-bottom: 0.75rem; font-size: 0.9rem; font-weight: 700;" id="txt-signin-title">Customer Sign In</h3>
                    <label id="lbl-phone">Phone Number</label>
                    <input type="tel" id="signin-phone" placeholder="e.g., 0612345678" />
                    <label id="lbl-password">Password</label>
                    <input type="password" id="signin-password" placeholder="Your password" />
                    
                    <div class="form-footer-actions">
                        <a onclick="switchAuthMode('recover')" id="txt-forgot" style="color: var(--primary);">Forgot Password?</a>
                        <a href="/?mode=worker" style="color: var(--accent); text-decoration: none;" id="txt-staff-inline">🔒 Staff Portal</a>
                    </div>

                    <button class="btn-main" onclick="loginCustomer()" id="btn-signin-action">Sign In to Account</button>
                </div>

                <!-- REGISTER FORM -->
                <div id="form-register" class="hidden">
                    <h3 style="margin-bottom: 0.75rem; font-size: 0.9rem; font-weight: 700; color: var(--accent);" id="txt-reg-title">Create New Account</h3>
                    <label id="lbl-reg-phone">Phone Number</label>
                    <input type="tel" id="reg-phone" placeholder="e.g., 0612345678" />
                    <label id="lbl-reg-pass">Password</label>
                    <input type="password" id="reg-password" placeholder="Create a password" />
                    <label id="lbl-reg-pin">Recovery PIN (4-Digits for Reset)</label>
                    <input type="password" id="reg-pin" placeholder="e.g., 1234" maxlength="4" />
                    <button class="btn-main" onclick="registerCustomer()" style="background: linear-gradient(135deg, #38bdf8 0%, #0284c7 100%); color: #090d16; margin-top: 0.4rem;" id="btn-reg-action">Register & Create Account</button>
                </div>

                <!-- RECOVER FORM -->
                <div id="form-recover" class="hidden">
                    <h3 style="margin-bottom: 0.75rem; font-size: 0.9rem; font-weight: 700; color: var(--primary);" id="txt-rec-title">PIN Recovery & Reset</h3>
                    <label id="lbl-rec-phone">Phone Number</label>
                    <input type="tel" id="recover-phone" placeholder="e.g., 0612345678" />
                    <label id="lbl-rec-pin">4-Digit Recovery PIN</label>
                    <input type="password" id="recover-pin" placeholder="e.g., 1234" maxlength="4" />
                    <label id="lbl-rec-new">New Password</label>
                    <input type="password" id="recover-new-pass" placeholder="Enter new password" />
                    <button class="btn-main" onclick="recoverCustomer()" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; margin-top: 0.4rem;" id="btn-rec-action">Reset Password & Login ✓</button>
                    <div style="text-align: center; margin-top: 0.65rem;">
                        <a onclick="switchAuthMode('signin')" style="font-size: 0.72rem; color: var(--text-muted); cursor: pointer;" id="txt-back-signin">Back to Sign In</a>
                    </div>
                </div>
            </div>
            
            <div id="dashboard-section" class="card hidden" style="padding: 1rem;">
                <div class="wallet-card">
                    <div class="wallet-top-row">
                        <span class="tier-badge" id="customer-tier-badge">Classic Member</span>
                        <button class="refresh-balance-btn" onclick="triggerRefreshBalance()" id="btn-refresh">🔄 Refresh</button>
                    </div>
                    <div class="wallet-balance-label" id="lbl-balance">Your Balance</div>
                    <div class="wallet-balance-number" id="points-val">0</div>
                    <div class="cashback-badge" id="client-cashback-badge">⚡ 10% Bill Cashback Active</div>
                </div>
                
                <div>
                    <div class="rewards-section-title" id="lbl-rewards-title">🎁 Redeemable Rewards</div>
                    <div id="customer-rewards-list" class="rewards-list">
                        <div style="text-align:center; color:var(--text-muted); font-size:0.72rem; padding: 1rem 0;">Loading rewards...</div>
                    </div>
                </div>

                <div style="border-top: 1px solid var(--border); margin-top: 0.4rem; padding-top: 0.65rem;">
                    <label id="referral-label-text">👥 Refer a Friend (+50 pts on 1st visit)</label>
                    <input type="tel" id="friend-phone" placeholder="Friend's Phone Number" />
                    <button class="btn-main" onclick="referFriend()" style="background: linear-gradient(135deg, #38bdf8 0%, #0284c7 100%); color: #090d16; padding: 0.55rem; font-size: 0.8rem;" id="btn-refer">Register Friend</button>
                </div>

                <a href="https://maps.google.com" target="_blank" class="review-link" id="review-link-btn" onclick="claimReview()">
                    ⭐ Leave Google Review (+50 Points)
                </a>

                <div class="dashboard-actions">
                    <button class="dash-action-btn" onclick="openClientPasswordModal()" id="btn-client-pwd">🔒 Password</button>
                    <button class="logout-btn" onclick="logoutCustomer()" id="btn-client-logout">🚪 Log Out</button>
                </div>
            </div>
        </div>

        <!-- CLIENT: MENU & NFC AUTOMATED ORDERING TAB -->
        <div id="tab-menu" class="client-view hidden">
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.65rem;">
                    <h3 style="font-size: 0.95rem; font-weight: 700; color: var(--accent);" id="txt-menu-title">📖 Interactive Menu & Order</h3>
                </div>

                <div id="table-selection-container"></div>
                <div id="server-badge-container" style="margin-bottom: 0.75rem;"></div>

                <div id="menu-container" class="menu-grid">
                    <div style="text-align:center; color:var(--text-muted); font-size:0.8rem; padding: 2rem 0;">Loading menu...</div>
                </div>

                <label id="lbl-cart-title">🛒 Your App Order Cart:</label>
                <div id="app-cart-box" class="cart-box">
                    <div style="text-align: center; color: var(--text-muted);" id="txt-empty-cart">Cart is empty. Tap items above to add!</div>
                </div>

                <label id="lbl-tip-amount" style="margin-top: 0.5rem;">💸 Tip Your Dedicated Server (MAD):</label>
                <input type="number" step="5" id="app-tip-input" placeholder="e.g., 10 MAD" value="0" />

                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.65rem; font-weight: 800; font-size: 0.9rem;">
                    <span id="lbl-total">Total Bill (Incl. Tip):</span>
                    <span id="app-total-val" style="color: var(--accent);">0.00 MAD</span>
                </div>

                <button class="btn-main" id="place-order-btn" onclick="submitAppOrder()" style="background: var(--success); color: white; padding: 0.7rem; font-size: 0.85rem;">Place App Order & Earn Cashback ✓</button>
            </div>
        </div>

        <!-- OWNER / WORKER CONTROL CENTER -->
        <div id="tab-admin" class="hidden">
            <div class="admin-subnav" id="admin-subnav-container">
                <button class="admin-sub-btn active" onclick="switchAdminSub('queue')" id="sub-btn-queue">
                    <span class="nav-icon">🔥</span><span class="nav-text" id="nav-t-queue">Queue</span>
                </button>
                <button class="admin-sub-btn" onclick="switchAdminSub('menu')" id="sub-btn-menu">
                    <span class="nav-icon">📖</span><span class="nav-text" id="nav-t-menu">Menu</span>
                </button>
                <button class="admin-sub-btn" onclick="switchAdminSub('reports')" id="sub-btn-reports">
                    <span class="nav-icon">📊</span><span class="nav-text" id="nav-t-reports">Reports</span>
                </button>
                <button class="admin-sub-btn" onclick="switchAdminSub('orders_history')" id="sub-btn-orders_history">
                    <span class="nav-icon">📜</span><span class="nav-text" id="nav-t-orders_history">Orders</span>
                </button>
                <button class="admin-sub-btn" onclick="switchAdminSub('tips_history')" id="sub-btn-tips_history">
                    <span class="nav-icon">💵</span><span class="nav-text" id="nav-t-tips_history">Tips</span>
                </button>
                <button class="admin-sub-btn" onclick="switchAdminSub('rewards')" id="sub-btn-rewards">
                    <span class="nav-icon">🎁</span><span class="nav-text" id="nav-t-rewards">Rewards</span>
                </button>
                <button class="admin-sub-btn" onclick="switchAdminSub('pos')" id="sub-btn-pos">
                    <span class="nav-icon">🛒</span><span class="nav-text" id="nav-t-pos">POS</span>
                </button>
                <button class="admin-sub-btn" onclick="switchAdminSub('floor')" id="sub-btn-floor">
                    <span class="nav-icon">🪑</span><span class="nav-text" id="nav-t-floor">Floor</span>
                </button>
                <button class="admin-sub-btn" onclick="switchAdminSub('analytics')" id="sub-btn-analytics">
                    <span class="nav-icon">📈</span><span class="nav-text" id="nav-t-analytics">Insights</span>
                </button>
                <button class="admin-sub-btn" onclick="switchAdminSub('settings')" id="sub-btn-settings">
                    <span class="nav-icon">⚙️</span><span class="nav-text" id="nav-t-settings">Settings</span>
                </button>
            </div>

            <!-- 1. QUEUE -->
            <div id="admin-sub-queue" class="admin-section">
                <div class="card">
                    <h3 style="margin-bottom: 0.35rem; font-size: 0.9rem; font-weight: 700; color: var(--accent);" id="txt-live-queue">⚡ Live Orders & Redemptions Queue</h3>
                    <p style="font-size: 0.68rem; color: var(--text-muted); margin-bottom: 0.65rem;" id="txt-queue-desc">Real-time kitchen orders & customer redemptions</p>
                    <div id="admin-queue-container" class="queue-grid">
                        <div style="text-align:center; color:var(--text-muted); font-size:0.72rem;" id="txt-no-orders">No active orders right now.</div>
                    </div>
                </div>
            </div>

            <!-- 2. MENU -->
            <div id="admin-sub-menu" class="admin-section hidden admin-restricted">
                <div class="card">
                    <h3 style="margin-bottom: 0.65rem; font-size: 0.9rem; font-weight: 700; color: var(--accent);" id="txt-admin-menu-title">📖 Menu Management</h3>
                    <label id="lbl-adm-cat">Category</label>
                    <input type="text" id="admin-cat" placeholder="e.g., Burgers, Drinks" />
                    <label id="lbl-adm-name">Item Name</label>
                    <input type="text" id="admin-name" placeholder="Item Name" />
                    <label id="lbl-adm-price">Price (MAD)</label>
                    <input type="text" id="admin-price" placeholder="e.g. 65" />
                    <label id="lbl-adm-img">Image URL (Optional)</label>
                    <input type="text" id="admin-img" placeholder="https://..." />
                    <button class="btn-main" onclick="addAdminMenu()" style="margin-bottom: 0.85rem; padding: 0.55rem; font-size: 0.78rem;" id="btn-add-item">+ Add Menu Item</button>
                    
                    <label id="lbl-adm-existing">Existing Items:</label>
                    <div id="admin-menu-list" style="max-height: 140px; overflow-y: auto;"></div>
                </div>
            </div>

            <!-- 3. REPORTS -->
            <div id="admin-sub-reports" class="admin-section hidden admin-restricted">
                <div class="card" style="text-align: center;">
                    <h3 style="margin-bottom: 0.35rem; font-size: 0.9rem; font-weight: 700; color: var(--accent);" id="txt-rep-title">📊 Daily Shift Z-Report</h3>
                    <div id="shift-label-display" style="font-size: 0.68rem; color: var(--success); margin-bottom: 0.75rem; font-weight: 700;">Active Shift: 07:00 - 00:00</div>
                    
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 0.85rem;">
                        <div style="background: var(--bg-deep); padding: 9px; border-radius: 10px; border: 1px solid var(--border);">
                            <div style="font-size: 0.62rem; color: var(--text-muted); text-transform: uppercase;" id="lbl-rep-rev">Total Revenue</div>
                            <div id="rep-revenue" style="font-size: 1.1rem; font-weight: 800; color: var(--success);">0 MAD</div>
                        </div>
                        <div style="background: var(--bg-deep); padding: 9px; border-radius: 10px; border: 1px solid var(--border);">
                            <div style="font-size: 0.62rem; color: var(--text-muted); text-transform: uppercase;" id="lbl-rep-orders">Orders Sold</div>
                            <div id="rep-orders" style="font-size: 1.1rem; font-weight: 800; color: var(--primary);">0</div>
                        </div>
                    </div>

                    <div style="background: var(--bg-deep); padding: 9px; border-radius: 10px; border: 1px solid var(--border); margin-bottom: 0.85rem; text-align: left;">
                        <div style="font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px;" id="lbl-rep-tips">💵 Total Tips & Worker Breakdown</div>
                        <div id="rep-tips-total" style="font-size: 1rem; font-weight: 800; color: var(--accent); margin-bottom: 6px;">0 MAD</div>
                        <div id="rep-worker-tips-list" style="font-size: 0.75rem; color: var(--text-main);">Loading worker tips...</div>
                    </div>

                    <button class="danger-btn" onclick="openClearReportsModal()" style="width: 100%; padding: 0.55rem; font-size: 0.78rem; border-radius: 9px;" id="btn-clear-rep">🗑️ Clear / Reset Shift Data</button>
                </div>
            </div>

            <!-- 4. ORDERS HISTORY TAB -->
            <div id="admin-sub-orders_history" class="admin-section hidden">
                <div class="card">
                    <h3 style="margin-bottom: 0.35rem; font-size: 0.9rem; font-weight: 700; color: var(--accent);" id="txt-ord-hist-title">📜 Individual Orders History</h3>
                    <p style="font-size: 0.68rem; color: var(--text-muted); margin-bottom: 0.65rem;" id="txt-ord-hist-desc">Every order recorded separately for this shift</p>
                    <div id="admin-orders-history-list" style="max-height: 240px; overflow-y: auto;">
                        <div style="text-align:center; color:var(--text-muted); font-size:0.72rem;">No orders recorded yet.</div>
                    </div>
                </div>
            </div>

            <!-- 5. TIPS HISTORY TAB -->
            <div id="admin-sub-tips_history" class="admin-section hidden">
                <div class="card">
                    <h3 style="margin-bottom: 0.35rem; font-size: 0.9rem; font-weight: 700; color: var(--accent);" id="txt-tip-hist-title">💵 Individual Tips History & Workers</h3>
                    <p style="font-size: 0.68rem; color: var(--text-muted); margin-bottom: 0.65rem;" id="txt-tip-hist-desc">Every tip tracked separately by worker name</p>
                    <div id="admin-tips-history-list" style="max-height: 240px; overflow-y: auto;">
                        <div style="text-align:center; color:var(--text-muted); font-size:0.72rem;">No tips recorded yet.</div>
                    </div>
                </div>
            </div>

            <!-- 6. REWARDS -->
            <div id="admin-sub-rewards" class="admin-section hidden admin-restricted">
                <div class="card">
                    <h3 style="margin-bottom: 0.65rem; font-size: 0.9rem; font-weight: 700; color: var(--accent);" id="txt-rew-builder-title">🎁 Rewards Builder</h3>
                    <label id="lbl-rew-title">Reward Title</label>
                    <input type="text" id="reward-title-input" placeholder="e.g. Free Gourmet Dessert" />
                    <label id="lbl-rew-cost">Points Required</label>
                    <input type="number" id="reward-cost-input" placeholder="e.g. 100" />
                    <label id="lbl-rew-img">Image URL (Optional)</label>
                    <input type="text" id="reward-img-input" placeholder="https://..." />
                    <button class="btn-main" onclick="addRewardTier()" style="background: #3b82f6; color: white; padding: 0.55rem; font-size: 0.78rem; margin-bottom: 0.85rem;" id="btn-create-rew">+ Create Reward</button>
                    
                    <label id="lbl-rew-configured">Configured Rewards:</label>
                    <div id="admin-rewards-list" style="max-height: 140px; overflow-y: auto;"></div>
                </div>
            </div>

            <!-- 7. POS -->
            <div id="admin-sub-pos" class="admin-section hidden">
                <div class="card">
                    <h3 style="margin-bottom: 0.35rem; font-size: 0.9rem; font-weight: 700; color: var(--accent);" id="txt-pos-title">🛒 Touchscreen POS Builder</h3>
                    <p style="font-size: 0.68rem; color: var(--text-muted); margin-bottom: 0.65rem;" id="txt-pos-desc">Select table & tap items to build and adjust order cart</p>
                    
                    <label id="lbl-pos-table">Select Table Number / Walk-in</label>
                    <select id="pos-table-select">
                        <option value="1">Table 1</option>
                        <option value="2">Table 2</option>
                        <option value="3">Table 3</option>
                        <option value="4">Table 4</option>
                        <option value="5">Table 5</option>
                        <option value="6">Table 6</option>
                        <option value="VIP">VIP Lounge</option>
                        <option value="Counter">Counter / Walk-in</option>
                    </select>

                    <div id="pos-menu-grid" class="pos-grid">
                        <div style="text-align:center; color:var(--text-muted); font-size:0.68rem; grid-column: span 2;">Loading items...</div>
                    </div>

                    <label id="lbl-pos-cart">Order Cart (Use + / - to adjust quantities):</label>
                    <div id="pos-cart-box" class="cart-box">
                        <div style="text-align: center; color: var(--text-muted);" id="txt-pos-empty">Cart is empty</div>
                    </div>

                    <label id="lbl-pos-tip">Optional Tip (MAD):</label>
                    <input type="number" id="pos-tip-input" placeholder="0" value="0" />

                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; font-weight: 800; font-size: 0.9rem;">
                        <span id="lbl-pos-total">Total:</span>
                        <span id="pos-total-val" style="color: var(--accent);">0.00 MAD</span>
                    </div>

                    <button class="btn-main" onclick="confirmPOSOrder()" style="background: var(--success); color: white; padding: 0.65rem; font-size: 0.8rem;" id="btn-confirm-pos">Confirm & Submit Order ✓</button>
                </div>
            </div>

            <!-- FLOOR PLAN VIEW & TABLE CLAIMING -->
            <div id="admin-sub-floor" class="admin-section hidden">
                <div class="card">
                    <h3 style="margin-bottom: 0.35rem; font-size: 0.9rem; font-weight: 700; color: var(--accent);" id="txt-floor-title">🪑 Visual Table Floor Plan & Claiming</h3>
                    <p style="font-size: 0.68rem; color: var(--text-muted); margin-bottom: 0.65rem;" id="txt-floor-desc">Claim tables as staff to receive direct customer tips</p>
                    <div id="admin-floor-grid" style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px;">
                        <div style="text-align:center; color:var(--text-muted); font-size:0.72rem; grid-column: span 2;">Loading floor map...</div>
                    </div>
                </div>
            </div>

            <!-- SMART ANALYTICS & CRM -->
            <div id="admin-sub-analytics" class="admin-section hidden admin-restricted">
                <div class="card">
                    <h3 style="margin-bottom: 0.35rem; font-size: 0.9rem; font-weight: 700; color: var(--accent);" id="txt-analytics-title">📈 Smart Analytics & CRM</h3>
                    <p style="font-size: 0.68rem; color: var(--text-muted); margin-bottom: 0.65rem;" id="txt-analytics-desc">Monthly performance and customer retention</p>
                    
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 0.85rem;">
                        <div style="background: var(--bg-deep); padding: 9px; border-radius: 10px; border: 1px solid var(--border); text-align: center;">
                            <div style="font-size: 0.62rem; color: var(--text-muted); text-transform: uppercase;" id="lbl-ana-month">This Month Revenue</div>
                            <div id="analytics-monthly-rev" style="font-size: 1.05rem; font-weight: 800; color: var(--success);">0 MAD</div>
                        </div>
                        <div style="background: var(--bg-deep); padding: 9px; border-radius: 10px; border: 1px solid var(--border); text-align: center;">
                            <div style="font-size: 0.62rem; color: var(--text-muted); text-transform: uppercase;" id="lbl-ana-growth">Monthly Growth</div>
                            <div id="analytics-growth-pct" style="font-size: 1.05rem; font-weight: 800; color: var(--primary);">+0%</div>
                        </div>
                    </div>

                    <label id="lbl-ana-vip">⭐ Top VIP Spenders Leaderboard:</label>
                    <div id="analytics-vip-list" style="max-height: 120px; overflow-y: auto;">
                        <div style="text-align:center; color:var(--text-muted); font-size:0.72rem;">Loading VIPs...</div>
                    </div>
                </div>
            </div>

            <!-- SETTINGS & STAFF MANAGEMENT -->
            <div id="admin-sub-settings" class="admin-section hidden admin-restricted">
                <div class="card">
                    <h3 style="margin-bottom: 0.65rem; font-size: 0.9rem; font-weight: 700; color: var(--accent);" id="txt-settings-title">⚙️ Campaign, Shift & Staff Settings</h3>
                    
                    <label id="lbl-set-review">Google Review Points</label>
                    <input type="number" id="setting-review-pts" placeholder="e.g. 50" />
                    
                    <label id="lbl-set-referral">Friend Referral Points</label>
                    <input type="number" id="setting-referral-pts" placeholder="e.g. 50" />
                    
                    <label id="lbl-set-cb">Cashback Percentage (%)</label>
                    <input type="number" step="0.5" id="setting-cb-pct" placeholder="e.g. 10" />

                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 0.75rem;">
                        <div>
                            <label id="lbl-set-open">Shift Open</label>
                            <input type="time" id="setting-open-time" value="07:00" />
                        </div>
                        <div>
                            <label id="lbl-set-close">Shift Close</label>
                            <input type="time" id="setting-close-time" value="00:00" />
                        </div>
                    </div>

                    <button class="btn-main" onclick="saveCampaignSettings()" style="background: var(--accent); color: #090d16; padding: 0.65rem; font-size: 0.8rem; margin-bottom: 1rem;" id="btn-save-settings">Save Campaign Settings ✓</button>

                    <div style="border-top: 1px solid var(--border); padding-top: 0.75rem; margin-bottom: 0.75rem;">
                        <label style="color: var(--primary);" id="lbl-set-manage-staff">👥 Manage Staff Workers (Add / Delete)</label>
                        <input type="text" id="new-worker-id" placeholder="Worker ID / Username (e.g. staff2)" />
                        <input type="text" id="new-worker-name" placeholder="Worker Full Name (e.g. Youssef Benali)" />
                        <input type="password" id="new-worker-pass" placeholder="Worker Login Password" />
                        <input type="password" id="new-worker-pin" placeholder="Worker Recovery PIN (4-Digits)" maxlength="4" />
                        <button class="btn-main" onclick="createNewWorker()" style="background: var(--primary); color: #090d16; padding: 0.6rem; font-size: 0.78rem; margin-bottom: 0.75rem;" id="btn-add-staff">+ Create New Worker Account</button>
                        
                        <label id="lbl-set-active-staff">Active Staff Accounts:</label>
                        <div id="admin-workers-list" style="max-height: 120px; overflow-y: auto;">
                            <div style="text-align:center; color:var(--text-muted); font-size:0.72rem;">Loading staff...</div>
                        </div>
                    </div>

                    <div style="border-top: 1px solid var(--border); padding-top: 0.75rem; margin-bottom: 1rem;">
                        <label style="color: var(--accent);" id="lbl-set-change-pwd">🔒 Change Owner Password</label>
                        <input type="password" id="admin-old-pass" placeholder="Current Admin Password" />
                        <input type="password" id="admin-new-pass" placeholder="New Admin Password" />
                        <button class="btn-main" onclick="changeAdminPassword()" style="background: var(--accent); color: #090d16; padding: 0.55rem; font-size: 0.75rem;" id="btn-update-pwd">Update Admin Password</button>
                    </div>
                </div>
            </div>

            <!-- LOGOUT BUTTON -->
            <div style="text-align: center; margin-top: 1rem;">
                <button class="logout-btn" onclick="logoutAdminPanel()" style="width: 100%; padding: 0.7rem; font-size: 0.85rem; border-radius: 12px;" id="btn-admin-logout">🚪 Log Out of Panel</button>
            </div>
        </div>

        <!-- FOOTER BAR -->
        <div class="app-footer-bar">
            <select id="lang-select" class="lang-selector" onchange="changeLanguage(this.value)">
                <option value="en">🇺🇸 EN</option>
                <option value="fr">🇫🇷 FR</option>
                <option value="ar">🇲🇦 AR</option>
            </select>
            <div id="support-text-label">Support: <a href="mailto:contact@smartable.online">contact@smartable.online</a></div>
        </div>
    </div>

    <!-- MODALS -->
    <div id="client-password-modal" class="modal">
        <div class="modal-content">
            <h3 style="font-size: 1.05rem; font-weight: 700; color: var(--accent); margin-bottom: 0.35rem;" id="mod-pwd-title">Change Password</h3>
            <p style="font-size: 0.72rem; color: var(--text-muted); margin-bottom: 0.85rem;" id="mod-pwd-desc">Update your account password securely:</p>
            <label style="text-align: left;" id="mod-pwd-curr">Current Password</label>
            <input type="password" id="client-old-pass" placeholder="Current password" />
            <label style="text-align: left;" id="mod-pwd-new">New Password</label>
            <input type="password" id="client-new-pass" placeholder="New password" />
            <label style="text-align: left;" id="mod-pwd-repeat">Repeat New Password</label>
            <input type="password" id="client-repeat-pass" placeholder="Confirm new password" />
            <button class="btn-main" onclick="submitClientPasswordChange()" style="margin-bottom: 0.4rem; margin-top: 0.4rem;" id="mod-pwd-save">Save New Password ✓</button>
            <button class="close-modal" onclick="document.getElementById('client-password-modal').style.display='none'" id="mod-pwd-cancel">Cancel</button>
        </div>
    </div>

    <div id="clear-reports-modal" class="modal">
        <div class="modal-content">
            <h3 style="font-size: 1.05rem; font-weight: 700; color: var(--danger); margin-bottom: 0.35rem;" id="mod-rep-title">Reset Shift Data?</h3>
            <p style="font-size: 0.72rem; color: var(--text-muted); margin-bottom: 0.85rem;" id="mod-rep-desc">This will permanently wipe daily revenue and cashback logs. Enter your admin password to confirm:</p>
            <input type="password" id="reset-admin-pwd" placeholder="Enter admin password" style="margin-bottom: 0.85rem;" />
            <button class="btn-main" onclick="executeClearReports()" style="background: var(--danger); color: white; margin-bottom: 0.4rem;" id="mod-rep-confirm">Confirm & Wipe Shift</button>
            <button class="close-modal" onclick="document.getElementById('clear-reports-modal').style.display='none'" id="mod-rep-cancel">Cancel</button>
        </div>
    </div>

    <div id="redeem-name-modal" class="modal">
        <div class="modal-content">
            <h3 style="font-size: 0.95rem; font-weight: 700; color: var(--accent); margin-bottom: 0.35rem;" id="mod-claim-title">Claim Reward</h3>
            <p style="font-size: 0.72rem; color: var(--text-muted); margin-bottom: 0.85rem;" id="mod-claim-desc">Please enter your name for the waiter:</p>
            <input type="text" id="customer-name-input" placeholder="e.g., Mohammed Daou" style="margin-bottom: 0.85rem;" />
            <button class="btn-main" onclick="confirmRedeem()" style="margin-bottom: 0.4rem;" id="mod-claim-confirm">Confirm & Get PIN</button>
            <button class="close-modal" onclick="document.getElementById('redeem-name-modal').style.display='none'" id="mod-claim-cancel">Cancel</button>
        </div>
    </div>

    <div id="voucher-modal" class="modal">
        <div class="modal-content">
            <h3 style="font-size: 0.95rem; font-weight: 700; color: var(--success); margin-bottom: 0.2rem;" id="mod-vouch-title">Reward Unlocked!</h3>
            <p style="font-size: 0.72rem; color: var(--text-muted);" id="mod-vouch-desc">Show PIN to waiter:</p>
            <div id="modal-voucher-code" class="voucher-code-box">----</div>
            <img id="modal-voucher-img" class="modal-img" src="" style="height: 110px; margin-bottom: 0.4rem;" />
            <div id="modal-voucher-title" style="font-size: 0.82rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.65rem;"></div>
            <button class="close-modal" onclick="closeVoucherModal()" id="mod-vouch-done">Done</button>
        </div>
    </div>

    <div id="image-modal" class="modal">
        <div class="modal-content">
            <img id="modal-img-tag" class="modal-img" src="" />
            <h3 id="modal-title" style="font-size: 1.05rem; font-weight: 700; margin-bottom: 0.2rem; color: var(--text-main);"></h3>
            <div id="modal-price" style="font-size: 0.95rem; font-weight: 800; color: var(--accent); margin-bottom: 0.4rem;"></div>
            <button class="close-modal" onclick="closeModal()" id="mod-img-close">Close Preview</button>
        </div>
    </div>

    <script>
        let currentPhone = '';
        const currentSlug = 'default-restaurant';
        let selectedRewardId = null;
        let posCart = {};
        let appCart = {};
        let menuItemsCache = [];
        let lockedTableNumber = null;
        let assignedServer = { worker_id: '', worker_name: 'General Staff' };
        let activeQueueCache = [];
        let previousQueueCount = 0;
        let currentLang = 'en';
        let loggedWorkerId = '';

        const translations = {
            en: {
                subtitle: "Enterprise POS & Loyalty",
                tabRewards: "🏆 Rewards",
                tabMenu: "📖 Menu & Order",
                signIn: "Sign In",
                register: "Register",
                customerSignIn: "Customer Sign In",
                phoneNum: "Phone Number",
                password: "Password",
                forgotPwd: "Forgot Password?",
                staffInline: "🔒 Staff Portal",
                signInBtn: "Sign In to Account",
                createAcc: "Create New Account",
                regPin: "Recovery PIN (4-Digits for Reset)",
                regBtn: "Register & Create Account",
                recTitle: "PIN Recovery & Reset",
                recNew: "New Password",
                recBtn: "Reset Password & Login ✓",
                backSignin: "Back to Sign In",
                balance: "Your Balance",
                refresh: "🔄 Refresh",
                rewardsTitle: "🎁 Redeemable Rewards",
                referFriend: "👥 Refer a Friend (+50 pts on 1st visit)",
                registerFriend: "Register Friend",
                leaveReview: "⭐ Leave Google Review (+50 Points)",
                passwordBtn: "🔒 Password",
                logoutBtn: "🚪 Log Out",
                menuTitle: "📖 Interactive Menu & Order",
                yourCart: "🛒 Your App Order Cart:",
                emptyCart: "Cart is empty. Tap items above to add!",
                totalBill: "Total Bill (Incl. Tip):",
                placeOrder: "Place App Order & Earn Cashback ✓",
                navQueue: "Queue",
                navMenu: "Menu",
                navReports: "Reports",
                navOrdersHist: "Orders",
                navTipsHist: "Tips",
                navRewards: "Rewards",
                navPos: "POS",
                navFloor: "Floor",
                navInsights: "Insights",
                navSettings: "Settings",
                liveQueueTitle: "⚡ Live Orders & Redemptions Queue",
                queueDesc: "Real-time kitchen orders & customer redemptions",
                noOrders: "No active orders right now.",
                adminMenuTitle: "📖 Menu Management",
                admCat: "Category",
                admName: "Item Name",
                admPrice: "Price (MAD)",
                admImg: "Image URL (Optional)",
                addItemBtn: "+ Add Menu Item",
                admExisting: "Existing Items:",
                repTitle: "📊 Daily Shift Z-Report",
                repRev: "Total Revenue",
                repOrders: "Orders Sold",
                clearRepBtn: "🗑️ Clear / Reset Shift Data",
                rewBuilderTitle: "🎁 Rewards Builder",
                rewTitle: "Reward Title",
                rewCost: "Points Required",
                rewImg: "Image URL (Optional)",
                createRewBtn: "+ Create Reward",
                rewConfigured: "Configured Rewards:",
                posTitle: "🛒 Touchscreen POS Builder",
                posDesc: "Select table & tap items to build and adjust order cart",
                posTableLbl: "Select Table Number / Walk-in",
                posCartLbl: "Order Cart (Use + / - to adjust quantities):",
                posEmpty: "Cart is empty",
                confirmPos: "Confirm & Submit Order ✓",
                floorTitle: "🪑 Visual Table Floor Plan & Claiming",
                floorDesc: "Claim tables as staff to receive direct customer tips",
                analyticsTitle: "📈 Smart Analytics & CRM",
                analyticsDesc: "Monthly performance and customer retention",
                anaMonth: "This Month Revenue",
                anaGrowth: "Monthly Growth",
                anaVip: "⭐ Top VIP Spenders Leaderboard:",
                settingsTitle: "⚙️ Campaign, Shift & Staff Settings",
                setReview: "Google Review Points",
                setReferral: "Friend Referral Points",
                setCb: "Cashback Percentage (%)",
                setOpen: "Shift Open",
                setClose: "Shift Close",
                saveSettingsBtn: "Save Campaign Settings ✓",
                manageStaffLbl: "👥 Manage Staff Workers (Add / Delete)",
                addStaffBtn: "+ Create New Worker Account",
                activeStaffLbl: "Active Staff Accounts:",
                changePwdLbl: "🔒 Change Owner Password",
                updatePwdBtn: "Update Admin Password",
                adminLogout: "🚪 Log Out of Panel",
                supportLbl: "Support:",
                modPwdTitle: "Change Password",
                modPwdDesc: "Update your account password securely:",
                modPwdCurr: "Current Password",
                modPwdNew: "New Password",
                modPwdRepeat: "Repeat New Password",
                modPwdSave: "Save New Password ✓",
                modPwdCancel: "Cancel",
                modRepTitle: "Reset Shift Data?",
                modRepDesc: "This will permanently wipe daily revenue and cashback logs. Enter your admin password to confirm:",
                modRepConfirm: "Confirm & Wipe Shift",
                modRepCancel: "Cancel",
                modClaimTitle: "Claim Reward",
                modClaimDesc: "Please enter your name for the waiter:",
                modClaimConfirm: "Confirm & Get PIN",
                modClaimCancel: "Cancel",
                modVouchTitle: "Reward Unlocked!",
                modVouchDesc: "Show PIN to waiter:",
                modVouchDone: "Done",
                modImgClose: "Close Preview"
            },
            fr: {
                subtitle: "POS & Fidélité Entreprise",
                tabRewards: "🏆 Récompenses",
                tabMenu: "📖 Menu & Commande",
                signIn: "Connexion",
                register: "Inscription",
                customerSignIn: "Connexion Client",
                phoneNum: "Numéro de Téléphone",
                password: "Mot de Passe",
                forgotPwd: "Mot de passe oublié ?",
                staffInline: "🔒 Portail Staff",
                signInBtn: "Se connecter au compte",
                createAcc: "Créer un Nouveau Compte",
                regPin: "PIN de Récupération (4 chiffres)",
                regBtn: "S'inscrire & Créer le Compte",
                recTitle: "Récupération & Réinitialisation PIN",
                recNew: "Nouveau Mot de Passe",
                recBtn: "Réinitialiser & Connexion ✓",
                backSignin: "Retour à la connexion",
                balance: "Votre Solde",
                refresh: "🔄 Actualiser",
                rewardsTitle: "🎁 Récompenses Échangeables",
                referFriend: "👥 Parrainer un ami (+50 pts)",
                registerFriend: "Enregistrer l'ami",
                leaveReview: "⭐ Laisser un avis Google (+50 Points)",
                passwordBtn: "🔒 Mot de passe",
                logoutBtn: "🚪 Déconnexion",
                menuTitle: "📖 Menu Interactif & Commande",
                yourCart: "🛒 Votre Panier:",
                emptyCart: "Panier vide. Touchez les articles ci-dessus !",
                totalBill: "Total Addition (Tip Incl.) :",
                placeOrder: "Commander & Gagner du Cashback ✓",
                navQueue: "File",
                navMenu: "Menu",
                navReports: "Rapports",
                navOrdersHist: "Commandes",
                navTipsHist: "Pourboires",
                navRewards: "Cadeaux",
                navPos: "Caisse",
                navFloor: "Salle",
                navInsights: "Analyses",
                navSettings: "Paramètres",
                liveQueueTitle: "⚡ File d'attente & Commandes en direct",
                queueDesc: "Commandes de cuisine en temps réel",
                noOrders: "Aucune commande active pour le moment.",
                adminMenuTitle: "📖 Gestion du Menu",
                admCat: "Catégorie",
                admName: "Nom de l'article",
                admPrice: "Prix (MAD)",
                admImg: "URL Image (Optionnel)",
                addItemBtn: "+ Ajouter l'article",
                admExisting: "Articles Existants:",
                repTitle: "📊 Rapport Z Quotidien",
                repRev: "Revenu Total",
                repOrders: "Commandes Vendues",
                clearRepBtn: "🗑️ Réinitialiser les Données",
                rewBuilderTitle: "🎁 Créateur de Récompenses",
                rewTitle: "Titre de la Récompense",
                rewCost: "Points Requis",
                rewImg: "URL Image (Optionnel)",
                createRewBtn: "+ Créer la Récompense",
                rewConfigured: "Récompenses Configurées:",
                posTitle: "🛒 Caisse Tactile",
                posDesc: "Sélectionnez la table et gérez le panier",
                posTableLbl: "Sélectionner la Table",
                posCartLbl: "Panier (Utilisez + / - pour ajuster) :",
                posEmpty: "Panier vide",
                confirmPos: "Confirmer & Soumettre la Commande ✓",
                floorTitle: "🪑 Plan de Salle Visuel & Attribution",
                floorDesc: "Revendiquez les tables pour recevoir les pourboires",
                analyticsTitle: "📈 Analyses & CRM",
                analyticsDesc: "Performance mensuelle et rétention client",
                anaMonth: "Revenu du Mois",
                anaGrowth: "Croissance Mensuelle",
                anaVip: "⭐ Meilleurs Clients VIP :",
                settingsTitle: "⚙️ Paramètres & Personnel",
                setReview: "Points d'Avis Google",
                setReferral: "Points de Parrainage",
                setCb: "Pourcentage de Cashback (%)",
                setOpen: "Ouverture Shift",
                setClose: "Fermeture Shift",
                saveSettingsBtn: "Enregistrer les Paramètres ✓",
                manageStaffLbl: "👥 Gérer les Employés (Ajouter / Supprimer)",
                addStaffBtn: "+ Créer un Compte Employé",
                activeStaffLbl: "Comptes Actifs:",
                changePwdLbl: "🔒 Changer le Mot de Passe Admin",
                updatePwdBtn: "Mettre à jour le Mot de Passe",
                adminLogout: "🚪 Déconnexion du Panneau",
                supportLbl: "Support :",
                modPwdTitle: "Modifier le Mot de Passe",
                modPwdDesc: "Mettez à jour votre mot de passe en toute sécurité :",
                modPwdCurr: "Mot de Passe Actuel",
                modPwdNew: "Nouveau Mot de Passe",
                modPwdRepeat: "Répéter le Nouveau Mot de Passe",
                modPwdSave: "Enregistrer ✓",
                modPwdCancel: "Annuler",
                modRepTitle: "Réinitialiser les Données ?",
                modRepDesc: "Ceci effacera définitivement les revenus et les logs. Entrez votre mot de passe admin :",
                modRepConfirm: "Confirmer & Effacer",
                modRepCancel: "Annuler",
                modClaimTitle: "Réclamer la Récompense",
                modClaimDesc: "Veuillez entrer votre nom pour le serveur :",
                modClaimConfirm: "Confirmer & Obtenir le PIN",
                modClaimCancel: "Annuler",
                modVouchTitle: "Récompense Débloquée !",
                modVouchDesc: "Montrez le PIN au serveur :",
                modVouchDone: "Terminé",
                modImgClose: "Fermer l'aperçu"
            },
            ar: {
                subtitle: "نظام نقاط الولاء وإدارة المطاعم",
                tabRewards: "🏆 المكافآت",
                tabMenu: "📖 القائمة والطلب",
                signIn: "تسجيل الدخول",
                register: "إنشاء حساب",
                customerSignIn: "تسجيل دخول العميل",
                phoneNum: "رقم الهاتف",
                password: "كلمة المرور",
                forgotPwd: "نسيت كلمة المرور؟",
                staffInline: "🔒 بوابة الموظفين",
                signInBtn: "تسجيل الدخول للحساب",
                createAcc: "إنشاء حساب جديد",
                regPin: "رقم الاسترداد السري (4 أرقام)",
                regBtn: "تسجيل وإنشاء الحساب",
                recTitle: "استرداد وإعادة تعيين كلمة المرور",
                recNew: "كلمة المرور الجديدة",
                recBtn: "إعادة التعيين والدخول ✓",
                backSignin: "العودة لتسجيل الدخول",
                balance: "رصيدك الحالي",
                refresh: "🔄 تحديث",
                rewardsTitle: "🎁 المكافآت المتاحة للاستبدال",
                referFriend: "👥 دعوة صديق (+50 نقطة عند الزيارة الأولى)",
                registerFriend: "تسجيل الصديق",
                leaveReview: "⭐ تقييم قوقل (+50 نقطة)",
                passwordBtn: "🔒 كلمة المرور",
                logoutBtn: "🚪 تسجيل الخروج",
                menuTitle: "📖 القائمة التفاعلية والطلب",
                yourCart: "🛒 سلة الطلبات:",
                emptyCart: "السلة فارغة. انقر على الأصناف لإضافتها!",
                totalBill: "المجموع الكلي (مع الإكرامية):",
                placeOrder: "إرسال الطلب واكتساب الكاش باك ✓",
                navQueue: "الطلبات",
                navMenu: "القائمة",
                navReports: "التقارير",
                navOrdersHist: "السجل",
                navTipsHist: "الإكراميات",
                navRewards: "المكافآت",
                navPos: "الكاشير",
                navFloor: "الطاولات",
                navInsights: "التحليلات",
                navSettings: "الإعدادات",
                liveQueueTitle: "⚡ قائمة الطلبات الحية والوجبات الجاهزة",
                queueDesc: "طلبات المطبخ والاسترداد الفوري",
                noOrders: "لا توجد طلبات نشطة حالياً.",
                adminMenuTitle: "📖 إدارة قائمة الطعام",
                admCat: "الفئة",
                admName: "اسم الصنف",
                admPrice: "السعر (درهم)",
                admImg: "رابط الصورة (اختياري)",
                addItemBtn: "+ إضافة صنف للقائمة",
                admExisting: "الأصناف الحالية:",
                repTitle: "📊 تقرير الإيرادات اليومي",
                repRev: "إجمالي الإيرادات",
                repOrders: "الطلبات المباعة",
                clearRepBtn: "🗑️ مسح وتصفير بيانات الوردية",
                rewBuilderTitle: "🎁 صانع المكافآت",
                rewTitle: "عنوان المكافأة",
                rewCost: "النقاط المطلوبة",
                rewImg: "رابط الصورة (اختياري)",
                createRewBtn: "+ إنشاء مكافأة جديدة",
                rewConfigured: "المكافآت المفعلة:",
                posTitle: "🛒 نقطة البيع السريعة للكاشير",
                posDesc: "حدد الطاولة وأضف الأصناف وعدل الكميات بكل سهولة",
                posTableLbl: "اختر الطاولة / سفري",
                posCartLbl: "سلة الطلبات (استخدم + / - للتعديل):",
                posEmpty: "السلة فارغة",
                confirmPos: "تأكيد وإرسال الطلب ✓",
                floorTitle: "🪑 مخطط الطاولات وتسجيل النادل",
                floorDesc: "اختر طاولتك كموظف لتلقي إكراميات العملاء مباشرة",
                analyticsTitle: "📈 التحليلات الذكية وإدارة العملاء",
                analyticsDesc: "الأداء الشهري ومعدل الاحتفاظ بالعملاء",
                anaMonth: "إيرادات هذا الشهر",
                anaGrowth: "النمو الشهري",
                anaVip: "⭐ قائمة كبار العملاء (VIP):",
                settingsTitle: "⚙️ إعدادات الحملات، الورديات والموظفين",
                setReview: "نقاط تقييم قوقل",
                setReferral: "نقاط دعوة الأصدقاء",
                setCb: "نسبة الكاش باك (%)",
                setOpen: "فتح الوردية",
                setClose: "إغلاق الوردية",
                saveSettingsBtn: "حفظ الإعدادات ✓",
                manageStaffLbl: "👥 إدارة موظفي الطاقم (إضافة / حذف)",
                addStaffBtn: "+ إنشاء حساب موظف جديد",
                activeStaffLbl: "حسابات الموظفين النشطة:",
                changePwdLbl: "🔒 تغيير كلمة مرور المالك",
                updatePwdBtn: "تحديث كلمة المرور",
                adminLogout: "🚪 تسجيل الخروج من اللوحة",
                supportLbl: "الدعم الفني:",
                modPwdTitle: "تغيير كلمة المرور",
                modPwdDesc: "قم بتحديث كلمة المرور الخاصة بحسابك بأمان:",
                modPwdCurr: "كلمة المرور الحالية",
                modPwdNew: "كلمة المرور الجديدة",
                modPwdRepeat: "تكرار كلمة المرور الجديدة",
                modPwdSave: "حفظ كلمة المرور الجديدة ✓",
                modPwdCancel: "إلغاء",
                modRepTitle: "تصفير بيانات الوردية؟",
                modRepDesc: "سيؤدي هذا إلى مسح الإيرادات وسجلات الكاش باك نهائياً. أدخل كلمة مرور المدير للتأكيد:",
                modRepConfirm: "تأكيد ومسح الوردية",
                modRepCancel: "إلغاء",
                modClaimTitle: "استبدال المكافأة",
                modClaimDesc: "الرجاء إدخال اسمك للويتر / النادل:",
                modClaimConfirm: "تأكيد وإظهار الرمز السري",
                modClaimCancel: "إلغاء",
                modVouchTitle: "تم إلغاق المكافأة بنجاح!",
                modVouchDesc: "اعرض الرمز السري للويتر:",
                modVouchDone: "تم",
                modImgClose: "إغلاق المعاينة"
            }
        };

        function changeLanguage(lang) {
            currentLang = lang;
            const t = translations[lang];
            const isAr = (lang === 'ar');
            
            if (isAr) {
                document.body.classList.add('lang-ar');
            } else {
                document.body.classList.remove('lang-ar');
            }

            const adminSubnav = document.getElementById('admin-subnav-container');
            if(adminSubnav) {
                const visibleButtons = adminSubnav.querySelectorAll('button:not([style*="display: none"])');
                adminSubnav.style.gridTemplateColumns = `repeat(${visibleButtons.length}, 1fr)`;
            }

            document.getElementById('app-subtitle').innerText = t.subtitle;
            document.getElementById('tab-btn-rewards').innerText = t.tabRewards;
            document.getElementById('tab-btn-menu').innerText = t.tabMenu;
            document.getElementById('txt-staff-inline').innerText = t.staffInline;
            document.getElementById('btn-toggle-signin').innerText = t.signIn;
            document.getElementById('btn-toggle-register').innerText = t.register;
            document.getElementById('txt-signin-title').innerText = t.customerSignIn;
            document.getElementById('lbl-phone').innerText = t.phoneNum;
            document.getElementById('lbl-password').innerText = t.password;
            document.getElementById('txt-forgot').innerText = t.forgotPwd;
            document.getElementById('btn-signin-action').innerText = t.signInBtn;
            document.getElementById('txt-reg-title').innerText = t.createAcc;
            document.getElementById('lbl-reg-phone').innerText = t.phoneNum;
            document.getElementById('lbl-reg-pass').innerText = t.password;
            document.getElementById('lbl-reg-pin').innerText = t.regPin;
            document.getElementById('btn-reg-action').innerText = t.regBtn;
            document.getElementById('txt-rec-title').innerText = t.recTitle;
            document.getElementById('lbl-rec-phone').innerText = t.phoneNum;
            document.getElementById('lbl-rec-pin').innerText = t.regPin;
            document.getElementById('lbl-rec-new').innerText = t.recNew;
            document.getElementById('btn-rec-action').innerText = t.recBtn;
            document.getElementById('txt-back-signin').innerText = t.backSignin;
            document.getElementById('lbl-balance').innerText = t.balance;
            document.getElementById('btn-refresh').innerText = t.refresh;
            document.getElementById('lbl-rewards-title').innerText = t.rewardsTitle;
            document.getElementById('referral-label-text').innerText = t.referFriend;
            document.getElementById('btn-refer').innerText = t.registerFriend;
            document.getElementById('review-link-btn').innerText = t.leaveReview;
            document.getElementById('btn-client-pwd').innerText = t.passwordBtn;
            document.getElementById('btn-client-logout').innerText = t.logoutBtn;
            document.getElementById('txt-menu-title').innerText = t.menuTitle;
            document.getElementById('lbl-cart-title').innerText = t.yourCart;
            document.getElementById('txt-empty-cart').innerText = t.emptyCart;
            document.getElementById('lbl-total').innerText = t.totalBill;
            document.getElementById('place-order-btn').innerText = t.placeOrder;
            
            document.getElementById('nav-t-queue').innerText = t.navQueue;
            document.getElementById('nav-t-menu').innerText = t.navMenu;
            document.getElementById('nav-t-reports').innerText = t.navReports;
            document.getElementById('nav-t-orders_history').innerText = t.navOrdersHist;
            document.getElementById('nav-t-tips_history').innerText = t.navTipsHist;
            document.getElementById('nav-t-rewards').innerText = t.navRewards;
            document.getElementById('nav-t-pos').innerText = t.navPos;
            document.getElementById('nav-t-floor').innerText = t.navFloor;
            document.getElementById('nav-t-analytics').innerText = t.navInsights;
            document.getElementById('nav-t-settings').innerText = t.navSettings;
            
            document.getElementById('txt-live-queue').innerText = t.liveQueueTitle;
            document.getElementById('txt-queue-desc').innerText = t.queueDesc;
            document.getElementById('txt-admin-menu-title').innerText = t.adminMenuTitle;
            document.getElementById('lbl-adm-cat').innerText = t.admCat;
            document.getElementById('lbl-adm-name').innerText = t.admName;
            document.getElementById('lbl-adm-price').innerText = t.admPrice;
            document.getElementById('lbl-adm-img').innerText = t.admImg;
            document.getElementById('btn-add-item').innerText = t.addItemBtn;
            document.getElementById('lbl-adm-existing').innerText = t.admExisting;

            document.getElementById('txt-rep-title').innerText = t.repTitle;
            document.getElementById('lbl-rep-rev').innerText = t.repRev;
            document.getElementById('lbl-rep-orders').innerText = t.repOrders;
            document.getElementById('btn-clear-rep').innerText = t.clearRepBtn;

            document.getElementById('txt-rew-builder-title').innerText = t.rewBuilderTitle;
            document.getElementById('lbl-rew-title').innerText = t.rewTitle;
            document.getElementById('lbl-rew-cost').innerText = t.rewCost;
            document.getElementById('lbl-rew-img').innerText = t.rewImg;
            document.getElementById('btn-create-rew').innerText = t.createRewBtn;
            document.getElementById('lbl-rew-configured').innerText = t.rewConfigured;

            document.getElementById('txt-pos-title').innerText = t.posTitle;
            document.getElementById('txt-pos-desc').innerText = t.posDesc;
            document.getElementById('lbl-pos-table').innerText = t.posTableLbl;
            document.getElementById('lbl-pos-cart').innerText = t.posCartLbl;
            document.getElementById('txt-pos-empty').innerText = t.posEmpty;
            document.getElementById('lbl-pos-total').innerText = t.totalBill.replace(':', '');
            document.getElementById('btn-confirm-pos').innerText = t.confirmPos;

            document.getElementById('txt-floor-title').innerText = t.floorTitle;
            document.getElementById('txt-floor-desc').innerText = t.floorDesc;

            document.getElementById('txt-analytics-title').innerText = t.analyticsTitle;
            document.getElementById('txt-analytics-desc').innerText = t.analyticsDesc;
            document.getElementById('lbl-ana-month').innerText = t.anaMonth;
            document.getElementById('lbl-ana-growth').innerText = t.anaGrowth;
            document.getElementById('lbl-ana-vip').innerText = t.anaVip;

            document.getElementById('txt-settings-title').innerText = t.settingsTitle;
            document.getElementById('lbl-set-review').innerText = t.setReview;
            document.getElementById('lbl-set-referral').innerText = t.setReferral;
            document.getElementById('lbl-set-cb').innerText = t.setCb;
            document.getElementById('lbl-set-open').innerText = t.setOpen;
            document.getElementById('lbl-set-close').innerText = t.setClose;
            document.getElementById('btn-save-settings').innerText = t.saveSettingsBtn;
            document.getElementById('lbl-set-manage-staff').innerText = t.manageStaffLbl;
            document.getElementById('btn-add-staff').innerText = t.addStaffBtn;
            document.getElementById('lbl-set-active-staff').innerText = t.activeStaffLbl;
            document.getElementById('lbl-set-change-pwd').innerText = t.changePwdLbl;
            document.getElementById('btn-update-pwd').innerText = t.updatePwdBtn;
            document.getElementById('btn-admin-logout').innerText = t.adminLogout;

            document.getElementById('mod-pwd-title').innerText = t.modPwdTitle;
            document.getElementById('mod-pwd-desc').innerText = t.modPwdDesc;
            document.getElementById('mod-pwd-curr').innerText = t.modPwdCurr;
            document.getElementById('mod-pwd-new').innerText = t.modPwdNew;
            document.getElementById('mod-pwd-repeat').innerText = t.modPwdRepeat;
            document.getElementById('mod-pwd-save').innerText = t.modPwdSave;
            document.getElementById('mod-pwd-cancel').innerText = t.modPwdCancel;

            document.getElementById('mod-rep-title').innerText = t.modRepTitle;
            document.getElementById('mod-rep-desc').innerText = t.modRepDesc;
            document.getElementById('mod-rep-confirm').innerText = t.modRepConfirm;
            document.getElementById('mod-rep-cancel').innerText = t.modRepCancel;

            document.getElementById('mod-claim-title').innerText = t.modClaimTitle;
            document.getElementById('mod-claim-desc').innerText = t.modClaimDesc;
            document.getElementById('mod-claim-confirm').innerText = t.modClaimConfirm;
            document.getElementById('mod-claim-cancel').innerText = t.modClaimCancel;

            document.getElementById('mod-vouch-title').innerText = t.modVouchTitle;
            document.getElementById('mod-vouch-desc').innerText = t.modVouchDesc;
            document.getElementById('mod-vouch-done').innerText = t.modVouchDone;
            document.getElementById('mod-img-close').innerText = t.modImgClose;
        }

        window.onload = async function() {
            loadRestaurantSettings();
            
            const urlParams = new URLSearchParams(window.location.search);
            const modeParam = urlParams.get('mode');
            const tableParam = urlParams.get('table');
            const tableContainer = document.getElementById('table-selection-container');

            if(modeParam === 'admin') {
                document.getElementById('admin-login-modal').style.display = 'flex';
                document.getElementById('worker-login-modal').style.display = 'none';
            } else if(modeParam === 'worker') {
                document.getElementById('worker-login-modal').style.display = 'flex';
                document.getElementById('admin-login-modal').style.display = 'none';
            }
            
            if(tableParam) {
                lockedTableNumber = tableParam.trim();
                tableContainer.innerHTML = `
                    <div class="table-badge-locked">
                        <span>📍 NFC Scanned Table:</span>
                        <span style="font-size: 0.9rem; font-weight: 800; color: white; background: var(--primary); padding: 3px 10px; border-radius: 8px;">Table ${lockedTableNumber}</span>
                    </div>
                `;
                await fetchAssignedServer(lockedTableNumber);
            } else {
                tableContainer.innerHTML = `
                    <div class="table-badge-unlocked">
                        ⚠️ No Table NFC Tag Detected!<br>Please scan the NFC sticker or QR code on your table.
                    </div>
                `;
                document.getElementById('place-order-btn').disabled = true;
                document.getElementById('place-order-btn').style.opacity = '0.5';
                document.getElementById('place-order-btn').style.cursor = 'not-allowed';
            }

            if(modeParam !== 'admin' && modeParam !== 'worker') {
                loadMenu();
            }
        };

        async function fetchAssignedServer(tblNum) {
            try {
                const res = await fetch(`/api/table/assigned-server/${currentSlug}/${tblNum}`);
                const data = await res.json();
                assignedServer = data;
                const sContainer = document.getElementById('server-badge-container');
                sContainer.innerHTML = `
                    <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); color: var(--accent); padding: 8px 12px; border-radius: 10px; font-size: 0.8rem; font-weight: 700; display: flex; align-items: center; justify-content: space-between;">
                        <span>👤 Your Dedicated Server Today:</span>
                        <span style="background: var(--accent); color: #090d16; padding: 2px 8px; border-radius: 6px; font-weight: 800;">${assignedServer.worker_name}</span>
                    </div>
                `;
            } catch(e) {}
        }

        function openWorkerLoginFromAdmin() {
            document.getElementById('admin-login-modal').style.display = 'none';
            document.getElementById('worker-login-modal').style.display = 'flex';
        }

        function openAdminLoginFromWorker() {
            document.getElementById('worker-login-modal').style.display = 'none';
            document.getElementById('admin-login-modal').style.display = 'flex';
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
                    enterDashboard('admin', 'Owner Admin', '');
                } else {
                    showToast(data.detail || 'Invalid login', true);
                }
            } catch(e) {
                showToast('Connection error', true);
            }
        }

        async function loginWorker() {
            const workerId = document.getElementById('worker-id-input').value.trim();
            const pass = document.getElementById('worker-pass-input').value.trim();
            if(!workerId || !pass) { showToast('Enter worker credentials', true); return; }
            try {
                const res = await fetch('/api/worker/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ worker_id: workerId, password: pass })
                });
                const data = await res.json();
                if(res.ok) {
                    loggedWorkerId = data.worker_id;
                    enterDashboard('worker', data.worker_name, data.worker_id);
                } else {
                    showToast(data.detail || 'Invalid worker login', true);
                }
            } catch(e) {
                showToast('Connection error', true);
            }
        }

        function enterDashboard(role, name, wId) {
            document.getElementById('admin-login-modal').style.display = 'none';
            document.getElementById('worker-login-modal').style.display = 'none';
            document.getElementById('client-nav').classList.add('hidden');
            document.getElementById('tab-rewards').classList.add('hidden');
            document.getElementById('tab-admin').classList.remove('hidden');
            document.getElementById('app-subtitle').innerText = role === 'admin' ? "Owner Control Center" : `Staff Portal (${name})`;

            loggedWorkerId = wId;
            const restrictedTabs = document.querySelectorAll('.admin-restricted');
            const subnavContainer = document.getElementById('admin-subnav-container');

            if(role === 'worker') {
                restrictedTabs.forEach(el => el.style.display = 'none');
                ['menu', 'reports', 'orders_history', 'tips_history', 'rewards', 'analytics', 'settings'].forEach(s => {
                    const btn = document.getElementById('sub-btn-' + s);
                    if(btn) btn.style.display = 'none';
                });
                subnavContainer.style.gridTemplateColumns = 'repeat(3, 1fr)';
                switchAdminSub('queue');
            } else {
                restrictedTabs.forEach(el => el.style.display = 'block');
                ['menu', 'reports', 'orders_history', 'tips_history', 'rewards', 'analytics', 'settings'].forEach(s => {
                    const btn = document.getElementById('sub-btn-' + s);
                    if(btn) btn.style.display = 'flex';
                });
                subnavContainer.style.gridTemplateColumns = 'repeat(10, 1fr)';
                switchAdminSub('queue');
                loadDailyReport();
                loadAdminMenu();
                loadAdminRewards();
                loadAnalytics();
                loadAdminWorkers();
            }

            loadAdminQueue();
            loadPOSMenu();
            loadAdminFloorPlan();
            setInterval(loadAdminQueue, 5000);
            showToast(`${name} authorized successfully!`);
        }

        function logoutAdminPanel() {
            document.getElementById('tab-admin').classList.add('hidden');
            document.getElementById('client-nav').classList.remove('hidden');
            document.getElementById('tab-rewards').classList.remove('hidden');
            document.getElementById('app-subtitle').innerText = translations[currentLang].subtitle;
            window.location.href = '/';
        }

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

        async function createNewWorker() {
            const worker_id = document.getElementById('new-worker-id').value.trim();
            const worker_name = document.getElementById('new-worker-name').value.trim();
            const password = document.getElementById('new-worker-pass').value.trim();
            const recovery_pin = document.getElementById('new-worker-pin').value.trim();
            if(!worker_id || !worker_name || !password || !recovery_pin) { showToast('Fill all worker fields including PIN', true); return; }
            try {
                const res = await fetch('/api/admin/workers/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ worker_id, worker_name, password, recovery_pin, restaurant_slug: currentSlug })
                });
                const data = await res.json();
                if(res.ok) {
                    showToast(data.message);
                    document.getElementById('new-worker-id').value = '';
                    document.getElementById('new-worker-name').value = '';
                    document.getElementById('new-worker-pass').value = '';
                    document.getElementById('new-worker-pin').value = '';
                    loadAdminWorkers();
                } else {
                    showToast(data.detail || 'Failed to create worker', true);
                }
            } catch(e) {
                showToast('Connection error', true);
            }
        }

        async function loadAdminWorkers() {
            try {
                const res = await fetch('/api/admin/workers/' + currentSlug);
                const workers = await res.json();
                const container = document.getElementById('admin-workers-list');
                if(!workers || workers.length === 0) {
                    container.innerHTML = '<div style="color:var(--text-muted); font-size:0.72rem;">No staff accounts.</div>';
                    return;
                }
                container.innerHTML = workers.map(w => `
                    <div class="admin-item-row">
                        <span><b>${w.worker_name}</b> (ID: ${w.worker_id}, PIN: ${w.recovery_pin || 'N/A'})</span>
                        <button class="danger-btn" onclick="deleteWorker('${w.worker_id}')">Remove</button>
                    </div>
                `).join('');
            } catch(e) {}
        }

        async function deleteWorker(workerId) {
            if(!confirm(`Remove staff account ${workerId}?`)) return;
            try {
                const res = await fetch('/api/admin/workers/' + encodeURIComponent(workerId), { method: 'DELETE' });
                if(res.ok) {
                    showToast('Worker account removed.');
                    loadAdminWorkers();
                }
            } catch(e) {
                showToast('Error removing worker', true);
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
                if(lockedTableNumber) fetchAssignedServer(lockedTableNumber);
            }
        }

        function switchAdminSub(subName) {
            ['queue', 'menu', 'reports', 'orders_history', 'tips_history', 'rewards', 'pos', 'floor', 'analytics', 'settings'].forEach(s => {
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
            if(subName === 'floor') loadAdminFloorPlan();
            if(subName === 'analytics') loadAnalytics();
            if(subName === 'pos') loadPOSMenu();
            if(subName === 'reports' || subName === 'orders_history' || subName === 'tips_history') loadDailyReport();
            if(subName === 'settings') loadAdminWorkers();
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
            if(!lockedTableNumber) {
                showToast('Please scan your table NFC tag first!', true);
                return;
            }
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
            const tipVal = parseFloat(document.getElementById('app-tip-input').value) || 0;

            if(keys.length === 0) {
                box.innerHTML = '<div style="text-align: center; color: var(--text-muted);" id="txt-empty-cart">Cart is empty. Tap items above to add!</div>';
                document.getElementById('app-total-val').innerText = (tipVal).toFixed(2) + ' MAD';
                return;
            }
            let total = 0;
            box.innerHTML = keys.map(k => {
                const c = appCart[k];
                const lineTotal = c.priceNum * c.qty;
                total += lineTotal;
                return `<div class="cart-row"><span>${c.qty}x ${c.name}</span><span>${lineTotal.toFixed(2)} MAD</span></div>`;
            }).join('');
            document.getElementById('app-total-val').innerText = (total + tipVal).toFixed(2) + ' MAD';
        }

        document.getElementById('app-tip-input').addEventListener('input', renderAppCart);

        async function submitAppOrder() {
            if(!lockedTableNumber) {
                showToast('Table NFC tag required to place order.', true);
                return;
            }
            const keys = Object.keys(appCart);
            const tipAmt = parseFloat(document.getElementById('app-tip-input').value) || 0;
            if(keys.length === 0 && tipAmt <= 0) { showToast('Your order cart is empty!', true); return; }

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
                        items_summary: summaryParts.join(', ') || 'Tip Only',
                        total_amount: total,
                        table_number: lockedTableNumber,
                        customer_phone: currentPhone,
                        tip_amount: tipAmt,
                        worker_id: assignedServer.worker_id
                    })
                });
                const data = await res.json();
                if(res.ok) {
                    showToast(`🎉 Order placed for Table ${lockedTableNumber}! Tip sent to ${assignedServer.worker_name}.`);
                    appCart = {};
                    document.getElementById('app-tip-input').value = '0';
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
                    container.innerHTML = '<div style="grid-column: span 2; text-align:center; color:var(--text-muted); font-size:0.72rem;">No items found.</div>';
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

        function changePOSQty(id, delta) {
            if(!posCart[id]) return;
            posCart[id].qty += delta;
            if(posCart[id].qty <= 0) {
                delete posCart[id];
            }
            renderPOSCart();
        }

        function renderPOSCart() {
            const box = document.getElementById('pos-cart-box');
            const keys = Object.keys(posCart);
            const tipVal = parseFloat(document.getElementById('pos-tip-input').value) || 0;

            if(keys.length === 0) {
                box.innerHTML = '<div style="text-align: center; color: var(--text-muted);" id="txt-pos-empty">Cart is empty</div>';
                document.getElementById('pos-total-val').innerText = (tipVal).toFixed(2) + ' MAD';
                return;
            }
            let total = 0;
            box.innerHTML = keys.map(k => {
                const c = posCart[k];
                const lineTotal = c.priceNum * c.qty;
                total += lineTotal;
                return `
                    <div class="cart-row">
                        <span>${c.name} (${lineTotal.toFixed(2)} MAD)</span>
                        <div class="cart-controls">
                            <button class="cart-btn-qty" onclick="changePOSQty(${k}, -1)">-</button>
                            <span style="font-weight: 800; min-width: 15px; text-align: center;">${c.qty}</span>
                            <button class="cart-btn-qty" onclick="changePOSQty(${k}, 1)">+</button>
                        </div>
                    </div>
                `;
            }).join('');
            document.getElementById('pos-total-val').innerText = (total + tipVal).toFixed(2) + ' MAD';
        }

        document.getElementById('pos-tip-input').addEventListener('input', renderPOSCart);

        async function confirmPOSOrder() {
            const keys = Object.keys(posCart);
            const tipAmt = parseFloat(document.getElementById('pos-tip-input').value) || 0;
            if(keys.length === 0 && tipAmt <= 0) { showToast('Cart is empty.', true); return; }
            const chosenTable = document.getElementById('pos-table-select').value;
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
                    body: JSON.stringify({
                        restaurant_slug: currentSlug,
                        items_summary: summaryParts.join(', ') || 'POS Tip',
                        total_amount: total,
                        table_number: chosenTable,
                        customer_phone: '',
                        tip_amount: tipAmt,
                        worker_id: loggedWorkerId
                    })
                });
                if(res.ok) {
                    showToast(`Order confirmed & sent for Table ${chosenTable}!`);
                    posCart = {};
                    document.getElementById('pos-tip-input').value = '0';
                    renderPOSCart();
                    loadDailyReport();
                    loadAdminQueue();
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
                document.getElementById('rep-tips-total').innerText = data.total_tips_collected.toFixed(2) + ' MAD';

                const workerListEl = document.getElementById('rep-worker-tips-list');
                if(!data.worker_tips_breakdown || data.worker_tips_breakdown.length === 0) {
                    workerListEl.innerHTML = '<span style="color: var(--text-muted);">No worker tips recorded yet.</span>';
                } else {
                    workerListEl.innerHTML = data.worker_tips_breakdown.map(wt => `
                        <div style="display: flex; justify-content: space-between; margin-bottom: 3px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 2px;">
                            <span><b>${wt.worker_name}</b> (${wt.tips_count} tips):</span>
                            <span style="color: var(--accent); font-weight: 800;">${wt.total_tips.toFixed(2)} MAD</span>
                        </div>
                    `).join('');
                }

                const ordersHistEl = document.getElementById('admin-orders-history-list');
                if(!data.orders_history || data.orders_history.length === 0) {
                    ordersHistEl.innerHTML = '<div style="text-align:center; color:var(--text-muted); font-size:0.72rem;">No orders recorded yet.</div>';
                } else {
                    ordersHistEl.innerHTML = data.orders_history.map(o => `
                        <div class="admin-item-row">
                            <span><b>Table ${o.table_number}</b>: ${o.items_summary} (${o.time})</span>
                            <span style="color: var(--success); font-weight: 800;">${o.total_amount.toFixed(2)} MAD</span>
                        </div>
                    `).join('');
                }

                const tipsHistEl = document.getElementById('admin-tips-history-list');
                if(!data.tips_history || data.tips_history.length === 0) {
                    tipsHistEl.innerHTML = '<div style="text-align:center; color:var(--text-muted); font-size:0.72rem;">No tips recorded yet.</div>';
                } else {
                    tipsHistEl.innerHTML = data.tips_history.map(t => `
                        <div class="admin-item-row">
                            <span><b>Table ${t.table_number}</b> → Server: <b>${t.worker_name}</b> (${t.time})</span>
                            <span style="color: var(--accent); font-weight: 800;">+${t.tip_amount.toFixed(2)} MAD</span>
                        </div>
                    `).join('');
                }
            } catch(e) {}
        }

        function openClearReportsModal() {
            document.getElementById('reset-admin-pwd').value = '';
            document.getElementById('clear-reports-modal').style.display = 'flex';
        }

        async function executeClearReports() {
            const pwd = document.getElementById('reset-admin-pwd').value.trim();
            if(!pwd) { showToast('Admin password required', true); return; }

            try {
                const res = await fetch('/api/admin/' + currentSlug + '/reports/clear', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ password: pwd })
                });
                const data = await res.json();
                if(res.ok) {
                    document.getElementById('clear-reports-modal').style.display = 'none';
                    showToast('Shift data & tip logs cleared successfully!');
                    loadDailyReport();
                } else {
                    showToast(data.detail || 'Incorrect password', true);
                }
            } catch(e) {
                showToast('Error clearing data', true);
            }
        }

        async function loadAnalytics() {
            try {
                const res = await fetch('/api/admin/' + currentSlug + '/analytics');
                const data = await res.json();
                document.getElementById('analytics-monthly-rev').innerText = data.monthly_revenue.toFixed(2) + ' MAD';
                
                const growthEl = document.getElementById('analytics-growth-pct');
                const growthVal = data.monthly_growth_percentage;
                growthEl.innerText = (growthVal >= 0 ? '+' : '') + growthVal + '%';
                growthEl.style.color = growthVal >= 0 ? 'var(--success)' : 'var(--danger)';

                const vipContainer = document.getElementById('analytics-vip-list');
                if(!data.vip_spenders || data.vip_spenders.length === 0) {
                    vipContainer.innerHTML = '<div style="color:var(--text-muted); font-size:0.72rem;">No VIP customers yet.</div>';
                    return;
                }
                vipContainer.innerHTML = data.vip_spenders.map((v, i) => `
                    <div class="admin-item-row">
                        <span><b>#${i+1} ${v.phone}</b></span>
                        <span style="color: var(--accent); font-weight: 800;">⭐ ${v.points} pts</span>
                    </div>
                `).join('');
            } catch(e) {}
        }

        async function loadAdminFloorPlan() {
            const tables = ['1', '2', '3', '4', '5', '6', 'VIP'];
            const grid = document.getElementById('admin-floor-grid');
            
            try {
                const res = await fetch('/api/admin/workers/' + currentSlug);
                const workers = await res.json();

                grid.innerHTML = tables.map(t => {
                    return `
                        <div class="floor-card status-green">
                            <div style="font-size: 0.95rem; font-weight: 800; color: var(--text-main); margin-bottom: 3px;">Table ${t}</div>
                            <select id="claim-select-table-${t}" style="padding: 4px; font-size: 0.7rem; margin-top: 4px; margin-bottom: 4px;">
                                <option value="">-- Assign Server --</option>
                                ${workers.map(w => `<option value="${w.worker_id}">${w.worker_name}</option>`).join('')}
                            </select>
                            <button class="btn-main" onclick="claimTable('${t}')" style="padding: 4px; font-size: 0.7rem; background: var(--primary); color: #090d16;">Claim Table</button>
                        </div>
                    `;
                }).join('');
            } catch(e) {}
        }

        async function claimTable(tblNum) {
            const selectEl = document.getElementById(`claim-select-table-${tblNum}`);
            const wId = selectEl.value;
            if(!wId) { showToast('Please select a worker first', true); return; }

            try {
                const res = await fetch('/api/worker/claim-table', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ restaurant_slug: currentSlug, table_number: tblNum, worker_id: wId })
                });
                const data = await res.json();
                if(res.ok) {
                    showToast(data.message);
                } else {
                    showToast(data.detail || 'Failed to claim table', true);
                }
            } catch(e) {
                showToast('Connection error', true);
            }
        }

        function playQueueBeep() {
            try {
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(880, ctx.currentTime);
                gain.gain.setValueAtTime(0.15, ctx.currentTime);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start();
                osc.stop(ctx.currentTime + 0.25);
            } catch(e) {}
        }

        async function loadAdminQueue() {
            try {
                const res = await fetch('/api/admin/' + currentSlug + '/redemptions');
                const data = await res.json();
                activeQueueCache = data.queue || [];

                if(activeQueueCache.length > previousQueueCount && previousQueueCount !== 0) {
                    playQueueBeep();
                    showToast('🚨 New Order Received in Queue!');
                }
                previousQueueCount = activeQueueCache.length;

                const container = document.getElementById('admin-queue-container');
                if(!activeQueueCache || activeQueueCache.length === 0) {
                    container.innerHTML = `<div style="text-align:center; color:var(--text-muted); font-size:0.72rem; padding: 1rem 0;" id="txt-no-orders">${translations[currentLang].noOrders}</div>`;
                    return;
                }
                
                const now = new Date();

                container.innerHTML = activeQueueCache.map(item => {
                    const orderDate = new Date(item.raw_time);
                    const diffMinutes = Math.floor((now - orderDate) / 60000);

                    return `
                        <div class="redemption-card">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                                <span style="background: var(--primary); color: #090d16; padding: 2px 7px; border-radius: 4px; font-weight: bold; font-size: 0.7rem;">Table ${item.table_number}</span>
                                <span style="font-size: 0.72rem; font-weight: 800; color: var(--text-muted);">${diffMinutes}m ago</span>
                            </div>
                            <div style="font-weight: 700; font-size: 0.9rem; color: var(--accent); margin-bottom: 2px;">👤 ${item.customer_name} (${item.customer_phone || 'Walk-in'})</div>
                            <div style="font-weight: 700; font-size: 0.85rem; color: var(--text-main);">${item.reward_item}</div>
                            ${item.security_pin !== 'POS' && item.security_pin !== 'APP' ? `<div class="pin-display">PIN: ${item.security_pin}</div>` : ''}
                            <button class="btn-main" onclick="fulfillRedemption(${item.id})" style="background: var(--success); color: white; padding: 7px; font-size: 0.78rem; margin-top: 5px;">Mark Fulfilled ✓</button>
                        </div>
                    `;
                }).join('');
            } catch(e) {}
        }

        async function fulfillRedemption(id) {
            await fetch('/api/admin/redemptions/fulfill/' + id, { method: 'POST' });
            showToast('Order marked fulfilled!');
            loadAdminQueue();
        }

        async function loadCustomerData() {
            try {
                const res = await fetch('/api/rewards/' + currentSlug);
                const rewards = await res.json();
                const container = document.getElementById('customer-rewards-list');
                if(!rewards || rewards.length === 0) {
                    container.innerHTML = '<div style="color:var(--text-muted); font-size:0.72rem; text-align:center;">No rewards available.</div>';
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
            if(!items || items.length === 0) { container.innerHTML = '<div style="color:var(--text-muted); font-size:0.72rem;">No items.</div>'; return; }
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
            if(!rewards || rewards.length === 0) { container.innerHTML = '<div style="color:var(--text-muted); font-size:0.72rem;">No rewards.</div>'; return; }
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

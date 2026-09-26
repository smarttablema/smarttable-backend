import os
import random
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_7aYbfrQdjcq6@ep-cold-lake-b1djlrzp-pooler.c-5.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

app = FastAPI(title="SmartTable.ma SaaS Engine", version="7.2.0")

class CustomerAuth(BaseModel):
    phone_number: str
    restaurant_slug: str = "default-restaurant"

class ReviewReward(BaseModel):
    phone_number: str

class ReferralCreate(BaseModel):
    referrer_phone: str
    friend_phone: str

class PurchaseLog(BaseModel):
    phone_number: str
    amount_spent: float

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

class VoucherValidate(BaseModel):
    code: str

@app.get("/api/health")
def health_check():
    return {"status": "online", "database": "neon-postgres", "brand": "smarttable.ma"}

@app.post("/api/customer/auth")
def authenticate_customer(data: CustomerAuth):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (data.phone_number,))
        customer = cur.fetchone()
        if not customer:
            cur.execute("INSERT INTO customers (phone_number, points_balance, has_purchased) VALUES (%s, 0, FALSE) RETURNING *;", (data.phone_number,))
            customer = cur.fetchone()
            conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "points_balance": customer["points_balance"]}
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
        return {"status": "success", "message": "Item successfully added!"}
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
        return {"status": "success", "message": "Price updated successfully!"}
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
        return {"status": "success", "message": "Item removed!"}
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
        return {"status": "success", "message": "Reward tier added!"}
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
                {"id": 1, "name": "Classic Burger Tier", "min_points": 0},
                {"id": 2, "name": "Double Burger Tier", "min_points": 100},
                {"id": 3, "name": "S-Tier VIP Burger", "min_points": 300}
            ]
        return tiers
    except Exception:
        return [
            {"id": 1, "name": "Classic Burger Tier", "min_points": 0},
            {"id": 2, "name": "Double Burger Tier", "min_points": 100},
            {"id": 3, "name": "S-Tier VIP Burger", "min_points": 300}
        ]

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
        return {"status": "success", "message": "Tier successfully created!"}
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
        img = reward.get("image_url") if reward else ""
        if not img:
            img = "https://images.unsplash.com/photo-1551024709-8f23befc6f87?w=500"

        if customer["points_balance"] < cost:
            raise HTTPException(status_code=400, detail="Insufficient points balance.")

        new_balance = customer["points_balance"] - cost
        cur.execute("UPDATE customers SET points_balance = %s WHERE phone_number = %s;", (new_balance, phone))
        
        v_code = str(random.randint(1000, 9999))
        
        cur.execute("INSERT INTO active_vouchers (code, phone_number, reward_title, image_url) VALUES (%s, %s, %s, %s);", (v_code, phone, title, img))
        conn.commit()
        cur.close()
        conn.close()

        return {"status": "success", "new_balance": new_balance, "voucher_code": v_code, "reward_title": title, "image_url": img}
    except HTTPException as he:
        raise he
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
            raise HTTPException(status_code=404, detail="Invalid or already used voucher code.")
        
        cur.execute("UPDATE active_vouchers SET status = 'redeemed' WHERE code = %s;", (code_input,))
        conn.commit()
        cur.close()
        conn.close()
        return {
            "status": "success",
            "reward_title": voucher["reward_title"],
            "image_url": voucher["image_url"] or "https://images.unsplash.com/photo-1551024709-8f23befc6f87?w=500",
            "phone_number": voucher["phone_number"]
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rewards/claim-review")
def claim_google_review(data: ReviewReward):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (data.phone_number,))
        customer = cur.fetchone()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found.")
        new_balance = customer["points_balance"] + 50
        cur.execute("UPDATE customers SET points_balance = %s WHERE phone_number = %s;", (new_balance, data.phone_number))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "new_balance": new_balance, "message": "50 points added for your review!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rewards/refer-friend")
def refer_friend(data: ReferralCreate):
    try:
        if data.referrer_phone == data.friend_phone:
            raise HTTPException(status_code=400, detail="You cannot refer your own number.")
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (data.friend_phone,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="This friend already has an account.")
        cur.execute(
            "INSERT INTO customers (phone_number, points_balance, referred_by, has_purchased) VALUES (%s, 0, %s, FALSE);",
            (data.friend_phone, data.referrer_phone)
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Friend registered! 50 points unlock on their first visit."}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- WORLD-CLASS SAAS ENTERPRISE UI ---
@app.get("/", response_class=HTMLResponse)
def serve_mobile_frontend():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SmartTable.ma | Enterprise Table Experience</title>
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
        
        .app-frame { width: 100%; max-width: 410px; background: var(--surface); border-radius: var(--radius); padding: 1.5rem; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7); border: 1px solid var(--border); position: relative; overflow: hidden; }
        
        .brand-header { text-align: center; margin-bottom: 1.25rem; }
        .logo { font-size: 1.65rem; font-weight: 800; color: var(--text-main); letter-spacing: -0.5px; }
        .logo span { color: var(--accent); }
        .brand-tag { font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 2px; margin-top: 2px; font-weight: 600; }
        
        .nav-tabs { display: flex; background: var(--bg-deep); border-radius: 14px; padding: 5px; margin-bottom: 1.25rem; border: 1px solid var(--border); }
        .tab-btn { flex: 1; padding: 0.6rem; text-align: center; border-radius: 10px; font-size: 0.8rem; font-weight: 600; color: var(--text-muted); cursor: pointer; border: none; background: transparent; transition: all 0.3s; }
        .tab-btn.active { background: var(--surface-card); color: var(--text-main); box-shadow: 0 4px 12px rgba(0,0,0,0.3); border: 1px solid var(--border); }
        
        .card { background: var(--surface-card); border-radius: 16px; padding: 1.25rem; margin-bottom: 1rem; border: 1px solid var(--border); }
        
        label { display: block; font-size: 0.75rem; font-weight: 600; color: var(--text-muted); margin-bottom: 0.4rem; text-transform: uppercase; letter-spacing: 0.5px; }
        input { width: 100%; padding: 0.8rem 1rem; border-radius: 12px; border: 1px solid var(--border); background: var(--bg-deep); color: white; font-size: 0.9rem; margin-bottom: 0.85rem; outline: none; transition: border-color 0.2s; }
        input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
        
        .btn-main { width: 100%; padding: 0.8rem; border-radius: 12px; border: none; background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: #090d16; font-weight: 700; font-size: 0.95rem; cursor: pointer; transition: transform 0.1s; box-shadow: 0 4px 14px var(--accent-glow); }
        .btn-main:active { transform: scale(0.98); }
        
        .hidden { display: none !important; }
        
        .points-display { text-align: center; padding: 0.2rem 0; }
        .points-label { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }
        .points-number { font-size: 2.75rem; font-weight: 800; color: var(--success); letter-spacing: -1px; margin: 0.2rem 0; }
        .tier-badge { display: inline-block; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); color: var(--accent); padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 700; margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 0.5px; }
        .cashback-badge { display: inline-block; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); color: var(--success); padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; margin-bottom: 0.75rem; }

        .rewards-list { display: flex; flex-direction: column; gap: 0.5rem; max-height: 160px; overflow-y: auto; margin-top: 0.5rem; padding-right: 2px; }
        .reward-item { display: flex; align-items: center; justify-content: space-between; background: var(--bg-deep); padding: 0.5rem 0.75rem; border-radius: 12px; border: 1px solid var(--border); gap: 0.5rem; }
        .reward-thumb { width: 40px; height: 40px; border-radius: 8px; object-fit: cover; background: var(--surface); }
        .reward-info { flex: 1; }
        .reward-title { font-size: 0.82rem; font-weight: 700; color: var(--text-main); }
        .reward-cost { font-size: 0.7rem; color: var(--accent); font-weight: 700; }
        .redeem-btn { background: var(--success); color: white; border: none; padding: 6px 10px; border-radius: 8px; font-weight: 700; font-size: 0.72rem; cursor: pointer; }

        .review-link { display: flex; align-items: center; justify-content: center; gap: 8px; text-align: center; margin-top: 1rem; padding: 0.8rem; background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.3); color: var(--accent); border-radius: 12px; text-decoration: none; font-weight: 700; font-size: 0.82rem; }

        .menu-grid { display: flex; flex-direction: column; gap: 0.75rem; max-height: 360px; overflow-y: auto; padding-right: 2px; }
        .menu-card { display: flex; align-items: center; background: var(--bg-deep); border-radius: 14px; padding: 0.75rem; border: 1px solid var(--border); gap: 0.85rem; cursor: pointer; transition: all 0.2s; }
        .menu-card:hover { border-color: var(--accent); }
        .menu-img { width: 55px; height: 55px; border-radius: 10px; object-fit: cover; background: var(--surface); }
        .menu-info { flex: 1; }
        .menu-name { font-size: 0.95rem; font-weight: 700; color: var(--text-main); margin-bottom: 2px; }
        .menu-cat { font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700; }
        .menu-price { font-size: 0.9rem; font-weight: 800; color: var(--accent); }

        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(9, 13, 22, 0.85); backdrop-filter: blur(8px); justify-content: center; align-items: center; padding: 1.5rem; }
        .modal-content { background: var(--surface); padding: 1.5rem; border-radius: 24px; max-width: 360px; width: 100%; text-align: center; border: 1px solid var(--border); box-shadow: 0 25px 50px rgba(0,0,0,0.8); animation: modalPop 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
        @keyframes modalPop { from { transform: scale(0.9); opacity: 0; } to { transform: scale(1); opacity: 1; } }
        .modal-img { width: 100%; height: 200px; border-radius: 16px; object-fit: cover; margin-bottom: 1rem; border: 1px solid var(--border); }
        .close-modal { background: var(--border); color: var(--text-main); border: none; padding: 0.75rem; border-radius: 12px; cursor: pointer; font-weight: 700; width: 100%; transition: background 0.2s; }
        .close-modal:hover { background: var(--danger); }

        .voucher-code-box { font-size: 2.2rem; font-weight: 800; color: var(--accent); background: var(--bg-deep); padding: 0.75rem; border-radius: 12px; border: 1px dashed var(--accent); margin: 0.75rem 0; letter-spacing: 2px; }

        .admin-item-row { display: flex; justify-content: space-between; align-items: center; background: var(--bg-deep); padding: 0.75rem; border-radius: 12px; margin-bottom: 0.5rem; font-size: 0.85rem; border: 1px solid var(--border); }
        .danger-btn { background: rgba(239, 68, 68, 0.15); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); padding: 6px 10px; border-radius: 8px; cursor: pointer; font-weight: 700; }
        .edit-btn { background: rgba(56, 189, 248, 0.15); color: var(--primary); border: 1px solid rgba(56, 189, 248, 0.3); padding: 6px 10px; border-radius: 8px; cursor: pointer; font-weight: 700; margin-right: 6px; }

        .message-box { margin-top: 0.75rem; padding: 0.75rem; border-radius: 10px; font-size: 0.8rem; text-align: center; font-weight: 600; }
        .success-msg { background: rgba(16, 185, 129, 0.15); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.3); }
        .error-msg { background: rgba(239, 68, 68, 0.15); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); }

        .proximity-banner { background: linear-gradient(135deg, rgba(56, 189, 248, 0.15) 0%, rgba(16, 185, 129, 0.15) 100%); border: 1px solid var(--primary); padding: 0.75rem; border-radius: 12px; font-size: 0.78rem; text-align: center; color: var(--primary); margin-bottom: 1rem; font-weight: 600; display: none; }
    </style>
</head>
<body>
    <div class="app-frame">
        <div id="geo-banner" class="proximity-banner">📍 You are 50m away! Drop in for 10% cashback today!</div>
        
        <div class="brand-header">
            <div class="logo">SmartTable<span>.ma</span></div>
            <div class="brand-tag">Table Experience & Loyalty</div>
        </div>
        
        <div class="nav-tabs">
            <button class="tab-btn active" onclick="switchTab('rewards')">🏆 Rewards</button>
            <button class="tab-btn" onclick="switchTab('menu')">📖 Menu</button>
            <button class="tab-btn hidden" id="admin-tab-btn" onclick="switchTab('admin')">🔒 Owner</button>
        </div>

        <div id="tab-rewards">
            <div id="login-section" class="card">
                <h3 style="margin-bottom: 0.85rem; font-size: 1rem; font-weight: 700;">Customer Loyalty Portal</h3>
                <label>Phone Number</label>
                <input type="tel" id="phone-input" placeholder="e.g., 06XXXXXXXX" />
                <button class="btn-main" onclick="loginCustomer()">Access My Account</button>
            </div>
            
            <div id="dashboard-section" class="card hidden">
                <div class="points-display">
                    <div class="tier-badge" id="customer-tier-badge">S-Tier VIP Burger</div>
                    <div class="points-label">Your Balance</div>
                    <div class="points-number" id="points-val">0</div>
                    <div class="cashback-badge">⚡ 10% Cashback Active</div>
                </div>
                
                <div style="margin-top: 0.5rem;">
                    <label>🎁 Redeemable Rewards</label>
                    <div id="customer-rewards-list" class="rewards-list">
                        <div style="text-align:center; color:var(--text-muted); font-size:0.75rem;">Loading rewards...</div>
                    </div>
                </div>

                <div style="border-top: 1px solid var(--border); margin-top: 1rem; padding-top: 0.75rem;">
                    <label>👥 Refer a Friend (+50 pts on 1st visit)</label>
                    <input type="tel" id="friend-phone" placeholder="Friend's Phone Number" />
                    <button class="btn-main" onclick="referFriend()" style="background: linear-gradient(135deg, #38bdf8 0%, #0284c7 100%); color: #090d16; padding: 0.6rem; font-size: 0.85rem;">Register Friend</button>
                </div>

                <a href="https://maps.google.com" target="_blank" class="review-link" onclick="claimReview()">
                    ⭐ Leave Google Review (+50 Points)
                </a>
            </div>
        </div>

        <div id="tab-menu" class="card hidden">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.85rem;">
                <h3 style="font-size: 1rem; font-weight: 700; color: var(--accent);">Live Menu</h3>
                <span style="font-size: 0.7rem; color: var(--text-muted);">Tap to zoom</span>
            </div>
            <div id="menu-container" class="menu-grid">
                <div style="text-align:center; color:var(--text-muted); font-size:0.85rem; padding: 2rem 0;">Loading menu...</div>
            </div>
        </div>

        <div id="tab-admin" class="card hidden">
            <h3 style="margin-bottom: 0.75rem; font-size: 0.95rem; font-weight: 700; color: var(--accent);">🔒 Owner Control Center</h3>
            
            <div style="background: var(--bg-deep); padding: 0.75rem; border-radius: 12px; border: 1px solid var(--border); margin-bottom: 1rem;">
                <label style="color: var(--success); margin-bottom: 0.25rem;">Validate Customer Voucher</label>
                <input type="text" id="voucher-input" placeholder="Enter 4-digit code (e.g. 4892)" style="margin-bottom: 0.5rem;" />
                <button class="btn-main" onclick="validateVoucher()" style="background: var(--success); color: white; padding: 0.5rem; font-size: 0.8rem; margin-bottom: 0.75rem;">Verify Code</button>
                <div id="voucher-result" class="hidden" style="text-align: center; border-top: 1px solid var(--border); padding-top: 0.5rem;">
                    <img id="v-img" style="width: 60px; height: 60px; border-radius: 10px; object-fit: cover; margin-bottom: 4px;" />
                    <div id="v-title" style="font-size: 0.85rem; font-weight: 700; color: var(--success);"></div>
                    <div id="v-phone" style="font-size: 0.7rem; color: var(--text-muted);"></div>
                </div>
            </div>

            <label>Manage Loyalty Tiers</label>
            <input type="text" id="tier-name-input" placeholder="Tier Name (e.g. Double Burger Tier)" />
            <input type="number" id="tier-points-input" placeholder="Min Points Required (e.g. 100)" />
            <button class="btn-main" onclick="addTier()" style="background: var(--accent); color: #090d16; padding: 0.5rem; font-size: 0.8rem; margin-bottom: 0.75rem;">+ Create Loyalty Tier</button>
            <div id="admin-tiers-list" style="max-height: 90px; overflow-y: auto; margin-bottom: 1rem;"></div>

            <label>Add Custom Reward</label>
            <input type="text" id="reward-title-input" placeholder="Reward Title (e.g. Free Dessert)" />
            <input type="number" id="reward-cost-input" placeholder="Points Required (e.g. 100)" />
            <input type="text" id="reward-img-input" placeholder="Image URL (optional)" />
            <button class="btn-main" onclick="addRewardTier()" style="background: #3b82f6; color: white; padding: 0.5rem; font-size: 0.8rem; margin-bottom: 1rem;">+ Create Reward</button>
            
            <label>Manage Rewards:</label>
            <div id="admin-rewards-list" style="max-height: 100px; overflow-y: auto; margin-bottom: 1rem;"></div>

            <label>Add Menu Item</label>
            <input type="text" id="admin-cat" placeholder="Category (e.g., Burgers)" />
            <input type="text" id="admin-name" placeholder="Item Name" />
            <input type="text" id="admin-price" placeholder="Price in numbers (e.g. 65)" />
            <input type="text" id="admin-img" placeholder="Image URL (optional)" />
            <button class="btn-main" onclick="addMenuItem()" style="margin-bottom: 1rem; padding: 0.5rem; font-size: 0.8rem;">+ Add to Menu</button>
            
            <label>Manage Menu Items:</label>
            <div id="admin-menu-list" style="max-height: 120px; overflow-y: auto;"></div>
        </div>

        <div id="feedback-msg" class="message-box hidden"></div>
    </div>

    <div id="voucher-modal" class="modal">
        <div class="modal-content">
            <h3 style="font-size: 1rem; font-weight: 700; color: var(--success); margin-bottom: 0.25rem;">Reward Unlocked!</h3>
            <p style="font-size: 0.75rem; color: var(--text-muted);">Show this code to your waiter:</p>
            <div id="modal-voucher-code" class="voucher-code-box">----</div>
            <img id="modal-voucher-img" class="modal-img" src="" style="height: 140px; margin-bottom: 0.5rem;" />
            <div id="modal-voucher-title" style="font-size: 0.9rem; font-weight: 700; color: var(--text-main); margin-bottom: 1rem;"></div>
            <button class="close-modal" onclick="closeVoucherModal()">Done</button>
        </div>
    </div>

    <div id="image-modal" class="modal">
        <div class="modal-content">
            <img id="modal-img-tag" class="modal-img" src="" />
            <h3 id="modal-title" style="font-size: 1.1rem; font-weight: 700; margin-bottom: 0.25rem; color: var(--text-main);"></h3>
            <div id="modal-price" style="font-size: 1rem; font-weight: 800; color: var(--accent); margin-bottom: 1.25rem;"></div>
            <button class="close-modal" onclick="closeModal()">Close Preview</button>
        </div>
    </div>

    <script>
        let currentPhone = '';
        const currentSlug = 'default-restaurant';
        
        window.onload = function() {
            const urlParams = new URLSearchParams(window.location.search);
            if(urlParams.get('mode') === 'admin') {
                const adminBtn = document.getElementById('admin-tab-btn');
                if(adminBtn) adminBtn.classList.remove('hidden');
                switchTab('admin');
            }
            if(navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(() => {
                    document.getElementById('geo-banner').style.display = 'block';
                }, () => {});
            }
        };

        function switchTab(tabName) {
            document.querySelectorAll('.tab-btn').forEach(b => {
                if(b.id !== 'admin-tab-btn' || !b.classList.contains('hidden')) {
                    b.classList.remove('active');
                }
            });
            document.getElementById('tab-rewards').classList.add('hidden');
            document.getElementById('tab-menu').classList.add('hidden');
            document.getElementById('tab-admin').classList.add('hidden');
            
            if(tabName === 'rewards') {
                document.querySelectorAll('.tab-btn')[0].classList.add('active');
                document.getElementById('tab-rewards').classList.remove('hidden');
                if(currentPhone) loadCustomerData();
            } else if(tabName === 'menu') {
                document.querySelectorAll('.tab-btn')[1].classList.add('active');
                document.getElementById('tab-menu').classList.remove('hidden');
                loadMenu();
            } else {
                const adminBtn = document.getElementById('admin-tab-btn');
                if(adminBtn) adminBtn.classList.add('active');
                document.getElementById('tab-admin').classList.remove('hidden');
                loadAdminMenu();
                loadAdminRewards();
                loadAdminTiers();
            }
        }

        async function loadMenu() {
            try {
                const res = await fetch('/api/menu/' + currentSlug);
                const items = await res.json();
                const container = document.getElementById('menu-container');
                if(!items || items.length === 0) {
                    container.innerHTML = '<div style="text-align:center; color:var(--text-muted); padding: 2rem 0;">No items available yet.</div>';
                    return;
                }
                container.innerHTML = items.map(item => {
                    const imgSrc = item.image_url || 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=500';
                    return `
                        <div class="menu-card" onclick="openModal('${imgSrc}', '${item.name.replace(/'/g, "\\'")}', '${item.price}')">
                            <img src="${imgSrc}" class="menu-img" />
                            <div class="menu-info">
                                <div class="menu-cat">${item.category}</div>
                                <div class="menu-name">${item.name}</div>
                                <div class="menu-price">${item.price}</div>
                            </div>
                        </div>
                    `;
                }).join('');
            } catch(e) {
                document.getElementById('menu-container').innerHTML = '<div style="text-align:center; color:var(--danger);">Failed to load menu.</div>';
            }
        }

        async function loadCustomerData() {
            try {
                const points = parseInt(document.getElementById('points-val').innerText) || 0;
                const tierRes = await fetch('/api/tiers/' + currentSlug);
                const tiers = await tierRes.json();
                
                let activeTier = "Classic Member";
                if(tiers && tiers.length > 0) {
                    let sorted = tiers.sort((a,b) => b.min_points - a.min_points);
                    for(let t of sorted) {
                        if(points >= t.min_points) {
                            activeTier = t.name;
                            break;
                        }
                    }
                }
                document.getElementById('customer-tier-badge').innerText = activeTier;

                const res = await fetch('/api/rewards/' + currentSlug);
                const rewards = await res.json();
                const container = document.getElementById('customer-rewards-list');
                if(!rewards || rewards.length === 0) {
                    container.innerHTML = '<div style="color:var(--text-muted); font-size:0.75rem; text-align:center;">No rewards configured.</div>';
                    return;
                }
                container.innerHTML = rewards.map(r => {
                    const img = r.image_url || 'https://images.unsplash.com/photo-1551024709-8f23befc6f87?w=500';
                    return `
                        <div class="reward-item">
                            <img src="${img}" class="reward-thumb" />
                            <div class="reward-info">
                                <div class="reward-title">${r.title}</div>
                                <div class="reward-cost">${r.points_required} pts</div>
                            </div>
                            <button class="redeem-btn" onclick="redeemReward(${r.id})">Redeem</button>
                        </div>
                    `;
                }).join('');
            } catch(e) {
                console.error(e);
            }
        }

        async function redeemReward(rewardId) {
            try {
                const res = await fetch('/api/rewards/redeem', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ phone_number: currentPhone, reward_id: rewardId, restaurant_slug: currentSlug })
                });
                const data = await res.json();
                if(res.ok) {
                    document.getElementById('points-val').innerText = data.new_balance;
                    document.getElementById('modal-voucher-code').innerText = data.voucher_code;
                    document.getElementById('modal-voucher-title').innerText = data.reward_title;
                    document.getElementById('modal-voucher-img').src = data.image_url;
                    document.getElementById('voucher-modal').style.display = 'flex';
                    loadCustomerData();
                } else {
                    alert(data.detail || 'Redemption failed.');
                }
            } catch(e) {
                alert('Connection error.');
            }
        }

        function closeVoucherModal() {
            document.getElementById('voucher-modal').style.display = 'none';
        }

        async function validateVoucher() {
            const code = document.getElementById('voucher-input').value;
            const resBox = document.getElementById('voucher-result');
            if(!code) { alert('Enter voucher code.'); return; }
            try {
                const res = await fetch('/api/admin/validate-voucher', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ code })
                });
                const data = await res.json();
                if(res.ok) {
                    document.getElementById('v-img').src = data.image_url;
                    document.getElementById('v-title').innerText = "✓ Validated: " + data.reward_title;
                    document.getElementById('v-phone').innerText = "Client Phone: " + data.phone_number;
                    resBox.classList.remove('hidden');
                    document.getElementById('voucher-input').value = '';
                } else {
                    resBox.classList.add('hidden');
                    alert(data.detail || 'Invalid code');
                }
            } catch(e) {
                alert('Error validating code');
            }
        }

        async function addTier() {
            const name = document.getElementById('tier-name-input').value;
            const min_points = document.getElementById('tier-points-input').value;
            if(!name || !min_points) { alert('Fill in tier name and minimum points.'); return; }
            try {
                const res = await fetch('/api/admin/tiers/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ restaurant_slug: currentSlug, name, min_points: parseInt(min_points) })
                });
                const data = await res.json();
                showMsg(data.message, 'success-msg');
                document.getElementById('tier-name-input').value = '';
                document.getElementById('tier-points-input').value = '';
                loadAdminTiers();
            } catch(e) {
                alert('Error adding tier.');
            }
        }

        async function loadAdminTiers() {
            try {
                const res = await fetch('/api/tiers/' + currentSlug);
                const tiers = await res.json();
                const container = document.getElementById('admin-tiers-list');
                if(!tiers || tiers.length === 0) {
                    container.innerHTML = '<div style="color:var(--text-muted); font-size:0.75rem;">No tiers found.</div>';
                    return;
                }
                container.innerHTML = tiers.map(t => `
                    <div class="admin-item-row">
                        <span><b>${t.name}</b> (${t.min_points}+ pts)</span>
                        <button class="danger-btn" onclick="deleteTier(${t.id})" style="padding:2px 6px; font-size:0.7rem;">Delete</button>
                    </div>
                `).join('');
            } catch(e) {}
        }

        async function deleteTier(id) {
            if(!confirm('Delete this tier?')) return;
            try {
                await fetch('/api/admin/tiers/' + id, { method: 'DELETE' });
                loadAdminTiers();
            } catch(e) {
                alert('Error deleting tier.');
            }
        }

        async function addRewardTier() {
            const title = document.getElementById('reward-title-input').value;
            const points_required = document.getElementById('reward-cost-input').value;
            const image_url = document.getElementById('reward-img-input').value;
            if(!title || !points_required) { alert('Fill in title and points.'); return; }
            try {
                const res = await fetch('/api/admin/rewards/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ restaurant_slug: currentSlug, title, points_required: parseInt(points_required), image_url })
                });
                const data = await res.json();
                showMsg(data.message, 'success-msg');
                document.getElementById('reward-title-input').value = '';
                document.getElementById('reward-cost-input').value = '';
                document.getElementById('reward-img-input').value = '';
                loadAdminRewards();
            } catch(e) {
                alert('Error adding reward.');
            }
        }

        async function loadAdminRewards() {
            try {
                const res = await fetch('/api/rewards/' + currentSlug);
                const rewards = await res.json();
                const container = document.getElementById('admin-rewards-list');
                if(!rewards || rewards.length === 0) {
                    container.innerHTML = '<div style="color:var(--text-muted); font-size:0.75rem;">No rewards found.</div>';
                    return;
                }
                container.innerHTML = rewards.map(r => `
                    <div class="admin-item-row">
                        <span><b>${r.title}</b> (${r.points_required} pts)</span>
                        <button class="danger-btn" onclick="deleteReward(${r.id})" style="padding:2px 6px; font-size:0.7rem;">Delete</button>
                    </div>
                `).join('');
            } catch(e) {}
        }

        async function deleteReward(id) {
            if(!confirm('Delete this reward?')) return;
            try {
                await fetch('/api/admin/rewards/' + id, { method: 'DELETE' });
                loadAdminRewards();
            } catch(e) {
                alert('Error deleting reward.');
            }
        }

        function openModal(imgUrl, name, price) {
            document.getElementById('modal-img-tag').src = imgUrl;
            document.getElementById('modal-title').innerText = name;
            document.getElementById('modal-price').innerText = price;
            document.getElementById('image-modal').style.display = 'flex';
        }

        function closeModal() {
            document.getElementById('image-modal').style.display = 'none';
        }

        async function loadAdminMenu() {
            try {
                const res = await fetch('/api/menu/' + currentSlug);
                const items = await res.json();
                const container = document.getElementById('admin-menu-list');
                if(!items || items.length === 0) {
                    container.innerHTML = '<div style="color:var(--text-muted); font-size:0.75rem; text-align:center;">No items.</div>';
                    return;
                }
                container.innerHTML = items.map(item => `
                    <div class="admin-item-row">
                        <span><b>${item.name}</b> (${item.price})</span>
                        <div>
                            <button class="edit-btn" onclick="editPrice(${item.id})">Edit</button>
                            <button class="danger-btn" onclick="deleteItem(${item.id})">Delete</button>
                        </div>
                    </div>
                `).join('');
            } catch(e) {}
        }

        async function addMenuItem() {
            const category = document.getElementById('admin-cat').value;
            const name = document.getElementById('admin-name').value;
            const price = document.getElementById('admin-price').value;
            const image_url = document.getElementById('admin-img').value;
            if(!category || !name || !price) { alert('Fill category, name, price.'); return; }
            try {
                const res = await fetch('/api/admin/menu/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ restaurant_slug: currentSlug, category, name, price, image_url })
                });
                const data = await res.json();
                showMsg(data.message, 'success-msg');
                document.getElementById('admin-cat').value = '';
                document.getElementById('admin-name').value = '';
                document.getElementById('admin-price').value = '';
                document.getElementById('admin-img').value = '';
                loadAdminMenu();
            } catch(e) {
                alert('Error adding item.');
            }
        }

        async function editPrice(id) {
            const newPrice = prompt("Enter new price in MAD:");
            if(!newPrice) return;
            try {
                const res = await fetch('/api/admin/menu/' + id, {
                    method: 'PATCH',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ price: newPrice })
                });
                const data = await res.json();
                showMsg(data.message, 'success-msg');
                loadAdminMenu();
            } catch(e) {
                alert('Error updating price.');
            }
        }

        async function deleteItem(id) {
            if(!confirm('Delete item?')) return;
            try {
                await fetch('/api/admin/menu/' + id, { method: 'DELETE' });
                loadAdminMenu();
            } catch(e) {
                alert('Error deleting item.');
            }
        }

        async function loginCustomer() {
            const phone = document.getElementById('phone-input').value;
            if(!phone) { alert('Enter phone number.'); return; }
            currentPhone = phone;
            try {
                const res = await fetch('/api/customer/auth', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ phone_number: phone, restaurant_slug: currentSlug })
                });
                const data = await res.json();
                if(res.ok) {
                    document.getElementById('points-val').innerText = data.points_balance;
                    document.getElementById('login-section').classList.add('hidden');
                    document.getElementById('dashboard-section').classList.remove('hidden');
                    loadCustomerData();
                    showMsg('Welcome!', 'success-msg');
                } else {
                    showMsg(data.detail || 'Login failed', 'error-msg');
                }
            } catch(e) {
                showMsg('Connection error', 'error-msg');
            }
        }

        async function claimReview() {
            try {
                const res = await fetch('/api/rewards/claim-review', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ phone_number: currentPhone })
                });
                const data = await res.json();
                document.getElementById('points-val').innerText = data.new_balance;
                loadCustomerData();
                showMsg(data.message, 'success-msg');
            } catch(e) {
                showMsg('Error claiming points', 'error-msg');
            }
        }

        async function referFriend() {
            const friendPhone = document.getElementById('friend-phone').value;
            if(!friendPhone) { alert("Enter friend's phone number."); return; }
            try {
                const res = await fetch('/api/rewards/refer-friend', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ referrer_phone: currentPhone, friend_phone: friendPhone })
                });
                const data = await res.json();
                if(res.ok) {
                    showMsg(data.message, 'success-msg');
                    document.getElementById('friend-phone').value = '';
                } else {
                    showMsg(data.detail || 'Error referring friend', 'error-msg');
                }
            } catch(e) {
                showMsg('Connection error', 'error-msg');
            }
        }

        function showMsg(text, className) {
            const box = document.getElementById('feedback-msg');
            box.innerText = text;
            box.className = 'message-box ' + className;
            setTimeout(() => box.classList.add('hidden'), 4000);
        }
    </script>
</body>
</html>
    ```

Commit this into your GitHub repo, and Railway will build successfully in seconds!

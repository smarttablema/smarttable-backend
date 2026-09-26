import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

DATABASE_URL = "postgresql://neondb_owner:npg_7aYbfrQdjcq6@ep-cold-lake-b1djlrzp-pooler.c-5.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

app = FastAPI(title="SmartTable.ma SaaS Engine", version="5.0.0")

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
        return {"status": "success", "message": "Item successfully added to live menu!"}
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
        return {"status": "success", "message": "Item removed from menu!"}
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
            raise HTTPException(status_code=400, detail="This friend already has a loyalty account.")
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

@app.post("/api/rewards/purchase-cashback")
def purchase_cashback(data: PurchaseLog):
    try:
        earned_points = int(data.amount_spent * 0.10) # 10% cashback
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (data.phone_number,))
        customer = cur.fetchone()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found.")
        
        if not customer["has_purchased"] and customer["referred_by"]:
            referrer_phone = customer["referred_by"]
            cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (referrer_phone,))
            referrer = cur.fetchone()
            if referrer:
                new_ref_balance = referrer["points_balance"] + 50
                cur.execute("UPDATE customers SET points_balance = %s WHERE phone_number = %s;", (new_ref_balance, referrer_phone))
        
        new_balance = customer["points_balance"] + earned_points
        cur.execute(
            "UPDATE customers SET points_balance = %s, has_purchased = TRUE WHERE phone_number = %s;",
            (new_balance, data.phone_number)
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "earned": earned_points, "new_balance": new_balance}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- WORLD-CLASS PROFESSIONAL SAAS UI ---
@app.get("/", response_class=HTMLResponse)
def serve_mobile_frontend():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SmartTable.ma | Premium Table Experience</title>
    <link rel="icon" type="image/png" href="https://img.icons8.com/color/48/qr-code.png">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-deep: #090d16;
            --surface: #131c31;
            --surface-card: #1a2642;
            --accent: #f59e0b; /* Warm Moroccan Gold */
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
        .tab-btn { flex: 1; padding: 0.6rem; text-align: center; border-radius: 10px; font-size: 0.8rem; font-weight: 600; color: var(--text-muted); cursor: pointer; border: none; background: transparent; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
        .tab-btn.active { background: var(--surface-card); color: var(--text-main); box-shadow: 0 4px 12px rgba(0,0,0,0.3); border: 1px solid var(--border); }
        
        .card { background: var(--surface-card); border-radius: 16px; padding: 1.25rem; margin-bottom: 1rem; border: 1px solid var(--border); }
        
        label { display: block; font-size: 0.75rem; font-weight: 600; color: var(--text-muted); margin-bottom: 0.4rem; text-transform: uppercase; letter-spacing: 0.5px; }
        input { width: 100%; padding: 0.8rem 1rem; border-radius: 12px; border: 1px solid var(--border); background: var(--bg-deep); color: white; font-size: 0.9rem; margin-bottom: 0.85rem; outline: none; transition: border-color 0.2s; }
        input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
        
        .btn-main { width: 100%; padding: 0.8rem; border-radius: 12px; border: none; background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: #090d16; font-weight: 700; font-size: 0.95rem; cursor: pointer; transition: transform 0.1s, opacity 0.2s; box-shadow: 0 4px 14px var(--accent-glow); }
        .btn-main:active { transform: scale(0.98); }
        
        .hidden { display: none !important; }
        
        .points-display { text-align: center; padding: 0.5rem 0; }
        .points-label { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }
        .points-number { font-size: 3rem; font-weight: 800; color: var(--success); letter-spacing: -1px; margin: 0.2rem 0; }
        .cashback-badge { display: inline-block; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); color: var(--success); padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; margin-bottom: 1rem; }

        .referral-box { border-top: 1px solid var(--border); margin-top: 1rem; padding-top: 1rem; }
        
        .review-link { display: flex; align-items: center; justify-content: center; gap: 8px; text-align: center; margin-top: 1rem; padding: 0.85rem; background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.3); color: var(--accent); border-radius: 12px; text-decoration: none; font-weight: 700; font-size: 0.85rem; transition: background 0.2s; }
        .review-link:hover { background: rgba(245, 158, 11, 0.15); }

        .menu-grid { display: flex; flex-direction: column; gap: 0.75rem; max-height: 360px; overflow-y: auto; padding-right: 2px; }
        .menu-card { display: flex; align-items: center; background: var(--bg-deep); border-radius: 14px; padding: 0.75rem; border: 1px solid var(--border); gap: 0.85rem; cursor: pointer; transition: all 0.2s; }
        .menu-card:hover { border-color: var(--accent); transform: translateY(-1px); }
        .menu-img { width: 55px; height: 55px; border-radius: 10px; object-fit: cover; background: var(--surface); }
        .menu-info { flex: 1; }
        .menu-name { font-size: 0.95rem; font-weight: 700; color: var(--text-main); margin-bottom: 2px; }
        .menu-cat { font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; font-weight: 700; }
        .menu-price { font-size: 0.9rem; font-weight: 800; color: var(--accent); }

        /* Modal Overlay */
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(9, 13, 22, 0.85); backdrop-filter: blur(8px); justify-content: center; align-items: center; padding: 1.5rem; }
        .modal-content { background: var(--surface); padding: 1.5rem; border-radius: 24px; max-width: 360px; width: 100%; text-align: center; border: 1px solid var(--border); box-shadow: 0 25px 50px rgba(0,0,0,0.8); animation: modalPop 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
        @keyframes modalPop { from { transform: scale(0.9); opacity: 0; } to { transform: scale(1); opacity: 1; } }
        .modal-img { width: 100%; height: 230px; border-radius: 16px; object-fit: cover; margin-bottom: 1rem; border: 1px solid var(--border); }
        .close-modal { background: var(--border); color: var(--text-main); border: none; padding: 0.75rem; border-radius: 12px; cursor: pointer; font-weight: 700; width: 100%; transition: background 0.2s; }
        .close-modal:hover { background: var(--danger); }

        .admin-item-row { display: flex; justify-content: space-between; align-items: center; background: var(--bg-deep); padding: 0.75rem; border-radius: 12px; margin-bottom: 0.5rem; font-size: 0.85rem; border: 1px solid var(--border); }
        .danger-btn { background: rgba(239, 68, 68, 0.15); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); padding: 6px 10px; border-radius: 8px; cursor: pointer; font-weight: 700; transition: background 0.2s; }
        .danger-btn:hover { background: var(--danger); color: white; }
        .edit-btn { background: rgba(56, 189, 248, 0.15); color: var(--primary); border: 1px solid rgba(56, 189, 248, 0.3); padding: 6px 10px; border-radius: 8px; cursor: pointer; font-weight: 700; margin-right: 6px; transition: background 0.2s; }
        .edit-btn:hover { background: var(--primary); color: #090d16; }

        .message-box { margin-top: 0.75rem; padding: 0.75rem; border-radius: 10px; font-size: 0.8rem; text-align: center; font-weight: 600; }
        .success-msg { background: rgba(16, 185, 129, 0.15); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.3); }
        .error-msg { background: rgba(239, 68, 68, 0.15); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); }
    </style>
</head>
<body>
    <div class="app-frame">
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
                    <div class="points-label">Your Balance</div>
                    <div class="points-number" id="points-val">0</div>
                    <div class="cashback-badge">⚡ Earn 10% Cashback on Every Order</div>
                </div>
                
                <div class="referral-box">
                    <label>Refer a Friend</label>
                    <input type="tel" id="friend-phone" placeholder="Friend's Phone Number" />
                    <button class="btn-main" onclick="referFriend()" style="background: linear-gradient(135deg, #38bdf8 0%, #0284c7 100%); color: #090d16;">Register Friend (+50 pts on 1st visit)</button>
                </div>

                <a href="https://maps.google.com" target="_blank" class="review-link" onclick="claimReview()">
                    ⭐ Leave Google Review & Claim +50 Points
                </a>
            </div>
        </div>

        <div id="tab-menu" class="card hidden">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.85rem;">
                <h3 style="font-size: 1rem; font-weight: 700; color: var(--accent);">Live Menu</h3>
                <span style="font-size: 0.7rem; color: var(--text-muted);">Tap item to zoom</span>
            </div>
            <div id="menu-container" class="menu-grid">
                <div style="text-align:center; color:var(--text-muted); font-size:0.85rem; padding: 2rem 0;">Loading menu...</div>
            </div>
        </div>

        <div id="tab-admin" class="card hidden">
            <h3 style="margin-bottom: 0.85rem; font-size: 1rem; font-weight: 700; color: var(--accent);">Owner Menu Manager</h3>
            <label>Category</label>
            <input type="text" id="admin-cat" placeholder="e.g., Burgers & Grills" />
            
            <label>Item Name</label>
            <input type="text" id="admin-name" placeholder="e.g., Cheesy Burger" />
            
            <label>Price (MAD)</label>
            <input type="text" id="admin-price" placeholder="e.g., 65" />
            
            <label>Image URL (Optional)</label>
            <input type="text" id="admin-img" placeholder="https://..." />
            
            <button class="btn-main" onclick="addMenuItem()" style="margin-bottom: 1.25rem;">+ Add to Live Menu</button>
            
            <label style="margin-bottom: 0.5rem;">Active Inventory</label>
            <div id="admin-menu-list" style="max-height: 160px; overflow-y: auto; padding-right: 2px;"></div>
        </div>

        <div id="feedback-msg" class="message-box hidden"></div>
    </div>

    <!-- High-Resolution Image Zoom Modal -->
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
            } else if(tabName === 'menu') {
                document.querySelectorAll('.tab-btn')[1].classList.add('active');
                document.getElementById('tab-menu').classList.remove('hidden');
                loadMenu();
            } else {
                const adminBtn = document.getElementById('admin-tab-btn');
                if(adminBtn) adminBtn.classList.add('active');
                document.getElementById('tab-admin').classList.remove('hidden');
                loadAdminMenu();
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
                    container.innerHTML = '<div style="color:var(--text-muted); font-size:0.75rem; text-align:center; padding:1rem;">No inventory found.</div>';
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
            } catch(e) {
                console.error(e);
            }
        }

        async function addMenuItem() {
            const category = document.getElementById('admin-cat').value;
            const name = document.getElementById('admin-name').value;
            const price = document.getElementById('admin-price').value;
            const image_url = document.getElementById('admin-img').value;
            if(!category || !name || !price) { alert('Please fill in category, name, and price.'); return; }
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
            const newPrice = prompt("Enter new price in MAD (e.g., 70):");
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
            if(!confirm('Are you sure you want to delete this menu item?')) return;
            try {
                const res = await fetch('/api/admin/menu/' + id, { method: 'DELETE' });
                const data = await res.json();
                showMsg(data.message, 'success-msg');
                loadAdminMenu();
            } catch(e) {
                alert('Error deleting item.');
            }
        }

        async function loginCustomer() {
            const phone = document.getElementById('phone-input').value;
            if(!phone) { alert('Please enter your phone number.'); return; }
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
                    showMsg('Welcome back to SmartTable.ma!', 'success-msg');
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
                showMsg(data.message, 'success-msg');
            } catch(e) {
                showMsg('Error claiming points', 'error-msg');
            }
        }

        async function referFriend() {
            const friendPhone = document.getElementById('friend-phone').value;
            if(!friendPhone) { alert("Please enter your friend's phone number."); return; }
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
    """

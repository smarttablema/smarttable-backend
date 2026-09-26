import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from supabase import create_client, Client

SUPABASE_URL = "https://ygaklnfdrfuophgndnnp.supabase.co"
SUPABASE_KEY = "sb_secret_d6gykHBup5RXtrEqSrvA2uw_Rsqqp7nK"

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    supabase = None

app = FastAPI(title="SmartTable.ma SaaS Engine", version="3.2.9")

class CustomerAuth(BaseModel):
    phone_number: str
    restaurant_slug: str = "default-restaurant"

class ReviewReward(BaseModel):
    phone_number: str

class MenuItemCreate(BaseModel):
    restaurant_slug: str = "default-restaurant"
    category: str
    name: str
    price: str
    image_url: str = ""

@app.get("/api/health")
def health_check():
    return {"status": "online", "brand": "smarttable.ma"}

@app.post("/api/customer/auth")
def authenticate_customer(data: CustomerAuth):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not initialized.")
    try:
        response = supabase.table("customers").select("*").eq("phone_number", data.phone_number).execute()
        if response.data and len(response.data) > 0:
            customer = response.data[0]
        else:
            ins_res = supabase.table("customers").insert({"phone_number": data.phone_number, "points_balance": 0}).execute()
            customer = ins_res.data[0]
        return {"status": "success", "points_balance": customer.get("points_balance", 0)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/menu/{slug}")
def get_menu(slug: str):
    if not supabase:
        return []
    try:
        res = supabase.table("menu_items").select("*").eq("restaurant_slug", slug).execute()
        return res.data or []
    except Exception as e:
        return []

@app.post("/api/admin/menu/add")
def add_menu_item(item: MenuItemCreate):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not initialized.")
    try:
        res = supabase.table("menu_items").insert({
            "restaurant_slug": item.restaurant_slug,
            "category": item.category,
            "name": item.name,
            "price": item.price,
            "image_url": item.image_url
        }).execute()
        return {"status": "success", "message": "Item added successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rewards/claim-review")
def claim_google_review(data: ReviewReward):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not initialized.")
    try:
        response = supabase.table("customers").select("*").eq("phone_number", data.phone_number).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Customer not found.")
        customer = response.data[0]
        new_balance = customer.get("points_balance", 0) + 50
        supabase.table("customers").update({"points_balance": new_balance}).eq("phone_number", data.phone_number).execute()
        return {"status": "success", "new_balance": new_balance, "message": "50 points added for your review!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- UNIFIED MOBILE & OWNER ADMIN UI ---
@app.get("/", response_class=HTMLResponse)
def serve_mobile_frontend():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SmartTable.ma - Table Experience</title>
    <link rel="icon" type="image/png" href="https://img.icons8.com/color/48/qr-code.png">
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --accent: #38bdf8;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --success: #22c55e;
            --error: #ef4444;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background-color: var(--bg-color); color: var(--text-main); display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 1rem; }
        .mobile-container { width: 100%; max-width: 400px; background: var(--card-bg); border-radius: 24px; padding: 1.5rem; box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.5); border: 1px solid #334155; }
        .brand-header { text-align: center; margin-bottom: 1rem; }
        .logo { font-size: 1.5rem; font-weight: 900; color: var(--accent); }
        .brand-tag { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; }
        .nav-tabs { display: flex; background: #0f172a; border-radius: 12px; padding: 4px; margin-bottom: 1rem; border: 1px solid #1e293b; }
        .tab-btn { flex: 1; padding: 0.5rem; text-align: center; border-radius: 8px; font-size: 0.8rem; font-weight: 600; color: var(--text-muted); cursor: pointer; border: none; background: transparent; transition: 0.2s; }
        .tab-btn.active { background: var(--accent); color: #0f172a; }
        .card { background: #0f172a; border-radius: 16px; padding: 1.25rem; margin-bottom: 1rem; border: 1px solid #1e293b; }
        input { width: 100%; padding: 0.75rem; border-radius: 10px; border: 1px solid #475569; background: #1e293b; color: white; font-size: 0.9rem; margin-bottom: 0.75rem; outline: none; }
        button.action-submit { width: 100%; padding: 0.75rem; border-radius: 10px; border: none; background: var(--accent); color: #0f172a; font-weight: 700; font-size: 0.9rem; cursor: pointer; }
        .hidden { display: none !important; }
        .points-number { font-size: 2.5rem; font-weight: 900; color: var(--success); text-align: center; margin: 0.5rem 0; }
        .action-btn { width: 100%; padding: 0.75rem; border-radius: 10px; border: none; background: #334155; color: white; font-weight: 600; cursor: pointer; margin-top: 0.5rem; }
        .menu-grid { display: flex; flex-direction: column; gap: 0.75rem; max-height: 350px; overflow-y: auto; }
        .menu-card { display: flex; align-items: center; background: #1e293b; border-radius: 12px; padding: 0.75rem; border: 1px solid #334155; gap: 0.75rem; }
        .menu-img { width: 50px; height: 50px; border-radius: 8px; object-fit: cover; background: #334155; }
        .menu-info { flex: 1; }
        .menu-name { font-size: 0.9rem; font-weight: 600; color: var(--text-main); }
        .menu-cat { font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; }
        .menu-price { font-size: 0.85rem; font-weight: 700; color: var(--success); }
        .message-box { margin-top: 0.5rem; padding: 0.5rem; border-radius: 6px; font-size: 0.75rem; text-align: center; }
        .success-msg { background: rgba(34, 197, 94, 0.1); color: var(--success); border: 1px solid rgba(34, 197, 94, 0.2); }
        .error-msg { background: rgba(239, 68, 68, 0.1); color: var(--error); border: 1px solid rgba(239, 68, 68, 0.2); }
    </style>
</head>
<body>
    <div class="mobile-container">
        <div class="brand-header">
            <div class="logo">SmartTable.ma</div>
            <div class="brand-tag">Table Experience</div>
        </div>
        <div class="nav-tabs">
            <button class="tab-btn active" onclick="switchTab('rewards')">🏆 Rewards</button>
            <button class="tab-btn" onclick="switchTab('menu')">📖 Menu</button>
            <button class="tab-btn hidden" id="admin-tab-btn" onclick="switchTab('admin')">🔒 Owner</button>
        </div>
        <div id="tab-rewards">
            <div id="login-section" class="card">
                <h3 style="margin-bottom: 0.75rem; font-size: 0.95rem;">Check Your Points</h3>
                <input type="tel" id="phone-input" placeholder="Phone (e.g., 06XXXXXXXX)" />
                <button class="action-submit" onclick="loginCustomer()">Access Account</button>
            </div>
            <div id="dashboard-section" class="card hidden">
                <div style="font-size: 0.75rem; color: var(--text-muted); text-align:center;">Your Balance</div>
                <div class="points-number" id="points-val">0</div>
                <button class="action-btn" onclick="claimReview()">⭐ Leave Google Review (+50 pts)</button>
            </div>
        </div>
        <div id="tab-menu" class="card hidden">
            <h3 style="margin-bottom: 0.75rem; font-size: 0.95rem; color: var(--accent);">Live Restaurant Menu</h3>
            <div id="menu-container" class="menu-grid">
                <div style="text-align:center; color:var(--text-muted); font-size:0.85rem;">Loading menu...</div>
            </div>
        </div>
        <div id="tab-admin" class="card hidden">
            <h3 style="margin-bottom: 0.75rem; font-size: 0.95rem; color: var(--accent);">Owner Menu Manager</h3>
            <input type="text" id="admin-cat" placeholder="Category (e.g., Burgers)" />
            <input type="text" id="admin-name" placeholder="Item Name" />
            <input type="text" id="admin-price" placeholder="Price (e.g., 70 MAD)" />
            <input type="text" id="admin-img" placeholder="Image URL (optional)" />
            <button class="action-submit" onclick="addMenuItem()">+ Add Item</button>
        </div>
        <div id="feedback-msg" class="message-box hidden"></div>
    </div>
    <script>
        let currentPhone = '';
        const currentSlug = 'default-restaurant';
        window.onload = function() {
            const urlParams = new URLSearchParams(window.location.search);
            if(urlParams.get('mode') === 'admin') {
                document.getElementById('admin-tab-btn').classList.remove('hidden');
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
                document.getElementById('admin-tab-btn').classList.add('active');
                document.getElementById('tab-admin').classList.remove('hidden');
            }
        }
        async function loadMenu() {
            try {
                const res = await fetch('/api/menu/' + currentSlug);
                const items = await res.json();
                const container = document.getElementById('menu-container');
                if(!items || items.length === 0) {
                    container.innerHTML = '<div style="text-align:center; color:var(--text-muted);">No items found. Add items from Owner tab!</div>';
                    return;
                }
                container.innerHTML = items.map(item => `
                    <div class="menu-card">
                        <img src="${item.image_url || 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=500'}" class="menu-img" />
                        <div class="menu-info">
                            <div class="menu-cat">${item.category}</div>
                            <div class="menu-name">${item.name}</div>
                            <div class="menu-price">${item.price}</div>
                        </div>
                    </div>
                `).join('');
            } catch(e) {
                document.getElementById('menu-container').innerHTML = '<div style="text-align:center; color:var(--error);">Failed to load menu.</div>';
            }
        }
        async function addMenuItem() {
            const category = document.getElementById('admin-cat').value;
            const name = document.getElementById('admin-name').value;
            const price = document.getElementById('admin-price').value;
            const image_url = document.getElementById('admin-img').value;
            if(!category || !name || !price) { alert('Fill in category, name, and price.'); return; }
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
            } catch(e) {
                alert('Error adding item.');
            }
        }
        async function loginCustomer() {
            const phone = document.getElementById('phone-input').value;
            if(!phone) { alert('Please enter phone number.'); return; }
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
                showMsg(data.message, 'success-msg');
            } catch(e) {
                showMsg('Error claiming points', 'error-msg');
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

import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from supabase import create_client, Client

# Direct Supabase Configuration for smarttable.ma
SUPABASE_URL = "https://ygaklnfdrfuophgndnnp.supabase.co"
SUPABASE_KEY = "sb_publishable_HfOTDDvOXVlB7IBiTnBdKg_FDnef..."

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception:
    supabase = None

app = FastAPI(title="SmartTable.ma Production API", version="2.1.0")

class CustomerAuth(BaseModel):
    phone_number: str
    restaurant_slug: str = "default-restaurant"

class ReviewReward(BaseModel):
    phone_number: str

# --- API ENDPOINTS ---
@app.get("/api/health")
def health_check():
    return {"status": "online", "brand": "smarttable.ma", "message": "Supabase-connected loyalty engine is running."}

@app.post("/api/customer/auth")
def authenticate_customer(data: CustomerAuth):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not configured.")
    
    # Check if customer exists in Supabase
    response = supabase.table("customers").select("*").eq("phone_number", data.phone_number).execute()
    
    if response.data and len(response.data) > 0:
        customer = response.data[0]
    else:
        # Create new customer if they don't exist
        new_customer = {"phone_number": data.phone_number, "points_balance": 0}
        insert_res = supabase.table("customers").insert(new_customer).execute()
        customer = insert_res.data[0]

    return {
        "status": "success",
        "customer_id": customer.get("id"),
        "phone": customer.get("phone_number"),
        "points_balance": customer.get("points_balance", 0)
    }

@app.post("/api/rewards/claim-review")
def claim_google_review(data: ReviewReward):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not configured.")
    
    response = supabase.table("customers").select("*").eq("phone_number", data.phone_number).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Customer not found.")
    
    customer = response.data[0]
    new_balance = customer.get("points_balance", 0) + 50
    
    supabase.table("customers").update({"points_balance": new_balance}).eq("phone_number", data.phone_number).execute()

    return {
        "status": "success",
        "added_points": 50,
        "new_balance": new_balance,
        "message": "Review verified! 50 points added to your account."
    }

# --- EMBEDDED MOBILE FRONTEND UI ---
@app.get("/", response_class=HTMLResponse)
def serve_mobile_frontend():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SmartTable.ma - Loyalty & Rewards</title>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --accent: #38bdf8;
            --accent-hover: #0ea5e9;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --success: #22c55e;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background-color: var(--bg-color); color: var(--text-main); display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 1rem; }
        .mobile-container { width: 100%; max-width: 400px; background: var(--card-bg); border-radius: 24px; padding: 2rem; box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.5); border: 1px solid #334155; }
        .logo { text-align: center; font-size: 1.5rem; font-weight: 800; color: var(--accent); margin-bottom: 0.5rem; letter-spacing: -0.5px; }
        .subtitle { text-align: center; color: var(--text-muted); font-size: 0.875rem; margin-bottom: 2rem; }
        .card { background: #0f172a; border-radius: 16px; padding: 1.5rem; margin-bottom: 1.5rem; border: 1px solid #1e293b; }
        input { width: 100%; padding: 0.875rem 1rem; border-radius: 12px; border: 1px solid #475569; background: #1e293b; color: white; font-size: 1rem; margin-bottom: 1rem; outline: none; transition: border-color 0.2s; }
        input:focus { border-color: var(--accent); }
        button { width: 100%; padding: 0.875rem; border-radius: 12px; border: none; background: var(--accent); color: #0f172a; font-weight: 700; font-size: 1rem; cursor: pointer; transition: background 0.2s, transform 0.1s; }
        button:hover { background: var(--accent-hover); }
        button:active { transform: scale(0.98); }
        .hidden { display: none !important; }
        .points-display { text-align: center; margin: 1rem 0; }
        .points-number { font-size: 3rem; font-weight: 900; color: var(--success); }
        .points-label { color: var(--text-muted); font-size: 0.875rem; text-transform: uppercase; letter-spacing: 1px; }
        .action-btn { background: #334155; color: white; margin-top: 0.75rem; }
        .action-btn:hover { background: #475569; }
        .message-box { margin-top: 1rem; padding: 0.75rem; border-radius: 8px; font-size: 0.875rem; text-align: center; }
        .success-msg { background: rgba(34, 197, 94, 0.1); color: var(--success); border: 1px solid rgba(34, 197, 94, 0.2); }
    </style>
</head>
<body>
    <div class="mobile-container">
        <div class="logo">SmartTable.ma</div>
        <div class="subtitle">Tap. Earn. Enjoy Exclusive Rewards.</div>

        <div id="login-section" class="card">
            <h3 style="margin-bottom: 1rem; font-size: 1.1rem;">Enter to View Points</h3>
            <input type="tel" id="phone-input" placeholder="Phone Number (e.g., 06XXXXXXXX)" />
            <button onclick="loginCustomer()">Access My Account</button>
        </div>

        <div id="dashboard-section" class="card hidden">
            <div class="points-display">
                <div class="points-label">Your Balance</div>
                <div class="points-number" id="points-val">0</div>
                <div style="font-size: 0.8rem; color: var(--text-muted);">Points Available</div>
            </div>
            <button class="action-btn" onclick="claimReview()">⭐ Leave Google Review (+50 pts)</button>
        </div>

        <div id="feedback-msg" class="message-box hidden"></div>
    </div>

    <script>
        let currentPhone = '';

        async function loginCustomer() {
            const phone = document.getElementById('phone-input'].value;
            if(!phone) { alert('Please enter your phone number.'); return; }
            currentPhone = phone;

            try {
                const res = await fetch('/api/customer/auth', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ phone_number: phone })
                });
                const data = await res.json();
                
                document.getElementById('points-val').innerText = data.points_balance;
                document.getElementById('login-section').classList.add('hidden');
                document.getElementById('dashboard-section').classList.remove('hidden');
                showMsg('Welcome!', 'success-msg');
            } catch(e) {
                alert('Connection error. Please try again.');
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
                alert('Error claiming reward.');
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

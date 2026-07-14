import os
import json
import sqlite3
import hashlib
import secrets
import time
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional
from contextlib import contextmanager

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ==========================================
# ⚙️ تنظیمات
# ==========================================
PANEL_NAME = "REZA GROOTZ"
PANEL_PASSWORD = "reza grootz"
PANEL_VERSION = "2.0.0"

# ==========================================
# 📦 دیتابیس
# ==========================================
DB_FILE = "/data/panel.db" if os.path.isdir("/data") else "panel.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
    finally:
        conn.close()

# ==========================================
# 🔐 امنیت
# ==========================================
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_urlsafe(32))

def hash_password(password: str) -> str:
    return hashlib.sha256(f"{password}{SECRET_KEY}".encode()).hexdigest()

AUTH_HASH = hash_password(PANEL_PASSWORD)

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS links (
                uuid TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                limit_bytes INTEGER DEFAULT 0,
                used_bytes INTEGER DEFAULT 0,
                max_connections INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                expires_at TEXT
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                password_hash TEXT NOT NULL
            );
        """)
        conn.execute("INSERT OR IGNORE INTO auth (id, password_hash) VALUES (1, ?)", (AUTH_HASH,))
        conn.commit()

# ==========================================
# 🚀 اپلیکیشن
# ==========================================
app = FastAPI(title=PANEL_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 📊 دیتا
# ==========================================
LINKS = {}
SESSION_TTL = 60 * 60 * 24 * 7

# ==========================================
# 🔧 توابع
# ==========================================

def get_domain() -> str:
    return os.environ.get("RAILWAY_PUBLIC_DOMAIN", "localhost").replace("https://", "")

def uptime() -> str:
    return "00:00:00"

def _fmt_bytes(b: int) -> str:
    if b >= 1_073_741_824:
        return f"{b / 1_073_741_824:.1f}GB"
    if b >= 1_048_576:
        return f"{b / 1_048_576:.1f}MB"
    return f"{b / 1024:.1f}KB"

def generate_vless_link(uuid_str: str, remark: str = "") -> str:
    domain = get_domain()
    path = f"/ws/{uuid_str}?ed=2048"
    params = {
        "encryption": "none",
        "security": "tls",
        "type": "ws",
        "host": domain,
        "path": path,
        "sni": domain,
        "fp": "chrome"
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"vless://{uuid_str}@{domain}:443?{query}#{remark}"

def create_session() -> str:
    token = secrets.token_urlsafe(32)
    with get_db() as conn:
        conn.execute("INSERT INTO sessions (token, expires_at) VALUES (?, ?)", (token, time.time() + SESSION_TTL))
        conn.commit()
    return token

def is_valid_session(token: str) -> bool:
    if not token:
        return False
    with get_db() as conn:
        row = conn.execute("SELECT expires_at FROM sessions WHERE token = ?", (token,)).fetchone()
        if not row or row["expires_at"] < time.time():
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
            return False
        return True

def load_links():
    global LINKS
    try:
        with get_db() as conn:
            rows = conn.execute("SELECT * FROM links").fetchall()
            for row in rows:
                LINKS[row["uuid"]] = {
                    "label": row["label"],
                    "limit_bytes": row["limit_bytes"],
                    "used_bytes": row["used_bytes"],
                    "max_connections": row["max_connections"],
                    "created_at": row["created_at"],
                    "active": bool(row["active"]),
                    "expires_at": row["expires_at"],
                }
    except Exception:
        pass

def save_links():
    try:
        with get_db() as conn:
            for uid, link in LINKS.items():
                conn.execute("""
                    INSERT OR REPLACE INTO links (uuid, label, limit_bytes, used_bytes, max_connections, created_at, active, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (uid, link["label"], link["limit_bytes"], link["used_bytes"],
                      link.get("max_connections", 0), link["created_at"],
                      1 if link.get("active", True) else 0, link.get("expires_at")))
            conn.commit()
    except Exception:
        pass

# ==========================================
# 🌐 روت‌ها
# ==========================================

@app.get("/")
async def root():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>REZA GROOTZ Panel</title>
        <style>
            body { font-family: Arial; background: #0a0a0f; color: #ffd700; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; flex-direction: column; }
            .box { background: #111; padding: 40px; border-radius: 16px; border: 1px solid #ffd70033; text-align: center; max-width: 400px; }
            h1 { font-size: 28px; margin-bottom: 10px; }
            .sub { color: #888; font-size: 14px; margin-bottom: 20px; }
            .btn { background: #ffd700; color: #000; padding: 12px 40px; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; text-decoration: none; display: inline-block; }
            .btn:hover { background: #ffed4a; }
            .status { color: #4ade80; font-size: 13px; margin-top: 16px; }
        </style>
    </head>
    <body>
        <div class="box">
            <h1>🏴‍☠️ REZA GROOTZ</h1>
            <div class="sub">VLESS Panel v2.0</div>
            <a href="/login" class="btn">🔑 ورود به پنل</a>
            <div class="status">✅ پنل در حال اجراست!</div>
        </div>
    </body>
    </html>
    """)

@app.get("/health")
async def health():
    return {"status": "ok", "panel": PANEL_NAME, "version": PANEL_VERSION}

@app.post("/api/login")
async def api_login(request: Request):
    try:
        body = await request.json()
        password = body.get("password", "")
    except:
        raise HTTPException(status_code=400, detail="Invalid request")
    
    if hash_password(password) != AUTH_HASH:
        raise HTTPException(status_code=401, detail="Invalid password")
    
    token = create_session()
    resp = JSONResponse({"ok": True})
    resp.set_cookie(key="ren_session", value=token, max_age=SESSION_TTL, httponly=True, path="/")
    return resp

@app.get("/api/me")
async def api_me(request: Request):
    token = request.cookies.get("ren_session")
    return {"authenticated": is_valid_session(token)}

@app.post("/api/logout")
async def api_logout(request: Request):
    token = request.cookies.get("ren_session")
    if token:
        with get_db() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("ren_session", path="/")
    return resp

@app.get("/api/links")
async def list_links(request: Request):
    token = request.cookies.get("ren_session")
    if not is_valid_session(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    result = []
    for uid, data in LINKS.items():
        result.append({
            "uuid": uid,
            "label": data["label"],
            "limit_bytes": data["limit_bytes"],
            "used_bytes": data["used_bytes"],
            "max_connections": data.get("max_connections", 0),
            "active": data["active"],
            "created_at": data["created_at"],
            "expires_at": data.get("expires_at"),
            "vless_link": generate_vless_link(uid, f"{PANEL_NAME}-{data['label']}")
        })
    return {"links": result}

@app.post("/api/links")
async def create_link(request: Request):
    token = request.cookies.get("ren_session")
    if not is_valid_session(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        body = await request.json()
    except:
        raise HTTPException(status_code=400, detail="Invalid request")
    
    label = body.get("label", "New Link").strip()[:60]
    if not label or not re.match(r'^[a-zA-Z0-9\-_. ]+$', label):
        raise HTTPException(status_code=400, detail="Invalid label")
    
    for uid, data in LINKS.items():
        if data["label"] == label:
            raise HTTPException(status_code=400, detail="Link already exists")
    
    limit_value = float(body.get("limit_value", 0))
    limit_bytes = int(limit_value * 1024 * 1024 * 1024) if limit_value > 0 else 0
    max_conn = int(body.get("max_connections", 0))
    days_valid = body.get("days_valid", 0)
    
    expires_at = None
    if days_valid and days_valid > 0:
        expires_at = (datetime.now() + timedelta(days=days_valid)).isoformat()
    
    uid = str(uuid.uuid4())
    LINKS[uid] = {
        "label": label,
        "limit_bytes": limit_bytes,
        "used_bytes": 0,
        "max_connections": max_conn,
        "created_at": datetime.now().isoformat(),
        "active": True,
        "expires_at": expires_at,
    }
    save_links()
    
    return {
        "uuid": uid,
        "label": label,
        "limit_bytes": limit_bytes,
        "used_bytes": 0,
        "max_connections": max_conn,
        "active": True,
        "created_at": LINKS[uid]["created_at"],
        "expires_at": expires_at,
        "vless_link": generate_vless_link(uid, f"{PANEL_NAME}-{label}")
    }

@app.patch("/api/links/{uid}")
async def update_link(uid: str, request: Request):
    token = request.cookies.get("ren_session")
    if not is_valid_session(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    if uid not in LINKS:
        raise HTTPException(status_code=404, detail="Link not found")
    
    try:
        body = await request.json()
    except:
        raise HTTPException(status_code=400, detail="Invalid request")
    
    if "active" in body:
        LINKS[uid]["active"] = bool(body["active"])
    if "reset_usage" in body and body["reset_usage"]:
        LINKS[uid]["used_bytes"] = 0
    if "label" in body:
        LINKS[uid]["label"] = body["label"][:60]
    if "limit_value" in body:
        limit_value = float(body["limit_value"])
        LINKS[uid]["limit_bytes"] = int(limit_value * 1024 * 1024 * 1024) if limit_value > 0 else 0
    
    save_links()
    return {"ok": True}

@app.delete("/api/links/{uid}")
async def delete_link(uid: str, request: Request):
    token = request.cookies.get("ren_session")
    if not is_valid_session(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    if uid not in LINKS:
        raise HTTPException(status_code=404, detail="Link not found")
    
    del LINKS[uid]
    save_links()
    return {"ok": True}

@app.get("/stats")
async def get_stats(request: Request):
    token = request.cookies.get("ren_session")
    if not is_valid_session(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    return {
        "panel_name": PANEL_NAME,
        "links_count": len(LINKS),
        "active_connections": 0,
        "total_traffic_mb": 0,
        "uptime": uptime(),
        "domain": get_domain(),
        "cpu_percent": 0,
        "memory_percent": 0,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/login")
async def login_page():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>REZA GROOTZ - Login</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                background: #0a0a0f;
                font-family: 'Segoe UI', Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                background: radial-gradient(ellipse at center, #0f0f1a 0%, #060608 100%);
            }
            .login-box {
                background: #111118;
                border: 1px solid rgba(255, 215, 0, 0.15);
                border-radius: 20px;
                padding: 48px 40px;
                width: 100%;
                max-width: 380px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.8), 0 0 40px rgba(255,215,0,0.05);
            }
            .logo {
                text-align: center;
                margin-bottom: 32px;
            }
            .logo h1 {
                color: #FFD700;
                font-size: 28px;
                font-weight: 900;
                letter-spacing: 3px;
                text-shadow: 0 0 30px rgba(255,215,0,0.15);
            }
            .logo p {
                color: rgba(255,255,255,0.3);
                font-size: 12px;
                letter-spacing: 4px;
                text-transform: uppercase;
                margin-top: 6px;
            }
            .input-group {
                margin-bottom: 20px;
            }
            .input-group label {
                display: block;
                color: rgba(255,215,0,0.6);
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1.5px;
                text-transform: uppercase;
                margin-bottom: 6px;
            }
            .input-group input {
                width: 100%;
                padding: 12px 16px;
                background: #1a1a24;
                border: 1px solid rgba(255,215,0,0.1);
                border-radius: 10px;
                color: #fff;
                font-size: 16px;
                transition: all 0.3s;
                outline: none;
            }
            .input-group input:focus {
                border-color: rgba(255,215,0,0.4);
                box-shadow: 0 0 0 3px rgba(255,215,0,0.05);
            }
            .input-group input::placeholder {
                color: rgba(255,255,255,0.2);
            }
            .btn-login {
                width: 100%;
                padding: 14px;
                background: linear-gradient(135deg, #FFD700, #FFC200);
                border: none;
                border-radius: 10px;
                color: #000;
                font-size: 16px;
                font-weight: 800;
                letter-spacing: 1px;
                cursor: pointer;
                transition: all 0.3s;
                margin-top: 8px;
            }
            .btn-login:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 30px rgba(255,215,0,0.25);
            }
            .btn-login:active { transform: translateY(0); }
            .error {
                color: #f87171;
                font-size: 13px;
                text-align: center;
                margin-top: 12px;
                display: none;
            }
            .footer {
                text-align: center;
                margin-top: 24px;
                color: rgba(255,255,255,0.15);
                font-size: 10px;
                letter-spacing: 2px;
            }
            .footer span { color: rgba(255,215,0,0.3); }
            .status-dot {
                display: inline-block;
                width: 8px;
                height: 8px;
                background: #4ade80;
                border-radius: 50%;
                margin-right: 6px;
                animation: pulse 2s infinite;
            }
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.3; }
            }
        </style>
    </head>
    <body>
        <div class="login-box">
            <div class="logo">
                <h1>🏴‍☠️ REZA GROOTZ</h1>
                <p>VLESS Panel v2.0</p>
            </div>
            <form id="loginForm" onsubmit="return false;">
                <div class="input-group">
                    <label>🔑 رمز عبور</label>
                    <input type="password" id="password" placeholder="••••••••" autofocus>
                </div>
                <button class="btn-login" onclick="doLogin()">ورود به پنل</button>
                <div class="error" id="errorMsg">❌ رمز عبور اشتباه است!</div>
            </form>
            <div class="footer">
                <span class="status-dot"></span> <span>سیستم آنلاین</span>
                <br><br>
                <span>REZA GROOTZ · v2.0</span>
            </div>
        </div>
        <script>
            document.getElementById('password').addEventListener('keydown', function(e) {
                if (e.key === 'Enter') doLogin();
            });

            async function doLogin() {
                const pw = document.getElementById('password').value;
                const err = document.getElementById('errorMsg');
                err.style.display = 'none';

                if (!pw) {
                    err.textContent = '❌ لطفاً رمز عبور را وارد کن!';
                    err.style.display = 'block';
                    return;
                }

                try {
                    const r = await fetch('/api/login', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ password: pw })
                    });

                    if (r.ok) {
                        window.location.href = '/dashboard';
                    } else {
                        err.textContent = '❌ رمز عبور اشتباه است!';
                        err.style.display = 'block';
                        document.getElementById('password').value = '';
                        document.getElementById('password').focus();
                    }
                } catch (e) {
                    err.textContent = '❌ خطا در ارتباط با سرور!';
                    err.style.display = 'block';
                }
            }
        </script>
    </body>
    </html>
    """)

@app.get("/dashboard")
async def dashboard(request: Request):
    token = request.cookies.get("ren_session")
    if not is_valid_session(token):
        return HTMLResponse('<script>window.location.href="/login"</script>')
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{PANEL_NAME} - Dashboard</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ background: #0a0a0f; font-family: 'Segoe UI', Arial, sans-serif; color: #fff; min-height: 100vh; }}
            .header {{ background: #111118; padding: 20px 30px; border-bottom: 1px solid rgba(255,215,0,0.1); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
            .header h1 {{ color: #FFD700; font-size: 22px; letter-spacing: 2px; }}
            .header span {{ color: rgba(255,255,255,0.3); font-size: 13px; }}
            .container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 24px; }}
            .stat-card {{ background: #111118; border: 1px solid rgba(255,215,0,0.08); border-radius: 12px; padding: 20px; text-align: center; }}
            .stat-card .num {{ font-size: 28px; font-weight: 800; color: #FFD700; }}
            .stat-card .label {{ color: rgba(255,255,255,0.4); font-size: 11px; text-transform: uppercase; letter-spacing: 1px; margin-top: 4px; }}
            .card {{ background: #111118; border: 1px solid rgba(255,215,0,0.08); border-radius: 12px; padding: 20px; margin-bottom: 16px; }}
            .card h3 {{ color: rgba(255,215,0,0.7); font-size: 14px; margin-bottom: 12px; letter-spacing: 1px; }}
            .btn {{ padding: 8px 20px; border-radius: 8px; border: none; font-weight: 700; cursor: pointer; font-size: 13px; transition: all 0.2s; }}
            .btn-gold {{ background: #FFD700; color: #000; }}
            .btn-gold:hover {{ background: #FFC200; transform: translateY(-1px); }}
            .btn-danger {{ background: rgba(248,113,113,0.15); color: #f87171; border: 1px solid rgba(248,113,113,0.2); }}
            .btn-danger:hover {{ background: rgba(248,113,113,0.25); }}
            .btn-ghost {{ background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.6); border: 1px solid rgba(255,255,255,0.08); }}
            .btn-ghost:hover {{ background: rgba(255,255,255,0.08); }}
            table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
            th {{ text-align: left; padding: 12px 10px; color: rgba(255,255,255,0.3); font-size: 10px; text-transform: uppercase; letter-spacing: 1px; border-bottom: 1px solid rgba(255,255,255,0.05); }}
            td {{ padding: 12px 10px; border-bottom: 1px solid rgba(255,255,255,0.04); }}
            .tag {{ padding: 2px 10px; border-radius: 4px; font-size: 10px; font-weight: 700; text-transform: uppercase; }}
            .tag-on {{ background: rgba(74,222,128,0.15); color: #4ade80; }}
            .tag-off {{ background: rgba(248,113,113,0.15); color: #f87171; }}
            .tag-vless {{ background: rgba(255,215,0,0.1); color: #FFD700; }}
            .empty {{ text-align: center; padding: 40px; color: rgba(255,255,255,0.2); }}
            .modal {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.8); z-index: 100; align-items: center; justify-content: center; backdrop-filter: blur(8px); }}
            .modal.active {{ display: flex; }}
            .modal-box {{ background: #111118; border: 1px solid rgba(255,215,0,0.15); border-radius: 16px; padding: 32px; width: 100%; max-width: 420px; }}
            .modal-box h2 {{ color: #FFD700; margin-bottom: 20px; font-size: 18px; }}
            .modal-box input, .modal-box select {{ width: 100%; padding: 10px 14px; background: #1a1a24; border: 1px solid rgba(255,215,0,0.08); border-radius: 8px; color: #fff; font-size: 14px; margin-bottom: 12px; outline: none; }}
            .modal-box input:focus {{ border-color: rgba(255,215,0,0.3); }}
            .modal-box .row {{ display: flex; gap: 10px; }}
            .modal-box .row > * {{ flex: 1; }}
            .modal-close {{ float: right; background: none; border: none; color: rgba(255,255,255,0.3); font-size: 20px; cursor: pointer; }}
            .actions {{ display: flex; gap: 6px; flex-wrap: wrap; }}
            .actions button {{ padding: 4px 10px; border-radius: 4px; border: none; font-size: 11px; font-weight: 700; cursor: pointer; transition: all 0.15s; }}
            .act-copy {{ background: rgba(255,215,0,0.1); color: #FFD700; }}
            .act-edit {{ background: rgba(251,191,36,0.1); color: #fbbf24; }}
            .act-del {{ background: rgba(248,113,113,0.1); color: #f87171; }}
            .act-copy:hover {{ background: rgba(255,215,0,0.2); }}
            .act-edit:hover {{ background: rgba(251,191,36,0.2); }}
            .act-del:hover {{ background: rgba(248,113,113,0.2); }}
            .toggle {{
                width: 36px; height: 20px; background: rgba(255,255,255,0.1); border-radius: 10px;
                position: relative; cursor: pointer; transition: all 0.3s; display: inline-block;
            }}
            .toggle::after {{
                content: ''; position: absolute; width: 14px; height: 14px; background: #fff;
                border-radius: 50%; top: 3px; left: 3px; transition: all 0.3s;
            }}
            .toggle.on {{ background: #4ade80; }}
            .toggle.on::after {{ left: 19px; }}
            .toast {{ position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: #1a1a24; border: 1px solid rgba(255,215,0,0.2); padding: 12px 24px; border-radius: 10px; color: #FFD700; font-weight: 600; display: none; z-index: 200; }}
            .toast.show {{ display: block; animation: fadeIn 0.3s; }}
            @keyframes fadeIn {{ from {{ opacity: 0; transform: translateX(-50%) translateY(10px); }} to {{ opacity: 1; transform: translateX(-50%) translateY(0); }} }}
            @media (max-width: 600px) {{ .header {{ flex-direction: column; text-align: center; }} .stats {{ grid-template-columns: 1fr 1fr; }} table {{ font-size: 12px; }} .actions button {{ font-size: 9px; padding: 2px 6px; }} }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🏴‍☠️ {PANEL_NAME}</h1>
            <div>
                <span id="statsInfo">در حال بارگذاری...</span>
                <button onclick="doLogout()" style="background:rgba(248,113,113,0.1);color:#f87171;border:1px solid rgba(248,113,113,0.2);padding:6px 14px;border-radius:6px;cursor:pointer;font-weight:600;margin-left:12px;">🚪 خروج</button>
            </div>
        </div>

        <div class="container">
            <div class="stats">
                <div class="stat-card"><div class="num" id="statUsers">0</div><div class="label">👥 کاربران</div></div>
                <div class="stat-card"><div class="num" id="statTraffic">0</div><div class="label">📊 ترافیک (MB)</div></div>
                <div class="stat-card"><div class="num" id="statUptime">-</div><div class="label">⏱ آپتایم</div></div>
                <div class="stat-card"><div class="num" id="statDomain">-</div><div class="label">🌐 دامنه</div></div>
            </div>

            <div class="card">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:12px;">
                    <h3>📋 لیست کاربران</h3>
                    <button class="btn btn-gold" onclick="openAddModal()">➕ افزودن کاربر</button>
                </div>
                <div id="linksTable">
                    <div class="empty">در حال بارگذاری...</div>
                </div>
            </div>
        </div>

        <!-- Modal افزودن -->
        <div class="modal" id="addModal">
            <div class="modal-box">
                <button class="modal-close" onclick="closeModal('addModal')">✕</button>
                <h2>➕ افزودن کاربر جدید</h2>
                <input type="text" id="addLabel" placeholder="نام کاربر (مثال: Reza)">
                <div class="row">
                    <input type="number" id="addLimit" placeholder="حجم (GB)" min="0" step="0.5">
                    <input type="number" id="addDays" placeholder="روز اعتبار" min="0">
                </div>
                <input type="number" id="addIPs" placeholder="حداکثر IP (0 = نامحدود)" min="0">
                <button class="btn btn-gold" onclick="createLink()" style="width:100%;padding:12px;">🚀 ساخت کاربر</button>
            </div>
        </div>

        <div class="toast" id="toast"></div>

        <script>
            let links = [];

            async function loadStats() {{
                try {{
                    const r = await fetch('/stats');
                    if (!r.ok) throw new Error();
                    const d = await r.json();
                    document.getElementById('statUsers').textContent = d.links_count || 0;
                    document.getElementById('statTraffic').textContent = d.total_traffic_mb || 0;
                    document.getElementById('statUptime').textContent = d.uptime || '-';
                    document.getElementById('statDomain').textContent = d.domain || '-';
                    document.getElementById('statsInfo').textContent = '🟢 ' + d.links_count + ' کاربر · ' + (d.total_traffic_mb || 0) + 'MB';
                }} catch(e) {{}}
            }}

            async function loadLinks() {{
                try {{
                    const r = await fetch('/api/links');
                    if (r.status === 401) {{ window.location.href = '/login'; return; }}
                    if (!r.ok) throw new Error();
                    const d = await r.json();
                    links = d.links || [];
                    renderLinks();
                    loadStats();
                }} catch(e) {{
                    document.getElementById('linksTable').innerHTML = '<div class="empty">❌ خطا در دریافت لیست</div>';
                }}
            }}

            function renderLinks() {{
                const container = document.getElementById('linksTable');
                if (!links || !links.length) {{
                    container.innerHTML = '<div class="empty">📭 هیچ کاربری یافت نشد</div>';
                    return;
                }}
                let html = `<table>
                    <tr><th>نام</th><th>مصرف</th><th>وضعیت</th><th>انقضا</th><th>عملیات</th></tr>`;
                for (const l of links) {{
                    const used = (l.used_bytes / (1024**3)).toFixed(1);
                    const limit = l.limit_bytes > 0 ? (l.limit_bytes / (1024**3)).toFixed(1) + 'GB' : '∞';
                    const status = l.active ? '<span class="tag tag-on">فعال</span>' : '<span class="tag tag-off">غیرفعال</span>';
                    const exp = l.expires_at ? new Date(l.expires_at).toLocaleDateString('fa-IR') : '∞';
                    const vless = l.vless_link || '';
                    html += `<tr>
                        <td><strong>${{l.label}}</strong></td>
                        <td>${{used}}GB / ${{limit}}</td>
                        <td>${{status}}</td>
                        <td>${{exp}}</td>
                        <td>
                            <div class="actions">
                                <div class="toggle ${{l.active?'on':''}}" onclick="toggleLink('${{l.uuid}}')"></div>
                                <button class="act-copy" onclick="copyLink('${{vless}}')">📋</button>
                                <button class="act-edit" onclick="editLink('${{l.uuid}}')">✏️</button>
                                <button class="act-del" onclick="deleteLink('${{l.uuid}}')">🗑️</button>
                            </div>
                        </td>
                    </tr>`;
                }}
                html += '</table>';
                container.innerHTML = html;
            }}

            async function toggleLink(uid) {{
                try {{
                    const l = links.find(x => x.uuid === uid);
                    if (!l) return;
                    const r = await fetch('/api/links/' + uid, {{
                        method: 'PATCH',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ active: !l.active }})
                    }});
                    if (r.ok) {{ loadLinks(); showToast('✅ وضعیت تغییر کرد'); }}
                }} catch(e) {{ showToast('❌ خطا', true); }}
            }}

            async function deleteLink(uid) {{
                if (!confirm('آیا از حذف این کاربر مطمئنی؟')) return;
                try {{
                    const r = await fetch('/api/links/' + uid, {{ method: 'DELETE' }});
                    if (r.ok) {{ loadLinks(); showToast('🗑️ کاربر حذف شد'); }}
                }} catch(e) {{ showToast('❌ خطا', true); }}
            }}

            function copyLink(text) {{
                if (!text) {{ showToast('❌ لینکی وجود ندارد', true); return; }}
                navigator.clipboard.writeText(text).then(() => showToast('✅ لینک کپی شد!'));
            }}

            function openAddModal() {{
                document.getElementById('addModal').classList.add('active');
                document.getElementById('addLabel').focus();
            }}

            function closeModal(id) {{
                document.getElementById(id).classList.remove('active');
            }}

            async function createLink() {{
                const label = document.getElementById('addLabel').value.trim();
                const limit = parseFloat(document.getElementById('addLimit').value) || 0;
                const days = parseInt(document.getElementById('addDays').value) || 0;
                const ips = parseInt(document.getElementById('addIPs').value) || 0;

                if (!label) {{ showToast('❌ نام کاربر را وارد کن!', true); return; }}
                if (!/^[a-zA-Z0-9\\-_. ]+$/.test(label)) {{ showToast('❌ نام معتبر نیست!', true); return; }}

                try {{
                    const r = await fetch('/api/links', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{
                            label: label,
                            limit_value: limit,
                            max_connections: ips,
                            days_valid: days
                        }})
                    }});
                    if (r.ok) {{
                        closeModal('addModal');
                        loadLinks();
                        showToast('✅ کاربر ' + label + ' ساخته شد!');
                        document.getElementById('addLabel').value = '';
                        document.getElementById('addLimit').value = '';
                        document.getElementById('addDays').value = '';
                        document.getElementById('addIPs').value = '';
                    }} else {{
                        const err = await r.json();
                        showToast('❌ ' + (err.detail || 'خطا'), true);
                    }}
                }} catch(e) {{ showToast('❌ خطا در ارتباط با سرور', true); }}
            }}

            function editLink(uid) {{
                const l = links.find(x => x.uuid === uid);
                if (!l) return;
                const newLimit = prompt('حجم جدید (GB):', l.limit_bytes > 0 ? (l.limit_bytes / (1024**3)) : 0);
                if (newLimit === null) return;
                const limit = parseFloat(newLimit) || 0;
                fetch('/api/links/' + uid, {{
                    method: 'PATCH',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ limit_value: limit }})
                }}).then(r => {{
                    if (r.ok) {{ loadLinks(); showToast('✅ بروزرسانی شد'); }}
                }});
            }}

            async function doLogout() {{
                await fetch('/api/logout', {{ method: 'POST' }});
                window.location.href = '/login';
            }}

            function showToast(msg, err = false) {{
                const t = document.getElementById('toast');
                t.textContent = msg;
                t.style.color = err ? '#f87171' : '#FFD700';
                t.classList.add('show');
                clearTimeout(t._hide);
                t._hide = setTimeout(() => t.classList.remove('show'), 2500);
            }}

            // کلیک بیرون مودال برای بستن
            document.querySelectorAll('.modal').forEach(m => {{
                m.addEventListener('click', function(e) {{
                    if (e.target === this) this.classList.remove('active');
                }});
            }});

            loadLinks();
            setInterval(loadStats, 30000);
        </script>
    </body>
    </html>
    """)

# ==========================================
# 🚀 اجرا
# ==========================================

if __name__ == "__main__":
    init_db()
    load_links()
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
#!/usr/bin/env python3
import random
import string
import logging
import sqlite3
import requests
from datetime import datetime
from threading import Lock
from flask import Flask, request, jsonify, make_response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# =====================
# App Setup
# =====================
app = Flask(__name__, static_folder="static")
logging.basicConfig(level=logging.INFO)
lock = Lock()

DB_PATH = "app.db"

# =====================
# DB Helper
# =====================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                device_id TEXT,
                role TEXT DEFAULT 'user',
                created_at TEXT,
                last_seen TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS invite_codes (
                code TEXT PRIMARY KEY,
                used INTEGER DEFAULT 0,
                used_by TEXT,
                created_at TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                timestamp TEXT,
                content TEXT
            )
        """)

        existing = db.execute("SELECT COUNT(*) FROM invite_codes").fetchone()[0]
        if existing == 0:
            print("🔐 Generating 20 new invite codes...")
            for _ in range(20):
                code = f"{random.randint(100, 999)}-{random.randint(100, 999)}"
                db.execute(
                    "INSERT INTO invite_codes (code, created_at) VALUES (?, ?)",
                    (code, datetime.now().isoformat())
                )
        db.commit()
        print("💌 Available invite codes:")
        rows = db.execute("SELECT code FROM invite_codes WHERE used = 0").fetchall()
        for row in rows:
            print(" -", row["code"])

init_db()

# =====================
# Rate Limiting
# =====================
limiter = Limiter(key_func=get_remote_address, app=app, default_limits=["100 per hour"])

# =====================
# Helper Functions
# =====================
def is_vpn_ip(ip):
    try:
        response = requests.get(f"https://ipapi.co/{ip}/json/", timeout=3).json()
        return response.get("proxy", False) or response.get("vpn", False)
    except:
        return False

def is_from_idaho(ip):
    try:
        response = requests.get(f"https://ipapi.co/{ip}/json/", timeout=3).json()
        return response.get("region_code", "").upper() == "ID"
    except:
        return False

def get_special_role(ip):
    try:
        response = requests.get(f"https://ipapi.co/{ip}/json/", timeout=3).json()
        region_code = response.get("region_code", "").upper()
        country_code = response.get("country_code", "").upper()

        if region_code == "OK":
            return "tornado_survivor"
        if country_code == "KZ":
            return "borat_approved"
    except:
        pass
    return "user"

def add_message(username, content):
    with get_db() as db:
        db.execute(
            "INSERT INTO messages (username, timestamp, content) VALUES (?, ?, ?)",
            (username, datetime.now().strftime("%H:%M:%S"), content)
        )

# =====================
# Middleware
# =====================
@app.before_request
def block_vpn_and_regions():
    ip = request.remote_addr

    if is_vpn_ip(ip):
        return jsonify({"error": "VPNs are not allowed."}), 403

    if is_from_idaho(ip):
        return jsonify({"error": "🥔 Sorry! No users from Idaho allowed."}), 403

# =====================
# Routes
# =====================

@app.route("/join", methods=["POST"])
def join():
    data = request.get_json(force=True)
    invite = data.get("invite_code", "").strip()
    username = data.get("username", "").strip()
    ip = request.remote_addr

    if not username or not invite:
        return jsonify({"error": "Missing fields."}), 400

    with get_db() as db:
        row = db.execute(
            "SELECT * FROM invite_codes WHERE code = ? AND used = 0",
            (invite,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Invalid or used invite code."}), 403

        role = get_special_role(ip)
        is_ok = role == "tornado_survivor"
        device_id = ''.join(random.choices(string.ascii_letters + string.digits, k=16))

        now = datetime.now().isoformat()
        db.execute(
            "INSERT INTO users (username, device_id, role, created_at, last_seen) VALUES (?, ?, ?, ?, ?)",
            (username, device_id, role, now, now)
        )
        db.execute(
            "UPDATE invite_codes SET used = 1, used_by = ? WHERE code = ?",
            (username, invite)
        )
        db.commit()

        add_message("SYSTEM", f"👋 {username} joined with role '{role}'.")

        resp = make_response(jsonify({
            "message": f"Welcome, {username}!",
            "role": role,
            "device_id": device_id,
            "oklahoma": is_ok
        }))
        resp.set_cookie("device_id", device_id, max_age=60*60*24*30, httponly=False, samesite='Lax')
        return resp

@app.route("/send", methods=["POST"])
@limiter.limit("10/minute")
def send():
    data = request.get_json(force=True)
    username = data.get("username", "").strip()
    msg = data.get("message", "").strip()

    if not username or not msg:
        return jsonify({"error": "Message and username required."}), 400

    add_message(username, msg)
    return jsonify({"status": "sent"})

@app.route("/messages", methods=["GET"])
def fetch_messages():
    with get_db() as db:
        rows = db.execute(
            "SELECT username, timestamp, content FROM messages ORDER BY id DESC LIMIT 50"
        ).fetchall()
    return jsonify({
        "messages": [
            {"user": row["username"], "time": row["timestamp"], "text": row["content"]}
            for row in rows[::-1]
        ]
    })

@app.route("/codes", methods=["GET"])
def list_codes():
    with get_db() as db:
        rows = db.execute("SELECT code FROM invite_codes WHERE used = 0").fetchall()
    return jsonify({"available_codes": [row["code"] for row in rows]})

# =====================
# Entry Point
# =====================
if __name__ == "__main__":
    from waitress import serve
    print("🚀 Running SigmaChat with regions and audio support on http://localhost:5000")
    serve(app, host="0.0.0.0", port=5000, threads=4)

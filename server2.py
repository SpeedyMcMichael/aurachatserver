import socket
import threading
import unicodedata
import base64
import logging
from datetime import datetime
from pyngrok import ngrok

HOST = '8.tcp.ngrok.io'
PORT = 19228
MAX_USERNAME_LENGTH = 25

# Internal invite codes (raw)
RAW_CODES = ["JaydensBus", "SigmaPoopyPants", "Pancakes67", "Urethra"]

# Encode them in Base64 for public use
INVITE_CODES = {base64.b64encode(code.encode()).decode(): False for code in RAW_CODES}

clients = {}

log_filename = f"chat_sigmachat1_{datetime.now().strftime('%Y-%m-%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def is_valid_username(name):
    name = name.strip()
    if not (1 <= len(name) <= MAX_USERNAME_LENGTH):
        return False
    if not name.isprintable():
        return False
    for ch in name:
        cat = unicodedata.category(ch)
        if cat.startswith(('L', 'N')) or ch in "_ -":
            continue
        return False
    return True


def handle_client(conn, addr):
    try:
        # Step 1: Ask for invite code
        conn.sendall("Enter invite code (Base64): ".encode())
        code_input = conn.recv(1024).decode().strip()

        # Decode Base64 safely
        try:
            decoded = base64.b64decode(code_input).decode().upper()
        except Exception:
            conn.sendall("Invalid Base64 code format.\n".encode())
            conn.close()
            return

        # Check decoded code validity
        if code_input not in INVITE_CODES:
            conn.sendall("Invalid invite code. Connection refused.\n".encode())
            conn.close()
            return

        # Step 2: Ask for username
        conn.sendall("Enter your username: ".encode())
        username = conn.recv(1024).decode().strip()

        if not is_valid_username(username):
            conn.sendall("Invalid username. Must be 1–25 chars, letters/numbers/-/_ only.\n".encode())
            conn.close()
            return

        clients[conn] = username
        print(f"[+] {username} joined from {addr} with code {decoded}")
        conn.sendall(f"Welcome, {username}! You're now in the chat.\n".encode())

        broadcast(f"👋 {username} has joined the chat!\n", conn)

        # Step 3: Chat loop
        while True:
            data = conn.recv(1024)
            if not data:
                break
            msg = data.decode().strip()
            broadcast(f"[{username}]: {msg}\n", conn)

    except Exception as e:
        print(f"Error with {addr}: {e}")

    finally:
        if conn in clients:
            user = clients.pop(conn)
            broadcast(f"❌ {user} has left the chat.\n", conn)
        conn.close()


def broadcast(message, sender_conn=None):
    """Send a message to all clients except the sender."""
    for conn in list(clients.keys()):
        if conn != sender_conn:
            try:
                conn.sendall(message.encode())
            except:
                conn.close()
                clients.pop(conn, None)


def start_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f"Server listening on {HOST}:{PORT}")
        print("\n🪪 Invite Codes (Base64):")
        for code in INVITE_CODES.keys():
            print(f"  {code}")
        print()
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    ngrok.set_auth_token("1qHIQ4bfyHCjJabMZH94voKkFmx_5Js6mWJYxLLD2K6m2PajW")  # optional if already configured
    tunnel = ngrok.connect(PORT, "tcp")
    print(f"🌍 Public ngrok address: {tunnel.public_url}\n")
    print("💡 Give this host/port to your friends:")
    host_port = tunnel.public_url.replace("tcp://", "").split(":")
    print(f"HOST = {host_port[0]}")
    print(f"PORT = {host_port[1]}\n")
    start_server()

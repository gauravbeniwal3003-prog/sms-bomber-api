from flask import Flask, jsonify, request, send_from_directory
import os

app = Flask(__name__, static_folder='../admin', static_url_path='/admin')

@app.route('/')
@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "message": "SMS Bomber API is live!"})

@app.route('/api/requests')
def get_requests():
    return jsonify([{"name": "Testbook OTP", "active": True}])

@app.route('/admin')
@app.route('/admin/')
def serve_admin():
    return send_from_directory('../admin', 'index.html')

# Vercel requires this
def handler(request, *args, **kwargs):
    return app(request, *args, **kwargs)

if __name__ == '__main__':
    app.run()

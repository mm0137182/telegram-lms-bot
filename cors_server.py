#!/usr/bin/env python3
"""
CORS-enabled HTTP server that:
1. Serves gh_upload.json with CORS headers (so browser can fetch it)
2. Receives a GitHub token from the browser
3. Uses the token to upload all files to GitHub via the Contents API
"""
import json
import os
import http.server
import ssl
import urllib.request
import urllib.error
import threading
import time

DEPLOY_DIR = 'C:/Users/mm013/AppData/Local/hermes/cache/scratch/telegram_bot_deploy'
GITHUB_API = 'https://api.github.com'
REPO_OWNER = 'mm0137182'
REPO_NAME = 'telegram-lms-bot'

class CORSHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[SERVER] {args[0]}")
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        
        # Serve the gh_upload.json file
        filepath = os.path.join(DEPLOY_DIR, 'gh_upload.json')
        if self.path == '/gh_upload.json' and os.path.exists(filepath):
            with open(filepath, 'r') as f:
                data = f.read()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(data.encode())
            print(f"[SERVER] Served gh_upload.json ({len(data)} bytes)")
        elif self.path == '/' or self.path == '/health':
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Not Found')
    
    def do_POST(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length).decode('utf-8')
        data = json.loads(body)
        
        if data.get('action') == 'upload_files':
            token = data.get('token', '')
            print(f"[SERVER] Received token for upload: {token[:10]}...{token[-4:]} (len={len(token)})")
            print(f"[SERVER] Starting file upload...")
            
            # Load the gh_upload.json file
            upload_file = os.path.join(DEPLOY_DIR, 'gh_upload.json')
            with open(upload_file) as f:
                files_data = json.load(f)
            
            results = []
            for filename, content in files_data.items():
                url = f'{GITHUB_API}/repos/{REPO_OWNER}/{REPO_NAME}/contents/{filename}'
                api_data = json.dumps({
                    'message': '📦 Telegram LMS Bot — initial deployment package',
                    'content': content,
                    'branch': 'main'
                }).encode('utf-8')
                
                req = urllib.request.Request(url, data=api_data, method='PUT')
                req.add_header('Authorization', f'token {token}')
                req.add_header('Accept', 'application/vnd.github+json')
                req.add_header('Content-Type', 'application/json')
                
                try:
                    resp = urllib.request.urlopen(req, timeout=30)
                    status = resp.getcode()
                    results.append({'file': filename, 'status': status, 'ok': status == 201})
                    print(f"[SERVER] Uploaded: {filename} -> {status}")
                except urllib.error.HTTPError as e:
                    body = e.read().decode('utf-8', errors='replace')
                    results.append({'file': filename, 'status': e.code, 'ok': False, 'error': body[:200]})
                    print(f"[SERVER] Failed: {filename} -> {e.code}: {body[:100]}")
                except Exception as e:
                    results.append({'file': filename, 'status': 0, 'ok': False, 'error': str(e)[:100]})
                    print(f"[SERVER] Error: {filename} -> {e}")
            
            ok_count = sum(1 for r in results if r.get('ok'))
            print(f"[SERVER] Upload complete: {ok_count}/{len(results)} files OK")
            
            self.wfile.write(json.dumps({'results': results, 'ok': ok_count, 'total': len(results)}).encode())
        else:
            self.wfile.write(json.dumps({'error': 'Unknown action'}).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()

if __name__ == '__main__':
    server = http.server.HTTPServer(('127.0.0.1', 18081), CORSHandler)
    print(f"[SERVER] CORS-enabled server running on http://127.0.0.1:18080")
    server.serve_forever()

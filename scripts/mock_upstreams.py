#!/usr/bin/env python3
from __future__ import annotations
import base64,hashlib,json,os,signal,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
PORTS=(8000,18000,18003,18088,18102,18103,18104,18105,18106,18107,18108,18109,18110,18111,18112,18113,18114,18115,18116,18180,18200)
LOG=Path(os.environ['MOCK_UPSTREAM_LOG']); LOCK=threading.Lock()
class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*_): return
    def _record(self):
        record={'port':self.server.server_address[1],'method':self.command,'path':self.path,'host':self.headers.get('Host',''),'authorization_present':bool(self.headers.get('Authorization'))}
        with LOCK,LOG.open('a',encoding='utf-8') as handle: handle.write(json.dumps(record,sort_keys=True)+'\n')
    def _handle(self):
        length=int(self.headers.get('Content-Length','0') or 0)
        if length:self.rfile.read(min(length,20*1024*1024))
        self._record()
        if self.headers.get('Upgrade','').lower()=='websocket':
            key=self.headers.get('Sec-WebSocket-Key',''); accept=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode(); self.send_response(101); self.send_header('Upgrade','websocket'); self.send_header('Connection','Upgrade'); self.send_header('Sec-WebSocket-Accept',accept); self.end_headers(); return
        if self.server.server_address[1]==8000 and self.headers.get('Host')=='automation.codestra.co':
            self.send_response(302); self.send_header('Location','https://auth.codestra.co/realms/codestra/protocol/openid-connect/auth?client_id=n8n-automation'); self.send_header('Content-Length','0'); self.end_headers(); return
        if self.server.server_address[1]==18113 and self.path.startswith('/oauth2/auth'):
            self.send_response(200); self.send_header('X-Auth-Request-Access-Token','mock-access-token'); self.send_header('X-Auth-Request-User','operator'); self.send_header('Content-Length','0'); self.end_headers(); return
        payload=json.dumps({'mock':True,'port':self.server.server_address[1],'host':self.headers.get('Host',''),'path':self.path},sort_keys=True).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(payload))); self.end_headers()
        if self.command!='HEAD':self.wfile.write(payload)
    do_GET=_handle; do_HEAD=_handle; do_POST=_handle; do_PUT=_handle; do_PATCH=_handle; do_DELETE=_handle
servers=[]
for port in PORTS:
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler); threading.Thread(target=server.serve_forever,daemon=True).start(); servers.append(server)
def stop(*_):
    for server in servers:server.shutdown()
    raise SystemExit(0)
signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop); print('MOCK_UPSTREAMS=READY',flush=True); signal.pause()

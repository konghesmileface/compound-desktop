# -*- coding: utf-8 -*-
"""起本地 relay(worktree,支持 rtc/turn)+ 假账号服务,供 WebRTC 双端联调。
跑法: python3 test_webrtc_stack.py  → 首行打印 {"relay_port","account_port"},驻留待杀。
搭档: compound-mobile/scripts/webrtc_check.py(playwright 双页真 WebRTC)。
"""
import asyncio
import json
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


ACC_PORT, RELAY_PORT = free_port(), free_port()
os.environ["RELAY_PORT"] = str(RELAY_PORT)
os.environ["ACCOUNT_URL"] = "http://127.0.0.1:%d" % ACC_PORT
os.environ.setdefault("TURN_SECRET", "testsecret")   # 让 relay 也发 TURN 凭证(本机 loopback 不真用)
sys.path.insert(0, HERE)
import relay_server  # noqa: E402


class AccHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        tok = (self.headers.get("Authorization") or "").replace("Bearer ", "")
        if self.path == "/account/me" and tok:
            body, code = json.dumps({"ident": "testuser"}).encode(), 200
        else:
            body, code = b'{"error":"bad"}', 401
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.end_headers(); self.wfile.write(body)


def main():
    threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", ACC_PORT), AccHandler).serve_forever,
                     daemon=True).start()
    threading.Thread(target=lambda: asyncio.run(relay_server.main()), daemon=True).start()
    time.sleep(0.6)
    print(json.dumps({"relay_port": RELAY_PORT, "account_port": ACC_PORT}), flush=True)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()

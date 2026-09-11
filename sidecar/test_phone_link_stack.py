# -*- coding: utf-8 -*-
"""起一套本机通道栈(假账号+桩后端+真relay+真连接器)并开一个配对会话,供跨实现联调。

跑法: python3 test_phone_link_stack.py
      首行输出 JSON {"relay","payload"}(手机端拿去当扫码内容),然后驻留直到被杀。
搭档: compound-mobile/scripts/e2e_cross.mjs(Node 跑手机端真通道库打过来)
"""
import asyncio
import json
import os
import secrets
import socket
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="phone_link_stack_")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


ACC_PORT, BACK_PORT, RELAY_PORT = free_port(), free_port(), free_port()
os.environ["BRAIN_DATA"] = TMP
os.environ["RELAY_PORT"] = str(RELAY_PORT)
os.environ["ACCOUNT_URL"] = "http://127.0.0.1:%d" % ACC_PORT
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "relay-server"))
import phone_link            # noqa: E402
import relay_server          # noqa: E402


class AccHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        tok = (self.headers.get("Authorization") or "").replace("Bearer ", "")
        if self.path == "/account/me" and tok in ("tok-desktop", "tok-phone"):
            body, code = json.dumps({"ident": "testuser", "active": True}).encode(), 200
        else:
            body, code = b'{"error":"bad token"}', 401
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


class BackHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _out(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._out(200, b'{"ok":true}')
        elif self.path == "/api/ping":
            self._out(200, json.dumps({"auth_seen": self.headers.get("Authorization") or ""}).encode())
        else:
            self._out(404, b'{"detail":"nf"}')

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n)
        self._out(200, json.dumps({"echo_len": len(data),
                                   "ct": self.headers.get("Content-Type") or ""}).encode())


def main():
    threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", ACC_PORT), AccHandler).serve_forever,
                     daemon=True).start()
    threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", BACK_PORT), BackHandler).serve_forever,
                     daemon=True).start()
    threading.Thread(target=lambda: asyncio.run(relay_server.main()), daemon=True).start()
    time.sleep(0.8)

    phone_link._save({"cloud_token": "tok-desktop",
                      "relay_url": "ws://127.0.0.1:%d" % RELAY_PORT, "devices": []})
    phone_link.CONNECTOR.local_port = BACK_PORT
    phone_link.start()
    deadline = time.time() + 10
    while phone_link.CONNECTOR.state != "connected" and time.time() < deadline:
        time.sleep(0.2)
    if phone_link.CONNECTOR.state != "connected":
        print(json.dumps({"error": "connector_not_connected",
                          "state": phone_link.CONNECTOR.state,
                          "err": phone_link.CONNECTOR.last_err}))
        sys.exit(1)

    # 开配对会话(等价桌面 UI 点「配对新手机」)
    priv, pub_raw = phone_link._gen_keypair()
    tok = secrets.token_bytes(32)
    phone_link.CONNECTOR.pairing = {"priv": priv, "tok": tok, "exp": time.time() + 300}
    payload = json.dumps({
        "v": 1, "kind": "compound-pair",
        "relay": "ws://127.0.0.1:%d" % RELAY_PORT,
        "cloud": "http://127.0.0.1:%d" % ACC_PORT,
        "account": "testuser",
        "dpk": phone_link._b64(pub_raw), "tok": phone_link._b64(tok),
        "exp": int(time.time() + 300),
    }, separators=(",", ":"))
    print(json.dumps({"relay": "ws://127.0.0.1:%d" % RELAY_PORT, "payload": payload}), flush=True)
    # 驻留;跨端测试完由调用方杀掉
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()

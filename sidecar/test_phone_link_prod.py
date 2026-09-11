# -*- coding: utf-8 -*-
"""生产链路验证: 真账号 → wss://compoundtome.com/relay(106) → 本机连接器+桩后端。

跑法: COMPOUND_USER=手机号 COMPOUND_PASS=密码 python3 test_phone_link_prod.py
首行输出 {"relay","payload","token"}(JSON),然后驻留;搭档 e2e_cross.mjs 用 CLOUD_TOKEN 打进来。
"""
import json
import os
import secrets
import socket
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="phone_link_prod_")
CLOUD = "http://106.14.189.104:8000"
RELAY = "wss://compoundtome.com/relay"
for k in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
    os.environ.pop(k, None)
os.environ["BRAIN_DATA"] = TMP
sys.path.insert(0, HERE)
import phone_link  # noqa: E402


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class BackHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        body = (b'{"ok":true}' if self.path == "/health"
                else json.dumps({"auth_seen": self.headers.get("Authorization") or ""}).encode()
                if self.path == "/api/ping" else b'{"detail":"nf"}')
        code = 404 if body == b'{"detail":"nf"}' else 200
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"echo_len": len(data),
                                     "ct": self.headers.get("Content-Type") or ""}).encode())


def login():
    payload = json.dumps({"username": os.environ["COMPOUND_USER"],
                          "password": os.environ["COMPOUND_PASS"]}).encode()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    r = opener.open(urllib.request.Request(CLOUD + "/account/login", data=payload,
                                           headers={"Content-Type": "application/json"}), timeout=15)
    d = json.loads(r.read())
    tok = d.get("token") or d.get("access_token")
    if not tok:
        print(json.dumps({"error": "login_no_token", "resp": d}))
        sys.exit(1)
    return tok


def main():
    tok = login()
    back_port = free_port()
    threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", back_port), BackHandler).serve_forever,
                     daemon=True).start()
    phone_link._save({"cloud_token": tok, "relay_url": RELAY, "devices": []})
    phone_link.CONNECTOR.local_port = back_port
    phone_link.start()
    deadline = time.time() + 20
    while phone_link.CONNECTOR.state != "connected" and time.time() < deadline:
        time.sleep(0.3)
    if phone_link.CONNECTOR.state != "connected":
        print(json.dumps({"error": "connector_not_connected",
                          "state": phone_link.CONNECTOR.state, "err": phone_link.CONNECTOR.last_err}))
        sys.exit(1)

    priv, pub_raw = phone_link._gen_keypair()
    ptok = secrets.token_bytes(32)
    phone_link.CONNECTOR.pairing = {"priv": priv, "tok": ptok, "exp": time.time() + 300}
    payload = json.dumps({"v": 1, "kind": "compound-pair", "relay": RELAY, "cloud": CLOUD,
                          "account": os.environ["COMPOUND_USER"],
                          "dpk": phone_link._b64(pub_raw), "tok": phone_link._b64(ptok),
                          "exp": int(time.time() + 300)}, separators=(",", ":"))
    print(json.dumps({"relay": RELAY, "payload": payload, "token": tok}), flush=True)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()

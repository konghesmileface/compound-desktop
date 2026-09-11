# -*- coding: utf-8 -*-
"""M1 通道全链路本机 E2E: 模拟手机 <-> 真 relay <-> 真 phone_link 连接器 <-> 桩后端。

覆盖: hello 鉴权 / presence / 扫码配对(ECDH+HKDF+MAC) / 加密请求转发(带 Authorization)
      / 路径白名单 403 / 篡改密文拒绝 / 未知设备拒绝。
跑法: python3 test_phone_link_e2e.py   (全绿输出 E2E ALL PASS)
"""
import asyncio
import base64
import hashlib
import hmac
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
TMP = tempfile.mkdtemp(prefix="phone_link_e2e_")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


ACC_PORT, BACK_PORT, RELAY_PORT = free_port(), free_port(), free_port()

# ---- 环境必须在 import 被测模块前布好 ----
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
            body = json.dumps({"ident": "testuser", "active": True}).encode()
            self.send_response(200)
        else:
            body = b'{"error":"bad token"}'
            self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


class BackHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        if self.path == "/health":
            body, code = b'{"ok":true}', 200
        elif self.path == "/api/ping":
            body = json.dumps({"auth_seen": self.headers.get("Authorization") or ""}).encode()
            code = 200
        else:
            body, code = b'{"error":"nf"}', 404
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


def b64(b): return base64.b64encode(b).decode()
def unb64(s): return base64.b64decode(s)


class Phone:
    """模拟手机端(与 compound-mobile src/channel 同协议)。"""

    def __init__(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        self.priv = ec.generate_private_key(ec.SECP256R1())
        self.ppk = self.priv.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        self.key = None
        self.dev = None

    def derive(self, dpk_b64, tok_b64):
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives import hashes
        dpk = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), unb64(dpk_b64))
        shared = self.priv.exchange(ec.ECDH(), dpk)
        self.key = HKDF(algorithm=hashes.SHA256(), length=32,
                        salt=hashlib.sha256(unb64(tok_b64)).digest(),
                        info=b"compound-e2e-v1").derive(shared)

    def pair_frame(self, name="E2E手机"):
        mac = hmac.new(self.key, self.ppk + name.encode(), hashlib.sha256).digest()
        return {"t": "pair", "id": secrets.token_hex(4), "ppk": b64(self.ppk),
                "name": name, "mac": b64(mac)}

    def req_frame(self, method, path, headers=None, rid=None):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        plain = json.dumps({"method": method, "path": path,
                            "headers": headers or {}, "body_b64": None}).encode()
        n = secrets.token_bytes(12)
        ct = AESGCM(self.key).encrypt(n, plain, ("req:" + self.dev).encode())
        return {"t": "req", "id": rid or secrets.token_hex(4), "dev": self.dev,
                "n": b64(n), "d": b64(ct)}

    def open_resp(self, frame):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        plain = AESGCM(self.key).decrypt(unb64(frame["n"]), unb64(frame["d"]),
                                         ("resp:" + self.dev).encode())
        return json.loads(plain)


PASS = []


def ok(name, cond, extra=""):
    tag = "PASS" if cond else "FAIL"
    print("[%s] %s %s" % (tag, name, extra))
    PASS.append(bool(cond))


async def phone_flow():
    import websockets
    uri = "ws://127.0.0.1:%d" % RELAY_PORT

    # 1) 坏 token 拒绝
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"t": "hello", "v": 1, "role": "phone", "token": "bad"}))
        r = json.loads(await ws.recv())
        ok("hello 坏token拒绝", r.get("t") == "err" and r.get("code") == "auth")

    async with websockets.connect(uri, max_size=60 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"t": "hello", "v": 1, "role": "phone", "token": "tok-phone"}))
        r = json.loads(await ws.recv())
        ok("hello 鉴权通过", r.get("t") == "ok" and r.get("ident") == "testuser")
        r = json.loads(await ws.recv())
        ok("presence 桌面在线", r.get("t") == "presence" and r.get("online") is True)

        # 2) 配对: 直接驱动被测模块的配对会话(等价于桌面 UI 点"配对")
        priv, pub_raw = phone_link._gen_keypair()
        tok = secrets.token_bytes(32)
        phone_link.CONNECTOR.pairing = {"priv": priv, "tok": tok, "exp": time.time() + 300}
        phone = Phone()
        phone.derive(b64(pub_raw), b64(tok))
        await ws.send(json.dumps(phone.pair_frame()))
        r = json.loads(await ws.recv())
        ok("配对成功", r.get("t") == "pair_ok" and r.get("dev"), str(r))
        phone.dev = r.get("dev")
        st = json.load(open(os.path.join(TMP, "phone_link.json")))
        ok("设备已持久化", any(d["dev"] == phone.dev for d in st["devices"]))

        # 3) 加密请求 /health
        await ws.send(json.dumps(phone.req_frame("GET", "/health")))
        r = json.loads(await ws.recv())
        body = phone.open_resp(r)
        ok("加密请求 /health 200", body["status"] == 200 and
           json.loads(unb64(body["body_b64"])).get("ok") is True)

        # 4) Authorization 透传
        await ws.send(json.dumps(phone.req_frame("GET", "/api/ping",
                                                 {"Authorization": "Bearer tok-phone"})))
        body = phone.open_resp(json.loads(await ws.recv()))
        ok("Authorization 透传", json.loads(unb64(body["body_b64"]))["auth_seen"] == "Bearer tok-phone")

        # 5) 路径白名单
        await ws.send(json.dumps(phone.req_frame("GET", "/etc/passwd")))
        body = phone.open_resp(json.loads(await ws.recv()))
        ok("白名单外路径 403", body["status"] == 403)

        # 6) 篡改密文
        bad = phone.req_frame("GET", "/health")
        raw = bytearray(unb64(bad["d"]))
        raw[0] ^= 0xFF
        bad["d"] = b64(bytes(raw))
        await ws.send(json.dumps(bad))
        r = json.loads(await ws.recv())
        ok("篡改密文拒绝", r.get("t") == "err" and r.get("code") == "decrypt_failed", str(r))

        # 7) 未知设备
        fake = phone.req_frame("GET", "/health")
        fake["dev"] = "zzzzzzzzzzz"
        await ws.send(json.dumps(fake))
        r = json.loads(await ws.recv())
        ok("未知设备拒绝", r.get("code") in ("unknown_device", "decrypt_failed"), str(r))


def main():
    threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", ACC_PORT), AccHandler).serve_forever,
                     daemon=True).start()
    threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", BACK_PORT), BackHandler).serve_forever,
                     daemon=True).start()

    def run_relay():
        asyncio.run(relay_server.main())
    threading.Thread(target=run_relay, daemon=True).start()
    time.sleep(0.8)

    phone_link._save({"cloud_token": "tok-desktop",
                      "relay_url": "ws://127.0.0.1:%d" % RELAY_PORT, "devices": []})
    phone_link.CONNECTOR.local_port = BACK_PORT
    phone_link.start()

    deadline = time.time() + 10
    while phone_link.CONNECTOR.state != "connected" and time.time() < deadline:
        time.sleep(0.2)
    ok("桌面连接器上线", phone_link.CONNECTOR.state == "connected",
       phone_link.CONNECTOR.state + " " + phone_link.CONNECTOR.last_err)

    asyncio.run(asyncio.wait_for(phone_flow(), timeout=30))

    print()
    if all(PASS) and PASS:
        print("E2E ALL PASS (%d checks)" % len(PASS))
        sys.exit(0)
    print("E2E FAILED (%d/%d)" % (sum(PASS), len(PASS)))
    sys.exit(1)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""手机连接通道(M1 中转版): 手机 App <—wss 云中转—> 桌面端,端到端加密,服务器只见密文。

协议 v1(与手机端 src/channel/ 逐字节对齐,改动必须双端同步):
  - 传输: WebSocket 文本帧 JSON。桌面首帧 {"t":"hello","v":1,"role":"desktop","token":<云账号token>}
  - 配对: 桌面生成 P-256 临时密钥对+32B token,拼二维码 JSON;手机 ECDH 后
          key = HKDF-SHA256(ikm=共享x坐标32B, salt=SHA256(tok), info=b"compound-e2e-v1", 32B)
          mac = HMAC-SHA256(key, ppk_65B || utf8(设备名));桌面验 mac 通过即存设备。
  - 请求: {"t":"req","id","dev","n":<b64 12B nonce>,"d":<b64 AES-256-GCM密文>,"cid":<中转打的路由戳,原样回显>}
          明文 {"method","path","headers",{...},"body_b64"};AAD=utf8("req:"+dev)。
          响应 {"t":"resp",...} AAD=utf8("resp:"+dev),明文 {"status","headers","body_b64"}。
  - 转发: 解密后打到本机 FastAPI(127.0.0.1:WEB_PORT),鉴权用手机端自带的 Authorization,零豁免。

存储: BRAIN_DATA/phone_link.json {"cloud_token","relay_url","devices":[{"dev","name","key","created"}]}
"""
import asyncio
import base64
import hashlib
import hmac as hmac_mod
import io
import json
import os
import secrets
import threading
import time
import urllib.request
import urllib.error

from fastapi import APIRouter, Header, HTTPException

ROOT = os.path.dirname(os.path.abspath(__file__))
_STORE = os.path.join(os.environ.get("BRAIN_DATA", ROOT), "phone_link.json")
RELAY_DEFAULT = os.environ.get("COMPOUND_RELAY_URL", "wss://compoundtome.com/relay")
CLOUD_DEFAULT = os.environ.get("CLOUD_URL", "http://106.14.189.104:8000")
_INFO = b"compound-e2e-v1"
_MAX_BODY = 50 * 1024 * 1024          # 手机→桌面单请求体上限 50MB
_ALLOW_PREFIX = ("/api/", "/health")  # 只转发业务路径


def _b64(b): return base64.b64encode(b).decode()
def _unb64(s): return base64.b64decode(s)


def _load():
    try:
        with open(_STORE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"cloud_token": "", "relay_url": RELAY_DEFAULT, "devices": []}


def _save(st):
    os.makedirs(os.path.dirname(_STORE), exist_ok=True)
    tmp = _STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _STORE)


# ---------------- 加密原语(cryptography) ----------------

def _gen_keypair():
    from cryptography.hazmat.primitives.asymmetric import ec
    priv = ec.generate_private_key(ec.SECP256R1())
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    pub_raw = priv.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)  # 65B
    return priv, pub_raw


def _derive_key(priv, peer_pub_raw: bytes, tok: bytes) -> bytes:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), peer_pub_raw)
    shared = priv.exchange(ec.ECDH(), peer)                    # 32B x 坐标
    return HKDF(algorithm=hashes.SHA256(), length=32,
                salt=hashlib.sha256(tok).digest(), info=_INFO).derive(shared)


def _encrypt(key: bytes, aad: bytes, plaintext: bytes):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    n = secrets.token_bytes(12)
    return n, AESGCM(key).encrypt(n, plaintext, aad)


def _decrypt(key: bytes, aad: bytes, n: bytes, ct: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key).decrypt(n, ct, aad)


# ---------------- 连接器(常驻外连中转) ----------------

class _Connector:
    def __init__(self):
        self.state = "off"          # off / connecting / connected / auth_failed
        self.last_err = ""
        self.local_port = int(os.environ.get("WEB_PORT", "8200"))
        self.pairing = None         # {"priv","tok","exp"} 进行中的配对会话
        self._wake = None           # asyncio.Event, 用于立刻重连
        self._loop = None
        self._thread = None
        self._gen = 0               # token/配置变更代数,旧连接自杀

    # -- 生命周期 --
    def ensure_started(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="phone-link")
        self._thread.start()

    def restart(self):
        self._gen += 1
        self.ensure_started()
        loop, wake = self._loop, self._wake
        if loop and wake:
            loop.call_soon_threadsafe(wake.set)

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._wake = asyncio.Event()
        self._loop.run_until_complete(self._main())

    async def _main(self):
        backoff = 3
        while True:
            st = _load()
            tok = st.get("cloud_token") or ""
            if not tok:
                self.state = "off"
                await self._sleep(10)
                continue
            gen = self._gen
            try:
                self.state = "connecting"
                await self._session(st, tok, gen)
                backoff = 3
            except Exception as e:
                self.last_err = str(e)[:200]
                if self.state != "auth_failed":
                    self.state = "connecting"
            if self._gen == gen:
                await self._sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _sleep(self, sec):
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=sec)
        except asyncio.TimeoutError:
            pass
        self._wake.clear()

    async def _session(self, st, tok, gen):
        import websockets
        url = st.get("relay_url") or RELAY_DEFAULT
        async with websockets.connect(url, max_size=_MAX_BODY + 1024 * 1024,
                                      ping_interval=25, ping_timeout=20) as ws:
            await ws.send(json.dumps({"t": "hello", "v": 1, "role": "desktop", "token": tok}))
            first = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
            if first.get("t") != "ok":
                if first.get("code") == "auth":
                    self.state = "auth_failed"
                raise RuntimeError("relay hello rejected: %s" % first)
            self.state = "connected"
            self.last_err = ""
            async for raw in ws:
                if self._gen != gen:
                    return
                try:
                    frame = json.loads(raw)
                except Exception:
                    continue
                asyncio.get_running_loop().create_task(self._handle(ws, frame))

    async def _handle(self, ws, frame):
        t = frame.get("t")
        try:
            if t == "pair":
                await ws.send(json.dumps(self._on_pair(frame)))
            elif t == "req":
                resp = await asyncio.get_running_loop().run_in_executor(None, self._on_req, frame)
                await ws.send(json.dumps(resp))
        except Exception as e:
            try:
                await ws.send(json.dumps({"t": "err", "code": "internal", "id": frame.get("id"),
                                          "cid": frame.get("cid"), "msg": str(e)[:100]}))
            except Exception:
                pass

    # -- 配对 --
    def _on_pair(self, frame):
        base = {"t": "pair_err", "id": frame.get("id"), "cid": frame.get("cid")}
        p = self.pairing
        if not p or time.time() > p["exp"]:
            return dict(base, code="no_session")
        try:
            ppk = _unb64(frame["ppk"])
            name = str(frame.get("name") or "手机")[:40]
            key = _derive_key(p["priv"], ppk, p["tok"])
            want = hmac_mod.new(key, ppk + name.encode(), hashlib.sha256).digest()
            if not hmac_mod.compare_digest(want, _unb64(frame["mac"])):
                return dict(base, code="bad_mac")
        except Exception:
            return dict(base, code="bad_request")
        dev = base64.urlsafe_b64encode(hashlib.sha256(ppk).digest()[:8]).decode().rstrip("=")
        st = _load()
        st["devices"] = [d for d in st.get("devices", []) if d["dev"] != dev]
        st["devices"].append({"dev": dev, "name": name, "key": _b64(key),
                              "created": int(time.time())})
        _save(st)
        self.pairing = None   # 一码一设备,用完即废
        return {"t": "pair_ok", "id": frame.get("id"), "cid": frame.get("cid"), "dev": dev}

    # -- 请求转发(线程池里跑,阻塞 IO) --
    def _on_req(self, frame):
        base = {"t": "err", "id": frame.get("id"), "cid": frame.get("cid")}
        dev = frame.get("dev") or ""
        rec = next((d for d in _load().get("devices", []) if d["dev"] == dev), None)
        if not rec:
            return dict(base, code="unknown_device")
        key = _unb64(rec["key"])
        try:
            plain = _decrypt(key, ("req:" + dev).encode(), _unb64(frame["n"]), _unb64(frame["d"]))
            req = json.loads(plain)
        except Exception:
            return dict(base, code="decrypt_failed")
        status, headers, body = self._local_call(req)
        out = json.dumps({"status": status, "headers": headers,
                          "body_b64": _b64(body) if body else None}).encode()
        n, ct = _encrypt(key, ("resp:" + dev).encode(), out)
        return {"t": "resp", "id": frame.get("id"), "cid": frame.get("cid"), "dev": dev,
                "n": _b64(n), "d": _b64(ct)}

    def _local_call(self, req):
        path = req.get("path") or "/"
        if not path.startswith(_ALLOW_PREFIX):
            return 403, {"content-type": "application/json"}, b'{"error":"path_not_allowed"}'
        body = _unb64(req["body_b64"]) if req.get("body_b64") else None
        if body and len(body) > _MAX_BODY:
            return 413, {"content-type": "application/json"}, b'{"error":"too_large"}'
        headers = {k: v for k, v in (req.get("headers") or {}).items()
                   if k.lower() in ("authorization", "content-type", "accept")}
        url = "http://127.0.0.1:%d%s" % (self.local_port, path)
        r = urllib.request.Request(url, data=body, headers=headers,
                                   method=(req.get("method") or "GET").upper())
        # 本机回环直连,绝不走系统代理(clash 劫持回环的老坑)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(r, timeout=290) as resp:
                data = resp.read(_MAX_BODY)
                return resp.status, {"content-type": resp.headers.get("Content-Type", "")}, data
        except urllib.error.HTTPError as e:
            return e.code, {"content-type": e.headers.get("Content-Type", "")}, e.read(1024 * 1024)
        except Exception as e:
            return 502, {"content-type": "application/json"}, json.dumps(
                {"error": "local_backend_unreachable", "detail": str(e)[:100]}).encode()


CONNECTOR = _Connector()


def start(port: int = None):
    """app.py startup 钩子调用:有 cloud_token 就常驻外连。"""
    if port:
        CONNECTOR.local_port = port
    CONNECTOR.ensure_started()


# ---------------- 本地 API(配对 UI 用) ----------------

def build_router(me_fn):
    r = APIRouter()

    @r.post("/api/phone/cloud_token")
    def set_cloud_token(payload: dict, authorization: str = Header(None)):
        me_fn(authorization)
        tok = (payload or {}).get("token") or ""
        st = _load()
        if st.get("cloud_token") == tok:
            return {"ok": True, "changed": False}
        st["cloud_token"] = tok
        _save(st)
        CONNECTOR.restart()
        return {"ok": True, "changed": True}

    @r.post("/api/phone/pair/start")
    def pair_start(authorization: str = Header(None)):
        me = me_fn(authorization)
        priv, pub_raw = _gen_keypair()
        tok = secrets.token_bytes(32)
        CONNECTOR.pairing = {"priv": priv, "tok": tok, "exp": time.time() + 300}
        st = _load()
        payload = json.dumps({
            "v": 1, "kind": "compound-pair",
            "relay": st.get("relay_url") or RELAY_DEFAULT,
            "cloud": CLOUD_DEFAULT,
            "account": me,
            "dpk": _b64(pub_raw), "tok": _b64(tok),
            "exp": int(time.time() + 300),
        }, separators=(",", ":"))
        import qrcode
        img = qrcode.make(payload, box_size=6, border=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return {"qr": "data:image/png;base64," + _b64(buf.getvalue()),
                "payload": payload, "expires_in": 300}

    @r.get("/api/phone/status")
    def status(authorization: str = Header(None)):
        me_fn(authorization)
        st = _load()
        return {"relay": CONNECTOR.state, "relay_url": st.get("relay_url") or RELAY_DEFAULT,
                "last_err": CONNECTOR.last_err, "token_set": bool(st.get("cloud_token")),
                "pairing_open": bool(CONNECTOR.pairing and time.time() < CONNECTOR.pairing["exp"]),
                "devices": [{"dev": d["dev"], "name": d["name"], "created": d["created"]}
                            for d in st.get("devices", [])]}

    @r.delete("/api/phone/device/{dev}")
    def remove_device(dev: str, authorization: str = Header(None)):
        me_fn(authorization)
        st = _load()
        before = len(st.get("devices", []))
        st["devices"] = [d for d in st.get("devices", []) if d["dev"] != dev]
        _save(st)
        return {"ok": True, "removed": before - len(st["devices"])}

    return r

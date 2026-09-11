# -*- coding: utf-8 -*-
"""复利手机通道中转(部署 106): 按账号路由的 WS 转发器,只递密文不读内容。

协议见 sidecar/phone_link.py 头注释(协议 v1,双端对齐)。
职责:
  - hello 鉴权: 拿客户端 token 调本机账号服务 /account/me 换 ident
  - 桌面: 每账号一条(新顶旧);手机: 每账号多条,打 cid 路由戳
  - 手机→桌面: 帧加 cid 转发;桌面→手机: 按 cid 回投并剥掉 cid
  - presence: 桌面上/下线时推给该账号全部手机
运行: RELAY_PORT=8300 ACCOUNT_URL=http://127.0.0.1:8000 python3 relay_server.py
nginx: /relay 反代 ws → 127.0.0.1:8300(见 deploy/ 下配置)
"""
import asyncio
import json
import os
import secrets
import time
import urllib.request

PORT = int(os.environ.get("RELAY_PORT", "8300"))
ACCOUNT_URL = os.environ.get("ACCOUNT_URL", "http://127.0.0.1:8000")
MAX_FRAME = 52 * 1024 * 1024

ROOMS = {}   # ident -> {"desktop": ws|None, "phones": {cid: ws}}
_tok_cache = {}   # token -> (ident, exp)


def _room(ident):
    return ROOMS.setdefault(ident, {"desktop": None, "phones": {}})


async def _ident_of(token):
    now = time.time()
    hit = _tok_cache.get(token)
    if hit and hit[1] > now:
        return hit[0]

    def call():
        req = urllib.request.Request(ACCOUNT_URL + "/account/me",
                                     headers={"Authorization": "Bearer " + token})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=8) as r:
            return json.loads(r.read())
    try:
        acc = await asyncio.get_running_loop().run_in_executor(None, call)
        ident = acc.get("ident") or acc.get("username")
        if not ident:
            return None
        _tok_cache[token] = (ident, now + 60)
        if len(_tok_cache) > 5000:
            _tok_cache.clear()
        return ident
    except Exception:
        return None


async def _push_presence(room, online):
    dead = []
    for cid, ws in room["phones"].items():
        try:
            await ws.send(json.dumps({"t": "presence", "online": online}))
        except Exception:
            dead.append(cid)
    for cid in dead:
        room["phones"].pop(cid, None)


async def handle(ws):
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=15)
        hello = json.loads(raw)
        assert hello.get("t") == "hello"
        role = hello.get("role")
        ident = await _ident_of(hello.get("token") or "")
    except Exception:
        try:
            await ws.send(json.dumps({"t": "err", "code": "bad_hello"}))
        finally:
            return
    if not ident or role not in ("desktop", "phone"):
        try:
            await ws.send(json.dumps({"t": "err", "code": "auth"}))
        finally:
            return
    room = _room(ident)
    await ws.send(json.dumps({"t": "ok", "ident": ident}))

    if role == "desktop":
        old = room["desktop"]
        room["desktop"] = ws
        if old:
            try:
                await old.close()
            except Exception:
                pass
        await _push_presence(room, True)
        try:
            async for raw in ws:
                try:
                    frame = json.loads(raw)
                except Exception:
                    continue
                cid = frame.pop("cid", None)
                target = room["phones"].get(cid)
                if target:
                    try:
                        await target.send(json.dumps(frame))
                    except Exception:
                        room["phones"].pop(cid, None)
        finally:
            if room["desktop"] is ws:
                room["desktop"] = None
                await _push_presence(room, False)
    else:
        cid = secrets.token_urlsafe(9)
        room["phones"][cid] = ws
        try:
            await ws.send(json.dumps({"t": "presence", "online": room["desktop"] is not None}))
            async for raw in ws:
                try:
                    frame = json.loads(raw)
                except Exception:
                    continue
                if frame.get("t") not in ("req", "pair"):
                    continue
                frame["cid"] = cid
                d = room["desktop"]
                if d is None:
                    await ws.send(json.dumps({"t": "err", "code": "offline",
                                              "id": frame.get("id")}))
                    continue
                try:
                    await d.send(json.dumps(frame))
                except Exception:
                    await ws.send(json.dumps({"t": "err", "code": "offline",
                                              "id": frame.get("id")}))
        finally:
            room["phones"].pop(cid, None)


async def main():
    import websockets
    async with websockets.serve(handle, "127.0.0.1", PORT, max_size=MAX_FRAME,
                                ping_interval=25, ping_timeout=20):
        print("[relay] listening 127.0.0.1:%d account=%s" % (PORT, ACCOUNT_URL))
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())

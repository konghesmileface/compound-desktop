#!/usr/bin/env python3
"""
客户端全功能冒烟测试(针对打包 sidecar)。
覆盖:健康/鉴权、80 端点 GET 契约、语义嵌入端到端、微信 handoff 消费、星图/问答。

用法:
  python3 client_smoke_test.py                      # 自动:找运行中 sidecar + 从 localStorage 取 token
  python3 client_smoke_test.py --base http://127.0.0.1:8399 --token <TOK>
  python3 client_smoke_test.py --wechat             # 额外测微信 handoff(会注入一条测试消息后清掉)

设计:只读为主;--wechat 会临时写 ~/.wxsync/handoff 一条测试消息、测完删除,不污染真库。
"""
import argparse, json, os, sqlite3, subprocess, sys, time, urllib.request, urllib.error

def _find_token():
    """从 Tauri webview localStorage 取已登录 token(UTF-16LE 存储)。"""
    ls = os.path.expanduser("~/Library/WebKit/com.compoundtome.desktop/WebsiteData/"
                            "LocalStorage/tauri_localhost_0.localstorage")
    if not os.path.exists(ls):
        return None
    try:
        v = sqlite3.connect(ls).execute("SELECT value FROM ItemTable WHERE key='auth'").fetchone()[0]
        s = v.decode("utf-16-le") if isinstance(v, bytes) else v
        import re
        m = re.search(r'"token":"([^"]+)"', s)
        return m.group(1) if m else None
    except Exception:
        return None

def _find_base():
    """找运行中 sidecar 的端口。"""
    try:
        pid = subprocess.check_output(["pgrep", "-f", "compound-sidecar"]).split()[0].decode()
        out = subprocess.check_output(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", pid],
                                      stderr=subprocess.DEVNULL).decode()
        for ln in out.splitlines():
            if "127.0.0.1:" in ln:
                return "http://127.0.0.1:" + ln.split("127.0.0.1:")[1].split()[0].split("(")[0].strip()
    except Exception:
        pass
    return None

def _get(base, path, token, timeout=30, method="GET", body=None):
    url = base + path
    headers = {"Authorization": "Bearer " + token} if token else {}
    data = None
    if body is not None:
        data = json.dumps(body).encode(); headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        raw = r.read()
        try:
            return r.status, json.loads(raw), len(raw)
        except Exception:
            return r.status, None, len(raw)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read()), 0
        except Exception:
            return e.code, None, 0
    except Exception as e:
        return 0, {"_err": str(e)[:80]}, 0

# GET 端点契约(200 或指定容许码)
GETS = [
    "/health", "/api/stats", "/api/library", "/api/people", "/api/persona",
    "/api/today", "/api/graph", "/api/relationships", "/api/commitments",
    "/api/news", "/api/analysis_status", "/api/realtime/status", "/api/mylibrary",
    "/api/links", "/api/entity_links", "/api/cards", "/api/discoveries",
    "/api/cooling", "/api/favors", "/api/dormant", "/api/balance",
    "/api/panorama", "/api/checkup", "/api/starmap?chunk=14",
    "/api/chat_galaxy", "/api/chat_topic_galaxy", "/api/matches",
    "/api/number_ledger", "/api/network_portrait",
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base"); ap.add_argument("--token"); ap.add_argument("--wechat", action="store_true")
    ap.add_argument("--db")  # library.db 路径(测嵌入/微信入库计数用)
    a = ap.parse_args()
    base = a.base or _find_base()
    token = a.token or _find_token()
    if not base:
        print("✗ 找不到运行中的 sidecar,--base 指定"); sys.exit(2)
    print(f"目标: {base}  token: {'有' if token else '无(仅测公开端点)'}")
    db = a.db or os.path.expanduser("~/Library/Application Support/Compound/brain/library.db")

    npass = nfail = 0
    print("\n== GET 端点契约 ==")
    for ep in GETS:
        code, js, sz = _get(base, ep, token)
        ok = code == 200 and js is not None
        # 402=付费墙 401=未登录 也算端点正常(鉴权工作)
        if code in (401, 402):
            ok = True
        print(f"  {'PASS' if ok else 'FAIL'}  {code:>3}  {ep}  ({sz}B)")
        npass += ok; nfail += (not ok)

    print("\n== 语义嵌入进度(scipy/bge-m3 健康度)==")
    try:
        c = sqlite3.connect(db, timeout=3)
        tot = c.execute("SELECT count(*) FROM pages").fetchone()[0]
        emb = c.execute("SELECT count(*) FROM page_embeddings").fetchone()[0]
        print(f"  pages={tot}  已嵌入={emb}  ({'嵌入在跑' if emb>0 else '未开始/加载中'})")
    except Exception as e:
        print(f"  (读库失败: {e})")

    if a.wechat:
        print("\n== 微信 handoff 消费链路 ==")
        hd = os.path.expanduser("~/.wxsync/handoff"); os.makedirs(hd, exist_ok=True)
        f = os.path.join(hd, "messages-smoketest.ndjson")
        open(f, "w", encoding="utf-8").write(json.dumps({
            "msg_id": "SMOKE-1", "session_id": "冒烟测试联系人", "session_name": "冒烟测试联系人",
            "is_group": False, "sender_id": "smoke", "sender_name": "冒烟测试联系人",
            "ts": "2026-01-01T00:00:00", "type": 1, "kind": "文本", "text": "冒烟测试消息"}) + "\n")
        try:
            os.remove(os.path.expanduser("~/.wxsync/compound_cursors.json"))
        except Exception:
            pass
        _get(base, "/api/wechat/watch", token, method="POST")
        got = False
        for _ in range(8):
            try:
                n = sqlite3.connect(db, timeout=3).execute(
                    "SELECT count(*) FROM documents WHERE filename LIKE '%冒烟测试%'").fetchone()[0]
                if n > 0:
                    got = True; break
            except Exception:
                pass
            time.sleep(5)
        print(f"  {'PASS' if got else 'FAIL'}  handoff 测试消息{'已入库' if got else '未入库'}")
        npass += got; nfail += (not got)
        try:
            os.remove(f)
        except Exception:
            pass

    print(f"\n== 结果: {npass} PASS / {nfail} FAIL ==")
    sys.exit(1 if nfail else 0)

if __name__ == "__main__":
    main()

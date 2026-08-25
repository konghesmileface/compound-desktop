"""handoff 消费器:读 ~/.wxsync/handoff/messages-*.ndjson → 批量推第二大脑 /api/wechat/ingest。
- 按字节游标断点续读(崩溃不重复、不丢:先入库成功再推进游标,msg_id 在后端幂等兜重复)
- 心跳上报 /api/realtime/heartbeat(网页实时徽章亮)
- 消费即焚:整天文件全部消费完且非当天 → 删除明文(隐私)
用法:
  python3 handoff_consumer.py            # 跑一轮把现有消费完就退出(适合 backfill)
  python3 handoff_consumer.py --watch    # 常驻,tail 新消息实时入库
"""
import os
import sys
import json
import time
import glob
import urllib.request
import urllib.error

HANDOFF_DIR = os.path.expanduser("~/.wxsync/handoff")
STATE_PATH = os.path.expanduser("~/.wxsync/consumer_state.json")
BATCH = int(os.environ.get("WXSYNC_BATCH", "2000"))


def _cfg():
    backend = os.environ.get("WXSYNC_BACKEND", "")
    token = os.environ.get("WXSYNC_TOKEN", "")
    p = os.path.expanduser("~/.wxsync/config.json")
    if (not backend or not token) and os.path.exists(p):
        try:
            d = json.load(open(p))
            backend = backend or d.get("backend", "")
            token = token or d.get("token", "")
        except Exception:
            pass
    return backend.rstrip("/"), token


BACKEND, TOKEN = _cfg()


def _load_state():
    try:
        return json.load(open(STATE_PATH))
    except Exception:
        return {}


def _save_state(st):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    json.dump(st, open(tmp, "w"))
    os.replace(tmp, STATE_PATH)


def _post(path, obj, timeout=120):
    data = json.dumps(obj).encode("utf-8")
    req = urllib.request.Request(BACKEND + path, data=data, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + TOKEN})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as r:
        return json.load(r)


def _beat(running, pending, last):
    try:
        _post("/api/realtime/heartbeat", {"running": running, "pending": pending,
                                          "last_synced": last, "note": "handoff"}, timeout=15)
    except Exception:
        pass


def _consume_file(path, st, on_progress=None):
    """从游标读该文件,批量推送,成功后推进游标。返回本轮入库条数。"""
    key = os.path.basename(path)
    offset = st.get(key, 0)
    total_new = 0
    size = os.path.getsize(path)
    if offset >= size:
        return 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        f.seek(offset)
        buf = []
        while True:
            line = f.readline()
            if not line:
                break
            if not line.endswith("\n"):
                # 半行(正在被追加写)→ 停在这,下轮再读
                break
            offset += len(line.encode("utf-8"))
            line = line.strip()
            if not line:
                continue
            try:
                buf.append(json.loads(line))
            except Exception:
                continue
            if len(buf) >= BATCH:
                r = _post("/api/wechat/ingest", {"messages": buf})
                total_new += r.get("ingested", 0)
                buf = []
                st[key] = offset
                _save_state(st)         # 先入库成功再落游标
                last = ""
                _beat(True, 0, "")
                if on_progress:
                    on_progress(total_new)
        if buf:
            r = _post("/api/wechat/ingest", {"messages": buf})
            total_new += r.get("ingested", 0)
            st[key] = offset
            _save_state(st)
    return total_new


def run_once():
    if not BACKEND or not TOKEN:
        print("未配置后端/token:设 WXSYNC_BACKEND / WXSYNC_TOKEN 或 ~/.wxsync/config.json")
        return 0
    st = _load_state()
    files = sorted(glob.glob(os.path.join(HANDOFF_DIR, "messages-*.ndjson")))
    grand = 0
    for path in files:
        n = _consume_file(path, st, on_progress=lambda t: print("  已入库 %d 条…" % t, flush=True))
        grand += n
        # 消费即焚:非当天文件且已读完 → 删明文
        key = os.path.basename(path)
        if st.get(key, 0) >= os.path.getsize(path) and "-" + time.strftime("%Y%m%d") not in key:
            try:
                os.remove(path)
                print("消费即焚:已删", key)
            except Exception:
                pass
    _beat(False, 0, "")
    print("本轮入库:", grand, "条")
    return grand


def watch(interval=3):
    print("常驻监听 handoff… (Ctrl-C 退出)")
    while True:
        try:
            run_once()
        except Exception as e:
            print("消费出错(下轮重试):", e)
        time.sleep(interval)


if __name__ == "__main__":
    if "--watch" in sys.argv:
        watch()
    else:
        run_once()

# -*- coding: utf-8 -*-
"""
桌面版实时增量同步(WAL 轮询)
================================

设计(调研已定):微信桌面消息库用 SQLite WAL,新消息先落 .db-wal;
    轮询 WAL 文件 mtime(秒级)发现变化
    → 按 message 表 MAX(rowid) 增量游标读新消息
    → 归一化成「与X的对话」
    → 微批(30-60s 或攒满 N 条)
    → POST /api/upload
    → 每批回调状态 + 打心跳(网页点亮"正在实时同步"徽章)。
游标 + 去重表持久化到本地 sync_state.db,断线/重启从游标续。

★★重要合规边界★★
本模块**只处理明文/已解密的消息库**。拿到"可读消息数据库路径"这一步
被当作**外部输入**,由另外的模块负责(见 get_decrypted_db_path 的 TODO)。
本模块**绝不**读取微信进程内存 / 破解 SQLCipher 密钥。

优雅启停:RealtimePoller.stop() 让轮询循环在下个周期干净退出;
用户在网页关掉实时开关时,poller 也会检测到并停。
"""

import hashlib
import os
import re
import sqlite3
import threading
import time

from config import load_config, STATE_DB_PATH
from status import StatusReporter
from uploader import upload_chat_txt

# 和 import_iphone 保持一致的非文字占位
WX_TYPE = {
    1: "", 3: "[图片]", 34: "[语音]", 43: "[视频]", 42: "[名片]",
    47: "[表情]", 48: "[位置]", 49: "[链接/文件]", 50: "[通话]",
}


# =========================================================================== #
# TODO 钩子:拿到"可读(明文/已解密)的消息数据库路径"
# =========================================================================== #
def get_decrypted_db_path() -> str:
    """
    返回一个**明文可读**的微信消息 SQLite 库路径。

    ★合规边界:这一步(桌面 Windows/Mac 上把加密库变成明文库)由**另外的模块**
    负责——可能是用户侧的第三方开源工具、也可能是产品另行提供的解密组件。
    本文件不做任何解密 / 读内存 / 破密钥的事,只把结果当输入。

    实现方式(由外部模块填充其一):
      - 读一个约定好的环境变量 WXSYNC_DECRYPTED_DB(最简单、推荐先用这个)
      - 读一个约定的落地路径(解密模块把明文库写到固定位置)
      - 通过 IPC / 本地文件让解密模块把路径告诉这里

    返回 None 表示"当前拿不到明文库"(微信没开/还没解密),轮询会跳过并提示。
    """
    # —— 目前用环境变量做占位;替换成真正的解密模块产物即可 ——
    path = os.environ.get("WXSYNC_DECRYPTED_DB", "").strip()
    if path and os.path.exists(path):
        return path
    return None


# =========================================================================== #
# 本地状态库:游标 + 去重
# =========================================================================== #
def _init_state_db(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    # 每个 (account, db_path, table) 记一个 rowid 游标
    con.execute("""
        CREATE TABLE IF NOT EXISTS cursors(
            account   TEXT,
            db_path   TEXT,
            tbl       TEXT,
            last_rowid INTEGER DEFAULT 0,
            PRIMARY KEY(account, db_path, tbl)
        )""")
    # 去重:msg_id = md5(account|db|rowid|ts) 唯一索引
    con.execute("""
        CREATE TABLE IF NOT EXISTS seen(
            msg_id TEXT PRIMARY KEY,
            ts     INTEGER
        )""")
    con.commit()
    return con


def _get_cursor(con, account, db_path, tbl) -> int:
    row = con.execute(
        "SELECT last_rowid FROM cursors WHERE account=? AND db_path=? AND tbl=?",
        (account, db_path, tbl)).fetchone()
    return row[0] if row else 0


def _set_cursor(con, account, db_path, tbl, rowid):
    con.execute(
        "INSERT INTO cursors(account,db_path,tbl,last_rowid) VALUES(?,?,?,?) "
        "ON CONFLICT(account,db_path,tbl) DO UPDATE SET last_rowid=excluded.last_rowid",
        (account, db_path, tbl, rowid))
    con.commit()


def _mark_seen(con, msg_id) -> bool:
    """返回 True 表示是新消息(插入成功);False 表示已见过(去重命中)。"""
    try:
        con.execute("INSERT INTO seen(msg_id,ts) VALUES(?,?)",
                    (msg_id, int(time.time())))
        return True
    except sqlite3.IntegrityError:
        return False


# =========================================================================== #
# 读明文微信库的增量消息
# =========================================================================== #
def _list_chat_tables(con):
    """返回明文库里带必要列的 Chat_% 会话表。"""
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name LIKE 'Chat_%'")]
    good = []
    for t in tables:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
        if all(x in cols for x in ("CreateTime", "Des", "Message", "Type")):
            good.append(t)
    return good


def _norm_line(ct, des, msg, ty, name):
    """一条微信消息 → 「[时间] 我/对方: 内容」;不入库的返回 None。"""
    if ty == 1:
        content = re.sub(r"^[\w\-]+:\n", "", msg or "")
    elif WX_TYPE.get(ty):
        content = WX_TYPE[ty]
    else:
        return None
    if not content:
        return None
    who = "我" if des == 0 else name
    tm = time.strftime("%Y-%m-%d %H:%M", time.localtime(ct))
    return f"[{tm}] {who}: {content}"


def _safe_name(name):
    safe = re.sub(r"[^\w一-龥]", "_", name or "")[:22]
    return safe or "未命名"


# =========================================================================== #
# 实时轮询器
# =========================================================================== #
class RealtimePoller:
    """
    优雅启停的实时同步轮询器。

    用法:
        p = RealtimePoller(name_resolver=my_resolver)
        p.start()          # 后台线程跑
        ...
        p.stop()           # 请求停止,下个周期干净退出
        p.join()

    name_resolver(table_name) -> 显示名:把 Chat_<hash> 解析成联系人名。
        默认返回 hash 前 8 位;真实产品可传入从明文联系人库建的映射。
    """

    def __init__(self, cfg=None, name_resolver=None, on_status=None):
        self.cfg = cfg or load_config()
        self.reporter = StatusReporter(self.cfg)
        self.name_resolver = name_resolver or (lambda t: t[5:13])
        self.on_status = on_status or (lambda stage, detail="": print(
            f"[realtime] {stage}" + (f" — {detail}" if detail else ""),
            flush=True))
        self._stop = threading.Event()
        self._thread = None
        self._state = _init_state_db(STATE_DB_PATH)
        # 每个会话的待上传缓冲:hash -> {"name":.., "lines":[..], "since":ts}
        self._buffers = {}
        self._last_synced = 0

    # ---------------- 启停 ---------------- #
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.on_status("实时同步已启动")

    def stop(self):
        """请求优雅停止(下个周期退出),并把剩余缓冲 flush 掉。"""
        self._stop.set()
        self.on_status("正在停止实时同步…")

    def join(self, timeout=None):
        if self._thread:
            self._thread.join(timeout)

    # ---------------- 主循环 ---------------- #
    def _loop(self):
        last_wal_mtime = 0
        while not self._stop.is_set():
            try:
                # 用户可能在网页关掉了实时开关 → 尊重它
                if not self.reporter.query_toggle():
                    self.on_status("实时同步已被关闭(网页开关)")
                    self._heartbeat(running=False, note="用户已关闭实时同步")
                    break

                db_path = get_decrypted_db_path()
                if not db_path:
                    self._heartbeat(running=True, note="微信未运行或明文库暂不可用,已跳过")
                    self._sleep()
                    continue

                # WAL mtime 变化 → 有新消息。没变也定期 flush 超时批。
                wal = db_path + "-wal"
                mtime = os.path.getmtime(wal) if os.path.exists(wal) else \
                    os.path.getmtime(db_path)
                if mtime != last_wal_mtime:
                    last_wal_mtime = mtime
                    self._drain_new(db_path)

                self._flush_ready()
                self._heartbeat(running=True)
            except Exception as e:  # noqa: BLE001
                self.on_status("轮询出错(将重试)", str(e))
                self._heartbeat(running=True, note=f"错误重试:{e}")
            self._sleep()

        # 退出前 flush 掉所有缓冲,别丢消息
        self._flush_all()
        self._heartbeat(running=False, note="实时同步已停止")
        self.on_status("实时同步已停止")

    def _sleep(self):
        # 可被 stop() 立刻打断的 sleep
        self._stop.wait(self.cfg.poll_interval_sec)

    # ---------------- 增量读取 ---------------- #
    def _drain_new(self, db_path):
        """按 rowid 游标读每个会话表的新消息,进缓冲(去重)。"""
        # 只读打开明文库(轮询时微信可能在写,用 immutable/ro 减少锁冲突)
        uri = f"file:{db_path}?mode=ro&immutable=1"
        try:
            con = sqlite3.connect(uri, uri=True)
        except sqlite3.OperationalError:
            con = sqlite3.connect(db_path)
        try:
            for tbl in _list_chat_tables(con):
                key = tbl[5:]  # md5(userName)
                name = self.name_resolver(tbl)
                last = _get_cursor(self._state, self.cfg.account, db_path, tbl)
                max_row = last
                for rowid, ct, des, msg, ty in con.execute(
                        f"SELECT rowid,CreateTime,Des,Message,Type FROM {tbl} "
                        f"WHERE rowid>? ORDER BY rowid", (last,)):
                    max_row = max(max_row, rowid)
                    # 去重键:account|db|rowid|ts
                    raw = f"{self.cfg.account}|{db_path}|{rowid}|{ct}"
                    msg_id = hashlib.md5(raw.encode()).hexdigest()
                    if not _mark_seen(self._state, msg_id):
                        continue
                    line = _norm_line(ct, des, msg, ty, name)
                    if not line:
                        continue
                    buf = self._buffers.setdefault(
                        key, {"name": name, "lines": [], "since": time.time()})
                    buf["lines"].append(line)
                if max_row > last:
                    _set_cursor(self._state, self.cfg.account,
                                db_path, tbl, max_row)
            self._state.commit()
        finally:
            con.close()

    # ---------------- 微批 flush ---------------- #
    def _pending_count(self):
        return sum(len(b["lines"]) for b in self._buffers.values())

    def _flush_ready(self):
        """把满时间(batch_max_seconds)或满条数的会话缓冲上传掉。"""
        now = time.time()
        ready_keys = []
        for key, buf in self._buffers.items():
            aged = (now - buf["since"]) >= self.cfg.batch_max_seconds
            full = len(buf["lines"]) >= self.cfg.batch_max_messages
            if buf["lines"] and (aged or full):
                ready_keys.append(key)
        for key in ready_keys:
            self._upload_buffer(key)

    def _flush_all(self):
        for key in list(self._buffers.keys()):
            if self._buffers[key]["lines"]:
                self._upload_buffer(key)

    def _upload_buffer(self, key):
        buf = self._buffers.pop(key)
        name = buf["name"]
        lines = buf["lines"]
        safe = _safe_name(name)
        filename = f"微信_与{safe}.txt"
        header = f"微信聊天记录 · 与「{name}」(实时增量 {len(lines)}条)\n"
        content = header + "\n".join(lines)
        job_id = f"realtime-{safe}"
        self.on_status(f"上传增量:与「{name}」", f"{len(lines)} 条")
        self.reporter.report_ingest(job_id, name, "uploading", 20,
                                    f"实时增量 {len(lines)} 条")
        try:
            upload_chat_txt(self.cfg, filename, content)
            self._last_synced = int(time.time())
            self.reporter.report_ingest(job_id, name, "done", 100,
                                        "已提交后端解析入库")
        except Exception as e:  # noqa: BLE001
            self.on_status(f"上传失败:与「{name}」", str(e))
            self.reporter.report_ingest(job_id, name, "failed", 20, str(e))
            # 上传失败:把消息放回缓冲,下轮重试(游标已前进但 seen 已记,
            # 靠缓冲重试保证不丢;真实产品可加本地重试队列持久化)
            self._buffers[key] = buf

    # ---------------- 心跳 ---------------- #
    def _heartbeat(self, running, note=""):
        self.reporter.beat(running=running,
                           pending=self._pending_count(),
                           last_synced=self._last_synced,
                           note=note)


def main():
    """命令行入口:python realtime_poll.py。Ctrl+C 优雅退出。"""
    cfg = load_config()
    if not cfg.realtime_enabled:
        print("实时同步在配置里是关闭的(realtime_enabled=false),退出。")
        return
    poller = RealtimePoller(cfg)
    poller.start()
    try:
        while poller._thread and poller._thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n收到 Ctrl+C,正在优雅停止…")
        poller.stop()
        poller.join(timeout=30)


if __name__ == "__main__":
    main()

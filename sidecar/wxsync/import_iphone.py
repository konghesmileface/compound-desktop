# -*- coding: utf-8 -*-
"""
iPhone 备份路线:一次性把历史微信聊天导进第二大脑
===================================================

iOS 微信消息库本身就是**明文 SQLite**(和桌面版不同,无需任何解密)。
本模块只做合法的这一段:
    连手机 → idevicebackup2 全量备份到本机 → 解析 Manifest.db 找微信库
    → 抽成「[时间] 我/对方: 内容」对话 txt → 逐个 POST /api/upload。

全程通过 on_status 回调 / 打印上报**每个阶段**(连接手机 / 备份中 / 解析库 /
抽取聊天 / 上传中 / 完成),带百分比,让网页进度条能显示。

依赖(命令行工具,用户装一次):
    brew install libimobiledevice    # 提供 idevice_id / idevicebackup2
Windows 用户用 iTunes 或 libimobiledevice 的 Windows 构建;逻辑相同。

参考实现:项目里跑通过的 /tmp/wxfull.py 逻辑。
"""

import datetime
import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile

from config import load_config
from status import StatusReporter
from uploader import ingest_wechat_messages

# 微信消息 Type → 占位文本(非文字消息入库成占位,保留上下文)
WX_TYPE = {
    1: "",          # 文本(内容在 Message 里)
    3: "[图片]",
    34: "[语音]",
    43: "[视频]",
    42: "[名片]",
    47: "[表情]",
    48: "[位置]",
    49: "[链接/文件]",
    50: "[通话]",
}

# 微信 iOS 备份域
WX_DOMAIN_LIKE = "%tencent.xin%"


# --------------------------------------------------------------------------- #
# 状态回调:统一格式。stage 是给人看的中文阶段,percent 给进度条。
# --------------------------------------------------------------------------- #
def _default_status(stage: str, percent: int, detail: str = ""):
    bar = f"{percent:3d}%"
    line = f"[{bar}] {stage}"
    if detail:
        line += f" — {detail}"
    print(line, flush=True)


# --------------------------------------------------------------------------- #
# 1. 连手机 + 全量备份
# --------------------------------------------------------------------------- #
def _detect_udid() -> str:
    """列出已连接的 iPhone UDID(取第一台)。未连返回 None。"""
    try:
        out = subprocess.check_output(["idevice_id", "-l"], text=True, timeout=15)
    except FileNotFoundError:
        raise RuntimeError(
            "没找到 idevice_id 命令。请先安装:brew install libimobiledevice")
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"检测手机失败:{e}")
    udids = [x.strip() for x in out.splitlines() if x.strip()]
    return udids[0] if udids else None


def _run_backup(udid: str, dest_dir: str, on_status) -> str:
    """
    调 idevicebackup2 做全量备份。备份产物根目录 = dest_dir/<udid>。
    备份过程较长(几分钟到十几分钟),这里流式读输出估算进度。
    """
    on_status("正在备份手机(请保持连接、屏幕解锁)", 15,
              "首次备份较慢,期间不要拔线")
    cmd = ["idevicebackup2", "-u", udid, "backup", "--full", dest_dir]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    # idevicebackup2 会打印 "Sending files (12%)" 之类,抓百分比映射到 15%~55%
    pct_re = re.compile(r"\((\d+)%\)")
    for raw in iter(proc.stdout.readline, ""):
        m = pct_re.search(raw)
        if m:
            inner = int(m.group(1))
            mapped = 15 + int(inner * 0.40)  # 15→55
            on_status("正在备份手机", mapped, raw.strip())
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("备份失败,请确认手机已点『信任』且屏幕解锁后重试")
    backup_root = os.path.join(dest_dir, udid)
    if not os.path.isdir(backup_root):
        # 有些版本直接放在 dest_dir 根
        backup_root = dest_dir
    return backup_root


# --------------------------------------------------------------------------- #
# 2. 从 Manifest.db 找微信库并复制出来
# --------------------------------------------------------------------------- #
def _extract_wx_dbs(backup_root: str, work_dir: str, on_status):
    """
    读 Manifest.db 的 Files 表(fileID=40位SHA1,domain=AppDomain-com.tencent.xin),
    把消息库(Documents/<hash>/DB/message_*.sqlite)和联系人库(WCDB_Contact.sqlite)
    复制到 work_dir,返回 (msg_dbs, contact_dbs)。
    """
    manifest = os.path.join(backup_root, "Manifest.db")
    if not os.path.exists(manifest):
        raise RuntimeError(f"备份里没有 Manifest.db:{manifest}")
    on_status("正在解析备份索引", 58, "定位微信数据库")

    m = sqlite3.connect(manifest)
    msgs, conts = [], []
    q = ("SELECT fileID,relativePath FROM Files "
         "WHERE domain LIKE ? AND relativePath LIKE '%.sqlite' "
         "AND relativePath NOT LIKE '%material%'")
    for fid, rp in m.execute(q, (WX_DOMAIN_LIKE,)):
        # 备份里文件按 fileID[:2]/fileID 分桶存放
        real = os.path.join(backup_root, fid[:2], fid)
        if not os.path.exists(real):
            real = os.path.join(backup_root, fid)  # 无分桶布局兜底
        if not os.path.exists(real):
            continue
        if "/DB/message_" in rp:
            d = os.path.join(work_dir, f"msg_{fid[:8]}.db")
            shutil.copy(real, d)
            msgs.append(d)
        elif "WCDB_Contact" in rp:
            d = os.path.join(work_dir, f"contact_{fid[:8]}.db")
            shutil.copy(real, d)
            conts.append(d)
    m.close()
    on_status("已定位微信库", 62,
              f"消息库 {len(msgs)} 个 · 联系人库 {len(conts)} 个")
    if not msgs:
        raise RuntimeError("没在备份里找到微信消息库,可能这台手机没登录微信")
    return msgs, conts


# --------------------------------------------------------------------------- #
# 3. 认人:从联系人库建 md5(userName) → 显示名 映射
# --------------------------------------------------------------------------- #
# 微信系统号 userName,不作为联系人
_SYS_UN = {"filehelper", "weixin", "fmessage", "medianote", "floatbottle", "qqmail",
           "qmessage", "tmessage", "newsapp", "notifymessage", "notification_messages",
           "mphelper", "brandsessionholder", "exmail_tmessage", "officialaccounts"}


def _pb_field1(blob):
    """解析 protobuf,取 field 1 的字符串值。
    微信联系人库里 dbContactRemark.field1=备注名、dbContactProfile.field1=昵称。
    比"抓最长中文串"准得多(治 年/邀请进群 这类乱抓)。"""
    if not blob:
        return None
    i, n = 0, len(blob)
    while i < n:
        tag = blob[i]; i += 1
        field, wt = tag >> 3, tag & 7
        if wt == 2:
            length, shift = 0, 0
            while i < n:
                b = blob[i]; i += 1
                length |= (b & 0x7f) << shift
                if not (b & 0x80):
                    break
                shift += 7
            val = blob[i:i + length]; i += length
            if field == 1:
                try:
                    return val.decode("utf-8")
                except Exception:
                    return None
        elif wt == 0:
            while i < n and (blob[i] & 0x80):
                i += 1
            i += 1
        elif wt == 5:
            i += 4
        elif wt == 1:
            i += 8
        else:
            break
    return None


def _cn_name(*blobs):
    """旧的兜底:抓最长中文串(仅在 protobuf 取不到时用)。"""
    for b in blobs:
        if b:
            found = re.findall(rb"(?:[\xe4-\xed][\x80-\xbf]{2}){1,16}", b)
            if found:
                return max(found, key=len).decode("utf-8", "ignore")
    return None


def _build_name_map(contact_dbs, on_status):
    """返回 (namemap: md5(userName)->显示名, members: userName->名(认群发言人), skip: 系统号hash集)。
    名字优先取 protobuf 备注 > 昵称,治乱码名。"""
    namemap, members, skip = {}, {}, set()
    for cf in contact_dbs:
        try:
            con = sqlite3.connect(cf)
            rows = con.execute(
                "SELECT userName,dbContactRemark,dbContactProfile,"
                "dbContactChatRoom FROM Friend "
                "WHERE userName IS NOT NULL AND userName!=''")
            for un, rmk, prof, ck in rows:
                key = hashlib.md5(un.encode()).hexdigest()
                base = un.split("@")[0]
                if un in _SYS_UN or base in _SYS_UN or un.startswith("gh_"):
                    skip.add(key)
                    continue
                nm = _pb_field1(rmk) or _pb_field1(prof) or _cn_name(ck)
                if nm:
                    members[un] = nm
                namemap[key] = nm   # 可能 None,抽取时兜底成 会话_<hash6>
            con.close()
        except Exception as e:  # noqa: BLE001
            print(f"[import] 读联系人库出错(跳过):{e}")
    on_status("已建立联系人映射", 66, f"识别到 {len(namemap)} 位联系人")
    return namemap, members, skip


# --------------------------------------------------------------------------- #
# 4. 抽对话:遍历每个 Chat_<md5(userName)> 表 → [时间]我/对方:内容
# --------------------------------------------------------------------------- #
def _extract_chats(msg_dbs, namemap, on_status, members=None, skip=None):
    """遍历所有 Chat 表,一个不漏。返回 [(name, hash, lines[]), ...]。
    群消息按发言人 wxid 认名;系统号跳过;没解析到名的兜底 会话_<hash6>。"""
    members = members or {}
    skip = skip or set()
    merged = {}   # hash -> [name, lines]
    for db in msg_dbs:
        cc = sqlite3.connect(db)
        tables = [r[0] for r in cc.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name LIKE 'Chat_%'")]
        for t in tables:
            if t.startswith("ChatExt"):
                continue
            try:
                key = t[5:]  # 去掉 "Chat_" 前缀 = md5(userName)
                if key in skip:
                    continue
                cols = [r[1] for r in cc.execute(f"PRAGMA table_info({t})")]
                if not all(x in cols for x in
                           ("CreateTime", "Des", "Message", "Type")):
                    continue
                name = namemap.get(key)
                msgs = []
                for ct, des, msg, ty in cc.execute(
                        f"SELECT CreateTime,Des,Message,Type "
                        f"FROM {t} ORDER BY CreateTime"):
                    if isinstance(msg, (bytes, bytearray)):
                        msg = msg.decode("utf-8", "ignore")
                    sender_id = None
                    if ty == 1:
                        m = re.match(r"^([\w\-]+):\n", msg or "")
                        sender_id = m.group(1) if m else None
                        content = re.sub(r"^[\w\-]+:\n", "", msg or "")
                    elif WX_TYPE.get(ty):
                        content = WX_TYPE[ty]
                    else:
                        continue
                    if not content:
                        continue
                    if des == 0:
                        who = "我"
                    elif sender_id and sender_id in members:  # 群里认发言人
                        who = members[sender_id]
                    else:
                        who = name or "对方"
                    tm = datetime.datetime.fromtimestamp(ct).strftime(
                        "%Y-%m-%d %H:%M")
                    msgs.append({"ts": tm, "who": who,
                                 "sender_id": sender_id or "", "text": content})
                if not msgs:
                    continue
                if key in merged:
                    merged[key][1].extend(msgs)
                else:
                    merged[key] = [name, msgs]
            except Exception:  # noqa: BLE001
                continue
        cc.close()
    # 唯一命名(名字重复/为空时加后缀),按消息数排序
    result, used = [], {}
    for key, (name, msgs) in sorted(merged.items(), key=lambda x: -len(x[1][1])):
        disp = name or ("会话_" + key[:6])
        if disp in used:
            used[disp] += 1
            disp = f"{disp}({used[disp]})"
        else:
            used[disp] = 0
        # 会话内先按 (时间,发言人,正文) 去重并按时间排序(服务端还会跨通道再去一次重)
        seen, uniq = set(), []
        for mm in sorted(msgs, key=lambda z: (z["ts"], z["text"])):
            k = (mm["ts"], mm["who"], mm["text"])
            if k in seen:
                continue
            seen.add(k)
            uniq.append(mm)
        result.append((disp, key, uniq))
    on_status("已抽取全部聊天", 70, f"共 {len(result)} 个会话")
    return result


def _safe_name(name: str) -> str:
    """联系人名清成安全文件名(和后端解析器认的 微信_与X.txt 一致)。"""
    safe = re.sub(r"[^\w一-龥]", "_", name)[:22]
    return safe or "未命名"


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def run_import(on_status=None, min_lines: int = 2, keep_backup: bool = False):
    """
    一次性导入主流程。on_status(stage, percent, detail) 是状态回调;
    不传就打印到控制台。同时把进度上报后端(网页进度条)。
    """
    cfg = load_config()
    reporter = StatusReporter(cfg)
    cb = on_status or _default_status

    _last_rep = {"key": None}

    def status(stage, percent, detail="", contact="全部微信聊天",
               state="uploading"):
        cb(stage, percent, detail)
        # 本地 UI 每次都更新;后端节流:同(阶段,百分比,状态)不重复上报,避免备份刷屏
        key = (stage, int(percent), state)
        if key == _last_rep["key"]:
            return
        _last_rep["key"] = key
        # 备份/解析阶段用一个总 job 上报;真正上传时每个联系人各自 job
        reporter.report_ingest("iphone-import", contact, state, percent, stage)

    # 0. 连手机
    status("正在连接手机", 5, "读取 UDID")
    udid = _detect_udid()
    if not udid:
        status("未检测到手机", 0, "请用数据线连接 iPhone 并点『信任』",
               state="failed")
        raise RuntimeError("未检测到 iPhone,请插线并在手机上点『信任这台电脑』")
    status("已连接手机", 10, f"UDID {udid[:8]}…")

    # 1. 备份(用临时目录,除非 keep_backup)
    dest_dir = (os.path.join(tempfile.gettempdir(), "wxsync_backup")
                if not keep_backup else
                os.path.join(os.path.expanduser("~"), "wxsync_backup"))
    os.makedirs(dest_dir, exist_ok=True)
    # 传 status(而非裸 cb):备份/解析/认人各阶段也上报后端,网页五段进度才连续
    backup_root = _run_backup(udid, dest_dir, status)

    # 2. 解析库
    work_dir = tempfile.mkdtemp(prefix="wxsync_dbs_")
    try:
        msg_dbs, contact_dbs = _extract_wx_dbs(backup_root, work_dir, status)
        namemap, members, skip = _build_name_map(contact_dbs, status)
        chats = _extract_chats(msg_dbs, namemap, status, members=members, skip=skip)

        # 3. 逐个上传
        chats = [c for c in chats if len(c[2]) >= min_lines]
        total = len(chats)
        if total == 0:
            status("没有可导入的聊天", 100, "会话消息太少", state="done")
            return
        used_names = {}
        ok = 0
        for i, (name, _key, msgs) in enumerate(chats):
            safe = _safe_name(name)
            if safe in used_names:
                used_names[safe] += 1
                safe = f"{safe}_{used_names[safe]}"
            else:
                used_names[safe] = 0
            # 结构化消息 → /api/wechat/ingest(与桌面实时同一入口,服务端按内容指纹统一去重)
            payload = [{
                "session_name": name,
                "ts": mm["ts"],
                "sender_name": mm["who"],
                # 服务端 _wx_line:sender_id 为空即记为"我";非我消息补占位 id 免得被误判成我
                "sender_id": "" if mm["who"] == "我" else (mm["sender_id"] or "peer"),
                "text": mm["text"],
            } for mm in msgs]

            pct = 70 + int((i + 1) / total * 28)  # 70→98
            job_id = f"iphone-{safe}"
            cb(f"正在写入第 {i+1}/{total} 个会话", pct, f"与「{name}」")
            reporter.report_ingest(job_id, name, "uploading", pct,
                                  f"写入 与{name} 共{len(msgs)}条")
            try:
                r = ingest_wechat_messages(cfg, payload)
                reporter.report_ingest(job_id, name, "done", 100,
                                      f"已入库 {r.get('ingested', 0)} 条 · 去重 {r.get('dup', 0)}")
                ok += 1
            except Exception as e:  # noqa: BLE001
                cb(f"写入失败:{name}", pct, str(e))
                reporter.report_ingest(job_id, name, "failed", pct, str(e))

        status(f"导入完成:成功 {ok}/{total} 个会话", 100, "", state="done")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        if not keep_backup:
            shutil.rmtree(dest_dir, ignore_errors=True)


if __name__ == "__main__":
    # 命令行直接跑:python import_iphone.py
    run_import()

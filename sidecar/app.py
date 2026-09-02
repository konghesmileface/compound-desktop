#!/usr/bin/env python3
"""
第二大脑 —— web 后端骨架(FastAPI)。

只做后端 API,复用现有 ingest.py / backends.py / library.db / vault。
UI 暂不撸(等 design pass)。跑在本机,是未来 pywebview 套壳 Mac .app 的脊梁。

四条主接口:
    POST /api/upload         上传 PDF → 走 OCR 入库(后端可选)
    GET  /api/library        文库列表
    GET  /api/doc/{id}       读一份文档(逐页文本)
    GET  /api/search?q=      全文检索(FTS)
额外: GET /api/stats  GET /health

启动:  .venv/bin/python -m uvicorn web.app:app --reload --port 8200
或:    .venv/bin/python web/app.py
"""
from __future__ import annotations
import json
import re
import os
import sys
import shutil
import threading
import datetime as _dt

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Body, Header
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

# 复用根目录的 ingest / backends
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import ingest as I          # noqa: E402
import backends as B        # noqa: E402
import semantic as S        # noqa: E402
import entities as ENT     # noqa: E402  实体级KG
import relationships as REL  # noqa: E402  关系情报卡
import chat_intel as CI     # noqa: E402  深度聊天情报(承诺/数字/供需/履约)
import insights as INS      # noqa: E402  P1/P2洞察(降温/人情/沉默线索/资产负债表/业务全景/沟通体检/拟稿)
import llm as LLM           # noqa: E402
import generate as G        # noqa: E402

# ★uploads 落可写数据目录(BRAIN_DATA),不能落包内 ROOT——冻结客户端从只读位置(DMG/签名.app)
#   运行时 ROOT 是只读包目录,makedirs 会 OSError: Read-only file system 直接崩(与 generate.py 同类坑)。
UPLOADS = os.path.join(os.environ.get("BRAIN_DATA", ROOT), "uploads")
try:
    os.makedirs(UPLOADS, exist_ok=True)
except OSError:
    pass

BACKENDS = ["auto", "text", "rapidocr"]
# 高精 paddle:仅当本机 paddle worker 已起(高精版客户端 sidecar_main 会拉起并设 PADDLE_OCR_URL)才列出
if os.environ.get("PADDLE_OCR_URL"):
    BACKENDS.append("paddle")
BACKENDS += ["t430", "unlimited"]

app = FastAPI(title="第二大脑 · 后端骨架")
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


def _con():
    """每个请求开一条 SQLite 连接(连接不能跨线程共享)。"""
    return I.db_connect(I.DEFAULT_DB)


@app.get("/")
def root():
    """临时落地页(真正 UI 是 M2)。指向自带的交互式接口文档 /docs。"""
    return {
        "app": "第二大脑 · 后端(UI 待 M2)",
        "试试": {
            "交互式接口文档": "/docs",
            "健康": "/health",
            "文库": "/api/library",
            "统计": "/api/stats",
            "星系图数据": "/api/graph",
            "搜索": "/api/search?q=关键词",
        },
    }


@app.on_event("startup")
def _warm_cache():
    """后台预热检索缓存 + 嵌入模型,避免第一次问答慢。"""
    def w():
        try:
            con = _con()
            S.retrieve(con, "warmup", topk=1)
            con.close()
        except Exception as e:
            print(f"[warm] {e}")
    threading.Thread(target=w, daemon=True).start()


# ★★后台常驻嵌入驱动:客户端是单机、没有 106 上那种回填 cron,微信 handoff 入库的页
#   永远不会被嵌入 → "分析中"卡 0%、星图/语义问答/探索全空。这里持续把待嵌页嵌完(embed_pending
#   每48页 commit,进度实时可见),有活快转没活慢转。106 上它只补零星漏嵌,无害(统一单一代码)。
_BG_EMBED_LOCK = threading.Lock()

@app.on_event("startup")
def _start_bg_embedder():
    def _loop():
        while True:
            n = 0
            if _BG_EMBED_LOCK.acquire(blocking=False):
                try:
                    con = _con()
                    try:
                        # ★按机器内存动态分档(embed_profile):8G机小批限量节流护机器,强机全速。
                        #   每轮限量→调用短返回快,靠下面 sleep 给机器喘气,不一口气占死(load 186 空转事故根修)。
                        n = S.embed_pending(con)
                    finally:
                        con.close()
                except Exception as e:
                    print(f"[bg-embed] {e}")
                finally:
                    _BG_EMBED_LOCK.release()
            _time.sleep(2 if n else 30)   # 有待嵌页→2s喘一下再嵌下一段;嵌完→30s轻巡
    threading.Thread(target=_loop, daemon=True).start()


# ★★后台分析驱动:承诺雷达(intel)+ 人脉图谱(entities)也自动跑(2026-08-29 用户真机发现:
#   客户端只有 bg-embed 自动,intel/entities 无后台驱动、打开页面(refresh=0)也只读缓存不生成→
#   右下角这两层永远 0%,killer 功能不会自动出,违背"第二大脑自动通读分析"承诺)。仿 bg-embed:
#   逐个未分析的微信会话 build_intel(LLM)/ extract_doc_entities(LLM),节流,只在配了 key 时跑。
_BG_ANALYZE_LOCK = threading.Lock()

@app.on_event("startup")
def _start_bg_analyzer():
    def _loop():
        _time.sleep(25)   # 让嵌入先起步(语义层优先)
        import chat_intel as _CI, entities as _EN, dockind as _DK
        while True:
            worked = False
            if _BG_ANALYZE_LOCK.acquire(blocking=False):
                try:
                    con = _con()
                    try:
                        cfg = LLM.load_cfg()
                        if cfg.get("llm_key"):   # intel/entities 都要 LLM,没 key 不跑
                            con.execute("CREATE TABLE IF NOT EXISTS analysis_processed(owner TEXT, layer TEXT, doc_id INTEGER, PRIMARY KEY(owner,layer,doc_id))")
                            for (owner,) in con.execute("SELECT DISTINCT owner FROM documents WHERE filename LIKE '微信_与%'").fetchall():
                                # doc_kind:群/对话判定 + 真实最后联系日期(纯正则无LLM,便宜;喂给人脉卡显示)
                                try:
                                    if _DK.ensure_doc_kind(con, owner):
                                        worked = True
                                except Exception as _e:
                                    print(f"[bg-analyze] dockind {owner}: {_e}")
                                # 承诺雷达 intel:每轮处理 ≤3 个未缓存微信会话
                                pend = con.execute(
                                    "SELECT d.id, d.filename FROM documents d WHERE d.owner=? AND d.filename LIKE '微信_与%' AND d.pages>=2 "
                                    "AND NOT EXISTS(SELECT 1 FROM chat_intel ci WHERE ci.username=d.owner AND ci.contact=REPLACE(REPLACE(d.filename,'微信_与',''),'.txt','')) LIMIT 3",
                                    (owner,)).fetchall()
                                for did, fn in pend:
                                    contact = fn.replace("微信_与", "").replace(".txt", "")
                                    text = "\n".join(p[0] for p in con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no", (did,)).fetchall())
                                    try:
                                        intel = _CI.build_intel(contact, text)
                                        if intel:
                                            con.execute("INSERT OR REPLACE INTO chat_intel(username,contact,doc_id,msgcount,day,data) VALUES(?,?,?,?,?,?)",
                                                        (owner, contact, did, text.count("\n"), _dt.date.today().isoformat(), json.dumps(intel, ensure_ascii=False)))
                                            con.commit(); worked = True
                                    except Exception as _e: print(f"[bg-analyze] intel {contact}: {_e}")
                                # 人脉图谱 entities:每轮处理 ≤3 个未抽实体的文档
                                pend2 = con.execute(
                                    "SELECT d.id FROM documents d WHERE d.owner=? "
                                    "AND NOT EXISTS(SELECT 1 FROM analysis_processed ap WHERE ap.owner=d.owner AND ap.layer='entities' AND ap.doc_id=d.id) LIMIT 3",
                                    (owner,)).fetchall()
                                for (did,) in pend2:
                                    text = "\n".join(p[0] for p in con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no", (did,)).fetchall())[:6000]
                                    try: _EN.extract_doc_entities(con, did, owner, text)
                                    except Exception as _e: print(f"[bg-analyze] entities {did}: {_e}")
                                    con.execute("INSERT OR IGNORE INTO analysis_processed(owner,layer,doc_id) VALUES(?,?,?)", (owner, "entities", did))
                                    con.commit(); worked = True
                                # ★人脉卡预热(对齐 106 cardwarm.py:106 靠该脚本自动预热了 504 张卡,客户端单机无脚本→
                                #   必须 bg 自驱,否则人脉页永远空。/api/relationships 默认 generate=False 只读缓存、
                                #   "缺的交给后台 warm"——这里就是那个 warm)。每轮 ≤2 张,LLM 节流护机器。
                                con.execute("CREATE TABLE IF NOT EXISTS card_hidden(username TEXT, contact TEXT, PRIMARY KEY(username,contact))")
                                pend3 = con.execute(
                                    "SELECT d.id, d.filename, d.pages FROM documents d WHERE d.owner=? AND d.filename LIKE '微信_与%' AND d.pages>=2 "
                                    "AND NOT EXISTS(SELECT 1 FROM relationship_cards rc WHERE rc.username=d.owner AND rc.contact=REPLACE(REPLACE(d.filename,'微信_与',''),'.txt','') AND rc.msgcount=d.pages) "
                                    "AND NOT EXISTS(SELECT 1 FROM card_hidden ch WHERE ch.username=d.owner AND ch.contact=REPLACE(REPLACE(d.filename,'微信_与',''),'.txt','')) "
                                    "ORDER BY d.pages DESC LIMIT 2", (owner,)).fetchall()
                                for _cdid, _cfn, _cpg in pend3:
                                    _contact = _cfn.replace("微信_与", "").replace(".txt", "")
                                    _ctext = "\n".join(p[0] for p in con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no LIMIT 40", (_cdid,)).fetchall())
                                    try:
                                        _card = REL.build_card(_contact, _ctext)
                                        if _card:
                                            con.execute("INSERT OR REPLACE INTO relationship_cards(username,contact,doc_id,day,msgcount,data) VALUES(?,?,?,?,?,?)",
                                                        (owner, _contact, _cdid, _dt.date.today().isoformat(), _cpg or 0, json.dumps(_card, ensure_ascii=False)))
                                            con.commit(); worked = True
                                    except Exception as _e:
                                        print(f"[bg-analyze] card {_contact}: {_e}")
                                # ★生成了新卡→失效 relationships 计算缓存,否则 /api/relationships(默认只读缓存,
                                #   sig 只认文档变化不认卡新增)会一直返回旧的空结果,warmer 生成的卡看不见。
                                if pend3:
                                    con.execute("DELETE FROM compute_cache WHERE owner=? AND name='relationships'", (owner,))
                                    con.commit()
                                # ★预热"仅聊天"主题星系缓存:首次点即秒出(不用等10-30s KMeans+jieba)。
                                #   仅当嵌入全完成(无待嵌页)才算——否则首启嵌入期签名一直变、反复重算拖垮8G。
                                try:
                                    # 只看"微信页"嵌完没(chat星系只用微信页嵌入)——不等其它大文档(PDF等)嵌完,
                                    #   否则库里有大PDF在补嵌入时预热永不跑、用户首次点仅聊天要现算30s。
                                    _pend_emb = con.execute(
                                        "SELECT COUNT(*) FROM pages p JOIN documents d ON d.id=p.doc_id "
                                        "LEFT JOIN page_embeddings e ON e.page_id=p.id "
                                        "WHERE d.filename LIKE '微信_与%' AND e.page_id IS NULL AND length(trim(p.text))>0").fetchone()[0]
                                    if _pend_emb == 0:
                                        _db_cached(con, owner, "chat_topic_galaxy", lambda: CT.chat_topic_galaxy(con, owner))
                                except Exception as _e:
                                    print(f"[bg-analyze] chat_galaxy warm: {_e}")
                    finally:
                        con.close()
                except Exception as e:
                    print(f"[bg-analyze] {e}")
                finally:
                    _BG_ANALYZE_LOCK.release()
            _time.sleep(15 if worked else 90)   # ★8G机护航:后台分析节流(有活15s/没活90s),给用户操作留资源,别把机器占死
    threading.Thread(target=_loop, daemon=True).start()


# ★★定期同步固定文件夹(autosync):106 上只有个"能勾但没用"的摆设(勾选只写 localStorage、
#   上传不带参、后端零监听)。桌面版真正做出来:Tauri 目录对话框拿到文件夹绝对路径 → 注册到
#   autosync_folders → 本线程定期轮询(mtime/size 变化=新增或改动)→ 走同一条 _run_ingest_job
#   入库管线(自动嵌入/抽实体/预热缓存全复用)。不引 watchdog(轻量、跨平台、打包无新依赖)。
def _autosync_tables(con):
    con.execute("CREATE TABLE IF NOT EXISTS autosync_folders(owner TEXT, path TEXT, added_at TEXT, last_scan TEXT, PRIMARY KEY(owner,path))")
    con.execute("CREATE TABLE IF NOT EXISTS autosync_seen(owner TEXT, path TEXT, mtime REAL, size INTEGER, PRIMARY KEY(owner,path))")

def _autosync_changed(con, owner, path):
    """文件是否新增/改动(与已入库快照比 mtime+size)。异常(文件消失等)当未变。"""
    try:
        stt = os.stat(path); mt, sz = stt.st_mtime, stt.st_size
    except OSError:
        return None
    row = con.execute("SELECT mtime,size FROM autosync_seen WHERE owner=? AND path=?", (owner, path)).fetchone()
    if row and abs((row[0] or 0) - mt) < 1 and (row[1] or -1) == sz:
        return None
    return (mt, sz)

def _autosync_scan_owner(con, owner, per_round=12):
    """扫该 owner 所有监听文件夹,把新增/改动文件(≤per_round/轮,护 8G 机)入库。返回本轮入库数。"""
    folders = con.execute("SELECT path FROM autosync_folders WHERE owner=?", (owner,)).fetchall()
    todo, stamp = [], {}
    for (folder,) in folders:
        if not os.path.isdir(folder):
            continue
        for f in I.find_docs(folder):
            ch = _autosync_changed(con, owner, f)
            if ch:
                todo.append(f); stamp[f] = ch
                if len(todo) >= per_round:
                    break
        con.execute("UPDATE autosync_folders SET last_scan=? WHERE owner=? AND path=?",
                    (_dt.datetime.now().isoformat(timespec="seconds"), owner, folder))
        if len(todo) >= per_round:
            break
    con.commit()
    if not todo:
        return 0
    # 走标准入库管线(与手动上传完全一致:嵌入/实体/缓存全复用),进度也能在入库页看到
    jid = _new_job(len(todo), "auto")
    try:
        _run_ingest_job(jid, todo, "auto", 200, owner)
    except Exception as _e:
        print(f"[autosync] ingest job 部分失败: {_e}")
    # ★逐文件记 seen(无论整批成败都记):否则某个大文件/坏文件让 _run_ingest_job 抛异常→整批不记seen→
    #   下次扫描又当"新文件"重复入库(已入库的攒重复页+坏文件无限重试,8G机被磨死、count永远卡住)。
    #   已进 documents 的记真 mtime/size(防重复);没进的也记(标记已尝试,不无限重试;用户可改动文件触发重试)。
    done_paths = set(r[0] for r in con.execute(
        "SELECT source_path FROM documents WHERE owner=?", (owner,)).fetchall()) if owner else set()
    ok = 0
    for f in todo:
        mt, sz = stamp[f]
        con.execute("INSERT OR REPLACE INTO autosync_seen(owner,path,mtime,size) VALUES(?,?,?,?)", (owner, f, mt, sz))
        if f in done_paths:
            ok += 1
    con.commit()
    return ok

_BG_SYNC_LOCK = threading.Lock()

@app.on_event("startup")
def _start_bg_autosync():
    def _loop():
        _time.sleep(15)
        while True:
            worked = 0
            if _BG_SYNC_LOCK.acquire(blocking=False):
                try:
                    con = _con()
                    try:
                        _autosync_tables(con)
                        for (owner,) in con.execute("SELECT DISTINCT owner FROM autosync_folders").fetchall():
                            try:
                                worked += _autosync_scan_owner(con, owner)
                            except Exception as _e:
                                print(f"[bg-autosync] {owner}: {_e}")
                    finally:
                        con.close()
                except Exception as e:
                    print(f"[bg-autosync] {e}")
                finally:
                    _BG_SYNC_LOCK.release()
            _time.sleep(5 if worked else 30)   # 有新文件→5s继续消化;没有→30s轻巡文件夹
    threading.Thread(target=_loop, daemon=True).start()


@app.get("/api/autosync/list")
def autosync_list(authorization: str = Header(None)):
    """当前用户监听中的文件夹 + 已同步文件数 + 上次扫描时间。"""
    owner = _me(authorization)
    con = _con()
    try:
        _autosync_tables(con)
        out = []
        for path, added_at, last_scan in con.execute(
                "SELECT path,added_at,last_scan FROM autosync_folders WHERE owner=? ORDER BY added_at DESC", (owner,)).fetchall():
            # seen 按文件绝对路径存(文件夹/文件.ext),count 要按前缀匹配文件夹下的文件,不是 path=文件夹
            cnt = con.execute("SELECT COUNT(*) FROM autosync_seen WHERE owner=? AND (path=? OR path LIKE ?)",
                              (owner, path, os.path.join(path, "") + "%")).fetchone()[0]
            out.append({"path": path, "added_at": added_at, "last_scan": last_scan,
                        "synced": cnt, "exists": os.path.isdir(path)})
        return {"folders": out}
    finally:
        con.close()


@app.post("/api/autosync/add")
def autosync_add(payload: dict = Body(...), authorization: str = Header(None)):
    """注册一个要定期同步的文件夹(绝对路径,来自 Tauri 目录对话框)。立即扫一遍现有内容入库。"""
    owner = _me(authorization)
    path = (payload.get("path") or "").strip()
    if not path or not os.path.isdir(path):
        raise HTTPException(400, "文件夹不存在或路径无效")
    path = os.path.abspath(path)
    con = _con()
    try:
        _autosync_tables(con)
        con.execute("INSERT OR IGNORE INTO autosync_folders(owner,path,added_at) VALUES(?,?,?)",
                    (owner, path, _dt.datetime.now().isoformat(timespec="seconds")))
        con.commit()
    finally:
        con.close()
    # ★首扫放后台线程:现有文件可能很多、且要嵌入(bge-m3 首次加载数分钟),绝不能阻塞 HTTP
    #   (否则前端 fetch 超时、用户以为卡死)。与 /api/upload 一样立即返回,进度靠 /api/autosync/list 轮询。
    #   用 _BG_SYNC_LOCK 与后台巡检线程串行,避免两边同时入库。
    def _initial_scan(owner=owner):
        with _BG_SYNC_LOCK:
            try:
                c2 = _con()
                try:
                    while _autosync_scan_owner(c2, owner) >= 12:   # 大文件夹分批扫完(每轮 per_round=12)
                        pass
                finally:
                    c2.close()
            except Exception as e:
                print(f"[autosync-add] {e}")
    threading.Thread(target=_initial_scan, daemon=True).start()
    return {"ok": True, "path": path, "scanning": True}


@app.post("/api/autosync/remove")
def autosync_remove(payload: dict = Body(...), authorization: str = Header(None)):
    """取消监听一个文件夹(已入库的文档保留,只是不再自动同步新文件)。"""
    owner = _me(authorization)
    path = os.path.abspath((payload.get("path") or "").strip())
    con = _con()
    try:
        _autosync_tables(con)
        con.execute("DELETE FROM autosync_folders WHERE owner=? AND path=?", (owner, path))
        # seen 按文件绝对路径存(文件夹/文件.ext),故按前缀清,否则残留导致重加后不再入库
        con.execute("DELETE FROM autosync_seen WHERE owner=? AND (path=? OR path LIKE ?)",
                    (owner, path, os.path.join(path, "") + "%"))
        con.commit()
        return {"ok": True}
    finally:
        con.close()


@app.get("/health")
def health():
    return {"status": "ok", "db": I.DEFAULT_DB, "vault": I.DEFAULT_VAULT,
            "backends": BACKENDS}


@app.get("/api/stats")
def stats(authorization: str = Header(None)):
    me = _me(authorization)
    con = _con()
    try:
        d = con.execute(
            "SELECT COUNT(*), COALESCE(SUM(pages),0) FROM documents WHERE owner=?", (me,)).fetchone()
        methods = {m: c for m, c in con.execute(
            "SELECT p.method, COUNT(*) FROM pages p JOIN documents d ON d.id=p.doc_id "
            "WHERE d.owner=? GROUP BY p.method ORDER BY 2 DESC", (me,))}
        return {"documents": d[0], "pages": d[1], "methods": methods}
    finally:
        con.close()


_FTYPE = {
    ".pdf": "PDF", ".epub": "电子书", ".mobi": "电子书", ".azw3": "电子书", ".azw": "电子书",
    ".fb2": "电子书", ".docx": "Word", ".pptx": "PPT", ".xlsx": "Excel", ".xlsm": "Excel",
    ".md": "笔记", ".markdown": "笔记", ".txt": "文本", ".html": "网页", ".htm": "网页",
    ".csv": "数据", ".json": "数据", ".eml": "邮件",
}


def _ftype(fn):
    return _FTYPE.get(os.path.splitext(fn)[1].lower(), "其它")


# P1-16:文库归类结果缓存 —— doc_topics 每次跑要加载全部向量+KMeans+命名(冷启127-197s)。
# 按 文档数:最大doc_id:嵌入数 签名;命中秒回;有旧缓存则立即返旧+后台重建;仅首次同步构建。
_LIBTOPICS_GEN = set()


def _lib_topics_sig(con):
    a = con.execute("SELECT COUNT(*), COALESCE(MAX(id),0) FROM documents").fetchone()
    b = con.execute("SELECT COUNT(*) FROM page_embeddings").fetchone()
    return "%d:%d:%d" % (a[0] or 0, a[1] or 0, b[0] or 0)


def _doc_topics_cached(con):
    con.execute("CREATE TABLE IF NOT EXISTS library_topics_cache (k TEXT PRIMARY KEY, sig TEXT, data TEXT, built_at TEXT)")
    sig = _lib_topics_sig(con)
    row = con.execute("SELECT sig, data FROM library_topics_cache WHERE k='global'").fetchone()
    if row and row[0] == sig:
        return {int(k): tuple(v) for k, v in json.loads(row[1]).items()}

    def _save(c, t):
        c.execute("INSERT OR REPLACE INTO library_topics_cache(k,sig,data,built_at) VALUES('global',?,?,?)",
                  (_lib_topics_sig(c), json.dumps({str(k): list(v) for k, v in t.items()}, ensure_ascii=False),
                   _dt.datetime.now().isoformat(timespec="seconds")))
        c.commit()

    if row:  # 有旧缓存 → 立即返旧,后台重建(不阻塞请求,避免网关超时)
        if "global" not in _LIBTOPICS_GEN:
            _LIBTOPICS_GEN.add("global")

            def _bg():
                c2 = _con()
                try:
                    _save(c2, S.doc_topics(c2))
                except Exception as e:
                    print("[library] topics rebuild fail:", e)
                finally:
                    _LIBTOPICS_GEN.discard("global"); c2.close()
            threading.Thread(target=_bg, daemon=True).start()
        return {int(k): tuple(v) for k, v in json.loads(row[1]).items()}

    # 无任何缓存 → 绝不同步构建!doc_topics 要读全部向量+KMeans(700+文档/万级向量),
    #   同步跑会堵死 worker→整个 sidecar 无响应(health 000,用户实测文库把 sidecar 卡崩)。
    #   改:先返空(全部"未分类",文库照常列出所有文档)+ 后台构建,下次加载就有分类。
    if "global" not in _LIBTOPICS_GEN:
        _LIBTOPICS_GEN.add("global")

        def _bg_first():
            c2 = _con()
            try:
                _save(c2, S.doc_topics(c2))
            except Exception as e:
                print("[library] topics first-build fail:", e)
            finally:
                _LIBTOPICS_GEN.discard("global"); c2.close()
        threading.Thread(target=_bg_first, daemon=True).start()
    return {}


@app.get("/api/library")
def library(authorization: str = Header(None)):
    me = _me(authorization)
    con = _con()
    try:
        rows = con.execute(
            "SELECT id, filename, pages, backend, ingested_at "
            "FROM documents WHERE owner=? ORDER BY ingested_at DESC", (me,)).fetchall()
        try:
            topics = _doc_topics_cached(con)
        except Exception:
            topics = {}
        docs, tcount, fcount = [], {}, {}
        for r in rows:
            tname = topics.get(r[0], (0, "未分类"))[1] if topics else "未分类"
            ft = _ftype(r[1])
            docs.append({"id": r[0], "filename": r[1], "pages": r[2], "backend": r[3],
                         "ingested_at": r[4], "topic": tname, "ftype": ft})
            tcount[tname] = tcount.get(tname, 0) + 1
            fcount[ft] = fcount.get(ft, 0) + 1
        return {
            "documents": docs,
            "topics": sorted([{"name": k, "count": v} for k, v in tcount.items()], key=lambda x: -x["count"]),
            "ftypes": sorted([{"name": k, "count": v} for k, v in fcount.items()], key=lambda x: -x["count"]),
        }
    finally:
        con.close()


@app.get("/api/doc/{doc_id}")
def doc(doc_id: int, offset: int = Query(0, ge=0), limit: int = Query(40, gt=0, le=200), authorization: str = Header(None)):
    me = _me(authorization)
    con = _con()
    try:
        d = con.execute(
            "SELECT id, source_path, filename, pages, backend, ingested_at "
            "FROM documents WHERE id=? AND owner=?", (doc_id, me)).fetchone()
        if not d:
            raise HTTPException(404, "没有这份文档")
        total = con.execute("SELECT COUNT(*) FROM pages WHERE doc_id=?", (doc_id,)).fetchone()[0]
        pages = con.execute(
            "SELECT page_no, method, text FROM pages WHERE doc_id=? ORDER BY page_no "
            "LIMIT ? OFFSET ?", (doc_id, limit, offset)).fetchall()
        return {
            "id": d[0], "source_path": d[1], "filename": d[2], "pages": d[3],
            "backend": d[4], "ingested_at": d[5], "total_pages": total, "offset": offset,
            "content": [{"page_no": p[0], "method": p[1], "text": S.clean_ocr(p[2])} for p in pages],
        }
    finally:
        con.close()


@app.get("/api/search")
def search(q: str = Query(..., min_length=1), limit: int = Query(30, gt=0, le=100), authorization: str = Header(None)):
    me = _me(authorization)
    con = _con()
    try:
        rows = con.execute(
            """SELECT d.id, d.filename, p.page_no,
                      snippet(pages_fts, 0, '「', '」', ' … ', 14) AS snip
               FROM pages_fts
               JOIN pages p ON p.id = pages_fts.rowid
               JOIN documents d ON d.id = p.doc_id
               WHERE pages_fts MATCH ? AND d.owner=?
               ORDER BY rank LIMIT ?""", (q, me, limit)).fetchall()
        if not rows:
            # FTS trigram 对 <3 字中文(如"债券")无命中 → LIKE 回退(体检 P2)
            like = "%" + q.replace("%", "").replace("_", "") + "%"
            rows = con.execute(
                """SELECT d.id, d.filename, p.page_no, substr(p.text, 1, 80)
                   FROM pages p JOIN documents d ON d.id = p.doc_id
                   WHERE p.text LIKE ? AND d.owner=? LIMIT ?""", (like, me, limit)).fetchall()
        return {"query": q, "hits": [
            {"doc_id": r[0], "filename": r[1], "page_no": r[2],
             "snippet": (r[3] or "").strip()} for r in rows]}
    except Exception as e:
        # FTS 语法错(用户输了特殊字符)时,退化成加引号的短语查询
        try:
            phrase = '"' + q.replace('"', '') + '"'
            rows = con.execute(
                """SELECT d.id, d.filename, p.page_no,
                          snippet(pages_fts, 0, '「', '」', ' … ', 14)
                   FROM pages_fts JOIN pages p ON p.id = pages_fts.rowid
                   JOIN documents d ON d.id = p.doc_id
                   WHERE pages_fts MATCH ? AND d.owner=? ORDER BY rank LIMIT ?""",
                (phrase, me, limit)).fetchall()
            return {"query": q, "hits": [
                {"doc_id": r[0], "filename": r[1], "page_no": r[2],
                 "snippet": r[3].strip()} for r in rows]}
        except Exception:
            raise HTTPException(400, f"检索失败: {e}")
    finally:
        con.close()


@app.get("/api/similar/{doc_id}")
def similar(doc_id: int, topk: int = 8, authorization: str = Header(None)):
    me = _me(authorization)
    con = _con()
    try:
        mine = _my_ids(con, me)
        if doc_id not in mine:
            raise HTTPException(404, "没有这份文档")
        sims = [s for s in S.similar_docs(con, doc_id, topk * 4, owner=me) if s["doc_id"] in mine][:topk]
        return {"doc_id": doc_id, "similar": sims}
    finally:
        con.close()


@app.get("/api/doc_summary/{doc_id}")
def doc_summary(doc_id: int, authorization: str = Header(None)):
    """这份文档到底讲什么:v4-pro 出 2-3 句摘要 + 核心主题,落库缓存。"""
    me = _me(authorization)
    if not (1 <= doc_id < 2**63):
        raise HTTPException(404, "没有这份文档")
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS doc_summaries (doc_id INTEGER PRIMARY KEY, summary TEXT, topics TEXT)")
        d = con.execute("SELECT filename, pages FROM documents WHERE id=? AND owner=?", (doc_id, me)).fetchone()
        if not d:
            raise HTTPException(404, "没有这份文档")
        cached = con.execute("SELECT summary, topics FROM doc_summaries WHERE doc_id=?", (doc_id,)).fetchone()
        if cached:
            return {"doc_id": doc_id, "filename": d[0], "pages": d[1],
                    "summary": cached[0], "topics": json.loads(cached[1] or "[]"), "cached": True}
        rows = con.execute("SELECT text FROM pages WHERE doc_id=? AND length(trim(text))>0 ORDER BY page_no LIMIT 6", (doc_id,)).fetchall()
        sample = "\n\n".join(S.clean_ocr(r[0] or "")[:1200] for r in rows)[:6000]
        if not sample.strip():
            return {"doc_id": doc_id, "filename": d[0], "pages": d[1], "summary": "(这份文档没有可读文本)", "topics": [], "cached": False}
        sysp = ("下面是文档《%s》的若干页内容。请用中文:①用2-3句话说清这份文档到底讲什么(具体、不空泛、不复述标题);"
                "②给出3-5个核心主题词。只输出JSON:{\"summary\":\"...\",\"topics\":[\"...\"]}" % d[0])
        try:
            out = LLM.chat([{"role": "system", "content": sysp}, {"role": "user", "content": sample}], temperature=0.3, max_tokens=700)
            m = re.search(r"\{.*\}", out, re.S)
            data = json.loads(m.group(0)) if m else {"summary": out[:300], "topics": []}
        except Exception as e:
            raise HTTPException(400, "摘要失败(检查设置里的模型/key): %s" % e)
        summ = (data.get("summary") or "")[:600]
        topics = [str(t) for t in (data.get("topics") or [])][:6]
        con.execute("INSERT OR REPLACE INTO doc_summaries(doc_id, summary, topics) VALUES(?,?,?)",
                    (doc_id, summ, json.dumps(topics, ensure_ascii=False)))
        con.commit()
        return {"doc_id": doc_id, "filename": d[0], "pages": d[1], "summary": summ, "topics": topics, "cached": False}
    finally:
        con.close()



def _ftype_of(fn):
    e = (fn or "").lower().rsplit(".", 1)[-1] if "." in (fn or "") else ""
    return {"pdf": "PDF", "epub": "电子书", "mobi": "电子书", "azw3": "电子书",
            "docx": "Word", "doc": "Word", "pptx": "PPT", "ppt": "PPT", "xlsx": "Excel", "xls": "Excel",
            "mp3": "录音", "wav": "录音", "m4a": "录音",
            "mp4": "视频", "mov": "视频", "mkv": "视频",
            "png": "图片", "jpg": "图片", "jpeg": "图片", "webp": "图片",
            "txt": "文本", "md": "笔记", "html": "网页", "csv": "表格"}.get(e, "其它")



def _news_provider(cfg):
    """选新闻搜索源:全球优先 serper(GoogleNews) > tavily > 博查(中文兜底)。返回(provider,key)。"""
    for prov in ("serper_key", "tavily_key", "bocha_key"):
        k = (cfg.get(prov) or "").strip()
        if k:
            return prov.replace("_key", ""), k
    return None, None


def _news_search(query, prov, key, count=8):
    """统一新闻搜索,近一周,返回 [{title,url,snippet,date,site}]。serper/tavily 覆盖全球。"""
    import urllib.request as _u
    op = _u.build_opener(_u.ProxyHandler({}))
    out = []
    if prov == "serper":  # Google News,全球最佳
        body = json.dumps({"q": query, "num": count, "tbs": "qdr:w"}).encode("utf-8")
        req = _u.Request("https://google.serper.dev/news", data=body,
                         headers={"X-API-KEY": key, "Content-Type": "application/json"}, method="POST")
        with op.open(req, timeout=25) as r:
            d = json.load(r)
        for w in (d.get("news") or [])[:count]:
            out.append({"title": w.get("title", ""), "url": w.get("link", ""),
                        "snippet": (w.get("snippet") or "")[:220], "date": w.get("date", ""),
                        "site": w.get("source", "")})
    elif prov == "tavily":  # 全球 AI 搜索
        body = json.dumps({"api_key": key, "query": query, "topic": "news", "days": 7,
                           "max_results": count, "search_depth": "basic"}).encode("utf-8")
        req = _u.Request("https://api.tavily.com/search", data=body,
                         headers={"Content-Type": "application/json"}, method="POST")
        with op.open(req, timeout=25) as r:
            d = json.load(r)
        for w in (d.get("results") or [])[:count]:
            out.append({"title": w.get("title", ""), "url": w.get("url", ""),
                        "snippet": (w.get("content") or "")[:220],
                        "date": w.get("published_date", ""), "site": ""})
    else:  # bocha 中文兜底
        body = json.dumps({"query": query, "freshness": "oneWeek", "summary": True, "count": count}).encode("utf-8")
        req = _u.Request("https://api.bochaai.com/v1/web-search", data=body,
                         headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
        with op.open(req, timeout=25) as r:
            d = json.load(r)
        for w in (((d.get("data") or {}).get("webPages") or {}).get("value") or []):
            out.append({"title": w.get("name", ""), "url": w.get("url", ""),
                        "snippet": (w.get("summary") or w.get("snippet") or "")[:220],
                        "date": w.get("datePublished", "") or w.get("dateLastCrawled", ""),
                        "site": w.get("siteName", "")})
    return out


def _clean_news_title(t):
    """洗掉新闻标题里的 SEO 垃圾:|关键词|关键词| 堆砌、结尾 _站名 后缀。"""
    import re as _re
    t = (t or "").strip()
    if not t:
        return ""
    t = t.split("|")[0].strip()                 # 去掉 |关键词|... 堆砌
    t = _re.sub(r"_[^_]{1,15}$", "", t).strip()  # 去掉结尾 _站名
    t = _re.sub(r"\s+", " ", t)
    return t


_WM_DIGEST_CACHE = {}  # variant -> (day, items)


def _wm_feed_digest(variant, lang="en"):
    """从 WM(香港服务器)拉 175 源全球新闻摘要。必须 HTTPS 443 直连(http/80 会被 WAF 拒)。按天缓存。"""
    import ssl as _ssl
    day = _dt.date.today().isoformat()
    c = _WM_DIGEST_CACHE.get(variant)
    if c and c[0] == day:
        return c[1]
    out = []
    try:
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        op = _urlreq.build_opener(_urlreq.ProxyHandler({}), _urlreq.HTTPSHandler(context=ctx))
        url = "https://43.103.54.237/api/news/v1/list-feed-digest?variant=%s&lang=%s" % (variant, lang)
        req = _urlreq.Request(url, headers={"Host": "api.worldmonitor.app"})
        d = json.load(op.open(req, timeout=20))
        for cat, cv in (d.get("categories") or {}).items():
            for it in (cv.get("items") or []):
                title = (it.get("title") or "").strip()
                link = (it.get("link") or "").strip()
                if not title or not link:
                    continue
                date = ""
                try:
                    ts = int(it.get("publishedAt") or 0) / 1000.0
                    if ts > 0:
                        date = _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S")
                except Exception:
                    pass
                out.append({"title": title, "url": link, "snippet": "",
                            "date": date, "site": it.get("source", ""), "cat": cat})
    except Exception:
        out = []
    _WM_DIGEST_CACHE[variant] = (day, out)
    return out


def _wm_cn_feed():
    """WM 中文爬虫新闻(央媒/财经等,cn-intel)。HTTPS 443 直连 + 内部密钥。按天缓存。"""
    import ssl as _ssl
    day = _dt.date.today().isoformat()
    c = _WM_DIGEST_CACHE.get("cn")
    if c and c[0] == day:
        return c[1]
    out = []
    try:
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        op = _urlreq.build_opener(_urlreq.ProxyHandler({}), _urlreq.HTTPSHandler(context=ctx))
        req = _urlreq.Request("https://43.103.54.237/api/cn/feed",
                              headers={"Host": "api.worldmonitor.app", "X-Internal-Key": "cn-intel-relay-2026"})
        d = json.load(op.open(req, timeout=20))
        for it in (d.get("items") or []):
            title = (it.get("title") or "").strip()
            url = (it.get("url") or "").strip()
            if not title or not url:
                continue
            out.append({"title": title, "url": url, "snippet": "",
                        "date": it.get("date", ""), "site": it.get("source", ""), "cat": it.get("category", "")})
    except Exception:
        out = []
    _WM_DIGEST_CACHE["cn"] = (day, out)
    return out


def _wm_news_search(query, count=40):
    """新闻池 = WM 中文爬虫(央媒/财经)+ 全球 finance/tech/world。交错混合保证中英文都有,相关性交给 LLM。"""
    import itertools
    cn = _wm_cn_feed()
    fin = _wm_feed_digest("finance")
    tech = _wm_feed_digest("tech")[:50]
    world = _wm_feed_digest("world")[:50]
    pool = []
    for group in itertools.zip_longest(cn, fin, tech, world):
        for x in group:
            if x:
                pool.append(x)
    return pool


@app.get("/api/news")
def daily_news(refresh: int = 0, authorization: str = Header(None)):
    """每日新闻:基于用户画像关注领域,搜近一周新闻,LLM 按其知识库挑最相关的。每日缓存。"""
    me = _me(authorization)
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS news_cache (username TEXT PRIMARY KEY, day TEXT, data TEXT)")
        day = _dt.date.today().isoformat()
        if not refresh:
            row = con.execute("SELECT day,data FROM news_cache WHERE username=?", (me,)).fetchone()
            if row and row[0] == day:
                return {"cached": True, **json.loads(row[1])}
        cfg = LLM.load_cfg()
        # 关注领域来自画像
        pdata, _ = _my_persona(con, me)
        domains = [d.get("name", "") for d in (pdata.get("domains") or [])][:4]
        one = pdata.get("one_liner", "")
        if not domains:  # 画像缓存没有→用文库top学科兜底,保证新用户也有新闻
            try:
                domains = [r[0] for r in con.execute(
                    "SELECT topic, COUNT(*) c FROM documents WHERE owner=? AND topic IS NOT NULL AND topic!='' AND topic!='未分类' GROUP BY topic ORDER BY c DESC LIMIT 4", (me,)).fetchall() if r[0]]
            except Exception:
                domains = []
        if not domains:
            return {"items": [], "hint": "多喂点资料给第二大脑,它算出你的关注领域后就能推每日新闻。"}
        # 拉 WM 全球新闻池,清洗标题 + 去重
        cands = []
        seen = set()
        for w in _wm_news_search("", 40):
            t = _clean_news_title(w.get("title", ""))
            if not t:
                continue
            w["title"] = t
            nk = re.sub(r"[\s\W]+", "", t.lower())[:32]  # 规范化去重键(跨源同题只留一条)
            if nk in seen:
                continue
            seen.add(nk)
            cands.append(w)
        if not cands:
            return {"items": [], "hint": "这几天你关注的领域没搜到新东西,明天再看看。"}
        # LLM 按用户知识库相关性筛选 + 中文标题 + "为什么和你相关"
        lst = "\n".join("%d. [%s] %s (%s)" % (i + 1, c.get("cat", ""), c["title"], c.get("site", ""))
                         for i, c in enumerate(cands[:40]))
        sysp = ("你是用户的第二大脑,从今天的全球新闻里挑出**和他最相关**的 10-12 条。"
                "他关注:%s。他是:%s。"
                "优先和他领域强相关、有信息量的;去重、去营销/标题党。"
                "候选是英文标题,请为每条给出**简洁准确的中文标题**。"
                "每条输出:idx(候选编号)、title_cn(中文标题)、why(一句话'为什么和你相关',点名他的领域,像朋友帮你留意)。"
                "只输出JSON:"
                '{"picks":[{"idx":1,"title_cn":"…","why":"和你关注的X相关,…"}]}') % ("、".join(domains), one or "(未知)")
        picks = []
        for _att in range(2):   # flash 带 thinking 会吃 token,给足 4000 + 解析失败重试一次(治 why/中文标题全空、掉回英文原池)
            try:
                out = LLM.chat([{"role": "system", "content": sysp}, {"role": "user", "content": lst}],
                               temperature=0.4, max_tokens=4000, model=LLM.fast_model())
                m = re.search(r"\{.*\}", out, re.S)
                picks = (json.loads(m.group(0)).get("picks") if m else []) or []
                if picks:
                    break
            except Exception:
                picks = []
        items = []
        for pk in picks:
            try:
                c = cands[int(pk.get("idx", 0)) - 1]
            except Exception:
                continue
            items.append({"title": (pk.get("title_cn") or c["title"]).strip(), "title_orig": c["title"],
                          "url": c["url"], "site": c.get("site", ""),
                          "date": c.get("date", ""), "why": (pk.get("why") or "")[:120]})
        if not items:  # LLM 挂了也别空,直接给前几条(原文标题)
            items = [{"title": c["title"], "title_orig": c["title"], "url": c["url"], "site": c.get("site", ""),
                      "date": c.get("date", ""), "why": ""} for c in cands[:12]]
        data = {"items": items[:12], "domains": domains}
        con.execute("INSERT OR REPLACE INTO news_cache(username,day,data) VALUES(?,?,?)", (me, day, json.dumps(data, ensure_ascii=False)))
        con.commit()
        return {"cached": False, **data}
    finally:
        con.close()




# ===== 通用计算结果缓存(DB级,重启不丢):签名=库内容,变了才重算 =====
def _docs_sig(con, owner):
    r = con.execute("SELECT COUNT(*), COALESCE(SUM(pages),0) FROM documents WHERE owner=?", (owner,)).fetchone()
    return "%s:%s" % (r[0], r[1])


def _db_cached(con, owner, name, builder):
    con.execute("CREATE TABLE IF NOT EXISTS compute_cache(owner TEXT, name TEXT, sig TEXT, data TEXT, PRIMARY KEY(owner,name))")
    sig = _docs_sig(con, owner)
    row = con.execute("SELECT sig, data FROM compute_cache WHERE owner=? AND name=?", (owner, name)).fetchone()
    if row and row[0] == sig:
        try:
            return json.loads(row[1])
        except Exception:
            pass
    v = builder()
    try:
        con.execute("INSERT OR REPLACE INTO compute_cache(owner,name,sig,data) VALUES(?,?,?,?)",
                    (owner, name, sig, json.dumps(v, ensure_ascii=False)))
        con.commit()
    except Exception:
        pass
    return v

@app.get("/api/relationships")
def relationships_api(refresh: int = 0, authorization: str = Header(None)):
    """关系情报卡:每个微信联系人一张AI活档案(身份/事实/未了结/人情/走势)。"""
    me = _me(authorization)
    con = _con()
    try:
        # 只读缓存,秒回;limit 放大到覆盖所有会话(否则只返回最大的40个,漏掉warm先出的小会话卡)
        if refresh:
            return {"cards": REL.all_cards(con, me, refresh=True, generate=True, limit=800)}
        return _db_cached(con, me, "relationships",
                          lambda: {"cards": REL.all_cards(con, me, refresh=False, generate=False, limit=800)})
    finally:
        con.close()


@app.post("/api/relationships/deepen")
def relationships_deepen(payload: dict = Body(...), authorization: str = Header(None)):
    """单张卡「深度分析」:用 pro 推理 + 长聊天 map-reduce 重算,质量更高(~1分钟)。"""
    me = _me(authorization)
    contact = str(payload.get("contact") or "").strip()
    if not contact:
        raise HTTPException(400, "缺少 contact")
    con = _con()
    try:
        fn = "微信_与" + contact + ".txt"
        row = con.execute("SELECT id, pages FROM documents WHERE owner=? AND filename=?", (me, fn)).fetchone()
        if not row:
            raise HTTPException(404, "没找到这个聊天")
        did, pcount = row[0], (row[1] or 0)
        pages = con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no", (did,)).fetchall()
        text = "\n".join(p[0] for p in pages)
        if len(text) > 16000:   # 控制单次时长:取首尾(承诺/近况多在近期)
            text = text[:4000] + "\n…(中间略)…\n" + text[-12000:]
        card = REL.build_card(contact, text, deep=True)
        if not card:
            raise HTTPException(500, "深度分析失败,请重试")
        con.execute("INSERT OR REPLACE INTO relationship_cards(username,contact,doc_id,day,msgcount,data) "
                    "VALUES(?,?,?,?,?,?)", (me, contact, did, _dt.date.today().isoformat(), pcount,
                                           json.dumps(card, ensure_ascii=False)))
        con.commit()
        lt, da = REL._last_time(con, did)
        return {"card": {"contact": contact, "doc_id": did, "last_time": lt, "days_ago": da,
                         "msgcount": pcount, "deep": True, **card}}
    finally:
        con.close()


@app.post("/api/relationships/delete")
def relationships_delete(payload: dict = Body(...), authorization: str = Header(None)):
    """删除一张关系卡(记入 card_hidden 防重新分析时又长出来)。
    默认★只删卡,聊天记录 documents/pages 一条不动。
    wipe_chat=True 时同步删除该联系人的微信聊天文档(documents/pages/embeddings,精确匹配 微信_与{contact}.txt)。"""
    me = _me(authorization)
    contact = str(payload.get("contact") or "").strip()
    wipe_chat = bool(payload.get("wipe_chat"))
    if not contact:
        raise HTTPException(400, "缺少 contact")
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS card_hidden(username TEXT, contact TEXT, PRIMARY KEY(username,contact))")
        con.execute("INSERT OR IGNORE INTO card_hidden(username,contact) VALUES(?,?)", (me, contact))
        con.execute("DELETE FROM relationship_cards WHERE username=? AND contact=?", (me, contact))
        wiped = 0
        if wipe_chat:
            # 精确匹配该联系人的微信聊天文档(不用 LIKE,防"王"误删"王昀")
            rows = con.execute("SELECT id FROM documents WHERE owner=? AND filename=?",
                               (me, "微信_与" + contact + ".txt")).fetchall()
            for (did,) in rows:
                con.execute("DELETE FROM page_embeddings WHERE page_id IN (SELECT id FROM pages WHERE doc_id=?)", (did,))
                con.execute("DELETE FROM pages WHERE doc_id=?", (did,))
                con.execute("DELETE FROM documents WHERE id=? AND owner=?", (did, me))
                wiped += 1
        con.commit()
        return {"ok": True, "wiped_chat_docs": wiped}
    finally:
        con.close()


@app.post("/api/loops/dismiss")
def loops_dismiss_api(payload: dict = Body(...), authorization: str = Header(None)):
    """删除一条「等你了结的事」——用户不打算做的待办可移除。★只标记忽略,聊天记录一条不动。"""
    me = _me(authorization)
    contact = str(payload.get("contact") or "").strip()
    text = str(payload.get("text") or "").strip()
    if not contact or not text:
        raise HTTPException(400, "缺少 contact/text")
    con = _con()
    try:
        return REL.dismiss_loop(con, me, contact, text)
    finally:
        con.close()


@app.post("/api/reach/dismiss")
def reach_dismiss_api(payload: dict = Body(...), authorization: str = Header(None)):
    """把某人从「该联系了」提醒里移除——不想联系的客户别老提醒。★只影响提醒,卡片/聊天都不动。"""
    me = _me(authorization)
    contact = str(payload.get("contact") or "").strip()
    if not contact:
        raise HTTPException(400, "缺少 contact")
    con = _con()
    try:
        return REL.dismiss_reach(con, me, contact)
    finally:
        con.close()


@app.get("/api/group_graph")
def group_graph_api(contact: str = "", refresh: int = 0, authorization: str = Header(None)):
    """群成员关系图:LLM 读群聊真实互动,抽成「成员 + 熟络度边」JSON,前端渲染关系网。按 doc 页数缓存。"""
    me = _me(authorization)
    contact = (contact or "").strip()
    if not contact:
        raise HTTPException(400, "缺少 contact")
    con = _con()
    try:
        row = con.execute("SELECT id, pages FROM documents WHERE owner=? AND filename=?",
                          (me, "微信_与" + contact + ".txt")).fetchone()
        if not row:
            row = con.execute("SELECT id, pages FROM documents WHERE owner=? AND filename LIKE ?",
                             (me, "微信_与" + contact + "%")).fetchone()
        if not row:
            return {"found": False, "members": [], "edges": []}
        did, pagecount = row[0], row[1] or 0
        con.execute("CREATE TABLE IF NOT EXISTS group_graph_cache(owner TEXT, doc_id INTEGER, pages INTEGER, data TEXT, PRIMARY KEY(owner,doc_id))")
        if not refresh:
            c = con.execute("SELECT pages, data FROM group_graph_cache WHERE owner=? AND doc_id=?", (me, did)).fetchone()
            if c and c[0] == pagecount:
                return {"found": True, "cached": True, **json.loads(c[1])}
        pages = con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no", (did,)).fetchall()
        full = "\n".join(p[0] for p in pages)
        sample = full if len(full) <= 9000 else (full[:3000] + "\n…(中间略)…\n" + full[-6000:])   # 提速:关系亲疏不需读全文,采样即可
        sysp = ("这是群聊「%s」的聊天记录。只**基于聊天里真实的互动**(谁常和谁一来一回、谁点名/回应谁、语气熟不熟、"
                "有没有私交流露)分析群成员之间的关系亲疏。绝不编造,没有互动依据的两人就别连边。只输出JSON:{"
                '"members":[{"name":"群里的原名","role":"在群里的身份/角色(一句,没有就空串)","is_me":false}],'
                '"edges":[{"a":"成员","b":"成员","closeness":"高|中|低","why":"依据:他们在聊天里怎么互动的(一句)"}]}'
                "。is_me 标记用户本人(在群里以「我」或本人名字发言的那个)。名字必须用聊天原名;最多取最活跃的约 15 人。") % contact
        try:
            out = LLM.chat([{"role": "system", "content": sysp}, {"role": "user", "content": sample}],
                           temperature=0.3, max_tokens=2600, model=LLM.fast_model())   # flash:关系亲疏不需重推理,收紧采样+tokens提速
            m = re.search(r"\{.*\}", out, re.S)
            data = json.loads(m.group(0)) if m else {"members": [], "edges": []}
        except Exception as e:
            raise HTTPException(400, "关系图生成失败(检查模型/key): %s" % e)
        data.setdefault("members", [])
        data.setdefault("edges", [])
        # LLM 不知道群里哪个名字是账号本人,后端按已知本人称呼补标 is_me(图里高亮"我")
        try:
            from graph_kg import _SELF as _SELFNAMES
        except Exception:
            _SELFNAMES = set()
        selfset = set(_SELFNAMES) | {"我", "(我)"}
        for mm in data.get("members", []):
            if mm.get("name") in selfset:
                mm["is_me"] = True
        dj = json.dumps(data, ensure_ascii=False)
        con.execute("INSERT OR REPLACE INTO group_graph_cache(owner,doc_id,pages,data) VALUES(?,?,?,?)", (me, did, pagecount, dj))
        con.commit()
        return {"found": True, "cached": False, **data}
    finally:
        con.close()


@app.get("/api/relation_timeline")
def relation_timeline_api(contact: str = "", refresh: int = 0, authorization: str = Header(None)):
    """我和某人的关系随时间变化:月度互动强度(真实时间戳,确定性)+ LLM 提炼的关键节点/走势。按 doc 缓存。"""
    me = _me(authorization)
    contact = (contact or "").strip()
    if not contact:
        raise HTTPException(400, "缺少 contact")
    con = _con()
    try:
        row = con.execute("SELECT id, pages FROM documents WHERE owner=? AND filename=?",
                          (me, "微信_与" + contact + ".txt")).fetchone()
        if not row:
            row = con.execute("SELECT id, pages FROM documents WHERE owner=? AND filename LIKE ?",
                             (me, "微信_与" + contact + "%")).fetchone()
        if not row:
            return {"found": False, "months": [], "milestones": []}
        did, pagecount = row[0], row[1] or 0
        con.execute("CREATE TABLE IF NOT EXISTS relation_timeline_cache(owner TEXT, doc_id INTEGER, pages INTEGER, data TEXT, PRIMARY KEY(owner,doc_id))")
        if not refresh:
            c = con.execute("SELECT pages, data FROM relation_timeline_cache WHERE owner=? AND doc_id=?", (me, did)).fetchone()
            if c and c[0] == pagecount:
                return {"found": True, "cached": True, **json.loads(c[1])}
        pages = con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no", (did,)).fetchall()
        # 月度互动强度(确定性:数真实时间戳,分我发/对方发)
        try:
            from graph_kg import _SELF as _SELFNAMES
        except Exception:
            _SELFNAMES = set()
        selfset = set(_SELFNAMES) | {"我", "(我)"}
        LINE = re.compile(r'^\[(\d{4})-(\d{2})-\d{2}[ T][\d:]{4,8}\]\s*([^:：\n]{1,28}?)[:：]')
        mtot, mmine = {}, {}
        for (t,) in pages:
            for line in (t or "").split("\n"):
                m = LINE.match(line)
                if not m:
                    continue
                ym = m.group(1) + "-" + m.group(2)
                mtot[ym] = mtot.get(ym, 0) + 1
                if m.group(3).strip() in selfset:
                    mmine[ym] = mmine.get(ym, 0) + 1
        months = [{"ym": ym, "count": mtot[ym], "mine": mmine.get(ym, 0), "theirs": mtot[ym] - mmine.get(ym, 0)}
                  for ym in sorted(mtot.keys())]
        full = "\n".join(p[0] for p in pages)
        sample = full if len(full) <= 14000 else (full[:3000] + "\n…(中间略)…\n" + full[-11000:])
        sysp = ("这是我和「%s」的一对一微信聊天记录。只**基于真实聊天**提炼这段关系的发展脉络,不编造。只输出JSON:{"
                '"trajectory":"一句话概括关系怎么一路变过来的(从认识到现在)",'
                '"phase":"现在所处阶段(如 新识/升温/热络/合作中/平淡/冷却,二到四字)",'
                '"milestones":[{"date":"YYYY-MM 或 YYYY-MM-DD","label":"关键节点一句(第一次合作/一起做了某事/帮了大忙/闹过不快 等)"}]}'
                "。里程碑取 3-6 个真实且重要的,按时间先后;日期必须用聊天里真实出现过的。") % contact
        try:
            out = LLM.chat([{"role": "system", "content": sysp}, {"role": "user", "content": sample}],
                           temperature=0.3, max_tokens=1800, model=LLM.fast_model())
            m = re.search(r"\{.*\}", out, re.S)
            info = json.loads(m.group(0)) if m else {}
        except Exception:
            info = {}
        data = {"months": months, "trajectory": info.get("trajectory", ""),
                "phase": info.get("phase", ""), "milestones": info.get("milestones", []) or [],
                "msg_count": sum(mtot.values()), "doc_id": did}
        dj = json.dumps(data, ensure_ascii=False)
        con.execute("INSERT OR REPLACE INTO relation_timeline_cache(owner,doc_id,pages,data) VALUES(?,?,?,?)", (me, did, pagecount, dj))
        con.commit()
        return {"found": True, "cached": False, **data}
    finally:
        con.close()


@app.post("/api/report")
def report_api(payload: dict = Body(...), authorization: str = Header(None)):
    """按需总结 / 输出文档:总结(flash秒回) / 营销复盘 / 周报 / 会议纪要(pro)。可选时间段。"""
    import reports as RPT
    me = _me(authorization)
    contact = str(payload.get("contact") or "").strip()
    mode = str(payload.get("mode") or "summary")
    since = str(payload.get("since") or "")
    until = str(payload.get("until") or "")
    if not contact:
        raise HTTPException(400, "缺少 contact")
    con = _con()
    try:
        fn = "微信_与" + contact + ".txt"
        row = con.execute("SELECT id FROM documents WHERE owner=? AND filename=?", (me, fn)).fetchone()
        if not row:
            raise HTTPException(404, "没找到这个聊天")
        pages = con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no", (row[0],)).fetchall()
        text = "\n".join(p[0] for p in pages)
        return RPT.build_report(contact, text, mode, since, until)
    finally:
        con.close()


_PORTRAIT_GEN = set()   # 正在后台重建画像的 owner(防并发重复重建)


@app.get("/api/network_portrait")
def network_portrait(refresh: int = 0, authorization: str = Header(None)):
    """人脉画像:我的联系人整体在什么行业/机构、和我什么交集(实体聚合 + 卡片身份 + AI叙述)。按天缓存。"""
    me = _me(authorization)
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS portrait_cache(owner TEXT PRIMARY KEY, day TEXT, data TEXT)")
        today = _dt.date.today().isoformat()
        if not refresh:
            cur = con.execute("SELECT day, data FROM portrait_cache WHERE owner=?", (me,)).fetchone()
            if cur and cur[0] == today:
                return json.loads(cur[1])
            # 今天没缓存但有旧的 → 立即返旧画像,后台重建今天的(叙述走 LLM 可能等 180s,绝不让前端干等/转圈)
            if cur:
                if me not in _PORTRAIT_GEN:
                    _PORTRAIT_GEN.add(me)

                    def _bg_portrait(_auth=authorization, _me2=me):
                        try:
                            network_portrait(refresh=1, authorization=_auth)
                        except Exception as _e:
                            print("[portrait] bg rebuild fail:", _e)
                        finally:
                            _PORTRAIT_GEN.discard(_me2)
                    threading.Thread(target=_bg_portrait, daemon=True).start()
                return json.loads(cur[1])
        # ★联系人数=全部 1对1 会话(通用:doc_kind 识别群,任何账号都对;不再用 pages>=2 漏掉短会话/混入群)
        ncontacts = con.execute(
            "SELECT COUNT(*) FROM documents d LEFT JOIN doc_kind k ON k.owner=d.owner AND k.doc_id=d.id "
            "WHERE d.owner=? AND d.filename LIKE '微信_与%' AND COALESCE(k.is_group,0)=0 "
            "AND d.filename NOT LIKE '%@chatroom%' AND d.filename NOT LIKE '%@openim%'",
            (me,)).fetchone()[0]
        # 高频实体(按覆盖多少个联系人=doc)
        # ★人脉画像只算 1对1 联系人:群/裸@chatroom 不当"人"(P0-4)
        _grp = set()
        try:
            for fn, in con.execute(
                "SELECT d.filename FROM documents d LEFT JOIN doc_kind k ON k.owner=d.owner AND k.doc_id=d.id "
                "WHERE d.owner=? AND d.filename LIKE '微信_与%' "
                "AND (COALESCE(k.is_group,0)=1 OR d.filename LIKE '%@chatroom%' OR d.filename LIKE '%@openim%')",
                (me,)).fetchall():
                _grp.add(fn.replace("微信_与", "").replace(".txt", ""))
        except Exception:
            pass
        _isperson = lambda c: c and c not in _grp and not re.match(r'^\d+@(chatroom|openim)', c or '')
        rows = con.execute(
            "SELECT e.etype, e.name, COUNT(DISTINCT e.doc_id) AS ppl "
            "FROM kb_entities e JOIN documents d ON d.id=e.doc_id "
            "LEFT JOIN doc_kind k ON k.owner=e.owner AND k.doc_id=e.doc_id "
            "WHERE e.owner=? AND d.filename LIKE '微信_与%' AND COALESCE(k.is_group,0)=0 "
            "GROUP BY e.norm ORDER BY ppl DESC, e.name", (me,)).fetchall()
        by_type = {}
        for et, nm, ppl in rows:
            by_type.setdefault(et or "其他", []).append({"name": nm, "people": ppl})
        # 卡片(名字+身份+doc):用于按领域分组的联系人墙 + 点击跳转(排除群/裸@chatroom)
        cardrows = con.execute(
            "SELECT contact, doc_id, json_extract(data,'$.identity') FROM relationship_cards WHERE username=?",
            (me,)).fetchall()
        idx = {c: d for c, d, _i in cardrows if c and _isperson(c)}
        idents = [(c, (i or "")) for c, d, i in cardrows if (i or "").strip() and _isperson(c)]
        narrative, groups = "", []
        if idents or rows:
            try:
                top = {k: v[:15] for k, v in by_type.items()}
                material = ("联系人(名字: 身份, 共%d人):\n" % len(idents)) + \
                    "\n".join("- %s: %s" % (c, i[:70]) for c, i in idents[:50])
                if top:
                    material += "\n\n高频实体(按覆盖联系人数):\n" + json.dumps(top, ensure_ascii=False)
                sysp = ("你是用户的第二大脑。基于下面用户微信联系人的名字+身份+高频实体做人脉画像。"
                        "把联系人按**领域/行业**分组(如 金融同业 / 园区政务 / 生活社交 等,分组数 4-8 个),members 用联系人原名。"
                        "只输出 JSON,不要多余文字:\n"
                        '{"narrative":"一段Markdown画像,含 ## 行业分布 ## 核心机构 ## 大家和你的交集 ## 特点,第二人称你,约260字",'
                        '"groups":[{"name":"领域名","members":["联系人名","..."]}]}')
                out = LLM.chat([{"role": "system", "content": sysp},
                                {"role": "user", "content": material}],
                               temperature=0.3, max_tokens=2800, model=LLM.fast_model())
                mjson = re.search(r"\{.*\}", out or "", re.S)
                if mjson:
                    try:
                        pj = json.loads(re.sub(r",\s*([}\]])", r"\1", mjson.group(0)))
                        narrative = (pj.get("narrative") or "").strip()
                        groups = [g for g in (pj.get("groups") or []) if g.get("name") and g.get("members")]
                    except Exception:
                        narrative = (out or "").strip()
                else:
                    narrative = (out or "").strip()
            except Exception:
                narrative = ""
        for g in groups:   # 给分组成员挂 doc_id(能点开聊天)
            g["members"] = [{"name": nm, "doc_id": idx.get(nm)} for nm in g["members"]][:40]
        result = {"contacts": ncontacts, "with_cards": len(idx), "entity_ready": bool(rows),
                  "by_type": by_type, "narrative": narrative, "groups": groups}
        if narrative or groups:   # 空结果(多半API被回填占满)不覆盖缓存,保住上次的好画像
            try:
                con.execute("INSERT OR REPLACE INTO portrait_cache(owner,day,data) VALUES(?,?,?)",
                            (me, today, json.dumps(result, ensure_ascii=False)))
                con.commit()
            except Exception:
                pass
        return result
    finally:
        con.close()


@app.get("/api/analysis_status")
def analysis_status(authorization: str = Header(None)):
    """第二大脑对聊天的加工进度:嵌入/关系卡/雷达/人脉图谱各层完成度。给前端进度提示。"""
    me = _me(authorization)
    con = _con()
    try:
        wpages = con.execute("SELECT COUNT(*) FROM pages p JOIN documents d ON d.id=p.doc_id "
                             "WHERE d.owner=? AND d.backend='wechat'", (me,)).fetchone()[0] or 0
        emb = con.execute("SELECT COUNT(*) FROM page_embeddings pe JOIN pages p ON p.id=pe.page_id "
                          "JOIN documents d ON d.id=p.doc_id WHERE d.owner=? AND d.backend='wechat'", (me,)).fetchone()[0] or 0
        docs2 = con.execute("SELECT COUNT(*) FROM documents WHERE owner=? AND filename LIKE '微信_与%' AND pages>=2", (me,)).fetchone()[0] or 0
        docs3 = con.execute("SELECT COUNT(*) FROM documents WHERE owner=? AND filename LIKE '微信_与%' AND pages>=3", (me,)).fetchone()[0] or 0
        try:
            intel = con.execute("SELECT COUNT(*) FROM chat_intel WHERE username=?", (me,)).fetchone()[0]
        except Exception:
            intel = 0
        try:
            entdocs = con.execute("SELECT COUNT(DISTINCT e.doc_id) FROM kb_entities e JOIN documents d ON d.id=e.doc_id "
                                  "WHERE e.owner=? AND d.backend='wechat'", (me,)).fetchone()[0]
        except Exception:
            entdocs = 0
        # ★用"已处理"标记算完成度(占位符空群本就无实体/无承诺,不能算没完成)
        con.execute("CREATE TABLE IF NOT EXISTS analysis_processed(owner TEXT, layer TEXT, doc_id INTEGER, PRIMARY KEY(owner,layer,doc_id))")

        def _proc(layer):
            return con.execute("SELECT COUNT(*) FROM analysis_processed WHERE owner=? AND layer=?", (me, layer)).fetchone()[0]
        intel_done = max(intel, _proc("intel"))
        ent_done = max(entdocs, _proc("entities"))
        layers = [
            {"key": "embed", "label": "语义问答", "hint": "让聊天能被语义搜索/提问", "done": min(emb, wpages), "total": max(wpages, 1)},
            {"key": "intel", "label": "承诺雷达", "hint": "抽承诺/数字/供需", "done": min(intel_done, docs3), "total": max(docs3, 1)},
            {"key": "entities", "label": "人脉图谱", "hint": "抽机构/项目建关系网", "done": min(ent_done, docs2), "total": max(docs2, 1)},
        ]
        for l in layers:
            l["pct"] = int(l["done"] / l["total"] * 100)
        overall = int(sum(l["pct"] for l in layers) / len(layers))
        return {"layers": layers, "overall_pct": overall, "done": all(l["pct"] >= 100 for l in layers)}
    finally:
        con.close()


_WXMSG_RE = re.compile(r'^\[(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(?::\d{2})?\]\s*([^:：]{1,24}?)[:：]\s*(.*)$')


@app.get("/api/wechat_messages")
def wechat_messages(contact: str, offset: int = 0, limit: int = 300, authorization: str = Header(None)):
    """微信聊天消息(按时间**倒序**分页:最近在前)。治页存储顺序不统一——服务端统一按时间戳排。
    天内保持正序(便于阅读),天与天之间新→旧。"""
    me = _me(authorization)
    con = _con()
    try:
        fn = "微信_与" + contact + ".txt"
        row = con.execute("SELECT id FROM documents WHERE owner=? AND filename=?", (me, fn)).fetchone()
        if not row:
            raise HTTPException(404, "没找到这个聊天")
        pages = con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no", (row[0],)).fetchall()
        msgs, cur = [], None
        for (t,) in pages:
            for line in (t or "").split("\n"):
                m = _WXMSG_RE.match(line.rstrip("\r"))
                if m:
                    if cur:
                        msgs.append(cur)
                    cur = {"day": m.group(1), "time": m.group(2), "sender": m.group(3).strip(),
                           "isMe": m.group(3).strip() == "我", "content": m.group(4)}
                elif cur and line.strip():
                    cur["content"] += "\n" + line
        if cur:
            msgs.append(cur)
        # 天倒序、天内正序:先按 time 正序,再按 day 倒序(稳定排序)
        msgs.sort(key=lambda x: x["time"])
        msgs.sort(key=lambda x: x["day"], reverse=True)
        total = len(msgs)
        return {"contact": contact, "total": total, "offset": offset,
                "messages": msgs[offset:offset + limit]}
    finally:
        con.close()


@app.get("/api/entity_links")
def entity_links_api(authorization: str = Header(None)):
    """实体级跨时间链接:同一个人/公司/项目/合同,散落在你哪些资料里。
    过滤噪音:地点类(上海/深圳…信息量低)和用户本人(自己出现在自己的聊天里不是发现)。"""
    me = _me(authorization)
    con = _con()
    try:
        links = ENT.entity_links(con, me, 24)
        try:
            import owner_ctx as _oc
            _on = _oc.resolve_owner_name(con, me) or ""
        except Exception:
            _on = ""

        def _noise(l):
            e = (l.get("entity") or "").strip()
            if l.get("etype") == "地点":
                return True
            if not e:
                return True
            try:
                import owner_ctx as _oc2
                if _oc2.is_owner(e):
                    return True
            except Exception:
                pass
            if _on and len(e) >= 2 and (e in _on or _on in e):
                return True
            return False

        links = [l for l in links if not _noise(l)][:12]

        def _ek(it):
            return "ent:" + (it.get("entity") or "")

        def _ep(it):
            ctxs = []
            for d in (it.get("docs") or [])[:3]:
                ctxs.append("《%s》:%s" % (d.get("filename", ""), _doc_snip(con, d.get("id"), 450)))
            return ("关键词「%s」出现在用户的 %s 份资料里,部分摘录:\n%s\n\n输出JSON "
                    "{\"why\":\"它在这些资料里的具体角色/上下文是什么,不超过50字\","
                    "\"get\":\"这些散落信息连起来,用户能得到什么,不超过40字\","
                    "\"do\":\"建议做的一件具体的事,不超过30字\"}") % (it.get("entity"), it.get("count"), "\n".join(ctxs))

        _attach_explains(con, me, links, _ek, _ep)
        return {"links": links}
    finally:
        con.close()


@app.get("/api/rel_graph")
def rel_graph_api(authorization: str = Header(None)):
    """人脉关系网:联系人↔联系人(共享实体连边)+ 人脉枢纽 + 关联why。"""
    me = _me(authorization)
    con = _con()
    try:
        import graph_kg as GK
        return _db_cached(con, me, "rel_graph", lambda: GK.rel_graph(con, me))
    except Exception as e:
        return {"nodes": [], "edges": [], "hubs": [], "contact_count": 0, "edge_count": 0, "error": str(e)}
    finally:
        con.close()


@app.get("/api/chat_galaxy")
def chat_galaxy_api(authorization: str = Header(None)):
    """探索·仅聊天:全部 1:1 联系人按聊天内容相似度连成语义星系(用现成向量,覆盖全部联系人)。"""
    me = _me(authorization)
    con = _con()
    try:
        import graph_kg as GK
        return _db_cached(con, me, "chat_galaxy", lambda: GK.chat_galaxy(con, me))
    except Exception as e:
        return {"nodes": [], "edges": [], "communities": [], "error": str(e)}
    finally:
        con.close()


def _cache_peek(con, owner, name):
    """只查不算:命中且签名匹配返回缓存,否则 None。用于异步端点先探缓存。"""
    try:
        con.execute("CREATE TABLE IF NOT EXISTS compute_cache(owner TEXT, name TEXT, sig TEXT, data TEXT, PRIMARY KEY(owner,name))")
        sig = _docs_sig(con, owner)
        row = con.execute("SELECT sig, data FROM compute_cache WHERE owner=? AND name=?", (owner, name)).fetchone()
        if row and row[0] == sig:
            return json.loads(row[1])
    except Exception:
        pass
    return None


@app.get("/api/chat_topic_galaxy")
def chat_topic_galaxy_api(authorization: str = Header(None)):
    """探索·仅聊天(A):全部聊天内容按语义聚成主题星系(每段聊天一颗星,簇=真实主题名)。
    异步:命中缓存立即返回;首次未缓存则后台聚类 + 返回 {pending:True},前端轮询(避免 WKWebView 60s 超时把首次点击打成空)。"""
    me = _me(authorization)
    con = _con()
    try:
        import chat_topics as CT
        cached = _cache_peek(con, me, "chat_topic_galaxy")
        if cached is not None:
            return cached
        key = "chatgalaxy:" + me
        j = _GEN_JOBS.get(key)
        if j and j.get("state") == "done":
            return j["result"]
        if not j or j.get("state") != "running":
            _GEN_JOBS[key] = {"state": "running"}
            def _work():
                try:
                    c2 = _con()
                    try:
                        r = _db_cached(c2, me, "chat_topic_galaxy", lambda: CT.chat_topic_galaxy(c2, me))
                    finally:
                        c2.close()
                    _GEN_JOBS[key] = {"state": "done", "result": r}
                except Exception as e:
                    import traceback
                    _GEN_JOBS[key] = {"state": "error", "error": str(e), "tb": traceback.format_exc()[-500:]}
            threading.Thread(target=_work, daemon=True).start()
        return {"pending": True, "nodes": [], "edges": [], "communities": []}
    except Exception as e:
        import traceback
        return {"nodes": [], "edges": [], "communities": [], "error": str(e), "tb": traceback.format_exc()[-500:]}
    finally:
        con.close()


@app.get("/api/rel_path")
def rel_path_api(a: str = "", b: str = "", authorization: str = Header(None)):
    """关系路径:A 通过谁认识 C(最短路 + 每跳共享实体)。"""
    me = _me(authorization)
    con = _con()
    try:
        import graph_kg as GK
        return GK.path_between(con, me, a, b)
    except Exception as e:
        return {"path": [], "why": [], "found": False, "error": str(e)}
    finally:
        con.close()


@app.get("/api/commitments")
def commitments_api(refresh: int = 0, authorization: str = Header(None)):
    """承诺雷达:跨人聚合未了结承诺(我欠的/等对方的),按到期排序。"""
    me = _me(authorization)
    con = _con()
    try:
        return CI.commitments_radar(con, me, refresh=bool(refresh))
    finally:
        con.close()


@app.post("/api/commitments/dismiss")
def commitments_dismiss_api(key: str = Body("", embed=True), authorization: str = Header(None)):
    """清除某条承诺(已了结/不再跟进)——只标记忽略,绝不删聊天记录。"""
    me = _me(authorization)
    if not key:
        return {"ok": False, "error": "缺少 key"}
    con = _con()
    try:
        return CI.dismiss_commitment(con, me, key)
    finally:
        con.close()


@app.get("/api/number_ledger")
def number_ledger_api(refresh: int = 0, authorization: str = Header(None)):
    """数字台账:每个联系人的报价/额度/期限等结构化数字。"""
    me = _me(authorization)
    con = _con()
    try:
        return CI.number_ledger(con, me, refresh=bool(refresh))
    finally:
        con.close()


@app.get("/api/matches")
def matches_api(refresh: int = 0, authorization: str = Header(None)):
    """供需撮合雷达:供给×需求跨人配对成可牵线机会。
    异步:冷缓存时配对要嵌入数百条信号+LLM(8G 上 >60s),同步会被 WKWebView 超时掐→前端落空 0×0。
    改:先秒返 base(供需计数,让 UI 有数),配对结果后台算+前端轮询。命中 matches 缓存则直接返回。"""
    me = _me(authorization)
    con = _con()
    try:
        base = CI.supply_demand_base(con, me)
        # 强制刷新(用户主动点,可等)或 无供需可配 → 直接同步返回(后者秒返空,不必开后台)
        if refresh or not (base["supply_count"] and base["demand_count"]):
            return CI.supply_demand_matches(con, me, refresh=bool(refresh))
        key = "matches:" + me
        j = _GEN_JOBS.get(key)
        if j and j.get("state") == "done":
            return j["result"]
        if not j or j.get("state") != "running":
            _GEN_JOBS[key] = {"state": "running"}
            def _work():
                try:
                    c2 = _con()
                    try:
                        r = CI.supply_demand_matches(c2, me, refresh=False)
                    finally:
                        c2.close()
                    _GEN_JOBS[key] = {"state": "done", "result": r}
                except Exception as e:
                    _GEN_JOBS[key] = {"state": "error", "error": str(e)}
            threading.Thread(target=_work, daemon=True).start()
        return {"pending": True, **base}   # 带 base:UI 显示"从 N 供给 × M 需求"+计算中,不再空 0×0
    finally:
        con.close()


@app.get("/api/briefing")
def briefing_api(contact: str = "", authorization: str = Header(None)):
    """见面前简报:未了结/雷区/暖场话题/关键数字/履约信用画像。"""
    me = _me(authorization)
    con = _con()
    try:
        return CI.briefing(con, me, contact)
    finally:
        con.close()


@app.get("/api/chat_node/{doc_id}")
def chat_node_api(doc_id: int, authorization: str = Header(None)):
    """仅聊天节点弹框:直接给这位联系人的高质量关系卡(身份/关键事实/未了结/人情/近况)+ 情报(承诺/数字/雷区/暖场)。全走缓存,秒回。"""
    me = _me(authorization)
    con = _con()
    try:
        d = con.execute("SELECT filename FROM documents WHERE id=? AND owner=?", (doc_id, me)).fetchone()
        if not d:
            raise HTTPException(404, "没有这份文档")
        fn = d[0] or ""
        if not fn.startswith("微信_与"):
            return {"is_chat": False}
        contact = fn.replace("微信_与", "").replace(".txt", "")
        out = {"is_chat": True, "contact": contact, "doc_id": doc_id, "card": None, "intel": None, "tags": [], "last_date": None}
        row = con.execute("SELECT data FROM relationship_cards WHERE username=? AND contact=?", (me, contact)).fetchone()
        if row:
            try:
                out["card"] = json.loads(row[0])
            except Exception:
                pass
        irow = con.execute("SELECT data FROM chat_intel WHERE username=? AND contact=?", (me, contact)).fetchone()
        if irow:
            try:
                it = json.loads(irow[0])
                out["intel"] = {
                    "commitments": [c for c in it.get("commitments", []) if not c.get("done")][:6],
                    "numbers": it.get("numbers", [])[:6],
                    "landmines": it.get("landmines", [])[:6],
                    "warm_topics": it.get("warm_topics", [])[:6],
                }
            except Exception:
                pass
        try:
            out["tags"] = [r[0] for r in con.execute(
                "SELECT name FROM kb_entities WHERE doc_id=? AND owner=? AND etype IN ('公司','机构','项目','产品','地点') "
                "ORDER BY mentions DESC LIMIT 6", (doc_id, me)).fetchall()]
        except Exception:
            pass
        try:
            k = con.execute("SELECT last_date FROM doc_kind WHERE owner=? AND doc_id=?", (me, doc_id)).fetchone()
            out["last_date"] = (k[0] if k else None)
        except Exception:
            pass
        return out
    finally:
        con.close()


# ==== 实时同步 / 入库进度(桌面客户端上报,网页显示进度条+实时徽章+开关)====
def _ensure_sync_tables(con):
    con.executescript(
        "CREATE TABLE IF NOT EXISTS ingest_progress("
        " owner TEXT, job_id TEXT, contact TEXT, state TEXT, percent INTEGER,"
        " message TEXT, ts REAL, PRIMARY KEY(owner, job_id, contact));"
        "CREATE TABLE IF NOT EXISTS realtime_state("
        " owner TEXT PRIMARY KEY, enabled INTEGER DEFAULT 0, running INTEGER DEFAULT 0,"
        " pending INTEGER DEFAULT 0, last_synced TEXT, last_beat_ts REAL, note TEXT);")


@app.post("/api/ingest/status")
def ingest_status_post(payload: dict = Body(...), authorization: str = Header(None)):
    """桌面客户端上报某个聊天的入库进度(owner 从 token 取,不信 body)。"""
    me = _me(authorization)
    con = _con()
    try:
        _ensure_sync_tables(con)
        con.execute("INSERT OR REPLACE INTO ingest_progress(owner,job_id,contact,state,percent,message,ts) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (me, str(payload.get("job_id", "")), str(payload.get("contact", "")),
                     str(payload.get("state", "")), int(payload.get("percent") or 0),
                     str(payload.get("message", "")), _time.time()))
        con.commit()
        return {"ok": True}
    finally:
        con.close()


@app.get("/api/ingest/progress")
def ingest_progress_get(authorization: str = Header(None)):
    """网页轮询:最近的入库进度(带状态机),用于进度条。"""
    me = _me(authorization)
    con = _con()
    try:
        _ensure_sync_tables(con)
        cutoff = _time.time() - 1800
        rows = con.execute("SELECT job_id,contact,state,percent,message,ts FROM ingest_progress "
                           "WHERE owner=? AND ts>? ORDER BY ts DESC LIMIT 60", (me, cutoff)).fetchall()
        items = [{"job_id": r[0], "contact": r[1], "state": r[2], "percent": r[3], "message": r[4], "ts": r[5]}
                 for r in rows]
        active = [x for x in items if x["state"] not in ("done", "failed")]
        return {"items": items, "active_count": len(active)}
    finally:
        con.close()


@app.post("/api/realtime/heartbeat")
def realtime_heartbeat(payload: dict = Body(...), authorization: str = Header(None)):
    """桌面客户端实时同步心跳。返回当前开关,客户端据此决定是否继续拉。"""
    me = _me(authorization)
    con = _con()
    try:
        _ensure_sync_tables(con)
        cur = con.execute("SELECT enabled FROM realtime_state WHERE owner=?", (me,)).fetchone()
        en = cur[0] if cur else 1
        con.execute("INSERT INTO realtime_state(owner,enabled,running,pending,last_synced,last_beat_ts,note) "
                    "VALUES(?,?,?,?,?,?,?) ON CONFLICT(owner) DO UPDATE SET "
                    "running=excluded.running,pending=excluded.pending,last_synced=excluded.last_synced,"
                    "last_beat_ts=excluded.last_beat_ts,note=excluded.note",
                    (me, en, int(bool(payload.get("running"))), int(payload.get("pending") or 0),
                     str(payload.get("last_synced", "")), _time.time(), str(payload.get("note", ""))))
        con.commit()
        return {"ok": True, "enabled": bool(en)}
    finally:
        con.close()


@app.get("/api/realtime/status")
def realtime_status(authorization: str = Header(None)):
    """网页轮询:实时同步状态(徽章亮=enabled且running且心跳新鲜)。"""
    me = _me(authorization)
    con = _con()
    try:
        _ensure_sync_tables(con)
        # 历史导入进度(前端区分「导入历史 X%」vs「实时同步中」)
        _tot = _HANDOFF_PROG.get("total", 0) or 0
        _done = _HANDOFF_PROG.get("done", 0) or 0
        _hist = {"importing": bool(_HANDOFF_PROG.get("importing")),
                 "hist_done": _done, "hist_total": _tot,
                 "hist_pct": int(_done * 100 / _tot) if _tot else 100}
        r = con.execute("SELECT enabled,running,pending,last_synced,last_beat_ts FROM realtime_state "
                        "WHERE owner=?", (me,)).fetchone()
        if not r:
            return {"enabled": False, "running": False, "fresh": False, "pending": 0,
                    "last_synced": "", "last_beat_ts": 0, **_hist}
        fresh = bool(r[4]) and (_time.time() - r[4] < 30)
        return {"enabled": bool(r[0]), "running": bool(r[1]), "fresh": fresh,
                "pending": r[2] or 0, "last_synced": r[3] or "", "last_beat_ts": r[4] or 0, **_hist}
    finally:
        con.close()


def _wx_safe(name):
    name = re.sub(r'[/\\:*?"<>|\n\r\t]', "_", (name or "未知").strip())
    return name[:60] or "未知"


def _wx_line(m):
    ts = str(m.get("ts") or "").replace("T", " ")[:16]
    sender = m.get("sender_name") or ""
    who = "我" if (sender == "(我)" or not (m.get("sender_id") or "").strip()) else sender
    text = m.get("text") or ""
    return "[%s] %s: %s" % (ts, who, text)


def _ingest_wechat_msgs(con, me, msgs):
    """把一批微信消息入库(内容指纹去重 + 按会话分页进FTS)。
    /api/wechat/ingest 与本地 handoff 消费线程共用。调用方负责 con.commit()/close()。
    返回 (ingested, dup, sessions)。"""
    import hashlib
    # 内容指纹去重(通用闸):不依赖各库 msg_id(iOS/桌面 ID 体系不同,对不上)。
    con.execute("CREATE TABLE IF NOT EXISTS wechat_lines(owner TEXT, fp TEXT, PRIMARY KEY(owner,fp))")
    by_sess = {}
    dup = 0
    for m in msgs:
        sess = (m.get("session_name") or m.get("session_id") or "未知").strip()
        text = m.get("text") or ""
        if not text:
            continue
        ts = str(m.get("ts") or "").replace("T", " ")[:16]   # 与 _wx_line 同口径(分钟精度)
        sname = (m.get("sender_name") or "").strip()
        is_me = sname in ("我", "(我)") or not (m.get("sender_id") or "").strip()
        skey = "我" if is_me else sname
        fp = hashlib.md5(("%s|%s|%s|%s|%s" % (me, sess, skey, ts, text)).encode("utf-8")).hexdigest()
        try:
            con.execute("INSERT INTO wechat_lines(owner,fp) VALUES(?,?)", (me, fp))
        except Exception:
            dup += 1
            continue
        by_sess.setdefault(sess, []).append(m)
    ingested = 0
    for sess, ms in by_sess.items():
        fn = "微信_与" + _wx_safe(sess) + ".txt"
        row = con.execute("SELECT id, pages FROM documents WHERE owner=? AND filename=?", (me, fn)).fetchone()
        if row:
            did, pcount = row[0], (row[1] or 0)
        else:
            con.execute("INSERT INTO documents(source_path,filename,pages,backend,file_hash,ingested_at,owner) "
                        "VALUES(?,?,?,?,?,datetime('now'),?)",
                        ("wechat_realtime:" + me + ":" + fn, fn, 0, "wechat", "wx:" + me + ":" + fn, me))
            did = con.execute("SELECT last_insert_rowid()").fetchone()[0]
            pcount = 0
        lines = [_wx_line(m) for m in ms]
        CH = 50
        for i in range(0, len(lines), CH):
            pcount += 1
            con.execute("INSERT INTO pages(doc_id,page_no,method,text) VALUES(?,?,?,?)",
                        (did, pcount, "wechat", "\n".join(lines[i:i + CH])))
            ingested += len(lines[i:i + CH])
        con.execute("UPDATE documents SET pages=? WHERE id=?", (pcount, did))
    return ingested, dup, len(by_sess)


@app.post("/api/wechat/ingest")
def wechat_ingest(payload: dict = Body(...), authorization: str = Header(None)):
    """实时微信入库:一批消息 → 内容指纹幂等去重 → 按会话追加到文档(pages,自动进FTS)。
    消费器把 handoff 的 NDJSON 批量推这里;向量嵌入另由后台增量补。"""
    me = _me(authorization)
    msgs = payload.get("messages") or []
    con = _con()
    try:
        ingested, dup, ns = _ingest_wechat_msgs(con, me, msgs)
        con.commit()
        return {"ok": True, "ingested": ingested, "dup": dup, "sessions": ns}
    finally:
        con.close()


# ── 本地 handoff 消费器(客户端内嵌):微信助手把消息写 ~/.wxsync/handoff/*.ndjson,
#    sidecar 常驻线程逐行读入库 + 心跳,免得再靠外部 handoff_consumer.py + token。
_HANDOFF_OWNER = {"v": None}          # 当前登录用户(由 /api/wechat/watch 设定)
_HANDOFF_THREAD = {"v": None}
# 历史导入进度(前端据此区分「导入历史」vs「实时同步」):done/total=已读/总字节,importing=还在补历史
_HANDOFF_PROG = {"done": 0, "total": 0, "importing": False, "alive": False}

def _handoff_dir():
    return os.path.join(os.path.expanduser("~"), ".wxsync", "handoff")

def _handoff_cursor_file():
    # 游标持久化:重开从上次位置续,不重扫历史(与库里指纹去重双保险)
    return os.path.join(os.path.expanduser("~"), ".wxsync", "compound_cursors.json")

def _handoff_load_cursors():
    try:
        import json as _j
        p = _handoff_cursor_file()
        if os.path.exists(p):
            d = _j.load(open(p, encoding="utf-8"))
            return d if isinstance(d, dict) else {}
    except Exception:
        pass
    return {}

def _handoff_save_cursors(cursors):
    try:
        import json as _j
        p = _handoff_cursor_file()
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            _j.dump(cursors, f)
        os.replace(p + ".tmp", p)
    except Exception:
        pass

def _handoff_beat(con, me):
    """写 realtime_state 心跳:running=1 + last_beat_ts=now,让 UI 从'等待客户端'变'实时同步中'。"""
    _ensure_sync_tables(con)
    cur = con.execute("SELECT enabled FROM realtime_state WHERE owner=?", (me,)).fetchone()
    en = cur[0] if cur else 1
    con.execute("INSERT INTO realtime_state(owner,enabled,running,pending,last_synced,last_beat_ts,note) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(owner) DO UPDATE SET "
                "running=excluded.running,last_beat_ts=excluded.last_beat_ts,note=excluded.note",
                (me, en, 1, 0, "", _time.time(), "本地助手"))

def _handoff_watch_loop():
    """逐文件字节游标(binary)分块读 NDJSON,批量入库 + 心跳 + 历史导入进度。
    ★游标持久化:重开从上次位置续,不重扫历史。★分块 4MB/tick 不 OOM。指纹去重防重复入库。
    ★进度:total=全部 handoff 字节,done=已读字节;done<total 且差>256KB=还在补历史(前端显示进度)。"""
    import json as _json
    CHUNK = 4 * 1024 * 1024
    cursors = _handoff_load_cursors()
    hd = _handoff_dir()
    while True:
        try:
            me = _HANDOFF_OWNER["v"]
            if me and os.path.isdir(hd):
                batch = []
                dirty = False
                total_bytes = 0
                done_bytes = 0
                for f in sorted(x for x in os.listdir(hd) if x.endswith(".ndjson")):
                    p = os.path.join(hd, f)
                    try:
                        sz = os.path.getsize(p)
                    except Exception:
                        continue
                    total_bytes += sz
                    off = cursors.get(p, 0)
                    if off > sz:          # 文件被截断/重建 → 重头读
                        off = 0
                    if sz > off:
                        try:
                            with open(p, "rb") as fh:
                                fh.seek(off)
                                raw = fh.read(CHUNK)
                            nl = raw.rfind(b"\n")
                            usable, adv = (raw, len(raw)) if nl < 0 else (raw[:nl], nl + 1)
                            cursors[p] = off + adv
                            dirty = True
                            for ln in usable.split(b"\n"):
                                ln = ln.strip()
                                if ln:
                                    try:
                                        batch.append(_json.loads(ln.decode("utf-8", "ignore")))
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                    done_bytes += min(cursors.get(p, 0), sz)
                # 助手活性:助手运行时每秒刷新 ~/.wxsync/state.json;关掉就不刷(关窗未退进程仍算在跑)。
                alive = False
                try:
                    _sj = os.path.join(os.path.expanduser("~"), ".wxsync", "state.json")
                    alive = os.path.exists(_sj) and (_time.time() - os.path.getmtime(_sj) < 15)
                except Exception:
                    alive = False
                importing = (total_bytes - done_bytes) > 256 * 1024   # 还有>256KB没读=在补历史
                _HANDOFF_PROG.update(done=done_bytes, total=total_bytes,
                                     importing=importing, alive=alive)
                con = _con()
                try:
                    if batch:
                        _ingest_wechat_msgs(con, me, batch)  # 入库总做
                    if alive:
                        _handoff_beat(con, me)               # 助手在跑=实时同步中
                    con.commit()
                except Exception:
                    pass
                finally:
                    con.close()
                if dirty:
                    _handoff_save_cursors(cursors)
        except Exception:
            pass
        _time.sleep(4)

def _handoff_watch_start(me):
    _HANDOFF_OWNER["v"] = me
    if _HANDOFF_THREAD["v"] is None:
        import threading
        t = threading.Thread(target=_handoff_watch_loop, daemon=True)
        t.start()
        _HANDOFF_THREAD["v"] = t


@app.post("/api/wechat/watch")
def wechat_watch(authorization: str = Header(None)):
    """客户端登录后调用:告知 sidecar 当前用户,启动本地 handoff 消费线程。"""
    me = _me(authorization)
    _handoff_watch_start(me)
    return {"ok": True}


# ── iPhone 历史导入(iOS,与微信助手无关):点「开始导入(连手机)」→ 这里后台跑
#    idevicebackup2 全量备份 → 解析微信库 → 认人 → 推 /api/wechat/ingest。进度写 ingest_progress
#    (job_id 以 iphone- 开头,前端 iOS tab 的五段式动画读它)。执行代码 = sidecar/wxsync/import_iphone。
_IPHONE_IMPORT = {"running": False}

@app.get("/api/iphone/status")
def iphone_status(authorization: str = Header(None)):
    """iOS 导入是否在跑 + 环境是否就绪(idevicebackup2 是否可用、有没有连手机)。"""
    _me(authorization)
    import shutil as _sh, subprocess as _sp
    have_tool = bool(_sh.which("idevicebackup2") and _sh.which("idevice_id"))
    connected = False
    battery = None; charging = None
    if have_tool:
        try:
            out = _sp.check_output(["idevice_id", "-l"], text=True, timeout=8)
            connected = bool([x for x in out.splitlines() if x.strip()])
        except Exception:
            connected = False
        # ★取电量:整机备份耗电>500mA口充电→电量低易中断,前端据此提醒用户先充电
        if connected and _sh.which("ideviceinfo"):
            try:
                b = _sp.check_output(["ideviceinfo", "-q", "com.apple.mobile.battery", "-k", "BatteryCurrentCapacity"], text=True, timeout=8).strip()
                battery = int(b) if b.isdigit() else None
            except Exception:
                battery = None
            try:
                c = _sp.check_output(["ideviceinfo", "-q", "com.apple.mobile.battery", "-k", "BatteryIsCharging"], text=True, timeout=8).strip()
                charging = (c.lower() == "true")
            except Exception:
                charging = None
    return {"running": _IPHONE_IMPORT["running"], "tool_ready": have_tool, "connected": connected,
            "battery": battery, "charging": charging}


@app.post("/api/iphone/import")
def iphone_import(authorization: str = Header(None)):
    """启动 iPhone 历史导入(后台线程)。立刻返回;前端轮询 /api/ingest/progress 看五段式进度。"""
    me = _me(authorization)
    tok = (authorization or "").replace("Bearer ", "")
    if _IPHONE_IMPORT["running"]:
        return {"ok": True, "already_running": True}

    import shutil as _sh
    if not (_sh.which("idevicebackup2") and _sh.which("idevice_id")):
        raise HTTPException(400, "未检测到 iPhone 备份工具(idevicebackup2)。请先安装:brew install libimobiledevice")

    _port = os.environ.get("WEB_PORT", "8200")
    _self = "http://127.0.0.1:%s" % _port

    def _run():
        _IPHONE_IMPORT["running"] = True
        # 让 import_iphone 的 uploader/status 推给 sidecar 自己(config 支持 WXSYNC_* 环境变量覆盖)
        os.environ["WXSYNC_BACKEND"] = _self
        os.environ["WXSYNC_TOKEN"] = tok
        try:
            import sys as _sys
            _wp = os.path.join(getattr(_sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "wxsync")
            if _wp not in _sys.path:
                _sys.path.insert(0, _wp)
            import import_iphone as _imp
            # 进度回调 → ingest_progress(job_id=iphone-import,前端五段式动画读)
            def _cb(stage, percent, detail="", contact="全部微信聊天", state=None):
                try:
                    c2 = _con()
                    try:
                        _st = state or ("done" if percent >= 100 else "importing")
                        c2.execute("INSERT OR REPLACE INTO ingest_progress(owner,job_id,contact,state,percent,message,ts) "
                                   "VALUES(?,?,?,?,?,?,?)",
                                   (me, "iphone-import", contact, _st, int(percent), stage + (" · " + detail if detail else ""), _time.time()))
                        c2.commit()
                    finally:
                        c2.close()
                except Exception:
                    pass
            _imp.run_import(on_status=_cb, min_lines=2, keep_backup=False)
        except Exception as e:
            try:
                c2 = _con()
                try:
                    c2.execute("INSERT OR REPLACE INTO ingest_progress(owner,job_id,contact,state,percent,message,ts) "
                               "VALUES(?,?,?,?,?,?,?)",
                               (me, "iphone-import", "全部微信聊天", "failed", 0, "导入失败:" + str(e)[:200], _time.time()))
                    c2.commit()
                finally:
                    c2.close()
            except Exception:
                pass
        finally:
            _IPHONE_IMPORT["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "started": True}


@app.post("/api/realtime/toggle")
def realtime_toggle(payload: dict = Body(...), authorization: str = Header(None)):
    """网页开关实时同步。客户端靠轮询 heartbeat 返回的 enabled 跟随。"""
    me = _me(authorization)
    con = _con()
    try:
        _ensure_sync_tables(con)
        en = int(bool(payload.get("enabled")))
        con.execute("INSERT INTO realtime_state(owner,enabled) VALUES(?,?) "
                    "ON CONFLICT(owner) DO UPDATE SET enabled=excluded.enabled", (me, en))
        con.commit()
        return {"ok": True, "enabled": bool(en)}
    finally:
        con.close()


# ==== P1/P2 洞察 ====
@app.get("/api/cooling")
def cooling_api(authorization: str = Header(None)):
    """关系降温预警(按互动节奏变化率,不是绝对天数)。"""
    me = _me(authorization)
    con = _con()
    try:
        return INS.cooling_alerts(con, me)
    finally:
        con.close()


@app.get("/api/favors")
def favors_api(authorization: str = Header(None)):
    """人情待还:谁帮过我/我欠谁 + 可借的暖场由头。"""
    me = _me(authorization)
    con = _con()
    try:
        return INS.favors_to_repay(con, me)
    finally:
        con.close()


@app.get("/api/dormant")
def dormant_api(authorization: str = Header(None)):
    """沉默线索复活:聊过没成、久未联系、可能时机到了的线索。"""
    me = _me(authorization)
    con = _con()
    try:
        return INS.dormant_leads(con, me)
    finally:
        con.close()


@app.get("/api/balance")
def balance_api(authorization: str = Header(None)):
    """关系资产负债表:升温/降温/流失/新增/核心 + 时间花在谁身上。"""
    me = _me(authorization)
    con = _con()
    try:
        return INS.relationship_balance(con, me)
    finally:
        con.close()


@app.get("/api/panorama")
def panorama_api(authorization: str = Header(None)):
    """业务全景:按事/项目聚合(涉及哪些联系人)。"""
    me = _me(authorization)
    con = _con()
    try:
        return INS.business_panorama(con, me)
    finally:
        con.close()


@app.get("/api/checkup")
def checkup_api(authorization: str = Header(None)):
    """沟通体检:谁在等我回、我对谁变冷了。"""
    me = _me(authorization)
    con = _con()
    try:
        return INS.communication_checkup(con, me)
    finally:
        con.close()


@app.get("/api/discoveries")
def discoveries_api(authorization: str = Header(None)):
    """主动发现:第二大脑替你盯着,有价值的事主动冒出来(该联系/对方在等你回/承诺到期/撮合)。
    即时计算(降温/沟通)+ 已缓存情报(承诺,不触发新生成,保证快)。"""
    me = _me(authorization)
    con = _con()
    out = []
    try:
        for a in INS.cooling_alerts(con, me).get("alerts", [])[:8]:
            out.append({"type": "cooling", "contact": a["contact"], "doc_id": a.get("doc_id"),
                        "title": a["contact"] + " 该联系了", "detail": a["reason"],
                        "urgency": 3 if a.get("level") == "严重" else 2,
                        "ask": "我和" + a["contact"] + "有阵子没联系了,回顾下我们聊到哪、有什么该跟进的,帮我想个自然的开场白"})
    except Exception:
        pass
    try:
        for w in INS.communication_checkup(con, me).get("they_wait", [])[:8]:
            out.append({"type": "reply", "contact": w["contact"], "doc_id": w.get("doc_id"),
                        "title": w["contact"] + " 在等你回复", "detail": "已 %d 天没回" % w.get("waiting_days", 0),
                        "urgency": 4 if w.get("waiting_days", 0) >= 3 else 3,
                        "ask": "我和" + w["contact"] + "的对话,对方最后发的还没回,帮我看看该怎么回"})
    except Exception:
        pass
    # 承诺到期:只读已缓存的 chat_intel(不触发新生成,保证快)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS chat_intel(username TEXT,contact TEXT,doc_id INTEGER,msgcount INTEGER,day TEXT,data TEXT,PRIMARY KEY(username,contact))")
        today = _dt.date.today()
        for contact, did, data in con.execute("SELECT contact, doc_id, data FROM chat_intel WHERE username=?", (me,)).fetchall():
            try:
                d = json.loads(data)
            except Exception:
                continue
            for cm in (d.get("commitments") or []):
                if cm.get("done"):
                    continue
                due = cm.get("due") or ""
                dt = None
                try:
                    dt = (_dt.date.fromisoformat(due) - today).days
                except Exception:
                    dt = None
                if dt is not None and -45 <= dt <= 7:   # 只报近期:逾期≤45天 / 7天内到期(几年前的旧承诺不刷屏)
                    who = "我" if (cm.get("who") or "").startswith("我") else contact
                    out.append({"type": "commitment", "contact": contact, "doc_id": did,
                                "title": ("你答应" + contact if who == "我" else contact + " 答应你") + "的事" + ("已逾期" if dt < 0 else "快到期"),
                                "detail": cm.get("what", "") + ("(%d天前)" % (-dt) if dt < 0 else "(%d天内)" % dt),
                                "urgency": 5 if dt < 0 else 4,
                                "ask": "帮我把和" + contact + "关于「" + cm.get("what", "") + "」的事跟进一下,该怎么说"})
    except Exception:
        pass
    con.close()
    out.sort(key=lambda x: -x.get("urgency", 0))
    return {"discoveries": out[:20], "count": len(out)}


@app.post("/api/draft_reply")
def draft_reply_api(payload: dict = Body(...), authorization: str = Header(None)):
    """帮我回这条:结合历史+我的说话风格,给3个回复草稿。"""
    me = _me(authorization)
    con = _con()
    try:
        return INS.draft_reply(con, me, str(payload.get("contact", "")), str(payload.get("incoming", "")))
    finally:
        con.close()


@app.get("/api/links")
def cross_links(limit: int = 8, refresh: int = 0, authorization: str = Header(None)):
    """跨时间/跨文件的细微链接:全库两两找强语义关联,挑出'你可能忘了它们其实相关'的对。每日缓存。"""
    me = _me(authorization)
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS links_cache (username TEXT PRIMARY KEY, day TEXT, data TEXT)")
        day = _dt.date.today().isoformat()
        if not refresh:
            row = con.execute("SELECT day,data FROM links_cache WHERE username=?", (me,)).fetchone()
            if row and row[0] == day:
                _d = json.loads(row[1])
                _attach_explains(con, me, _d.get("links", []), _link_expl_key, lambda it: _link_expl_prompt(con, it))
                return {"cached": True, **_d}
        docs = con.execute("SELECT id, filename, ingested_at FROM documents WHERE owner=? AND backend NOT LIKE 'card:%'", (me,)).fetchall()
        meta = {d[0]: {"fn": d[1] or "", "t": d[2] or ""} for d in docs}
        pairs = {}
        for did in meta:
            try:
                sims = S.similar_docs(con, did, 5, owner=me)
            except Exception:
                sims = []
            for sd in sims:
                oid = sd["doc_id"]; sc = sd["score"]
                if sc < 0.6 or oid not in meta:
                    continue
                key = tuple(sorted((did, oid)))
                if key in pairs:
                    continue
                a, b = meta[key[0]], meta[key[1]]
                ta, tb = _ftype_of(a["fn"]), _ftype_of(b["fn"])
                try:
                    gap = abs((_dt.date.fromisoformat(a["t"][:10]) - _dt.date.fromisoformat(b["t"][:10])).days)
                except Exception:
                    gap = 0
                pairs[key] = {"a": a["fn"][:36], "b": b["fn"][:36], "ta": ta, "tb": tb,
                              "a_id": key[0], "b_id": key[1],
                              "score": int(sc * 100), "gap": gap, "cross_type": ta != tb}
        _all = sorted(pairs.values(), key=lambda x: (x["cross_type"], x["gap"], x["score"]), reverse=True)
        ranked = []; _used = {}
        for _l in _all:  # 去重:每个文档最多出现2次,避免一个文件霸屏
            if _used.get(_l["a_id"], 0) >= 2 or _used.get(_l["b_id"], 0) >= 2:
                continue
            ranked.append(_l); _used[_l["a_id"]] = _used.get(_l["a_id"], 0) + 1; _used[_l["b_id"]] = _used.get(_l["b_id"], 0) + 1
            if len(ranked) >= limit: break
        data = {"links": ranked}
        con.execute("INSERT OR REPLACE INTO links_cache(username,day,data) VALUES(?,?,?)", (me, day, json.dumps(data, ensure_ascii=False)))
        con.commit()
        _attach_explains(con, me, ranked, _link_expl_key, lambda it: _link_expl_prompt(con, it))
        return {"cached": False, **data}
    finally:
        con.close()


# ===== 连接/实体解读层:每张卡带"为什么相关/能得到什么/该做什么"(快模型后台生成,缓存) =====
_EXPL_RUNNING = set()


def _expl_table(con):
    con.execute("CREATE TABLE IF NOT EXISTS conn_explain(owner TEXT, key TEXT, data TEXT, day TEXT, PRIMARY KEY(owner,key))")


def _doc_snip(con, doc_id, n=1100):
    rows = con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no LIMIT 6", (doc_id,)).fetchall()
    return ("\n".join(r[0] or "" for r in rows))[:n]


def _explain_worker(owner, jobs):
    con = _con()
    try:
        _expl_table(con)
        for key, prompt in jobs:
            try:
                out = LLM.chat([{"role": "system", "content": "你是用户的第二大脑,基于给定资料给出具体、可执行的解读。禁emoji,禁空话,必须点名具体的人/业务/数字。只输出JSON。"},
                                {"role": "user", "content": prompt}], temperature=0.3, max_tokens=1200, model=LLM.fast_model())
                m = re.search(r"\{.*\}", out, re.S)
                if not m:
                    continue
                d = json.loads(m.group(0))
                if d.get("why"):
                    con.execute("INSERT OR REPLACE INTO conn_explain(owner,key,data,day) VALUES(?,?,?,?)",
                                (owner, key, json.dumps(d, ensure_ascii=False), _dt.date.today().isoformat()))
                    con.commit()
            except Exception:
                continue
    finally:
        con.close()
        _EXPL_RUNNING.discard(owner)


def _attach_explains(con, owner, items, keyf, promptf):
    """给列表项附 explain(有缓存直接带上);缺的踢一个后台线程去生成,下次刷新可见。"""
    _expl_table(con)
    missing = []
    for it in items:
        k = keyf(it)
        row = con.execute("SELECT data FROM conn_explain WHERE owner=? AND key=?", (owner, k)).fetchone()
        if row:
            try:
                it["explain"] = json.loads(row[0])
            except Exception:
                pass
        else:
            try:
                missing.append((k, promptf(it)))
            except Exception:
                pass
    if missing and owner not in _EXPL_RUNNING:
        _EXPL_RUNNING.add(owner)
        threading.Thread(target=_explain_worker, args=(owner, missing), daemon=True).start()
    return items


def _link_expl_key(it):
    return "link:%s:%s" % (it["a_id"], it["b_id"])


def _link_expl_prompt(con, it):
    sa, sb = _doc_snip(con, it["a_id"]), _doc_snip(con, it["b_id"])
    return ("资料A《%s》摘录:\n%s\n\n资料B《%s》摘录:\n%s\n\n这两份资料被语义判定为相关。输出JSON "
            "{\"why\":\"相关的具体线索:点名双方各一个具体的人/业务/数字,不超过50字\","
            "\"get\":\"把两者连起来看,用户能得到什么此前没注意到的信息,不超过40字\","
            "\"do\":\"建议用户现在做的一件具体的事,不超过30字\"}") % (it["a"], sa, it["b"], sb)


@app.get("/api/connections/{doc_id}")
def connections(doc_id: int, refresh: int = 0, authorization: str = Header(None)):
    """主动发现连接:点开一份文档,AI 从全库挖出你可能忘了的非显而易见的跨界关联 + 一句跨界灵感。"""
    if not (1 <= doc_id < 2**63):
        raise HTTPException(404, "没有这份文档")
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS doc_connections (doc_id INTEGER PRIMARY KEY, data TEXT)")
        me = _me(authorization)
        d = con.execute("SELECT filename FROM documents WHERE id=? AND owner=?", (doc_id, me)).fetchone()
        if not d:
            raise HTTPException(404, "没有这份文档")
        if not refresh:
            c = con.execute("SELECT data FROM doc_connections WHERE doc_id=?", (doc_id,)).fetchone()
            if c:
                return {"doc_id": doc_id, "cached": True, **json.loads(c[0])}
        rows = con.execute("SELECT text FROM pages WHERE doc_id=? AND length(trim(text))>0 ORDER BY page_no LIMIT 4", (doc_id,)).fetchall()
        sample = "\n".join(S.clean_ocr(r[0] or "")[:900] for r in rows)[:3000]
        if not sample.strip():
            return {"doc_id": doc_id, "connections": [], "spark": "这份文档没有可读文本,暂时连不出关联。"}
        mine = _my_ids(con, me)
        srcs = S.retrieve(con, sample[:600], topk=40)
        seen = {doc_id}; cands = []
        for sc in srcs:
            did = sc.get("doc_id")
            if did in seen or did not in mine:
                continue
            seen.add(did); cands.append({"doc_id": did, "filename": sc.get("filename"), "snip": (sc.get("text") or "")[:220]})
            if len(cands) >= 6:
                break
        if not cands:
            return {"doc_id": doc_id, "connections": [], "spark": "库里还没有能和它连起来的其它文档,多喂点东西给你的第二大脑。"}
        ctx = ("【当前文档】《%s》:\n%s\n\n【候选关联文档】\n" % (d[0], sample[:1500])) + "\n".join(
            "[%d]《%s》: %s" % (c["doc_id"], c["filename"], c["snip"]) for c in cands)
        sysp = ("你是第二大脑的联想引擎。用户点开一份文档,你要从候选文档里挖出他自己可能都忘了的、非显而易见的跨界连接。"
                "铁律:不是简单说'都讲金融',而是点出共享的深层思路/方法/隐喻,给他惊喜和启发。"
                "★但只在**真有实质关联**时才连;若当前文档内容单薄、或候选和它并无真实共同点,就如实说'暂无明显关联',connections 给空数组、spark 一句实在话,**绝不为了凑数强行发散或牵强附会**。中文。只输出JSON:{"
                '"connections":[{"doc_id":候选文档编号,"insight":"一句话:这份和《当前文档》在什么深层点上相连(点名共享的思路/方法),别空泛"}],'
                '"spark":"一句跨界灵感:把这些连接碰撞起来能激发什么新想法/新产出,具体有启发"}')
        try:
            out = LLM.chat([{"role": "system", "content": sysp}, {"role": "user", "content": ctx}], temperature=0.6, max_tokens=1200)
            m = re.search(r"\{.*\}", out, re.S); data = json.loads(m.group(0)) if m else {}
        except Exception as e:
            raise HTTPException(400, "联想失败(检查模型/key): %s" % e)
        fn = {c["doc_id"]: c["filename"] for c in cands}
        conns = []
        for cc in (data.get("connections") or []):
            did = cc.get("doc_id")
            try:
                did = int(did)
            except Exception:
                did = None
            if did in fn:
                conns.append({"doc_id": did, "filename": fn[did], "insight": (cc.get("insight") or "")[:200]})
        res = {"connections": conns[:4], "spark": (data.get("spark") or "")[:280]}
        if conns:  # 空结果不缓存,避免偶发空被永久缓存住(同 today)
            con.execute("INSERT OR REPLACE INTO doc_connections(doc_id,data) VALUES(?,?)", (doc_id, json.dumps(res, ensure_ascii=False))); con.commit()
        return {"doc_id": doc_id, "cached": False, **res}
    finally:
        con.close()


@app.get("/api/graph")
def graph(topk: int = 6, threshold: float = 0.35, authorization: str = Header(None)):
    """星系图数据:节点=文档,连线=文档间语义相似。"""
    me = _me(authorization)
    con = _con()
    try:
        g = S.graph(con, topk=topk, threshold=threshold, owner=me)
        mine = _my_ids(con, me)
        g["nodes"] = [n for n in g["nodes"] if n["id"] in mine]
        g["edges"] = [e for e in g["edges"] if e["source"] in mine and e["target"] in mine]
        return g
    finally:
        con.close()


@app.get("/api/starmap")
def starmap(chunk: int = 12, k: int = 6, clusters: int = 14, authorization: str = Header(None)):
    """星海模式:细粒度节点(每 chunk 页一颗星)+ 聚类分色 + kNN 连线。"""
    me = _me(authorization)
    con = _con()
    try:
        # A1:星海图缓存(chunk_graph 每次重算=冷启29s)。按 owner+参数 缓存,_docs_sig 自动失效
        name = "starmap:%d:%d:%d" % (chunk, k, clusters)

        def _build():
            g = S.chunk_graph(con, chunk_pages=chunk, k=k, clusters=clusters, owner=me)
            mine = _my_ids(con, me)
            keep = {n["id"] for n in g["nodes"] if n.get("doc_id") in mine}
            g["nodes"] = [n for n in g["nodes"] if n["id"] in keep]
            g["edges"] = [e for e in g["edges"] if e["source"] in keep and e["target"] in keep]
            return g
        return _db_cached(con, me, name, _build)
    finally:
        con.close()



def _gen_nudge(card_id, ctype, content, owner=None):
    """卡片主动消息:AI 基于知识库发现"现在能推进的一步"并主动 push。后台线程跑。"""
    try:
        con = _con()
        try:
            con.execute("CREATE TABLE IF NOT EXISTS card_msgs (id INTEGER PRIMARY KEY, card_id INTEGER, content TEXT, created TEXT, read INTEGER DEFAULT 0)")
            try:
                srcs = S.retrieve(con, content, topk=24)
                if owner:
                    mine = _my_ids(con, owner)
                    srcs = [s for s in srcs if s["doc_id"] in mine][:4]
                else:
                    srcs = srcs[:4]
            except Exception:
                srcs = []
            ctx = "\n".join("・%s 第%s页:%s" % (x["filename"], x["page_no"], (x["text"] or "")[:220]) for x in srcs)
            actionable = ctype in ("goal", "task")
            if actionable:
                sysp = ("用户刚建了一个目标/任务卡片。你是他的「第二大脑」。请**主动**(不等他问)基于他知识库里的材料,"
                        "发现**现在就能推进这件事的具体一步**,并**主动提出帮他做**——比如『你库里有《X》和你记过的Y,我可以直接用它们帮你起草前几页/列出可行路径,要不要?』。"
                        "要具体、点名材料、可执行,像会主动帮忙的伙伴;若卡片里有期限就顺带提醒时间。一段话,别客套别说教。")
            else:
                sysp = ("用户刚写了一篇随记/日记。你是他的「第二大脑」,像懂他的朋友主动接话:发现它和他知识库/过往的关联,"
                        "给一个洞察或引导他深想一层。一段话,温暖、有洞察,别说教。")
            usr = "卡片内容:%s\n\n他知识库里相关的材料:\n%s" % (content, ctx or "(暂时没检索到直接相关的)")
            out = LLM.chat([{"role": "system", "content": sysp}, {"role": "user", "content": usr}], temperature=0.6, max_tokens=700, model=LLM.fast_model())
            con.execute("INSERT INTO card_msgs(card_id,content,created,read) VALUES(?,?,?,0)",
                        (card_id, (out or "").strip(), _dt.datetime.now().isoformat(timespec="seconds")))
            con.commit()
        finally:
            con.close()
    except Exception:
        pass


@app.post("/api/card")
def create_card(payload: dict = Body(...), authorization: str = Header(None)):
    """用户手写卡片(日记/目标/笔记/任务)→ 存为文档 + 嵌入,成为大脑的一部分。"""
    me = _me(authorization)
    import uuid
    ctype = payload.get("ctype", "note")
    title = (payload.get("title") or "").strip()
    content = (payload.get("content") or "").strip()
    if not content:
        raise HTTPException(400, "卡片内容为空")
    sp = "card://" + uuid.uuid4().hex
    fn = title or (content[:24] + ("…" if len(content) > 24 else ""))
    con = _con()
    try:
        cur = con.execute(
            "INSERT INTO documents(source_path,filename,pages,backend,file_hash,ingested_at,owner)"
            " VALUES(?,?,?,?,?,?,?)",
            (sp, fn, 1, "card:" + ctype, "card", _dt.datetime.now().isoformat(timespec="seconds"), me))
        did = cur.lastrowid
        con.execute("INSERT INTO pages(doc_id,page_no,method,text) VALUES(?,?,?,?)",
                    (did, 1, "card:" + ctype, content))
        con.commit()
        # ★不在这里同步嵌入:embed_pending 在 8G 机上要加载 bge-m3 + 逐页 encode(数分钟),
        #   会把保存卡片的 HTTP 请求拖到超时/失败。后台常驻嵌入线程会自动把这张新卡的页嵌入。
        import threading
        threading.Thread(target=_gen_nudge, args=(did, ctype, content, me), daemon=True).start()
        return {"id": did, "title": fn}
    finally:
        con.close()


@app.get("/api/cards")
def list_cards(authorization: str = Header(None)):
    me = _me(authorization)
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS card_msgs (id INTEGER PRIMARY KEY, card_id INTEGER, content TEXT, created TEXT, read INTEGER DEFAULT 0)")
        rows = con.execute(
            "SELECT id, filename, backend, ingested_at FROM documents "
            "WHERE backend LIKE 'card:%' AND owner=? ORDER BY id DESC", (me,)).fetchall()
        unread = dict(con.execute("SELECT card_id, COUNT(*) FROM card_msgs WHERE read=0 GROUP BY card_id").fetchall())
        con.execute("CREATE TABLE IF NOT EXISTS card_status (card_id INTEGER PRIMARY KEY, status TEXT)")
        stat = dict(con.execute("SELECT card_id, status FROM card_status").fetchall())
        cards = [{"id": r[0], "title": r[1],
                  "ctype": r[2].split(":", 1)[1] if ":" in r[2] else "note",
                  "created": r[3], "unread": unread.get(r[0], 0), "status": stat.get(r[0], "")} for r in rows]
        return {"cards": cards, "unread_total": sum(unread.get(r[0], 0) for r in rows)}
    finally:
        con.close()



# ========== 账号体系(users + pbkdf2 + HMAC token,零依赖) ==========
import hmac as _hmac, hashlib as _hl, base64 as _b64, time as _time
import urllib.request as _urlreq, urllib.error as _urlerr
# ===== 账号中心化(2026-08-07):账号/身份/短信全在云端 106.189,web 不持 secret =====
_CLOUD = os.environ.get("CLOUD_URL", "http://106.14.189.104:8000")
# ★绕过本机代理(clash 等)直连云账号服:否则装了代理的用户(国内很多),
#   登录/账号/支付/支付宝 全部转发失败(106 是内地IP,走 clash 连不上)。
_cloud_opener = _urlreq.build_opener(_urlreq.ProxyHandler({}))
_tok_cache = {}  # token -> (ident, expire_ts):验证走云,本地缓存2分钟减少往返
def _cloud_post(path, payload, authorization=None):
    """转发到云账号服务,返回其响应(补 username 字段兼容前端)。"""
    _h = {"Content-Type": "application/json"}
    if authorization:
        _h["Authorization"] = authorization
    try:
        r = _cloud_opener.open(_urlreq.Request(_CLOUD + path, json.dumps(payload).encode(), _h), timeout=15)
        d = json.loads(r.read())
        if "ident" in d and "username" not in d:
            d["username"] = d["ident"]
        return d
    except _urlerr.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("detail", "操作失败")
        except Exception:
            msg = "操作失败"
        raise HTTPException(e.code, msg if isinstance(msg, str) else "操作失败")
    except Exception:
        raise HTTPException(503, "云账号服务连接失败,请检查网络")
_AUTH_SECRET_FILE = os.path.join(os.environ.get("BRAIN_DATA","/home/kb/brain"), ".auth_secret")
def _auth_secret():
    if not os.path.exists(_AUTH_SECRET_FILE):
        with open(_AUTH_SECRET_FILE, "wb") as f:
            f.write(os.urandom(32))
    with open(_AUTH_SECRET_FILE, "rb") as f:
        return f.read()
def _sign(b): return _hmac.new(_auth_secret(), b, _hl.sha256).hexdigest()
def _make_token(username, pv=0, days=30):
    payload = json.dumps({"u": username, "pv": pv, "exp": int(_time.time()) + days * 86400}).encode()
    b = _b64.urlsafe_b64encode(payload).decode().rstrip("=")
    return b + "." + _sign(b.encode())
def _verify_token(tok):
    try:
        b, sig = (tok or "").split(".")
        if not _hmac.compare_digest(sig, _sign(b.encode())): return None
        pad = b + "=" * (-len(b) % 4)
        pl = json.loads(_b64.urlsafe_b64decode(pad))
        if pl.get("exp", 0) < _time.time(): return None
        return pl.get("u")
    except Exception:
        return None
def _hash_pwd(pwd, salt=None):
    salt = salt or os.urandom(16).hex()
    h = _hl.pbkdf2_hmac("sha256", pwd.encode(), bytes.fromhex(salt), 120000).hex()
    return salt, h
def _ensure_users(con):
    con.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, salt TEXT, pwd TEXT, created TEXT)")

@app.post("/api/auth/register")
def auth_register(payload: dict = Body(...)):
    # 账号中心化:注册走云端(106.189),owner=云账号 ident
    return _cloud_post("/account/register", payload)

@app.post("/api/auth/login")
def auth_login(payload: dict = Body(...)):
    return _cloud_post("/account/login", payload)

@app.get("/api/auth/me")
def auth_me(authorization: str = Header(None)):
    return {"username": _me(authorization)}



# ========== 好友 / 姻缘匹配 ==========
def _user_pv(con, u):
    """当前用户的 password_version(token 吊销用)。列/账号不存在均视作 0(向后兼容)。"""
    for tbl, col in (("users", "username"), ("users2", "phone")):
        try:
            r = con.execute("SELECT pv FROM %s WHERE %s=?" % (tbl, col), (u,)).fetchone()
            if r:
                return r[0] or 0
        except Exception:
            pass
    return 0


def _account_raw(authorization, fresh=False):
    """验证 token + 取云端账号/授权信息(ident/active/status/days_left/trial_until/tier_until),短缓存。
    ★不做付费门控(付费墙/试用倒计时/支付都要能读它)。云暂不可达用旧缓存降级。
    fresh=True 绕过缓存(付费墙轮询用,付款/退款后立刻拿最新状态)。"""
    tok = (authorization or "").replace("Bearer ", "")
    if not tok:
        raise HTTPException(401, "未登录")
    now = _time.time()
    hit = _tok_cache.get(tok)
    if hit and hit[1] > now and not fresh:
        return hit[0]
    try:
        r = _cloud_opener.open(_urlreq.Request(_CLOUD + "/account/me", headers={"Authorization": "Bearer " + tok}), timeout=10)
        acc = json.loads(r.read())
    except _urlerr.HTTPError as e:
        if e.code == 401:
            raise HTTPException(401, "登录已过期,请重新登录")
        raise HTTPException(503, "云账号服务异常")
    except Exception:
        if hit:
            return hit[0]   # 云暂不可达 → 用旧缓存降级
        raise HTTPException(503, "云账号服务连接失败,请检查网络")
    _tok_cache[tok] = (acc, now + 20)   # 会员状态会因付款/退款变化,缓存收短到 20s
    return acc


def _bust_account_cache(authorization):
    """付款/退款到账后清掉该 token 的账号缓存,让所有接口立刻看到最新会员状态。"""
    try:
        _tok_cache.pop((authorization or "").replace("Bearer ", ""), None)
    except Exception:
        pass


PAYWALL_ENFORCE = os.environ.get("PAYWALL_ENFORCE", "0") == "1"   # ★默认关:后端就位但不锁人;前端付费墙上线后翻成1才真拦


def _me(authorization):
    """功能门控入口:验证 + 试用/付费检查。开关开启且未激活(试用过期且未付费)→ 402(前端弹订阅墙)。返回 ident。"""
    acc = _account_raw(authorization)
    if isinstance(acc, dict):
        if PAYWALL_ENFORCE and acc.get("active") is False:   # 明确未激活才拦;字段缺失(旧云)默认放行不误伤
            raise HTTPException(402, {"error": "membership_required",
                                     "status": acc.get("status"), "days_left": acc.get("days_left"),
                                     "trial_until": acc.get("trial_until"), "tier_until": acc.get("tier_until")})
        return acc.get("ident")
    return acc   # 兼容极旧缓存(纯 ident 字符串)


def _my_ids(con, me):
    """当前用户拥有的 doc_id 集合(端点层隔离过滤用)。"""
    return {r[0] for r in con.execute("SELECT id FROM documents WHERE owner=?", (me,))}


# ===== 会员/付费:前端同源调本网关,网关转发到云账号服务(compound-server)。均不做付费门控。 =====
def _cloud_proxy(method, path, authorization, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = _urlreq.Request(_CLOUD + path, data=data, method=method,
                          headers={"Authorization": authorization or "", "Content-Type": "application/json"})
    try:
        with _cloud_opener.open(req, timeout=25) as r:
            return json.loads(r.read())
    except _urlerr.HTTPError as e:
        try:
            d = json.loads(e.read()).get("detail")
        except Exception:
            d = None
        raise HTTPException(e.code, d or "支付服务错误")
    except Exception:
        raise HTTPException(502, "支付服务连接失败")


# ========== 好友社交(走云 compound-server:手机号加+对方同意+画像共享算姻缘)==========
#   ★本地优先:数据在本地,只把"我的画像"这一份上传云端;云端只让已互为好友的双方互取画像。
#   加好友=按手机号发请求→对方同意(=授权双方算姻缘)。无发现池。
def _share_persona_to_cloud(authorization, data, mbti=""):
    """后台把我的画像上传到云社交库(供已同意好友算姻缘)。失败静默(不影响本地画像)。"""
    if not authorization:
        return
    def _do():
        try:
            _cloud_proxy("POST", "/social/persona/share", authorization,
                         {"data": data, "mbti": mbti})
        except Exception:
            pass
    import threading as _th
    _th.Thread(target=_do, daemon=True).start()

@app.post("/api/friend/request")
def friend_request_api(payload: dict = Body(...), authorization: str = Header(None)):
    """按手机号发好友请求(对方需同意)。"""
    _me(authorization)
    return _cloud_proxy("POST", "/social/friend/request", authorization, {"to": (payload.get("to") or "").strip()})

@app.get("/api/friend/requests")
def friend_requests_api(authorization: str = Header(None)):
    _me(authorization)
    return _cloud_proxy("GET", "/social/friend/requests", authorization)

@app.post("/api/friend/respond")
def friend_respond_api(payload: dict = Body(...), authorization: str = Header(None)):
    """同意/拒绝好友请求。同意=互为好友+双方可算姻缘。"""
    _me(authorization)
    return _cloud_proxy("POST", "/social/friend/respond", authorization,
                        {"from": (payload.get("from") or "").strip(), "accept": bool(payload.get("accept"))})

@app.get("/api/friend/list")
def friend_list_api(authorization: str = Header(None)):
    _me(authorization)
    return _cloud_proxy("GET", "/social/friend/list", authorization)

@app.post("/api/friend/remove")
def friend_remove_api(payload: dict = Body(...), authorization: str = Header(None)):
    _me(authorization)
    return _cloud_proxy("POST", "/social/friend/remove", authorization, {"other": (payload.get("other") or "").strip()})

def _fetch_friend_persona(authorization, other):
    """从云取已同意好友的画像(非好友返回 None)。"""
    try:
        r = _cloud_proxy("GET", "/social/friend/persona/" + _urlreq.quote(other), authorization)
        return r.get("data"), (r.get("mbti") or ""), (r.get("display") or other)
    except HTTPException:
        return None, "", other


@app.get("/api/account")
def api_account(authorization: str = Header(None), fresh: int = 0):
    """账号+授权(试用倒计时/付费墙用)。不门控:过期用户也要能读到自己状态。fresh=1 绕缓存。"""
    return _account_raw(authorization, fresh=bool(fresh))


@app.get("/api/plans")
def api_plans(authorization: str = Header(None)):
    return _cloud_proxy("GET", "/account/plans", authorization)


@app.post("/api/pay/create")
def api_pay_create(payload: dict = Body(...), authorization: str = Header(None)):
    _account_raw(authorization)   # 仅验证登录(不门控,过期才要付费)
    return _cloud_proxy("POST", "/account/pay/create", authorization, payload)


@app.get("/api/pay/query")
def api_pay_query(order_id: str, authorization: str = Header(None)):
    _account_raw(authorization)
    r = _cloud_proxy("GET", "/account/pay/query?order_id=" + order_id, authorization)
    if isinstance(r, dict) and r.get("status") == "paid":
        _bust_account_cache(authorization)   # 到账 → 立刻清缓存,后续所有接口秒见会员态
    return r


@app.get("/api/orders")
def api_orders(authorization: str = Header(None)):
    _account_raw(authorization)
    return _cloud_proxy("GET", "/account/orders", authorization)


@app.post("/api/orders/delete")
def api_orders_delete(payload: dict = Body(...), authorization: str = Header(None)):
    _account_raw(authorization)
    return _cloud_proxy("POST", "/account/orders/delete", authorization, payload)


def _own_doc(con, doc_id, me):
    """doc_id 是否归属当前用户(卡片/文档归属校验)。"""
    r = con.execute("SELECT owner FROM documents WHERE id=?", (doc_id,)).fetchone()
    return bool(r) and r[0] == me


def _owner_updir(owner):
    """按 owner 分目录的上传落盘目录(P0-5:防跨账号同名文件互相覆盖/owner劫持)。"""
    import re as _re
    d = os.path.join(UPLOADS, _re.sub(r"[^\w.-]", "_", owner or "_anon"))
    os.makedirs(d, exist_ok=True)
    return d

def _cos_emb(ba, bb):
    import struct
    if not ba or not bb:
        return None
    n = len(ba) // 4
    a = struct.unpack("%df" % n, ba); b = struct.unpack("%df" % (len(bb)//4), bb)
    return sum(x*y for x, y in zip(a, b))  # 已归一,点积=余弦

def _compat(a, b):
    # ★不同来源的画像结构可能不同:domains 元素可能是 dict{name} 或直接 str;thinking 可能是 dict 或字符串。
    #   全部防御性处理,否则跨用户合并/匹配时 'str'.get 崩(实测:云好友 bella 的 thinking 是字符串→合并全废)。
    def _dn(p):
        return "".join((d.get("name", "") if isinstance(d, dict) else str(d or "")) for d in (p.get("domains") or []))
    an = _dn(a); bn = _dn(b)
    ta = set(re.findall(r"..", an)); tb = set(re.findall(r"..", bn))
    ov = len(ta & tb) / max(1, min(len(ta), len(tb))) if ta and tb else 0
    at = a.get("thinking") or {}; bt = b.get("thinking") or {}
    if not isinstance(at, dict): at = {}
    if not isinstance(bt, dict): bt = {}
    td = 1 - (abs(at.get("depth", 50) - bt.get("depth", 50)) + abs(at.get("rational", 50) - bt.get("rational", 50))) / 200
    return round((ov * 0.6 + td * 0.4) * 100)

def _ensure_friends(con):
    con.execute("CREATE TABLE IF NOT EXISTS friendships (owner TEXT, friend TEXT, created TEXT, PRIMARY KEY(owner,friend))")

def _my_friends(con, me):
    _ensure_friends(con)
    return {r[0] for r in con.execute("SELECT friend FROM friendships WHERE owner=?", (me,)).fetchall()}

def _my_persona(con, me):
    r = con.execute("SELECT data,mbti FROM personas WHERE username=?", (me,)).fetchone()
    if r:
        return json.loads(r[0]), (r[1] or "")
    return {}, ""   # 无本人画像不回落全局/他人(P0-2 串号总闸修复)

@app.get("/api/people")
def people(authorization: str = Header(None)):
    me = _me(authorization)
    con = _con()
    try:
        # ★全新客户端:personas 表要带 emb 列(否则下句 SELECT emb 崩 no such column→前端误报"请先登录")
        con.execute("CREATE TABLE IF NOT EXISTS personas (username TEXT PRIMARY KEY, data TEXT, mbti TEXT, emb TEXT)")
        try: con.execute("ALTER TABLE personas ADD COLUMN emb TEXT")  # 老库补列
        except Exception: pass
        myp, _ = _my_persona(con, me)
        myrow = con.execute("SELECT emb FROM personas WHERE username=?", (me,)).fetchone()
        myemb = myrow[0] if myrow else None
        rows = con.execute("SELECT username,data,mbti,emb FROM personas WHERE username != ? AND username != 'kong'", (me,)).fetchall()
        friends = _my_friends(con, me)
        out = []
        for u, data, mbti, emb in rows:
            p = json.loads(data)
            cs = _cos_emb(myemb, emb)
            compat = round(max(0.0, cs) * 100) if cs is not None else _compat(myp, p)
            _rm = _user_profile(con, u)["mbti"]  # 真实填写优先,没填才用画像推断(前端据 mbti_real 诚实标注)
            _mbti_real = bool(_rm)
            out.append({"username": u, "display": p.get("display", u), "one_liner": p.get("one_liner", ""),
                        "tags": p.get("tags", []), "mbti": (_rm or mbti), "mbti_real": _mbti_real, "compat": compat,
                        "is_friend": u in friends})
        # ★合并云端好友(手机号加+对方同意的):他们的画像在云 shared_personas,拉进来才能在星云图显示+算姻缘。
        #   否则同意好友后本地不知情→星云图永远空(用户实测)。已在本地列表的标记 is_friend。
        try:
            _by = {o["username"]: o for o in out}
            fl = _cloud_proxy("GET", "/social/friend/list", authorization)
            for fr in (fl.get("friends") or []):
                fu = fr.get("username")
                if not fu or fu == me:
                    continue
                if fu in _by:
                    _by[fu]["is_friend"] = True
                    continue
                if not fr.get("has_persona"):
                    continue
                _pd, _pm, _pdisp = _fetch_friend_persona(authorization, fu)
                if not _pd:
                    continue
                _pp = _pd if isinstance(_pd, dict) else json.loads(_pd)
                out.append({"username": fu, "display": _pp.get("display", _pdisp or fu),
                            "one_liner": _pp.get("one_liner", ""), "tags": _pp.get("tags", []),
                            "mbti": _pm, "mbti_real": bool(_pm), "compat": _compat(myp, _pp), "is_friend": True})
        except Exception as _e:
            print(f"[people] 云好友合并: {_e}")
        out.sort(key=lambda x: -x["compat"])
        return {"me": me, "people": out}
    finally:
        con.close()

@app.post("/api/friend")
def friend_toggle(payload: dict = Body(...), authorization: str = Header(None)):
    me = _me(authorization)
    other = (payload.get("username") or "").strip()
    action = payload.get("action", "add")
    if not other:
        raise HTTPException(400, "缺少 username")
    con = _con()
    try:
        _ensure_friends(con)
        if action == "remove":
            con.execute("DELETE FROM friendships WHERE owner=? AND friend=?", (me, other))
            con.execute("DELETE FROM friendships WHERE owner=? AND friend=?", (other, me))
        else:
            ex = con.execute("SELECT 1 FROM users WHERE username=?", (other,)).fetchone()
            if not ex:
                try: ex = con.execute("SELECT 1 FROM users2 WHERE phone=?", (other,)).fetchone()
                except Exception: ex = None
            if not ex:
                # P1-02/P1-03:人物列表来自 personas(含种子用户/数字号),有画像即可加为好友
                try: ex = con.execute("SELECT 1 FROM personas WHERE username=?", (other,)).fetchone()
                except Exception: ex = None
            if not ex:
                raise HTTPException(404, "用户不存在")
            ts = _dt.datetime.now().isoformat(timespec="seconds")
            con.execute("INSERT OR IGNORE INTO friendships(owner,friend,created) VALUES(?,?,?)", (me, other, ts))
            con.execute("INSERT OR IGNORE INTO friendships(owner,friend,created) VALUES(?,?,?)", (other, me, ts))
        con.commit()
        return {"ok": True, "friends": sorted(_my_friends(con, me))}
    finally:
        con.close()

@app.get("/api/match/{other}")
def match(other: str, refresh: int = 0, authorization: str = Header(None)):
    me = _me(authorization)
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS match_cache (owner TEXT, other TEXT, data TEXT, PRIMARY KEY(owner,other))")
        if not refresh:
            c = con.execute("SELECT data FROM match_cache WHERE owner=? AND other=?", (me, other)).fetchone()
            if c:
                return {"cached": True, **json.loads(c[0])}
        pa, ma = _my_persona(con, me)
        if not pa:
            # P1-18:本人没画像就别发 LLM(会空耗 200s 产劣质报告)→ 让前端引导先完善画像
            return {"needs_persona": True, "other": other}
        # ★本地优先:对方画像先看本地(种子/老数据),没有就从云取"已同意好友"的画像(只共享AI画像非原文)。
        rb = con.execute("SELECT data,mbti FROM personas WHERE username=?", (other,)).fetchone()
        if rb:
            pb, mb = json.loads(rb[0]), (rb[1] or "")
        else:
            _cd, _cm, _ = _fetch_friend_persona(authorization, other)
            if not _cd:
                raise HTTPException(404, "还不能匹配:对方需先同意成为好友、且生成过画像")
            pb = _cd if isinstance(_cd, dict) else json.loads(_cd)
            mb = _cm
        # 真实填写的基础资料优先(MBTI 等绝不由 AI 编造):有真实填写就用真实的,没填就标未知
        _upa = _user_profile(con, me); _upb = _user_profile(con, other)
        ma_real = bool(_upa["mbti"]); mb_real = bool(_upb["mbti"])
        ma = _upa["mbti"] if ma_real else ma  # 真实优先覆盖 persona 推断
        mb = _upb["mbti"] if mb_real else mb
        def brief(p, mbti, up, mbti_real):
            return json.dumps({"一句话": p.get("one_liner"), "领域": [d.get("name") for d in p.get("domains", [])],
                               "思维": p.get("thinking"), "价值观": [v.get("trait") for v in p.get("values", [])],
                               "MBTI": ((mbti + "(本人真实填写)") if mbti_real else "未填(未知,不要编造)"),
                               "性别": (up["gender"] or "未填(未知)"), "年龄": (up["age"] or "未填(未知)"),
                               "星座": (up["zodiac"] or "未填(未知)")}, ensure_ascii=False)
        sysp = ("你在比较两个人的人格画像(都从真实知识/行为提炼)。生成一份比市面姻缘报告/MBTI配对深刻得多、有记忆点、能截图传播的匹配报告:有据、有冲突、有建议。"
                "铁律·真实不编造:性别/年龄/星座/MBTI 只以'本人真实填写'的为准;凡标注'未填/未知'的,一律当作未知,严禁编造或假装知道(尤其 MBTI,没填就不要在报告里断言 TA 是某型)。"
                "铁律:每个判断基于双方画像具体内容(点名领域/价值观),绝不空话套话;中文。只输出JSON:{"
                '"headline":"给你俩关系起一句有记忆点的定性标题(海报大标题,8-16字,如:理性灵魂的镜像之恋)",'
                '"archetype":{"name":"这段关系的原型2-6字(如:镜像者/共谋者/引路人/磁石/催化剂)","line":"一句话:为何是这个原型,点名双方具体特质"},'
                '"shadow":{"name":"压力下最易触发的阴影模式2-6字(如:各自为政/理性内耗/回避冲突)","line":"一句话:什么情境会触发、会表现成什么样"},'
                '"dimensions":[{"name":"思想同频","score":0到100},{"name":"视野互补","score":0到100},{"name":"价值观","score":0到100},{"name":"好奇共振","score":0到100},{"name":"表达节奏","score":0到100},{"name":"成长牵引","score":0到100}],'
                '"gap_insight":"全篇最有用的一句:找出维度间最大的落差,说清它意味着什么、怎么破(如:你俩思想同频92但表达节奏只54——想到一块却常各自沉默,先开口就是解药)",'
                '"resonance":["同频点:你俩共振在哪、会聊得来"],"complement":["互补点:不同但互补在哪"],'
                '"learn":["可互相学:谁在什么上更强、值得向对方请教"],'
                '"friction":["潜在磨合点:基于画像的具体冲突,别回避"],"advice":["相处/合作的可落地建议"],'
                '"love":{"score":0到100,"verdict":"一句姻缘定性","note":"恋爱视角:同频与冲突+磨合建议,基于画像别套话"},'
                '"mbti_line":"用双方MBTI说一句破冰配对趣话,再点出数据是否印证"}')
        usr = "甲(你):" + brief(pa, ma, _upa, ma_real) + "\n乙(TA):" + brief(pb, mb, _upb, mb_real)
        def _repair(s):
            s = re.sub(r"^```(?:json)?|```$", "", s.strip()).strip()
            s = re.sub(r",\s*([}\]])", r"\1", s)
            return s
        sysp2 = sysp + " 铁律:只输出一个合法 JSON 对象;字符串里若含引号一律用中文引号「」;不得有多余逗号,不要加注释或多余文字。"
        data = None; _err = None
        for _t in range(3):
            try:
                out = LLM.chat([{"role": "system", "content": sysp2}, {"role": "user", "content": usr}], temperature=0.5, max_tokens=2800)
                mm = re.search(r"\{.*\}", out, re.S)
                raw = mm.group(0) if mm else out
                try:
                    data = json.loads(raw)
                except Exception:
                    data = json.loads(_repair(raw))
                break
            except Exception as e:
                _err = e
        if data is None:
            raise HTTPException(400, "匹配生成失败: %s" % _err)
        data["other"] = other; data["display"] = pb.get("display", other)
        ea = con.execute("SELECT emb FROM personas WHERE username=?", (me,)).fetchone()
        eb = con.execute("SELECT emb FROM personas WHERE username=?", (other,)).fetchone()
        cs = _cos_emb(ea[0] if ea else None, eb[0] if eb else None)
        data["compat"] = round(max(0.0, cs) * 100) if cs is not None else _compat(pa, pb)
        data["mbti"] = mb; data["mbti_real"] = mb_real; data["my_mbti"] = ma; data["my_mbti_real"] = ma_real
        con.execute("INSERT OR REPLACE INTO match_cache(owner,other,data) VALUES(?,?,?)", (me, other, json.dumps(data, ensure_ascii=False)))
        con.commit()
        return {"cached": False, **data}
    finally:
        con.close()


import hashlib as _hashlib
import urllib.request as _urlreq
_GENIMG_DIR = os.path.join(os.environ.get("BRAIN_DATA", "/home/kb/brain"), "genimg")
os.makedirs(_GENIMG_DIR, exist_ok=True)
_MUSIC_DIR = os.path.join(os.environ.get("BRAIN_DATA", "/home/kb/brain"), "music")
_TTS_DIR = os.path.join(os.environ.get("BRAIN_DATA", "/home/kb/brain"), "tts")
os.makedirs(_TTS_DIR, exist_ok=True)

_VOICE_BOOK = {  # 声线与用户性别解绑: AI按画像+本片基调选, 每次生成可不同
    "温柔女声": ("zh-CN-XiaoxiaoNeural", "-6%", "+0Hz"),
    "清亮女声": ("zh-CN-XiaoyiNeural", "-4%", "+2Hz"),
    "爽朗女声": ("zh-CN-liaoning-XiaobeiNeural", "-2%", "+0Hz"),
    "软糯女声": ("zh-TW-HsiaoChenNeural", "-6%", "-2Hz"),
    "阳光男声": ("zh-CN-YunxiNeural", "-6%", "+0Hz"),
    "磁性男声": ("zh-CN-YunjianNeural", "-8%", "-4Hz"),
    "播音男声": ("zh-CN-YunyangNeural", "-6%", "-2Hz"),
    "书卷男声": ("zh-TW-YunJheNeural", "-4%", "+0Hz"),
    "少年":   ("zh-CN-YunxiaNeural", "-2%", "+4Hz"),
    "孩童":   ("zh-CN-YunxiaNeural", "+4%", "+12Hz"),
    "长者":   ("zh-CN-YunjianNeural", "-16%", "-12Hz"),
}

def _pick_voice(vkey, who):
    import hashlib as _hh
    vkey = (vkey or "").strip()
    if vkey in _VOICE_BOOK:
        return _VOICE_BOOK[vkey]
    for k in _VOICE_BOOK:               # 模糊匹配: LLM输出"温柔女"/"少年感"也认
        if k[:2] in vkey:
            return _VOICE_BOOK[k]
    items = sorted(_VOICE_BOOK.items()) # 兜底: 按人hash稳定分配
    _h = int(_hh.md5(("voice|" + str(who)).encode("utf-8")).hexdigest(), 16)
    return items[_h % len(items)][1]

def _tts_gen(text, gender, who="", slow=False, vkey=None):
    text = (text or "").strip()
    if not text:
        return None
    import hashlib as _hh
    voice, rate, pitch = _pick_voice(vkey, who)
    if slow:  # 片尾句更沉
        rate = "-12%"
    fn = _hh.md5((voice + rate + pitch + "|" + text).encode("utf-8")).hexdigest() + ".mp3"
    outp = os.path.join(_TTS_DIR, fn)
    if not os.path.exists(outp) or os.path.getsize(outp) < 500:
        try:
            import asyncio, edge_tts
            async def _go():
                await asyncio.wait_for(edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(outp), timeout=25)
            asyncio.run(_go())
        except Exception as e:
            print("[tts] fail:", e)
            try:
                if os.path.exists(outp):
                    os.remove(outp)
            except Exception:
                pass
            return None
        if not os.path.exists(outp) or os.path.getsize(outp) < 500:
            try:
                os.remove(outp)
            except Exception:
                pass
            return None
    return "/api/tts/" + fn

def _img_key():
    try:
        return json.load(open(os.path.join(os.environ.get("BRAIN_DATA", "/home/kb/brain"), "settings.json"))).get("image_key")
    except Exception:
        return None

import threading as _threading, time as _time
_COG_SEM = _threading.Semaphore(1)  # 免费档限并发 → 串行

def _cogview(prompt, size="1344x768"):
    """CogView-3-Flash 生成图 → 下载本地 → 返回我们域名路径(绕墙永久)。串行+429重试,缓存按哈希。"""
    key = _img_key()
    if not key or not prompt:
        return None
    h = _hashlib.md5((prompt + size).encode("utf-8")).hexdigest()
    fp = os.path.join(_GENIMG_DIR, h + ".jpg")
    if os.path.exists(fp) and os.path.getsize(fp) > 1000:
        return "/api/genimg/" + h + ".jpg"
    for attempt in range(4):
        try:
            with _COG_SEM:
                body = json.dumps({"model": "cogview-3-flash", "prompt": prompt[:900], "size": size}).encode("utf-8")
                req = _urlreq.Request("https://open.bigmodel.cn/api/paas/v4/images/generations", data=body,
                                      headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
                r = json.loads(_urlreq.urlopen(req, timeout=70).read())
                url = r["data"][0]["url"]
                img = _urlreq.urlopen(url, timeout=70).read()
                open(fp, "wb").write(img)
            return "/api/genimg/" + h + ".jpg"
        except Exception as e:
            code = getattr(e, "code", None)
            if code == 429 or "429" in str(e):
                _time.sleep(1.5 * (attempt + 1)); continue
            print("[cogview] fail:", e); return None
    return None

@app.get("/api/genimg/{name}")
def genimg(name: str):
    from fastapi.responses import FileResponse
    fp = os.path.join(_GENIMG_DIR, os.path.basename(name))
    if not os.path.exists(fp):
        raise HTTPException(404, "not found")
    return FileResponse(fp, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800"})

_GENVID_DIR = os.path.join(os.environ.get("BRAIN_DATA", "/home/kb/brain"), "genvid")
os.makedirs(_GENVID_DIR, exist_ok=True)

def _cogvideo(prompt):
    """CogVideoX-3 文生视频(异步:提交→轮询→下载mp4→返回我们域名路径)。串行(并发限1),缓存按哈希。"""
    key = _img_key()
    if not key or not prompt:
        return None
    h = _hashlib.md5(("vid:" + prompt).encode("utf-8")).hexdigest()
    fp = os.path.join(_GENVID_DIR, h + ".mp4")
    if os.path.exists(fp) and os.path.getsize(fp) > 10000:
        return "/api/genvid/" + h + ".mp4"
    try:
        with _COG_SEM:
            body = json.dumps({"model": "cogvideox-3", "prompt": prompt[:900], "quality": "quality",
                               "size": "1280x720", "fps": 30}).encode("utf-8")
            req = _urlreq.Request("https://open.bigmodel.cn/api/paas/v4/videos/generations", data=body,
                                  headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            sub = json.loads(_urlreq.urlopen(req, timeout=40).read())
            tid = sub.get("id")
            if not tid:
                return None
            url = None
            for _ in range(30):  # 最多 ~6 分钟
                _time.sleep(12)
                rq = _urlreq.Request("https://open.bigmodel.cn/api/paas/v4/async-result/" + tid,
                                     headers={"Authorization": "Bearer " + key})
                rr = json.loads(_urlreq.urlopen(rq, timeout=30).read())
                st = rr.get("task_status")
                if st == "SUCCESS":
                    vr = rr.get("video_result") or []
                    url = vr[0].get("url") if vr else None
                    break
                if st == "FAIL":
                    print("[cogvideo] task fail", tid); return None
            if not url:
                return None
            vid = _urlreq.urlopen(url, timeout=120).read()
            open(fp, "wb").write(vid)
        return "/api/genvid/" + h + ".mp4"
    except Exception as e:
        print("[cogvideo] fail:", e)
        return None


_MINIMAX_KEY_FILE = os.path.join(os.environ.get("BRAIN_DATA", "/home/kb/brain"), "minimax_key.txt")


def _minimax_key():
    try:
        return open(_MINIMAX_KEY_FILE).read().strip()
    except Exception:
        return None


def _minimax_image(prompt, ref_local_path=None):
    """MiniMax image-01 生成静图;传 ref 则用 subject_reference 锁人物+画风一致。返回 /api/genimg/xxx.jpg 或 None。"""
    key = _minimax_key()
    if not key:
        return None
    import base64 as _b64
    _rk = os.path.basename(ref_local_path) if (ref_local_path and os.path.exists(ref_local_path)) else ""
    h = _hashlib.md5(("mmimg:" + _rk + "|" + prompt).encode("utf-8")).hexdigest()
    fp2 = os.path.join(_GENIMG_DIR, h + ".jpg")
    if os.path.exists(fp2) and os.path.getsize(fp2) > 3000:
        return "/api/genimg/" + h + ".jpg"
    try:
        body = {"model": "image-01", "prompt": prompt[:1400], "aspect_ratio": "16:9", "response_format": "url", "n": 1}
        if ref_local_path and os.path.exists(ref_local_path):
            b64 = _b64.b64encode(open(ref_local_path, "rb").read()).decode()
            body["subject_reference"] = [{"type": "character", "image_file": "data:image/jpeg;base64," + b64}]
        req = _urlreq.Request("https://api.minimax.chat/v1/image_generation", data=json.dumps(body).encode("utf-8"),
                              headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        r = json.loads(_urlreq.urlopen(req, timeout=90).read())
        data = r.get("data") or {}
        urls = data.get("image_urls") or (data if isinstance(data, list) else [])
        if not urls:
            print("[mm img]", r.get("base_resp")); return None
        open(fp2, "wb").write(_urlreq.urlopen(urls[0], timeout=60).read())
        return "/api/genimg/" + h + ".jpg"
    except Exception as e:
        print("[mm img] err", e); return None


def _minimax_i2v(img_local_path, prompt):
    """MiniMax 图生视频:从静图长出视频(画风锁死),返回 /api/genvid/xxx.mp4 或 None。"""
    key = _minimax_key()
    if not key or not img_local_path or not os.path.exists(img_local_path):
        return None
    import base64 as _b64
    h = _hashlib.md5(("mm:" + os.path.basename(img_local_path) + prompt).encode("utf-8")).hexdigest()
    fp2 = os.path.join(_GENVID_DIR, h + ".mp4")
    if os.path.exists(fp2) and os.path.getsize(fp2) > 10000:
        return "/api/genvid/" + h + ".mp4"
    try:
        b64 = _b64.b64encode(open(img_local_path, "rb").read()).decode()
        body = json.dumps({"model": "I2V-01", "prompt": prompt[:400], "first_frame_image": "data:image/jpeg;base64," + b64}).encode("utf-8")
        req = _urlreq.Request("https://api.minimax.chat/v1/video_generation", data=body,
                              headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        r = json.loads(_urlreq.urlopen(req, timeout=60).read())
        tid = r.get("task_id")
        if not tid:
            print("[mm i2v] no task", r.get("base_resp")); return None
        for _ in range(30):
            _time.sleep(12)
            q = json.loads(_urlreq.urlopen(_urlreq.Request("https://api.minimax.chat/v1/query/video_generation?task_id=" + tid,
                                           headers={"Authorization": "Bearer " + key}), timeout=40).read())
            st = q.get("status")
            if st == "Success":
                fr = json.loads(_urlreq.urlopen(_urlreq.Request("https://api.minimax.chat/v1/files/retrieve?file_id=" + str(q.get("file_id")),
                                                headers={"Authorization": "Bearer " + key}), timeout=40).read())
                url = (fr.get("file") or {}).get("download_url")
                if not url:
                    return None
                open(fp2, "wb").write(_urlreq.urlopen(url, timeout=120).read())
                return "/api/genvid/" + h + ".mp4"
            if st == "Fail":
                print("[mm i2v] fail", tid); return None
        return None
    except Exception as e:
        print("[mm i2v] err", e); return None


_KLING_KEY_FILE = os.path.join(os.environ.get("BRAIN_DATA", "/home/kb/brain"), "kling_key.txt")


def _kling_key():
    try:
        return open(_KLING_KEY_FILE).read().strip()
    except Exception:
        return None


def _kling_i2v(img_local_path, prompt, tail_local_path=None):
    """Kling 图生视频;传 tail 则用首尾帧(本幕→下一幕),片段连成一条不再切。"""
    key = _kling_key()
    if not key or not img_local_path or not os.path.exists(img_local_path):
        return None
    import base64 as _b64
    _tk = os.path.basename(tail_local_path) if (tail_local_path and os.path.exists(tail_local_path)) else ""
    h = _hashlib.md5(("kling:" + os.path.basename(img_local_path) + "|" + _tk + "|" + prompt).encode("utf-8")).hexdigest()
    fp2 = os.path.join(_GENVID_DIR, h + ".mp4")
    if os.path.exists(fp2) and os.path.getsize(fp2) > 10000:
        return "/api/genvid/" + h + ".mp4"
    try:
        b64 = _b64.b64encode(open(img_local_path, "rb").read()).decode()
        _payload = {"model_name": "kling-v1-6", "image": b64, "prompt": prompt[:2000], "duration": "5", "mode": "std", "cfg_scale": 0.5}
        if tail_local_path and os.path.exists(tail_local_path):
            _payload["image_tail"] = _b64.b64encode(open(tail_local_path, "rb").read()).decode()
        body = json.dumps(_payload).encode("utf-8")
        req = _urlreq.Request("https://api.klingai.com/v1/videos/image2video", data=body,
                              headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        r = json.loads(_urlreq.urlopen(req, timeout=60).read())
        tid = (r.get("data") or {}).get("task_id")
        if not tid:
            print("[kling] no task", r.get("message")); return None
        for _ in range(45):
            _time.sleep(8)
            q = json.loads(_urlreq.urlopen(_urlreq.Request("https://api.klingai.com/v1/videos/image2video/" + str(tid),
                                           headers={"Authorization": "Bearer " + key}), timeout=40).read())
            d = q.get("data", {}); st = d.get("task_status")
            if st == "succeed":
                vids = (d.get("task_result") or {}).get("videos") or []
                url = vids[0].get("url") if vids else None
                if not url:
                    return None
                open(fp2, "wb").write(_urlreq.urlopen(url, timeout=120).read())
                return "/api/genvid/" + h + ".mp4"
            if st == "failed":
                print("[kling] fail", d.get("task_status_msg")); return None
        return None
    except Exception as e:
        print("[kling] err", e); return None

@app.get("/api/genvid/{name}")
def genvid(name: str):
    from fastapi.responses import FileResponse
    fp = os.path.join(_GENVID_DIR, os.path.basename(name))
    if not os.path.exists(fp):
        raise HTTPException(404, "not found")
    return FileResponse(fp, media_type="video/mp4", headers={"Cache-Control": "public, max-age=604800"})


_LIFE_GEN = set()   # P1-3:正在后台生成一生短片的 ckey


@app.get("/api/lifestory")
def lifestory(refresh: int = 0, style: str = "cinema", authorization: str = Header(None)):
    """诠释你一生:电影级旁白脚本 + 画风(cinema 电影 / pencil 手绘铅笔)。"""
    me = _me(authorization)
    style = "pencil" if style == "pencil" else "cinema"
    ckey = me if style == "cinema" else me + "|" + style
    _tp = os.path.join(os.environ.get("BRAIN_DATA", "/home/kb/brain"), "themes", me + ".mp3")
    _theme = ("/api/theme/" + me + ".mp3") if os.path.exists(_tp) else None
    _ffn = ("lifefilm_" + me + ".mp4") if style == "pencil" else ("lifefilm_cinema_" + me + ".mp4")
    _ffp = os.path.join(_GENVID_DIR, _ffn)
    _film = ("/api/genvid/" + _ffn + "?v=" + str(int(os.path.getmtime(_ffp)))) if os.path.exists(_ffp) else None
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS life_cache (username TEXT PRIMARY KEY, data TEXT)")
        if not refresh:
            c = con.execute("SELECT data FROM life_cache WHERE username=?", (ckey,)).fetchone()
            if c:
                return {"cached": True, "style": style, "theme_song": _theme, "film_url": _film, **json.loads(c[0])}
        if ckey in _LIFE_GEN:
            return {"generating": True, "style": style, "theme_song": _theme, "film_url": _film}
        # P1-13:空账号(没画像/没数据)直接回 empty,不启动生成线程 —— 否则每次轮询都重启 _build 又 bail = 永远转圈
        _p_chk, _ = _my_persona(con, me)
        if not _p_chk:
            return {"empty": True, "style": style, "theme_song": _theme, "film_url": _film}
        _LIFE_GEN.add(ckey)
        def _build():
            c2 = _con()
            try:
                p, mbti = _my_persona(c2, me)
                if not p:
                    return  # 原:raise HTTPException(400, "先去生成人格画像")
                _g, _a = _user_gp(c2, me)
                # 每月更新节奏:画像没有实质成长就"定格"上月的,不重新生成(省算力/省钱),前端挂"发芽"提示
                _pbrief = json.dumps({"o": p.get("one_liner"), "d": [dd.get("name") for dd in p.get("domains", [])], "v": [vv.get("trait") for vv in p.get("values", [])], "t": p.get("tags"), "c": p.get("curiosity")}, ensure_ascii=False, sort_keys=True)
                _phash = _hashlib.md5(_pbrief.encode("utf-8")).hexdigest()
                _oldrow = c2.execute("SELECT data FROM life_cache WHERE username=?", (ckey,)).fetchone()
                if _oldrow and not refresh:
                    _od = json.loads(_oldrow[0])
                    if _od.get("persona_hash") == _phash and _od.get("scenes"):
                        return {"cached": True, "frozen": True, "style": style, "theme_song": _theme, "film_url": _film, **_od}
                _up = _user_profile(c2, me)
                ctx = json.dumps({"一句话": p.get("one_liner"), "领域": [d.get("name") for d in p.get("domains", [])],
                                  "价值观": [v.get("trait") for v in p.get("values", [])], "在探索": p.get("curiosity"), "标签": p.get("tags"),
                                  "性别": (_up["gender"] or _g or "未标注,自行从画像推断"), "年龄": (_up["age"] or _a or "未标注"),
                                  "星座": (_up["zodiac"] or "未标注"), "MBTI": (_up["mbti"] or "未标注"),
                                  "自我介绍": (_up["bio"] or "")}, ensure_ascii=False)
                sysp = ("你是顶尖动画短片导演兼编剧。为某人创作一部【连续的微型动画短片】的分镜脚本 —— 不是散图、不是PPT、不是互不相干的意象,而是【一个完整的小故事】:同一个主角贯穿全片,有连续的情节、连续的动作、一致的人物形象、连贯递进的场景,像一部真正的动画电影。取材于TA真实人格画像。【最高目的·高于一切】这是送给TA一个人的温柔陪伴,要让TA感到被理解、被看见、被接住;诗意是为了抚慰情绪,不是炫技或冷淡;故事底下藏着对TA挣扎与孤独的共情,结尾给到温柔的安放与希望的余味,不煽情、不说教。"
                        "铁律一 反俗套:禁用励志鸡汤陈词(翻山越海、星辰大海、追梦、破茧、奔赴山海、点亮照亮 等)。"
                        "铁律二 连续性(最重要):6 个镜头讲【一个】完整故事,有起承转合;镜头之间必须能接上——上一镜结尾的场景与动作,自然过渡到下一镜开头(同一空间里的移动、或时间自然推进);主角在每一镜都在【做一个具体的、承接前后的连续动作】(不是静静站着)。"
                        "铁律三 人物一致:先定死一个固定主角形象(外形/穿着/发型/神态),之后每个镜头的 img 里都要【原样重复这段主角描述】,保证每一帧是同一个人、同一个世界。旁白克制有余味、不喊口号。中文。只输出JSON:"
                        '{"title":"不俗套的诗意片名","character":"英文:一句固定主角形象(具体外形/穿着/发型/神态,全片必须完全一致),例 a lean young man with short black hair and round glasses wearing a dark grey sweater, calm tired eyes","logline":"英文一句话故事梗概(连续剧情)","scenes":[{"name":"2-4字镜名","line":"一句克制诗意的中文旁白","img":"英文分镜prompt:先原样写出上面的 character 主角描述, 再写这一镜TA正在做的连续动作 + 与前后镜衔接的场景; storyboard cinematic shot, the exact same character throughout, coherent continuous location and story, artistic poetic"}],"closing":"结尾一句中文旁白","mood":"配乐流派,按这个人的气质从 epic(史诗)/calm(静谧)/uplift(明亮)/hiphop(嘻哈说唱)/funk(放克律动)/jazz(爵士)/electronic(电子)/lofi(慵懒lofi)/rock(摇滚)/guofeng(东方国风) 里选最贴的,只输出英文key","voice":"旁白声线,按这个人此刻的画像气质与本片基调从 温柔女声/清亮女声/爽朗女声/软糯女声/阳光男声/磁性男声/播音男声/书卷男声/少年/孩童/长者 里选一个(不必匹配用户性别: 男用户可配女声,沧桑的故事可配长者,童真的篇章可配孩童;每次生成允许不同)"}')
                _base = ("你是顶尖动画电影导演兼编剧,擅长用最朴素的画面讲最动人、人人都看得懂的故事(像《父与女》《回忆积木小屋》皮克斯短片那样——不懂任何专业的人也会看懂、会被打动)。为某个真实的人创作一部动画短片脚本,取材TA真实人格画像。"
                         "【最高目的·高于一切】这部片是送给TA一个人的温柔陪伴:让TA感到被理解、被看见、被轻轻接住;诗意是抚慰情绪的载体而非炫技或冷峻艺术腔,故事底下藏着对TA挣扎、疲惫与孤独的深深共情,结尾给到温柔的安放与一点希望的余味——像真正懂TA的朋友,不煽情、不说教、不喊口号,把TA说不出口的心事温柔地讲给TA听。"
                         "【尊重·与最高目的同等】画里是一个活生生、有尊严的真实的人,不是供你诊断、说教或改造的角色。严禁把TA写成孤独/可怜/冷漠/情感残缺,更严禁写成“冷漠理性的人终于学会了爱与感受”这类居高临下的救赎套路——那是对TA的不尊重。TA选择的生活方式、TA的秩序与专注本身就有尊严、值得珍视,不需要被“修好”。只从TA真实画像的material里长出故事,带着谦卑与平视:我们不替TA下结论、不替TA疗愈,只是看见TA、陪着TA、认出TA的不易与坚持里那份珍贵。共情是平等地认出,不是俯视的同情。"
                         "【读懂TA此刻的心境·因人而异,不一定都向上】动手前先真正读懂TA的画像与情绪状态,给TA此刻真正需要的东西——不是每个人都需要被鼓励“向上”。若TA正刻苦上进,就看见并珍视TA的不容易、努力与坚持,像懂TA的朋友为TA的每一分用功而心疼、骄傲、悄悄打气(“我看见你有多努力,这条路有多不容易,你的坚持很珍贵,你并不孤单”);若TA正压抑、疲惫、低落、困在原地,就千万不要催TA振作或奋斗,而是【温柔地安抚与陪伴】——静静接住TA的沉重,让它被看见、被理解、被允许(“你可以不用那么用力,累了就歇一会儿,我在这儿陪你,你已经很好了”)。该鼓励时鼓励,该安慰时就只是安慰。无论哪种,都用生活化、人人可感的画面来讲,不用任何专业术语。"
                         "【比TA更懂TA·最高洞察】不要停留在画像表面。要从TA真实收藏与亲手写下的material里,读出TA自己也未必说得清的内心与处境:刻苦背后的孤独、上进背后的自我怀疑与压力、坚持深处那个安静的渴望。然后用故事把它精准地说出来——说到TA心里那个一直没被说破的地方,让TA恍然“你怎么会知道?这就是我”。比TA更能懂TA的内心与处境,是这部片最深的力量。"
                         "【每一镜都是看得见的具体动作·铁律(最重要)】每一镜必须是主角正在做的一个【具体、清晰、一眼就能看懂的物理动作】(开灯、写字、把纸钉到墙上、揉皱纸团扔掉、起身、烧水、倒水、双手捧杯、揉眼睛、拉开窗帘…),配明确的道具和漫画动势线(水流、热气、涟漪、虚线弧、速度线),让观众一眼看出小人在干什么。【严禁】把抽象的、只在心里的、画不出清晰动作的状态单独做成一镜(如“听见自己的呼吸”“光从左边移到右边”“问自己还要多久”“水面还没平静”这类没有明确物理动作的,一律不要;要么换成一个具体动作,要么删掉)。"
                         "【一镜到底的连续·铁律】全片发生在【同一个地点】(他的书房/房间),时间自然推进(深夜→黎明);上一镜结束的动作和位置,自然引出下一镜的动作,像一台摄影机连续拍下来的,动作一个接一个不断裂。【严禁】突然跳到与这个房间无关的场景(如凭空出现的河流、马路、大海)——比喻也要发生在这个房间里(比如用“把揉皱的纸团一个个扔进纸篓”来表达反复尝试,而不是跳去河边扔石子)。让观众能顺着看下来,清楚每一步发生了什么、怎么一步步走到结尾。"
                         "【画面必须画出这句字·铁律】每一镜的 img 必须【直接画出这一镜 line 描述的那个画面】——line 说什么,画面就画什么,让观众读到的字和看到的画完全对应、一一对上。如果 line 是一个比喻(如“往河里投下石子”“拆解一座没有钥匙的锁”),就把这个比喻本身【当成真实画面画出来】(小人真的在河边扔石子、真的面对一把没有钥匙的大锁),绝不可以 line 写比喻、img 却画另一个字面场景(如敲电脑)。字画不对应是最大的失败。"
                         "【一抹亮色·点睛(签名手法,务必用)】全片基调保持克制的墨线/低饱和单色;唯独在整部片最动情的那一个转折镜头,让画面里承载情感的那个关键物件(一只气球、一盏灯、一个苹果、一片叶、一缕从窗缝漏进的光、一杯热茶的热气…)成为【全片唯一的一抹暖色】(温暖的红或琥珀黄)。这抹突然的色彩是全片情绪的高光,只此一处(至多两处),用在刀刃上,其余全部留白克制。请在被选中的那一个scene里:①line/story自然点到这个物件;②在该scene的img开头加上标记词 COLOR-ACCENT 并写明 the ONLY spot of warm color (red/amber) in an otherwise black-and-white ink frame is [那个物件]。只给一个scene加COLOR-ACCENT。"
                         "【第零原则·看得懂、有逻辑(压倒一切,高于诗意)】旁白必须是一个清晰、连贯、有逻辑的故事,一个普通人不用猜就能听懂:每一句都用平实、温暖的大白话,清楚地承接上一句、交代前因后果、把情节往前推一步;整段连起来是一条顺畅的故事线,不是零散的意象。严禁晦涩、跳跃、故弄玄虚的诗意碎片(像“风替他翻了一页”“散落的都是曾经紧握的”这种孤立起来谁都看不懂的句子,一律不要)。诗意必须服务于清楚,绝不能牺牲清楚——宁可朴素直白,也不要美丽却看不懂。观众听完,能顺畅地复述出这个故事讲了什么。"
                         "【诗意与故事性的取舍】看得懂、有逻辑是底线;但在看得懂的前提下,要保留恰到好处的诗意、画面感与余味——它是一个真实、可信、动人的故事(有具体的人、具体的事、具体的转变,像发生在现实里),同时读起来有美感、有回味。永远先保证【故事性与真实】,再让诗意为它加分;宁可故事扎实、诗意含蓄,也不要为了诗意牺牲故事。每一句都是这个真实故事里的一步,连起来是一条清楚又动人的线。"
                         "【第一原则·扎根TA真实具体的工作(最重要)】故事的场景和主角正在做的事,必须取材于TA【真实、具体的工作或钻研】(从画像里TA的领域、职业、在探索的东西来),要把它【具体地画出来】,让TA一眼认出“这就是我每天在做的事”。例如一个钻研金融、在建专业知识体系的人:深夜电脑屏幕上跳动的行情曲线和成片的数字、摊开的厚厚专业书、笔记本上密密麻麻的演算、一格一格搭建起来的知识笔记卡、反复推演一道算不通的题。【严禁】凭空发明一个和TA职业无关的活动来代替(比如把搞量化金融的人画成在墙上贴纸条、拉线的侦探破案板——那不是他的工作)。这是纠正过去“为去术语而翻译得太抽象、结果画成无关活动”的错误:画面要让人看出TA究竟是做什么行当、在忙什么具体的事;但旁白依然说人话、不堆砌专业术语。【第一原则·补·讲故事不讲专业】这是一个关于这个人内心的故事,不是TA的专业知识展示,更不是术语堆砌。必须把TA的职业与领域【彻底翻译成具体的生活画面、情感与人人可感的意象】——用物件、光线、天气、四季、一次迟到的拥抱、一杯凉掉的茶来讲,不用任何抽象概念。严禁出现任何专业术语、行话、公式或英文缩写(例如 R-square、波动率、息票、穿仓、随机游走、资产负债表、节点、封装、迭代 等,一律禁止,换成生活化的说法)。一个完全不懂TA行业的陌生人看完,必须能复述出:主角是谁、发生了什么事、内心经历了怎样的转变、最后到达了哪里。"
                         "【第二原则·完整且看得懂】先把故事讲完整、清晰、有诗意——镜头数是故事的结果不是前提,这是一部完整的短片,不是一首短诗——请用足够多的镜头(30到42个)把故事讲透讲满,不要吝惜篇幅。【中段最重要,必须厚】主角的挣扎、反复、试了又失败、情绪的起起落落,要一层一层、一件小事一件小事地充分铺开,有具体细节和小事件、有节奏递进(越来越难→濒临放弃→出现一个微小的转机),绝不能一笔带过、绝不能中间跳空缺失,让观众真切感到他到底经历了什么。【故事必须有完整的弧和真正的落点】要有一个清晰的情绪高潮或转折点,然后给到一个让人心里落定、被打动的结尾(有回响、有余味的收束),而不是戛然而止、不是又是平常的一天那样草草收场。观众看完要觉得讲完了、圆满了、被打动了。【结尾和最动情的几句必须说人话·铁律】结尾旁白和情绪最浓的那几句,必须是清楚、温暖、直接的大白话,像一个懂TA的人当面轻轻对TA说的话。严禁抽象格言、故弄玄虚的哲理警句、不知所云的对仗句(例如'它不需要被看懂,只需被你建成'这种让人反问是什么意思的话,一律不要)。要具体地看见TA今晚做了什么、点破TA的不容易、给到实实在在的看见、肯定与安慰,让TA听完心里一暖或鼻子一酸,而不是皱眉'这是什么意思'。宁可朴素直白到像一句家常话,也不要漂亮却空洞。清晰的故事弧:平常的TA → 一个具体的触发事件 → 内心的挣扎 → 一个低谷 → 一次微小而真实的转变 → 温柔的落点。每句旁白都能被听懂、有温度、并把故事往前推一步。"
                         "【第三原则·细致】每一镜都想清楚并写出:主角具体在做什么、为什么这么做(与上一镜的因果)、此刻内心的感受、画面里最关键的一两个视觉细节。宁可少而精,不空泛,不喊口号。反俗套,禁一切励志鸡汤(翻山越海/星辰大海/追梦/破茧 等)。"
                         "【第四原则·艺术性来自生活与感悟】真正的艺术性不来自华丽辞藻或聪明的概念游戏,而来自真实的生活细节、具体的生活质感、以及对生活的一点顿悟——从TA真实日常里的一个动作、一件旧物、一种光、一个季节里长出诗意与哲思,让观众在最普通的画面里忽然被击中、心头一软。")
                _ir = ("clean white paper, minimal black ink line-art, the SAME simple ink line figure (small round head, stick body, two dot eyes), Jimmy Liao doodle, flat 2D, no shading, no realism, no dark background" if style == "pencil" else "cinematic hand-drawn painterly frame, the exact same character throughout, coherent atmospheric world, artistic")
                sysp = _base + "严格输出合法JSON,字符串内引号用中文引号,不要多余逗号。只输出JSON:" + '{"title":"诗意片名","theme":"中文:这部片底下那个引人深思的追问或内核","character":"英文 主角 model sheet 固定不变","logline":"英文一句完整故事","scenes":[{"name":"2-4字镜名","line":"中文旁白 诗意克制可留白或无","story":"中文 这一镜发生了什么推进了什么 因果承接","action":"英文 主角具体动作表情","img":"英文分镜 ' + _ir + ' 主角这一镜的动作与场景 same figure throughout","camera":"英文运镜 motion 镜头运动加画面里在动的元素"}],"closing":"结尾中文 有回响","mood":"按人气质选配乐流派,只输出英文key: epic(史诗)/calm(静谧)/uplift(明亮)/hiphop(嘻哈说唱)/funk(放克律动)/jazz(爵士)/electronic(电子)/lofi(慵懒lofi)/rock(摇滚)/guofeng(东方国风)","voice":"旁白声线,按这个人此刻的画像气质与本片基调从 温柔女声/清亮女声/爽朗女声/软糯女声/阳光男声/磁性男声/播音男声/书卷男声/少年/孩童/长者 里选一个(不必匹配用户性别: 男用户可配女声,沧桑的故事可配长者,童真的篇章可配孩童;每次生成允许不同)"}'
                def _rep(x):
                    x = re.sub(r"^```(?:json)?|```$", "", x.strip()).strip()
                    return re.sub(r",\s*([}\]])", r"\1", x)
                data = None; _lerr = None
                for _t in range(4):
                    try:
                        out = LLM.chat([{"role": "system", "content": sysp}, {"role": "user", "content": ctx}], temperature=0.85, max_tokens=8000)
                        mm = re.search(r"\{.*\}", out, re.S); raw = mm.group(0) if mm else out
                        try:
                            data = json.loads(raw)
                        except Exception:
                            data = json.loads(_rep(raw))
                        break
                    except Exception as e:
                        _lerr = e
                if data is None:
                    return  # 原:raise HTTPException(400, "生成失败: %s" % _lerr)
                data["gender"] = _g
                data["persona"] = {"one_liner": p.get("one_liner"), "domains": p.get("domains", []), "tags": p.get("tags", []),
                                   "values": p.get("values", []), "curiosity": p.get("curiosity", [])}
                data["persona_hash"] = _phash
                data["generated_at"] = _dt.date.today().isoformat()
                # 先把脚本存下(秒返回);后台串行生成场景图,逐张写回 cache(前端轮询补上)
                c2.execute("INSERT OR REPLACE INTO life_cache(username,data) VALUES(?,?)", (ckey, json.dumps(data, ensure_ascii=False)))
                c2.commit()
                def _bg_imgs(_me, _data, _style):
                    char = _data.get("character", "")
                    scenes = _data.get("scenes", []) or []
                    def _save():
                        c2 = _con()
                        try:
                            c2.execute("INSERT OR REPLACE INTO life_cache(username,data) VALUES(?,?)", (_me, json.dumps(_data, ensure_ascii=False)))
                            c2.commit()
                        finally:
                            c2.close()
                    def _prompt(sc):
                        if _style == "pencil":
                            v = (sc.get("img") or sc.get("name") or "")
                            for w in ("cinematic film still", "dramatic lighting", "atmospheric", "dark", "darkness", "dim", "dimly", "night", "nocturnal", "shadow", "shadows", "moody", "noir", "chiaroscuro", "photographic", "realistic", "hyperrealistic", "rain", "raining", "smoke", "fog", "glowing", "neon"):
                                v = v.replace(w, "")
                            return (v + ", flat 2D hand-drawn black ink line-art on clean white paper, the EXACT SAME simple ink line figure (small round head, stick body, two dot eyes) throughout, Jimmy Liao 几米 storybook, minimal, no shading, no photographic realism, no dark background, consistent same figure and style")
                        return ((char + ". ") if char else "") + (sc.get("img") or sc.get("name") or "")
                    # narration audio (edge-tts, fast)
                    _gg = _data.get("gender", "")
                    _vk = _data.get("voice", "")
                    _ta = _tts_gen(_data.get("title", ""), _gg, who=me, vkey=_vk)
                    if _ta:
                        _data["title_audio"] = _ta
                    for sc in scenes:
                        _au = _tts_gen(sc.get("line", ""), _gg, who=me, vkey=_vk)
                        if _au:
                            sc["audio_url"] = _au
                    _cl = _tts_gen(_data.get("closing", ""), _gg, who=me, slow=True, vkey=_vk)
                    if _cl:
                        _data["closing_audio"] = _cl
                    _save()
                    # 第一遍:出图。首图当风格/人物参考锚点,其余用 MiniMax subject_reference 锁成同一支笔同一个人
                    _ref = None
                    for _j, sc in enumerate(scenes):
                        u = None
                        if _j > 0 and _ref and _minimax_key():
                            u = _minimax_image(_prompt(sc), _ref)
                        if not u:
                            u = _cogview(_prompt(sc))
                        if u:
                            sc["img_url"] = u; _save()
                            if _ref is None:
                                _ref = os.path.join(_GENIMG_DIR, os.path.basename(u))
                    # 第二遍:图生视频 优先 Kling(画质最高)> MiniMax > CogVideoX,都从静图长出锁画风
                    for _i, sc in enumerate(scenes):
                        v = None
                        ip = os.path.join(_GENIMG_DIR, os.path.basename(sc["img_url"])) if sc.get("img_url") else None
                        _tail = None
                        if _i + 1 < len(scenes) and scenes[_i + 1].get("img_url"):
                            _tail = os.path.join(_GENIMG_DIR, os.path.basename(scenes[_i + 1]["img_url"]))
                        _vp = sc.get("camera") or _prompt(sc)
                        if ip and _kling_key():
                            v = _kling_i2v(ip, _vp, _tail)
                        if not v and ip and _minimax_key():
                            v = _minimax_i2v(ip, _vp)
                        if not v:
                            try:
                                v = _cogvideo(_vp)
                            except Exception:
                                v = None
                        if v:
                            sc["vid_url"] = v
                        else:
                            sc["vid_failed"] = True
                        _save()
                    _data["videos_done"] = True
                    _save()
                _threading.Thread(target=_bg_imgs, args=(ckey, data, style), daemon=True).start()
                return {"cached": False, "generating_images": True, "style": style, "theme_song": _theme, "film_url": _film, **data}
            except Exception as _e:
                print("[lifestory] build fail:", _e)
            finally:
                _LIFE_GEN.discard(ckey)
                c2.close()
        _threading.Thread(target=_build, daemon=True).start()
        return {"generating": True, "style": style, "theme_song": _theme, "film_url": _film}
    finally:
        con.close()


# ★★谱曲在服务器(106 compound-brain)完成,客户端只转发(2026-08-30 修打包错搬):
#   设计=302 key 只在服务端(客户端绝不带 key),106 上 词稿→精修→Suno→themes 一体已做好且在用
#   (monthly_songs cron 即走它)。打包时错把本地谱曲(song_factory 直连 Suno)搬进客户端→
#   客户端无 key 必失败、前端永卡"谱曲中"。修=lifesong/song/make/status 转发 106,
#   谱好后把 mp3+歌词同步下载到本地 themes(mylibrary/播放照旧走本地,离线可听)。不改 106 一行。
_SONG_CLOUD = os.environ.get("SONG_CLOUD_URL", "http://106.14.189.104:8200")
_song_sync_lock = threading.Lock()

def _song_cloud_req(method, path, authorization, timeout=30):
    req = _urlreq.Request(_SONG_CLOUD + path, data=(b"" if method == "POST" else None),
                          headers={"Authorization": authorization or ""}, method=method)
    with _cloud_opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def _sync_cloud_songs(me, authorization):
    """把 106 上属于我的歌(mp3+歌词)拉到本地 themes,本地 mylibrary/播放即见。幂等,已有跳过。"""
    if not _song_sync_lock.acquire(blocking=False):
        return 0
    try:
        lib = _song_cloud_req("GET", "/api/mylibrary", authorization, timeout=20)
        os.makedirs(_THEMES_DIR, exist_ok=True)
        n = 0
        for s in (lib.get("songs") or []):
            fn = os.path.basename((s.get("url") or "").split("?")[0])
            if not (fn.endswith(".mp3") and fn.startswith(me)):
                continue
            dst = os.path.join(_THEMES_DIR, fn)
            if os.path.exists(dst):
                continue
            rq = _urlreq.Request(_SONG_CLOUD + "/api/theme/" + fn, headers={"Authorization": authorization or ""})
            with _cloud_opener.open(rq, timeout=120) as rr, open(dst, "wb") as f:
                f.write(rr.read())
            meta = {k: s.get(k) for k in ("title", "genre", "style", "lyrics", "need", "voice", "date") if s.get(k)}
            if meta:
                json.dump(meta, open(os.path.splitext(dst)[0] + ".lyrics.json", "w", encoding="utf-8"),
                          ensure_ascii=False, indent=1)
            n += 1
        return n
    except Exception as e:
        print("[song-sync]", str(e)[:120])
        return 0
    finally:
        _song_sync_lock.release()


@app.post("/api/song/make")
def song_make(force: int = 0, authorization: str = Header(None)):
    """成曲(服务端谱曲):转发 106 歌曲工厂。302 key 只在服务端,客户端不带。"""
    _me(authorization)   # 本地会员/鉴权门控照常
    try:
        return _song_cloud_req("POST", "/api/song/make" + ("?force=1" if force else ""), authorization)
    except _urlerr.HTTPError as e:
        try:
            detail = json.loads(e.read().decode()).get("detail", "")
        except Exception:
            detail = ""
        raise HTTPException(e.code, detail or "云端谱曲失败")
    except Exception:
        return {"started": False, "status": "error", "note": "谱曲服务连不上,请检查网络后重试"}


@app.get("/api/song/status")
def song_status(authorization: str = Header(None)):
    me = _me(authorization)
    try:
        st = _song_cloud_req("GET", "/api/song/status", authorization, timeout=15)
    except Exception:
        return {"status": "error", "note": "谱曲服务连不上,请检查网络"}
    if st.get("status") == "done":
        _sync_cloud_songs(me, authorization)   # 谱好→同步 mp3 到本地(幂等秒返),前端 loadLib 即见
    return st


@app.get("/api/lifesong")
def lifesong(refresh: int = 0, authorization: str = Header(None)):
    """按画像自动选曲风 + 写歌词,产出可直接丢进 Suno 的人生主题曲规格。
    ★词稿优先在 106 生成(song/make 从 106 的 song_cache 取词,词必须落在服务端才能成曲);
      106 连不上时回落本地生成(仅展示歌词用,成曲同样需要 106)。"""
    me = _me(authorization)
    try:
        return _song_cloud_req("GET", "/api/lifesong" + ("?refresh=1" if refresh else ""),
                               authorization, timeout=300)
    except Exception as _ce:
        print("[lifesong] 云端不可达,本地回落:", str(_ce)[:80])
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS song_cache (username TEXT PRIMARY KEY, data TEXT)")
        if not refresh:
            c = con.execute("SELECT data FROM song_cache WHERE username=?", (me,)).fetchone()
            if c:
                return {"cached": True, **json.loads(c[0])}
        p, mbti = _my_persona(con, me)
        if not p:
            raise HTTPException(400, "先去生成人格画像")
        _g, _a = _user_gp(con, me)
        life = con.execute("SELECT data FROM life_cache WHERE username=?", (me,)).fetchone()
        life_ctx = ""
        if life:
            ld = json.loads(life[0])
            life_ctx = " 已有的一生意象(可化用): " + ld.get("title", "") + " / " + " / ".join(s.get("line", "") for s in ld.get("scenes", []))
        _up = _user_profile(con, me)
        ctx = json.dumps({"一句话": p.get("one_liner"), "领域": [d.get("name") for d in p.get("domains", [])], "价值观": [v.get("trait") for v in p.get("values", [])], "标签": p.get("tags"), "性别": (_up["gender"] or _g), "年龄": (_up["age"] or ""), "星座": (_up["zodiac"] or ""), "MBTI": (_up["mbti"] or ""), "自我介绍": (_up["bio"] or "")}, ensure_ascii=False) + life_ctx
        sysp = ("你是顶尖词曲策划。为某人写一首人生主题曲的规格,直接可丢进 Suno 生成。"
                "铁律一 曲风按人定、要全面:从 港式经典/国语流行/民谣/美式乡村/摇滚/电子/嘻哈/古风/爵士/后摇/电影氛围 里,挑一个最贴合这个人气质的"
                "铁律一·补 人声也要按人千变万化、不要默认男声:根据这个人的气质,自由选择男声或女声,音色可以是清亮/低沉磁性/沙哑烟嗓/空灵/温柔/慵懒/有力,唱法可以是抒情/说唱/民谣吟唱/欧美流行快节奏/R&B/摇滚嘶吼 等——务必和曲风一起,在 style 里明确写出人声性别与音色(如 warm female vocal, husky raspy male vocal, airy female voice, energetic western pop female vocal 等),让不同的人听到完全不同性别与质感的声音。"
                "(极客冷静者可电影氛围或后摇;江湖豪迈者可摇滚或乡村;念旧深情者可港式经典;市井烟火者可国语流行),绝不千篇一律的欧式文艺。"
                "铁律二 反俗套:禁用励志鸡汤陈词(翻山越海、星辰大海、追梦、破茧 等)。歌词从 TA 真实的领域与思维里长出来,有意象、能唱、有记忆点、有副歌。"
                "铁律二·抽象化(重要):这是歌、不是聊天记录或流水账。【绝不直接堆砌】具体机构名/公司名/品牌/人名/专业术语/单据名/数字代号(如 农行、中行、报价单、存单、承兑、K线、某某项目 这类写实字眼一律不许原样出现在歌词里)。把这些工作与生活的细节升华成画面、情绪与隐喻——例如把「整天对农行中行报价」写成「替别人算清一笔笔账/深夜里跳动的数字/一通通没接完的电话」;把具体行业写成通感的场景与心境。歌词要抽象、留白、可共情,一个圈外人听了也能被打动,而不是只有 TA 自己看得懂那些行话。"
                "【最高目的】歌要能抚慰TA、让TA觉得被懂、被共情:副歌落在温柔的接纳与陪伴,像唱给TA一个人听,把TA的疲惫与坚持温柔唱出来,给到暖意与希望,不煽情、不喊口号。"
                "【读懂TA此刻的心境·因人而异,不一定都向上】先读懂TA真实的样子与情绪:若TA正刻苦上进,就让TA听到“我这么拼、这么难,有人看见了、懂了、在为我打气”,珍视TA的不容易与坚持、温柔鼓励向前;若TA正压抑、疲惫、低落,就不催TA奋斗,而是温柔安抚与陪伴,让TA觉得“累了可以歇,我在这儿陪你,你已经很好了”。平视不俯视、不说教;把心境写成生活化的画面与心声,不用专业术语行话。"
                "【比TA更懂TA·最高洞察】别停在表面。从TA真实收藏与书写的material里,读出TA自己都未必说得清的内心与处境(刻苦背后的孤独、上进背后的压力与自我怀疑、坚持深处的渴望),把它写进歌词最动人的那几句,让TA听到副歌时心里一震:“这就是我,你怎么会懂。”"
                "铁律三·歌名:起一个像真正流行歌的名字——意象化、有美感、留白、能勾起情绪。【绝不】用职业/行业/机构/专业术语/单据名当歌名(如 利率走廊、撮合者、报价单、存单 这种一看就是行话的名字一律不行)。从副歌的意象或最打动人的一句里凝练,2到6个字为佳(示范风格:把夜熬成微光 / 微光里的河 / 替两边取暖 / 还亮着的窗 / 熬夜的人 / 一个人的潮汐)。名字要让没听过歌的人也想点开。"
                "中文歌词(港式可用粤语字)。只输出JSON:"
                '{"title":"歌名(意象化、有美感,严禁行话/职业/术语)","genre":"中文一词概括曲风(如 电影氛围民谣/港式经典/美式乡村)","style":"给Suno的英文Style of Music一行:genre+人声+乐器+情绪,逗号分隔","lyrics":"完整歌词,用[Verse]/[Chorus]/[Bridge]/[Outro]分段,含副歌,能唱"}')
        def _rep(s):
            s = re.sub(r"^```(?:json)?|```$", "", s.strip()).strip()
            return re.sub(r",\s*([}\]])", r"\1", s)
        data = None; _err = None
        for _t in range(3):
            try:
                out = LLM.chat([{"role": "system", "content": sysp}, {"role": "user", "content": ctx}], temperature=0.85, max_tokens=1800)
                mm = re.search(r"\{.*\}", out, re.S); raw = mm.group(0) if mm else out
                try:
                    data = json.loads(raw)
                except Exception:
                    data = json.loads(_rep(raw))
                break
            except Exception as e:
                _err = e
        if data is None:
            raise HTTPException(400, "生成失败: %s" % _err)
        con.execute("INSERT OR REPLACE INTO song_cache(username,data) VALUES(?,?)", (me, json.dumps(data, ensure_ascii=False)))
        con.commit()
        return {"cached": False, **data}
    finally:
        con.close()



# ========== 手机号 + 短信验证码(开发模式:验证码直接返回;真短信接阿里云后关掉 dev) ==========
import random as _rand
SMS_DEV = os.environ.get("SMS_DEV", "1") == "1"   # 1=开发模式返回验证码;接入阿里云后设 0
def _ensure_sms(con):
    con.execute("CREATE TABLE IF NOT EXISTS users2 (phone TEXT PRIMARY KEY, nickname TEXT, created TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS sms_codes (phone TEXT PRIMARY KEY, code TEXT, exp INTEGER)")

@app.post("/api/auth/send_code")
def send_code(payload: dict = Body(...)):
    # 账号中心化:验证码由云端(106.189)真发(阿里云凭证只在云端)
    phone = (payload.get("phone") or "").strip()
    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        raise HTTPException(400, "请输入正确的手机号")
    r = _cloud_post("/account/sms/send", {"phone": phone})
    return {"sent": True, **({"dev_code": r["dev_code"]} if r.get("dev_code") else {})}

def _check_code(con, phone, code):
    row = con.execute("SELECT code,exp FROM sms_codes WHERE phone=?", (phone,)).fetchone()
    if not row or row[1] < _time.time() or not _hmac.compare_digest(row[0], (code or "").strip()):
        return False
    con.execute("DELETE FROM sms_codes WHERE phone=?", (phone,))
    return True

def _ensure_user_cols(con):
    for col in ("gender", "age", "zodiac", "mbti", "bio"):
        try: con.execute("ALTER TABLE users2 ADD COLUMN %s TEXT" % col)
        except Exception: pass


@app.on_event("startup")
def _bootstrap_auth_tables():
    """★全新客户端首启:确保本地资料表 users2/sms_codes 存在。
    否则密码登录(pwd_login)等直接查 users2 → no such table 崩(106上早建过所以没暴露)。"""
    try:
        _c = _con()
        _ensure_sms(_c)
        _ensure_user_cols(_c)
        # personas 带 emb 列(多处 SELECT emb FROM personas,老库/新库都补上,免 no such column)
        _c.execute("CREATE TABLE IF NOT EXISTS personas (username TEXT PRIMARY KEY, data TEXT, mbti TEXT, emb TEXT)")
        try: _c.execute("ALTER TABLE personas ADD COLUMN emb TEXT")
        except Exception: pass
        _c.commit()
        _c.close()
    except Exception:
        pass

def _user_profile(con, username):
    """用户【真实填写】的基础资料(来自 users2)。缺失即空串,绝不猜测。"""
    try:
        _ensure_user_cols(con)
        r = con.execute("SELECT gender,age,zodiac,mbti,bio FROM users2 WHERE phone=?", (username,)).fetchone()
        if not r:
            return {"gender": "", "age": "", "zodiac": "", "mbti": "", "bio": ""}
        return {"gender": (r[0] or ""), "age": (r[1] or ""), "zodiac": (r[2] or ""),
                "mbti": (r[3] or "").strip().upper(), "bio": (r[4] or "")}
    except Exception:
        return {"gender": "", "age": "", "zodiac": "", "mbti": "", "bio": ""}

def _user_gp(con, me):
    try:
        _ensure_user_cols(con)
        r = con.execute("SELECT gender,age FROM users2 WHERE phone=?", (me,)).fetchone()
        return ((r[0] or ""), (r[1] or "")) if r else ("", "")
    except Exception:
        return ("", "")

@app.post("/api/auth/phone_register")
def phone_register(payload: dict = Body(...)):
    # 云端验证码+建账号(ident=手机号);画像仍存本地 users2(phone=手机号=owner,天然一致)
    phone = (payload.get("phone") or "").strip(); code = payload.get("code") or ""; nick = (payload.get("nickname") or "").strip()
    gender = (payload.get("gender") or "").strip(); age = str(payload.get("age") or "").strip()
    zodiac = (payload.get("zodiac") or "").strip(); mbti = (payload.get("mbti") or "").strip().upper(); bio = (payload.get("bio") or "").strip()[:60]
    if len(nick) < 1: raise HTTPException(400, "请填昵称")
    r = _cloud_post("/account/sms/login", {"phone": phone, "code": code})
    con = _con()
    try:
        _ensure_sms(con); _ensure_user_cols(con)
        if con.execute("SELECT 1 FROM users2 WHERE phone=?", (phone,)).fetchone():
            con.execute("UPDATE users2 SET nickname=?,gender=?,age=?,zodiac=?,mbti=?,bio=? WHERE phone=?", (nick, gender, age, zodiac, mbti, bio, phone))
        else:
            con.execute("INSERT INTO users2(phone,nickname,gender,age,zodiac,mbti,bio,created) VALUES(?,?,?,?,?,?,?,datetime('now'))", (phone, nick, gender, age, zodiac, mbti, bio))
        con.commit()
    finally:
        con.close()
    return {"token": r["token"], "username": phone, "nickname": nick}

@app.post("/api/auth/phone_login")
def phone_login(payload: dict = Body(...)):
    phone = (payload.get("phone") or "").strip(); code = payload.get("code") or ""
    r = _cloud_post("/account/sms/login", {"phone": phone, "code": code})  # 云验证码+登录/建号
    con = _con()
    try:
        _ensure_sms(con)
        row = con.execute("SELECT nickname FROM users2 WHERE phone=?", (phone,)).fetchone()
        nick = (row[0] if row else None) or r.get("nickname") or phone[-4:]
        if not row:  # 本地画像表补一条(与云账号同 key = 手机号)
            con.execute("INSERT INTO users2(phone,nickname,created) VALUES(?,?,datetime('now'))", (phone, nick)); con.commit()
    finally:
        con.close()
    return {"token": r["token"], "username": phone, "nickname": nick}



# ========== 手机账号密码体系(设/改/重置/密码登录) ==========
def _pwd_make(pw: str) -> str:
    import hashlib as _h, os as _o
    salt = _o.urandom(12).hex()
    dk = _h.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt), 120000).hex()
    return "pbkdf2$" + salt + "$" + dk

def _pwd_check(pw: str, stored: str) -> bool:
    import hashlib as _h, hmac as _hm
    try:
        _, salt, dk = stored.split("$")
        cand = _h.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt), 120000).hex()
        return _hm.compare_digest(cand, dk)
    except Exception:
        return False

def _ensure_pwd_col(con):
    try:
        con.execute("ALTER TABLE users2 ADD COLUMN pwd TEXT")
        con.commit()
    except Exception:
        pass

_COMMON_PW = {"password","123456","12345678","123456789","111111","000000","qwerty","abc123",
              "iloveyou","admin","888888","666666","aa123456","woaini","5201314","a123456","123123","zxcvbnm"}


def _validate_password(pw):
    """服务端密码强度硬校验(核心隐私→不许弱口令)。前端也有强度条,这里兜底。"""
    pw = pw or ""
    if len(pw) < 8:
        raise HTTPException(400, "密码至少 8 位")
    low = pw.lower()
    if low in _COMMON_PW or any(c in low for c in _COMMON_PW):
        raise HTTPException(400, "密码太常见/太弱,请换一个(别用连号、常见词)")
    classes = sum([bool(re.search(r"[a-z]", pw)), bool(re.search(r"[A-Z]", pw)),
                   bool(re.search(r"\d", pw)), bool(re.search(r"[^A-Za-z0-9]", pw))])
    if classes < 2:
        raise HTTPException(400, "密码要混合字母/数字/符号中的至少两类")


@app.post("/api/auth/set_password")
def set_password(payload: dict = Body(...), authorization: str = Header(None)):
    """登录态设/改密码 → 云端(pv+1 吊销旧 token,返回新 token)。"""
    new = payload.get("new") or ""
    _validate_password(new)
    return _cloud_post("/account/set_password", {"password": new}, authorization)

@app.post("/api/auth/pwd_login")
def pwd_login(payload: dict = Body(...)):
    phone = (payload.get("phone") or "").strip()
    pw = payload.get("password") or ""
    r = _cloud_post("/account/login", {"username": phone, "password": pw})
    con = _con()
    try:
        row = con.execute("SELECT nickname FROM users2 WHERE phone=?", (phone,)).fetchone()
    finally:
        con.close()
    return {"token": r["token"], "username": phone, "nickname": (row[0] if row else None) or phone[-4:]}

@app.get("/api/auth/alipay/enabled")
def alipay_enabled():
    """支付宝扫码登录是否可用(云端没配 alipay.env 就 false,前端隐藏按钮)。"""
    try:
        r = _cloud_opener.open(_CLOUD + "/account/alipay/enabled", timeout=8)
        return json.loads(r.read().decode())
    except Exception:
        return {"enabled": False}

@app.get("/api/auth/alipay/login_url")
def alipay_login_url():
    r = _cloud_opener.open(_CLOUD + "/account/alipay/login_url", timeout=8)
    return json.loads(r.read().decode())

@app.post("/api/auth/alipay/bind")
def alipay_bind(payload: dict = Body(...)):
    """首次支付宝登录绑定手机号(票据+验证码)→ 云端。"""
    phone = (payload.get("phone") or "").strip()
    r = _cloud_post("/account/alipay/bind", {"ticket": payload.get("ticket") or "",
                                             "phone": phone, "code": payload.get("code") or ""})
    con = _con()
    try:
        row = con.execute("SELECT nickname FROM users2 WHERE phone=?", (phone,)).fetchone()
    finally:
        con.close()
    return {"token": r["token"], "username": phone,
            "nickname": (row[0] if row else None) or r.get("nickname") or phone[-4:]}

@app.post("/api/auth/reset_password")
def reset_password(payload: dict = Body(...)):
    """忘记密码:云端验证码校验后重置并直接登录。"""
    phone = (payload.get("phone") or "").strip()
    code = payload.get("code") or ""
    new = payload.get("new") or ""
    _validate_password(new)
    r = _cloud_post("/account/pwd_reset", {"phone": phone, "code": code, "password": new})
    con = _con()
    try:
        row = con.execute("SELECT nickname FROM users2 WHERE phone=?", (phone,)).fetchone()
    finally:
        con.close()
    return {"token": r["token"], "username": phone, "nickname": (row[0] if row else None) or phone[-4:]}


# ========== 头像(base64 data url,存库) ==========
@app.post("/api/avatar")
def set_avatar(payload: dict = Body(...), authorization: str = Header(None)):
    me = _me(authorization)
    dataurl = payload.get("dataurl") or ""
    if not dataurl.startswith("data:image") or len(dataurl) > 600000:
        raise HTTPException(400, "请上传图片(<400KB)")
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS avatars (username TEXT PRIMARY KEY, dataurl TEXT)")
        con.execute("INSERT OR REPLACE INTO avatars(username,dataurl) VALUES(?,?)", (me, dataurl))
        con.commit()
        return {"ok": True}
    finally:
        con.close()

@app.get("/api/avatars")
def get_avatars(users: str = "", authorization: str = Header(None)):
    _me(authorization)
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS avatars (username TEXT PRIMARY KEY, dataurl TEXT)")
        names = [u for u in (users or "").split(",") if u]
        if not names:
            return {"avatars": {}}
        q = ",".join("?" * len(names))
        rows = con.execute("SELECT username,dataurl FROM avatars WHERE username IN (%s)" % q, names).fetchall()
        return {"avatars": {r[0]: r[1] for r in rows}}
    finally:
        con.close()



@app.get("/api/auth/profile")
def auth_profile(authorization: str = Header(None)):
    me = _me(authorization)
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS users2 (phone TEXT PRIMARY KEY, nickname TEXT, created TEXT)")
        _ensure_user_cols(con)
        row = con.execute("SELECT nickname,created FROM users2 WHERE phone=?", (me,)).fetchone()
        g, a = _user_gp(con, me)
        _up = _user_profile(con, me)
        phone = me if (me or "").isdigit() else ""
        return {"username": me, "phone": phone, "nickname": (row[0] if row else me), "created": (row[1] if row else ""),
                "gender": g, "age": a, "zodiac": _up["zodiac"], "mbti": _up["mbti"], "bio": _up["bio"]}
    finally:
        con.close()

@app.post("/api/auth/update_profile")
def auth_update_profile(payload: dict = Body(...), authorization: str = Header(None)):
    me = _me(authorization)
    nick = (payload.get("nickname") or "").strip()
    gender = (payload.get("gender") or "").strip(); age = str(payload.get("age") or "").strip()
    zodiac = (payload.get("zodiac") or "").strip(); mbti = (payload.get("mbti") or "").strip().upper(); bio = (payload.get("bio") or "").strip()[:60]
    if len(nick) < 1 or len(nick) > 16:
        raise HTTPException(400, "昵称 1-16 字")
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS users2 (phone TEXT PRIMARY KEY, nickname TEXT, created TEXT)")
        _ensure_user_cols(con)
        # ★UPSERT:用户名账号从没建过 users2 行,纯 UPDATE 会影响0行→资料丢失。没行就插入。
        con.execute("INSERT INTO users2(phone,nickname,gender,age,zodiac,mbti,bio,created) "
                    "VALUES(?,?,?,?,?,?,?,datetime('now')) "
                    "ON CONFLICT(phone) DO UPDATE SET nickname=excluded.nickname,gender=excluded.gender,"
                    "age=excluded.age,zodiac=excluded.zodiac,mbti=excluded.mbti,bio=excluded.bio",
                    (me, nick, gender, age, zodiac, mbti, bio))
        con.commit()
        return {"ok": True, "nickname": nick, "gender": gender, "age": age, "zodiac": zodiac, "mbti": mbti, "bio": bio}
    finally:
        con.close()


def _recall_anchors(con, me):
    """主动回想/反遗忘:①周年回顾(N天前的今天入库过什么)②停滞目标(doing 但久无进展)③遗忘曲线该复习的笔记。
    返回喂给 /api/today 的文本线索,让'今日发现'有时间纵深。"""
    con.execute("CREATE TABLE IF NOT EXISTS card_status (card_id INTEGER PRIMARY KEY, status TEXT)")
    today = _dt.date.today()
    lines = []
    # ① 周年回顾:365/180/90/30/7 天前 ±1 天入库的材料/笔记
    for days, label in [(365, "一年前的今天"), (180, "半年前"), (90, "三个月前"), (30, "一个月前"), (7, "一周前")]:
        a = today - _dt.timedelta(days=days)
        try:
            rows = con.execute(
                "SELECT filename, backend FROM documents WHERE owner=? AND date(ingested_at) BETWEEN ? AND ? "
                "ORDER BY id DESC LIMIT 2",
                (me, (a - _dt.timedelta(days=1)).isoformat(), (a + _dt.timedelta(days=1)).isoformat())).fetchall()
        except Exception:
            rows = []
        for fn, bk in rows:
            kind = "笔记" if (bk or "").startswith("card:") else "材料"
            lines.append("[周年·%s] 你入库过%s《%s》" % (label, kind, (fn or "")[:40]))
    # ② 停滞目标:status=doing 且卡片入库 >14 天没动
    try:
        for (t,) in con.execute(
            "SELECT p.text FROM documents d JOIN pages p ON p.doc_id=d.id JOIN card_status s ON s.card_id=d.id "
            "WHERE d.owner=? AND d.backend LIKE 'card:%' AND s.status='doing' "
            "AND julianday('now')-julianday(d.ingested_at)>14 ORDER BY d.ingested_at ASC LIMIT 3", (me,)).fetchall():
            lines.append("[停滞目标·14天+无进展] %s" % ((t or "").strip()[:80]))
    except Exception:
        pass
    # ③ 遗忘曲线:重要笔记在 1/3/7/30 天锚点该复习
    try:
        for days in (1, 3, 7, 30):
            a = today - _dt.timedelta(days=days)
            for (t,) in con.execute(
                "SELECT p.text FROM documents d JOIN pages p ON p.doc_id=d.id "
                "WHERE d.owner=? AND d.backend LIKE 'card:%' AND date(d.ingested_at)=? ORDER BY d.id DESC LIMIT 1",
                (me, a.isoformat())).fetchall():
                lines.append("[该复习·%d天前记的] %s" % (days, (t or "").strip()[:70]))
    except Exception:
        pass
    # ④ 新旧自动连接:最近入库的东西和更早的旧材料高度相关 → 主动挑明(#3)
    try:
        recent = con.execute(
            "SELECT id, filename, ingested_at FROM documents WHERE owner=? AND date(ingested_at)>=date('now','-14 day') "
            "ORDER BY id DESC LIMIT 5", (me,)).fetchall()
        seen_pairs = set()
        for did, fn, ing in recent:
            for s in S.similar_docs(con, did, 6, owner=me):
                if s["score"] < 0.55 or s["doc_id"] == did:
                    continue
                orow = con.execute("SELECT filename, ingested_at FROM documents WHERE id=?", (s["doc_id"],)).fetchone()
                if not orow or (orow[1] or "") >= (ing or ""):   # 只连"更早入库"的旧材料
                    continue
                pair = tuple(sorted((did, s["doc_id"])))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                lines.append("[新旧连接·%d%%] 你最近存的《%s》和更早的《%s》其实是一回事,可以串起来" % (
                    int(s["score"] * 100), (fn or "")[:24], (orow[0] or "")[:24]))
                break   # 每个新 doc 只挑最强一条
    except Exception:
        pass
    return "\n".join(lines[:10])


@app.get("/api/media_structure")
def media_structure(doc_id: int, refresh: int = 0, authorization: str = Header(None)):
    """音视频转写 → LLM 结构化:章节 + 待办/决议 + 脑图(#6,对标通义听悟)。按 doc 缓存。"""
    me = _me(authorization)
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS media_structure (doc_id INTEGER PRIMARY KEY, data TEXT)")
        row = con.execute("SELECT backend FROM documents WHERE id=? AND owner=?", (doc_id, me)).fetchone()
        if not row:
            raise HTTPException(404, "文档不存在或无权限")
        if not (row[0] or "").startswith("asr:"):
            raise HTTPException(400, "该文档不是音视频转写")
        if not refresh:
            c = con.execute("SELECT data FROM media_structure WHERE doc_id=?", (doc_id,)).fetchone()
            if c:
                return {"cached": True, **json.loads(c[0])}
        txt = "\n".join(r[0] for r in con.execute(
            "SELECT text FROM pages WHERE doc_id=? ORDER BY page_no", (doc_id,)) if r[0])
        if not txt.strip():
            raise HTTPException(400, "转写为空")
        sysp = ("你是会议/音视频纪要助手。输入是一段**带时间戳**的转写(每行 [分:秒] 开头)。"
                "请输出结构化纪要,**只输出 JSON**:"
                '{"chapters":[{"time":"0:00","title":"章节标题","summary":"一句话小结"}],'
                '"todos":[{"text":"待办/决议/承诺","owner":"负责人或空"}],'
                '"mindmap":{"topic":"中心主题","branches":[{"name":"分支","points":["要点"]}]}}。'
                "章节按话题切 3-6 个、time 用该话题起始时间戳;todos 只抽明确的待办/决议;mindmap 提炼主干。"
                "中文,忠于原文、不编造。")
        usr = "转写:\n" + txt[:6000]
        try:
            out = LLM.chat([{"role": "system", "content": sysp}, {"role": "user", "content": usr}],
                           temperature=0.3, max_tokens=3500, model=LLM.fast_model())  # v4-flash thinking 吃 token,给足空间
            m = re.search(r"\{.*\}", out, re.S)
            data = json.loads(m.group(0)) if m else {"chapters": [], "todos": [], "mindmap": {}}
        except Exception:
            data = {"chapters": [], "todos": [], "mindmap": {}}
        try:
            con.execute("INSERT OR REPLACE INTO media_structure(doc_id,data) VALUES(?,?)",
                        (doc_id, json.dumps(data, ensure_ascii=False)))
            con.commit()
        except Exception:
            pass
        return {"cached": False, **data}
    finally:
        con.close()


@app.get("/api/today")
def today_feed(refresh: int = 0, authorization: str = Header(None)):
    """全局主动 AI:跨全脑发现今天值得用户知道/推进的 2-4 件事(含主动回想/反遗忘)。每日缓存。"""
    me = _me(authorization)
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS today_cache (username TEXT PRIMARY KEY, day TEXT, data TEXT)")
        day = _dt.date.today().isoformat()
        if not refresh:
            row = con.execute("SELECT day,data FROM today_cache WHERE username=?", (me,)).fetchone()
            if row and row[0] == day:
                return {"cached": True, **json.loads(row[1])}
        cards = con.execute("SELECT d.backend, p.text FROM documents d JOIN pages p ON p.doc_id=d.id WHERE d.owner=? AND d.backend LIKE 'card:%' ORDER BY d.id DESC LIMIT 30", (me,)).fetchall()
        recall = _recall_anchors(con, me)
        if not cards and not recall:
            return {"items": []}
        cardtxt = "\n".join("[%s] %s" % ((c[0].split(":",1)[1] if ":" in c[0] else "note"), (c[1] or "").strip()[:160]) for c in cards) or "(暂无卡片)"
        try:
            pdata, _ = _my_persona(con, me); one = pdata.get("one_liner", "")
        except Exception:
            one = ""
        sysp = ("你是用户的「第二大脑」。基于他的目标/日记卡片和整个知识库,**主动**发现 2-4 件今天最值得他知道或推进的事。"
                "★质量铁律:必须是高质量的真发现——他聊天/任务里提出的问题,在他的哪份文档/书/聊天里已经有答案或线索;他的目标,哪份资料现在就能推进它。"
                "浮于表面的'A和B有点像'不许出。每一件必须:①点名具体资料名/联系人名;②给出具体线索(引用一个具体的事实/数字/说法,不是转述);③说清他能得到什么;④给一个能立刻做的动作。"
                "若下面给了【答案线索】(他的任务与库里资料的语义匹配),优先做成'你在找的X,其实《某资料》里已经有——具体是…'型发现。"
                "若给了【回想线索】(周年回顾/停滞目标/该复习的旧笔记),可据此发起一件'主动回想'。"
                "中文,像真的懂他、主动关心他的伙伴,绝不套话空话。只输出JSON:"
                '{"items":[{"title":"短标题","insight":"我发现…(点名资料+具体线索)","gain":"你能得到什么","action":"一句主动提议(要我帮你做X吗)"}]}')
        usr = "他是:%s\n\n他的卡片(目标/日记):\n%s" % (one or "(未知)", cardtxt)
        if recall:
            usr += "\n\n【回想线索】(系统按周年/停滞/遗忘曲线自动浮出,请自然融入你的发现):\n" + recall
        try:
            _mine = {r[0] for r in con.execute("SELECT id FROM documents WHERE owner=?", (me,)).fetchall()}
            _ev = []
            for _c in cards[:5]:
                _q = (_c[1] or "").strip()[:120]
                if not _q:
                    continue
                for _s in S.retrieve(con, _q, topk=6):
                    if _s["doc_id"] not in _mine or _s.get("score", 0) < 0.45:
                        continue
                    _ev.append("你的卡片「%s…」 ↔ 《%s》第%s页:%s" % (
                        _q[:40], _s.get("filename", ""), _s.get("page_no", ""),
                        (_s.get("text", "") or "").replace("\n", " ")[:110]))
                    if len(_ev) >= 10:
                        break
                if len(_ev) >= 10:
                    break
            if _ev:
                usr += "\n\n【答案线索】(你的目标/任务 与 库里资料 的语义匹配——优先据此给出'你的问题其实已有答案'型发现,并注明出处):\n" + "\n".join(_ev)
        except Exception:
            pass
        try:
            _el = ENT.entity_links(con, me, 8)
            if _el:
                usr += "\n\n【实体线索】(同一个人/公司/项目/合同散落在多份资料里,可据此发现\"其实相关\"的联系):\n" + \
                       "\n".join("\u300c%s\u300d(%s) \u51fa\u73b0\u5728 %d \u4efd\u8d44\u6599" % (e["entity"], e.get("etype", ""), e["count"]) for e in _el)
        except Exception:
            pass
        try:
            out = LLM.chat([{"role": "system", "content": sysp}, {"role": "user", "content": usr}], temperature=0.6, max_tokens=1400, model=LLM.fast_model())
            m = re.search(r"\{.*\}", out, re.S)
            data = json.loads(m.group(0)) if m else {"items": []}
        except Exception:
            data = {"items": []}
        try:
            if data.get("items"):   # 空结果不写缓存,避免远端超时毒化后续全空(体检 P1)
                con.execute("INSERT OR REPLACE INTO today_cache(username,day,data) VALUES(?,?,?)", (me, day, json.dumps(data, ensure_ascii=False)))
                con.commit()
        except Exception:
            pass  # 缓存写不进(如撞锁)就不缓存, 数据照常返回, 绝不500
        return {"cached": False, **data}
    finally:
        con.close()


@app.get("/api/persona")
def persona(refresh: int = 0, authorization: str = Header(None)):
    """从你的第二大脑(读物清单+卡片)推断结构化人格画像,带证据、反巴纳姆。落库缓存(按账号)。"""
    me = _me(authorization)
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS personas (username TEXT PRIMARY KEY, data TEXT, mbti TEXT)")
        if not refresh:
            row = con.execute("SELECT data FROM personas WHERE username=?", (me,)).fetchone()
            if row:
                cd = json.loads(row[0])
                # ★自愈(P1-6):有微信数据但缓存是"纳入微信前"的旧版(无 social)→ 视为过期,落到下面重画
                has_wx = con.execute("SELECT 1 FROM documents WHERE owner=? AND filename LIKE '微信_与%' LIMIT 1", (me,)).fetchone()
                if cd.get("social") or not has_wx:
                    return {"cached": True, **cd}
        docs = con.execute("SELECT filename, pages FROM documents WHERE owner=? AND backend NOT LIKE 'card:%' ORDER BY pages DESC LIMIT 80", (me,)).fetchall()
        cards = con.execute("SELECT d.backend, p.text FROM documents d JOIN pages p ON p.doc_id=d.id WHERE d.owner=? AND d.backend LIKE 'card:%' ORDER BY d.id DESC LIMIT 40", (me,)).fetchall()
        # 微信聊天信号:用户真实的职业/社交圈,是画像最强的一层(不止读了什么书,更是天天在跟谁聊什么)
        wx_docs = con.execute("SELECT id FROM documents WHERE owner=? AND filename LIKE '微信_与%'", (me,)).fetchall()
        wx_ids = [r[0] for r in wx_docs]
        wechat_block, wx_contact_n, wx_topics = "", len(wx_ids), []
        if wx_ids:
            ph = ",".join("?" * len(wx_ids))
            wx_topics = [r[0] for r in con.execute(
                "SELECT name FROM kb_entities WHERE owner=? AND doc_id IN (%s) "
                "AND etype IN ('公司','机构','组织','项目','产品','话题','行业') "
                "GROUP BY norm ORDER BY SUM(mentions) DESC LIMIT 24" % ph, (me, *wx_ids)).fetchall()]
            idents = [r[0] for r in con.execute(
                "SELECT data FROM relationship_cards WHERE username=? ORDER BY msgcount DESC LIMIT 18", (me,)).fetchall()]
            id_lines = []
            for dj in idents:
                try:
                    o = json.loads(dj); s = (o.get("identity") or "").strip()
                    if s: id_lines.append(s[:70])
                except Exception:
                    pass
            wechat_block = ("\n\n微信聊天信号(共 %d 位联系人,这是TA真实的职业与社交世界):\n"
                            "· 高频机构/主题:%s\n· 部分联系人身份:\n%s" % (
                                wx_contact_n, "、".join(wx_topics[:20]) or "(暂无)",
                                "\n".join("  - " + x for x in id_lines[:14]) or "  (暂无)"))
        if not docs and not cards and not wx_ids:
            raise HTTPException(400, "知识库还是空的,先去入库")
        reading = "\n".join("《%s》(%s页)" % (d[0], d[1]) for d in docs) or "(暂无读物)"
        cardtxt = "\n".join("[%s] %s" % ((c[0].split(":",1)[1] if ":" in c[0] else "note"), (c[1] or "").strip()[:200]) for c in cards) or "(暂无卡片)"
        sysp = ("你是洞察力极强的人格分析师。下面是某人的「第二大脑」——TA真实收藏的读物、亲手写的卡片,"
                "以及TA微信里真实的聊天世界(跟谁聊、聊什么机构/主题)。"
                "请**只基于这些真实痕迹**推断一个**具体、有据、绝不套话**的人格画像。"
                "铁律:①每个判断都要能从下面读物/卡片/微信信号找到依据,禁止『你是爱思考的人』这种谁都适用的空话;"
                "②中文;③读物=关注什么/什么水平,微信高频机构主题=真实职业身份与所在行业,联系人身份=社交圈层——三者交叉印证;"
                "④若微信信号强烈指向某职业(如债券/同业/金融),one_liner 和 tags 要明确点出。"
                "⑤★evidence 里**绝不编造具体次数/份数**(如『重复三次』『读了5本』)——你数不准;要表达频次用『多次/反复/常』等定性词。"
                "⑥读物列表里若混进『微信_与…』这类聊天记录,不要当读物评价。"
                "只输出JSON:{"
                '"one_liner":"一句话精准画像(结合职业身份)",'
                '"domains":[{"name":"领域","weight":0-100,"evidence":"点名读物/卡片/微信机构主题的具体依据"}],'
                '"social":{"circle":"你的人脉与职业圈层一句话(基于微信联系人身份+高频机构)","evidence":"点名具体机构/联系人类型"},'
                '"thinking":{"depth":0-100,"rational":0-100,"note":"依据(depth:0极广度100极深挖; rational:0凭直觉100重数据理性)"},'
                '"values":[{"trait":"价值观/在意的东西","evidence":"具体依据"}],'
                '"curiosity":["当下在探索的方向"],"tags":["3-6个精准标签"]}')
        usr = "读物(按体量降序):\n" + reading + "\n\n卡片:\n" + cardtxt + wechat_block
        try:
            out = LLM.chat([{"role": "system", "content": sysp}, {"role": "user", "content": usr}], temperature=0.4, max_tokens=3000)  # 1600 会把画像 JSON 截断(体检 P0)
            m = re.search(r"\{.*\}", out, re.S)
            data = json.loads(m.group(0)) if m else {}
        except Exception as e:
            raise HTTPException(400, "画像生成失败(检查设置里的模型/key): %s" % e)
        data["doc_count"] = len(docs)
        data["card_count"] = len(cards)
        data["wechat_count"] = wx_contact_n
        dj = json.dumps(data, ensure_ascii=False)
        con.execute("INSERT OR IGNORE INTO personas(username, data) VALUES(?, ?)", (me, dj))
        con.execute("UPDATE personas SET data=? WHERE username=?", (dj, me))
        con.commit()
        # ★上传画像到云(供已同意好友算姻缘)。本地优先:数据在本地,只把画像这一份共享给云,
        #   且云端只让"已互为好友"的人取到(见 compound-server /social/friend/persona)。后台不阻塞。
        _share_persona_to_cloud(authorization, data, _user_profile(con, me).get("mbti") or "")
        return {"cached": False, **data}
    finally:
        con.close()


@app.post("/api/card/{card_id}/status")
def card_set_status(card_id: int, payload: dict = Body(...), authorization: str = Header(None)):
    me = _me(authorization)
    st = payload.get("status", "doing")
    con = _con()
    try:
        if not _own_doc(con, card_id, me):
            raise HTTPException(404, "没有这张卡片")
        con.execute("CREATE TABLE IF NOT EXISTS card_status (card_id INTEGER PRIMARY KEY, status TEXT)")
        con.execute("INSERT OR REPLACE INTO card_status(card_id,status) VALUES(?,?)", (card_id, st))
        con.commit()
        return {"ok": True, "status": st}
    finally:
        con.close()

@app.post("/api/card/{card_id}/edit")
def card_edit(card_id: int, payload: dict = Body(...), authorization: str = Header(None)):
    me = _me(authorization)
    content = (payload.get("content") or "").strip()
    title = (payload.get("title") or "").strip()   # ★与 create_card 一致:有 title 就用 title,别永远拿 content 前24字当标题
    if not content:
        raise HTTPException(400, "内容不能为空")
    con = _con()
    try:
        if not _own_doc(con, card_id, me):
            raise HTTPException(404, "没有这张卡片")
        fn = title or (content[:24] + ("…" if len(content) > 24 else ""))
        con.execute("UPDATE pages SET text=? WHERE doc_id=? AND page_no=1", (content, card_id))
        con.execute("UPDATE documents SET filename=? WHERE id=?", (fn, card_id))
        con.execute("DELETE FROM page_embeddings WHERE page_id IN (SELECT id FROM pages WHERE doc_id=?)", (card_id,))
        con.commit()
        try:
            S.embed_pending(con)
        except Exception:
            pass
        return {"ok": True, "title": fn}
    finally:
        con.close()


@app.delete("/api/card/{card_id}")
def delete_card(card_id: int, authorization: str = Header(None)):
    me = _me(authorization)
    con = _con()
    try:
        if not _own_doc(con, card_id, me):
            raise HTTPException(404, "没有这张卡片")
        # ★彻底清理:否则 SQLite 复用 rowid 后,旧卡的主动发现/向量会泄漏到新卡(串卡 bug)
        con.execute("DELETE FROM page_embeddings WHERE page_id IN (SELECT id FROM pages WHERE doc_id=?)", (card_id,))
        con.execute("DELETE FROM pages WHERE doc_id=?", (card_id,))
        con.execute("DELETE FROM card_msgs WHERE card_id=?", (card_id,))
        con.execute("DELETE FROM card_status WHERE card_id=?", (card_id,))
        con.execute("DELETE FROM documents WHERE id=? AND owner=? AND backend LIKE 'card:%'", (card_id, me))
        con.commit()
        return {"ok": True}
    finally:
        con.close()


_GEN_JOBS = {}   # 异步产出任务:job_id -> {state: running|done|error, result/error}

@app.post("/api/generate")
def gen(payload: dict = Body(...), authorization: str = Header(None)):
    """基于知识库检索的素材,生成 PPT/Word/Excel 真文件(异步:返回 job_id,前端轮询 /api/generate/status)。"""
    me = _me(authorization)
    topic = (payload.get("topic") or "").strip()
    fmt = payload.get("format", "ppt")
    theme = payload.get("theme", "deep")
    if not topic:
        raise HTTPException(400, "空主题")
    con = _con()
    try:
        mine = _my_ids(con, me)
        # ===== 交付物缓存:同主题+格式+模板+库没变化+当天 → 直接回上次生成的文件(全产品最贵调用,绝不重复烧)
        import hashlib as _hlib
        _sg = con.execute("SELECT COUNT(*), COALESCE(SUM(pages),0) FROM documents WHERE owner=?", (me,)).fetchone()
        _gk = _hlib.md5(("%s|%s|%s|%s:%s" % (topic, fmt, theme, _sg[0], _sg[1])).encode("utf-8")).hexdigest()
        con.execute("CREATE TABLE IF NOT EXISTS gen_cache(owner TEXT, k TEXT, day TEXT, data TEXT, PRIMARY KEY(owner,k))")
        _gr = con.execute("SELECT day, data FROM gen_cache WHERE owner=? AND k=?", (me, _gk)).fetchone()
        if _gr and _gr[0] == _dt.date.today().isoformat():
            _gd = json.loads(_gr[1])
            if os.path.exists(os.path.join(G.OUT_DIR, os.path.basename(_gd.get("file", "")))):
                _gd["cached"] = True
                return _gd
        srcs = [s for s in S.retrieve(con, topic, topk=40) if s["doc_id"] in mine][:10]
    finally:
        con.close()
    # ★异步任务:深度撰写+officecli 常 60-90s,而 Tauri WKWebView 有 ~60s 网络超时→同步请求必被掐断
    #   报"生成失败"(其实服务端产出了)。改成立即返 job_id、后台生成、前端轮询,彻底躲开超时。
    import uuid as _uuid
    jid = "gen-" + _uuid.uuid4().hex[:12]
    _GEN_JOBS[jid] = {"state": "running"}
    def _gen_work():
        try:
            tag = _dt.datetime.now().strftime("%m%d%H%M%S")
            r = G.generate(LLM, topic, srcs, fmt, tag, theme)
            _out = {**r, "url": f"/api/download/{r['file']}", "sources": srcs}
            try:
                _c3 = _con()
                try:
                    _c3.execute("INSERT OR REPLACE INTO gen_cache(owner,k,day,data) VALUES(?,?,?,?)",
                                (me, _gk, _dt.date.today().isoformat(), json.dumps(_out, ensure_ascii=False)))
                    _c3.commit()
                finally:
                    _c3.close()
            except Exception:
                pass
            _GEN_JOBS[jid] = {"state": "done", "result": _out}
        except Exception as e:
            _GEN_JOBS[jid] = {"state": "error", "error": str(e)}
    import threading as _th
    _th.Thread(target=_gen_work, daemon=True).start()
    return {"job_id": jid, "pending": True}


@app.get("/api/generate/status/{jid}")
def gen_status(jid: str, authorization: str = Header(None)):
    _me(authorization)
    j = _GEN_JOBS.get(jid)
    if not j:
        return {"state": "unknown"}
    if j["state"] == "done":
        return {"state": "done", **j["result"]}
    if j["state"] == "error":
        return {"state": "error", "error": j.get("error", "")}
    return {"state": "running"}


@app.get("/api/preview/{fname}")
def preview(fname: str):
    from fastapi.responses import FileResponse
    fp = os.path.join(G.OUT_DIR, os.path.basename(fname))
    if not os.path.exists(fp):
        raise HTTPException(404, "预览不存在")
    return FileResponse(fp, media_type="text/html")


@app.get("/api/download/{fname}")
def download(fname: str):
    from fastapi.responses import FileResponse
    p = os.path.join(G.OUT_DIR, os.path.basename(fname))
    if not os.path.exists(p):
        raise HTTPException(404, "文件不存在")
    return FileResponse(p, filename=fname)


@app.get("/api/music-list")
def music_list():
    out = {"epic": [], "calm": [], "uplift": []}
    try:
        for f in sorted(os.listdir(_MUSIC_DIR)):
            if f.endswith(".mp3") and "__" in f:
                out.setdefault(f.split("__", 1)[0], []).append("/api/music/" + f)
    except Exception:
        pass
    return out


@app.get("/api/music/{fname}")
def music_file(fname: str):
    from fastapi.responses import FileResponse
    p = os.path.join(_MUSIC_DIR, os.path.basename(fname))
    if not os.path.exists(p):
        raise HTTPException(404, "no music")
    return FileResponse(p, media_type="audio/mpeg")


@app.get("/api/tts/{fname}")
def tts_file(fname: str):
    from fastapi.responses import FileResponse
    p = os.path.join(_TTS_DIR, os.path.basename(fname))
    if not os.path.exists(p):
        raise HTTPException(404, "no tts")
    return FileResponse(p, media_type="audio/mpeg")


_THEMES_DIR = os.path.join(os.environ.get("BRAIN_DATA", "/home/kb/brain"), "themes")


@app.get("/api/theme/{fname}")
def theme_file(fname: str):
    from fastapi.responses import FileResponse
    p = os.path.join(_THEMES_DIR, os.path.basename(fname))
    if not os.path.exists(p):
        raise HTTPException(404, "no theme")
    return FileResponse(p, media_type="audio/mpeg")


# ========== 作品集:我的专辑(历史歌曲) + 我的故事集(历史动画短片) ==========
_songs_synced = set()   # 每进程每用户拉一次 106 历史歌(后台,不阻塞列表)

@app.get("/api/mylibrary")
def mylibrary(authorization: str = Header(None)):
    """当前用户的作品集:AI 为其一生谱写的历史歌曲 + 历史动画短片。"""
    me = _me(authorization)
    if me not in _songs_synced:   # 首次打开曲库→后台把 106 上已谱的历史歌同步到本地
        _songs_synced.add(me)
        threading.Thread(target=_sync_cloud_songs, args=(me, authorization), daemon=True).start()
    import time as _t
    def _ym(path):
        try:
            return _t.strftime("%Y-%m", _t.localtime(os.path.getmtime(path)))
        except Exception:
            return ""
    def _mt(path):
        try:
            return os.path.getmtime(path)
        except Exception:
            return 0.0

    # ---- 歌曲(专辑) ----
    songs = []
    song_meta = {}
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS song_cache (username TEXT PRIMARY KEY, data TEXT)")
        row = con.execute("SELECT data FROM song_cache WHERE username=?", (me,)).fetchone()
        if row:
            try:
                song_meta = json.loads(row[0])
            except Exception:
                song_meta = {}
    finally:
        con.close()

    # 用户名下全部主题曲(me*.mp3), 每首带歌词: sidecar .lyrics.json 优先, 否则 song_cache
    import glob as _glob
    ver = 0
    for fp in sorted(_glob.glob(os.path.join(_THEMES_DIR, me + "*.mp3")), key=_mt):
        fname = os.path.basename(fp)
        ver += 1
        entry = {
            "title": (song_meta.get("title") or "我的主题曲") + (" · 第%d版" % ver if ver > 1 else ""),
            "genre": song_meta.get("genre") or "",
            "style": song_meta.get("style") or "",
            "lyrics": song_meta.get("lyrics") or "",
            "date": _ym(fp),
            "url": "/api/theme/" + fname,
            "_ts": _mt(fp),
        }
        lyr_p = os.path.splitext(fp)[0] + ".lyrics.json"
        if os.path.exists(lyr_p):
            try:
                lj = json.load(open(lyr_p, encoding="utf-8"))
                entry["title"] = lj.get("title") or entry["title"]
                entry["style"] = lj.get("style") or entry["style"]
                entry["lyrics"] = lj.get("lyrics") or entry["lyrics"]
                entry["genre"] = lj.get("genre") or entry["genre"]
            except Exception:
                pass
        songs.append(entry)
    songs.sort(key=lambda s: s.get("_ts", 0), reverse=True)
    for s in songs:
        s.pop("_ts", None)

    # ---- 动画短片(故事集) ----
    life_titles = {}
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS life_cache (username TEXT PRIMARY KEY, data TEXT)")
        for _k in (me, me + "|pencil"):
            r = con.execute("SELECT data FROM life_cache WHERE username=?", (_k,)).fetchone()
            if r:
                try:
                    life_titles[_k] = (json.loads(r[0]) or {}).get("title") or ""
                except Exception:
                    pass
    finally:
        con.close()

    films = []
    film_defs = [
        ("pencil", "lifefilm_" + me + ".mp4", life_titles.get(me + "|pencil") or "", "铅笔手绘"),
    ]
    for mode, fname, title, modelabel in film_defs:
        fp = os.path.join(_GENVID_DIR, fname)
        if not os.path.exists(fp):
            continue
        films.append({
            "title": title or "我的一生",
            "mode": mode,
            "mode_label": modelabel,
            "date": _ym(fp),
            "url": "/api/genvid/" + fname,
            "poster": None,  # T430 无视频解码库,前端用 CSS 生成胶片海报
            "_ts": _mt(fp),
        })
    films.sort(key=lambda f: f.get("_ts", 0), reverse=True)
    for f in films:
        f.pop("_ts", None)

    return {"songs": songs, "films": films}



@app.get("/api/card/{card_id}/related")
def card_related(card_id: int, topk: int = 8, authorization: str = Header(None)):
    """一张卡片的关联历史:用卡片内容语义检索本账号库(排除自己)。"""
    me = _me(authorization)
    con = _con()
    try:
        if not _own_doc(con, card_id, me):
            raise HTTPException(404, "没有这张卡片")
        row = con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no LIMIT 1", (card_id,)).fetchone()
        content = row[0] if row else ""
        mine = _my_ids(con, me)
        # B-1:只留够相关的(短卡片会把随机聊天配成 57-60% 邻居,语义近但内容无关)。
        # 低于阈值宁可让前端显示"没找到明显相关"空态,也不硬塞错的匹配。
        REL_FLOOR = 0.62
        srcs = [s for s in S.retrieve(con, content, topk=40)
                if s["doc_id"] in mine and s["doc_id"] != card_id and (s.get("score") or 0) >= REL_FLOOR][:topk]
        con.execute("CREATE TABLE IF NOT EXISTS card_msgs (id INTEGER PRIMARY KEY, card_id INTEGER, content TEXT, created TEXT, read INTEGER DEFAULT 0)")
        msgs = [{"content": m[0], "created": m[1]} for m in con.execute("SELECT content,created FROM card_msgs WHERE card_id=? ORDER BY id", (card_id,)).fetchall()]
        con.execute("UPDATE card_msgs SET read=1 WHERE card_id=?", (card_id,)); con.commit()
        return {"card_id": card_id, "content": content, "related": srcs, "messages": msgs}
    finally:
        con.close()


@app.post("/api/ask")
def ask(payload: dict = Body(...), authorization: str = Header(None)):
    """针对卡片/问题:检索用户知识库 → LLM 基于原文作答(带来源)。"""
    me = _me(authorization)
    query = str(payload.get("query") or "").strip()
    history = payload.get("history") or []
    if not isinstance(history, list): history = []
    if not query:
        raise HTTPException(400, "空问题")
    con = _con()
    try:
        mine = _my_ids(con, me)
        contact = str(payload.get("contact") or "").strip()
        # ===== 执行缓存:同一问题 + 库没变化 + 当天 → 直接回上次结果(重复点卡不再重复烧钱等待)
        _ask_ck = None
        if not history:
            import hashlib as _hlib
            _sg = con.execute("SELECT COUNT(*), COALESCE(SUM(pages),0) FROM documents WHERE owner=?", (me,)).fetchone()
            _ask_ck = _hlib.md5((query + "|" + contact + "|%s:%s" % (_sg[0], _sg[1])).encode("utf-8")).hexdigest()
            con.execute("CREATE TABLE IF NOT EXISTS ask_cache(owner TEXT, k TEXT, day TEXT, data TEXT, PRIMARY KEY(owner,k))")
            _ar = con.execute("SELECT day, data FROM ask_cache WHERE owner=? AND k=?", (me, _ask_ck)).fetchone()
            if _ar and _ar[0] == _dt.date.today().isoformat():
                _ad = json.loads(_ar[1])
                _ad["cached"] = True
                return _ad
        if contact:
            # ★锁定到该联系人:只在TA的聊天会话 + TA的关系卡里检索,来源不再混入别人
            srcs = []
            row = con.execute("SELECT id FROM documents WHERE owner=? AND filename=?",
                              (me, "微信_与" + contact + ".txt")).fetchone()
            if row:
                did = row[0]
                qt = set(re.findall(r"[\w一-鿿]{2,}", query.lower()))
                pgs = con.execute("SELECT page_no, text FROM pages WHERE doc_id=? ORDER BY page_no", (did,)).fetchall()
                hit = [p for p in pgs if sum(1 for w in qt if w in (p[1] or "").lower())]
                pick = sorted(hit, key=lambda p: -sum(1 for w in qt if w in (p[1] or "").lower()))[:10] or pgs[:10]
                srcs = [{"doc_id": did, "page_no": p[0], "filename": "微信_与" + contact + ".txt",
                         "text": (p[1] or "")[:1400], "score": 1.0} for p in sorted(pick, key=lambda x: x[0])]
            rc = con.execute("SELECT data, doc_id FROM relationship_cards WHERE username=? AND contact=?",
                            (me, contact)).fetchone()
            if rc:
                try:
                    d = json.loads(rc[0]); parts = ["身份:" + (d.get("identity") or "")]
                    if d.get("facts"): parts.append("关键事实:" + "；".join((d.get("facts") or [])[:6]))
                    if d.get("open_loops"): parts.append("未了结:" + "；".join(d.get("open_loops") or []))
                    if d.get("favors"): parts.append("人情:" + "；".join(d.get("favors") or []))
                    srcs.insert(0, {"doc_id": rc[1], "page_no": 0, "filename": "人脉档案·" + contact,
                                    "text": ("；".join(parts))[:1000], "score": 0.99, "rel_card": True})
                except Exception:
                    pass
            rcards = []   # 联系人锁定模式:不做全局卡注入
        else:
            srcs = [s for s in S.retrieve(con, query, topk=40) if s["doc_id"] in mine][:8]
            # 实体级扩展(HippoRAG-lite):从语义命中的文档沿"共享实体"拉进相关资料,升到实体级检索
            try:
                have = {x["doc_id"] for x in srcs}
                expanded = set()
                for x in srcs[:3]:
                    for did in ENT.expand_via_entities(con, x["doc_id"], me, hops=1, cap=5):
                        expanded.add(did)
                for did in [d for d in expanded if d not in have][:3]:
                    row = con.execute(
                        "SELECT p.text, d.filename, p.page_no FROM pages p JOIN documents d ON d.id=p.doc_id "
                        "WHERE p.doc_id=? AND length(p.text)>60 ORDER BY length(p.text) DESC LIMIT 1", (did,)).fetchone()
                    if row:
                        srcs.append({"doc_id": did, "page_no": row[2], "filename": row[1],
                                     "text": row[0][:900], "score": 0.0, "via_entity": True})
            except Exception:
                pass
            # === 人脉档案注入:把提炼过的关系卡喂进检索(找人/找关联/总结才准)===
            rcards = con.execute(
                "SELECT contact, data, doc_id FROM relationship_cards WHERE username=?", (me,)).fetchall()
            if rcards:
                ql = query.lower()
                qterms = set(re.findall(r"[\w一-鿿]{2,}", ql))
                people_q = any(k in query for k in ("认识", "联系人", "人脉", "谁", "关系", "关联", "朋友",
                               "客户", "同业", "做什么", "对接", "帮我", "找人", "聊过", "聊了", "往来", "熟"))
                scored = []
                for contact, data, cdid in rcards:
                    try:
                        d = json.loads(data)
                    except Exception:
                        continue
                    blob = (contact + " " + (d.get("identity") or "") + " " + " ".join(d.get("facts") or [])
                            + " " + " ".join(d.get("open_loops") or []) + " " + " ".join(d.get("favors") or [])
                            + " " + (d.get("summary") or "")).lower()
                    sc = sum(1 for w in qterms if w in blob)
                    if contact.lower() in ql:
                        sc += 8
                    scored.append((sc, contact, d, cdid))
                scored.sort(key=lambda x: -x[0])
                hits = [s for s in scored if s[0] >= (1 if people_q else 4)][:6]
                if not hits and people_q:
                    hits = sorted(scored, key=lambda x: -(len(x[2].get("open_loops") or [])
                                  + len(x[2].get("facts") or [])))[:10]
                for sc, contact, d, cdid in hits:
                    parts = ["身份:" + (d.get("identity") or "")]
                    if d.get("facts"): parts.append("关键事实:" + "；".join((d.get("facts") or [])[:5]))
                    if d.get("open_loops"): parts.append("未了结:" + "；".join(d.get("open_loops") or []))
                    if d.get("favors"): parts.append("人情:" + "；".join(d.get("favors") or []))
                    if d.get("summary"): parts.append("概括:" + (d.get("summary") or ""))
                    card_txt = "联系人「" + contact + "」— " + "；".join(parts)
                    srcs.insert(0, {"doc_id": cdid, "page_no": 0, "filename": "人脉档案·" + contact,
                                    "text": card_txt[:1000], "score": 0.99, "rel_card": True})
    finally:
        con.close()
    context = "\n\n".join(
        f"【来源{i + 1}】{s['filename']} 第{s['page_no']}页:\n{s['text']}"
        for i, s in enumerate(srcs))
    system = ("你是用户的「第二大脑」,一个既深度了解用户、又有见识和判断力的私人助手。"
              "下面是从用户知识库里检索到的可能相关的资料。回答时:\n"
              "1) 凡是资料里有依据的事实,基于资料回答,并在该处用【来源N】标注出处,不要编造事实;\n"
              "2) 如果用户是在征求你的看法、判断、分析或建议,或者资料不足以回答,就**用你自己的知识和判断认真、有帮助地回答他**,"
              "别只甩一句'知识库里没有'。可以说明哪些是基于他的资料、哪些是你的分析。\n"
              "用中文,自然、诚恳、有洞察,像一个真正懂他的军师。**不要使用任何 emoji / 表情符号**;"
              "若产出文档,用清晰小标题分节,需要对比/清单时优先用 markdown 表格。\n\n"
              f"===== 用户知识库相关资料 =====\n{context}")
    messages = [{"role": "system", "content": system}]
    messages += history[-8:]
    messages += [{"role": "user", "content": query}]
    try:
        answer = LLM.chat(messages, max_tokens=8000, model=LLM.fast_model())   # 8000:产出文档/长答案不截断(用户要)
    except Exception as e:
        raise HTTPException(400, f"AI 调用失败(检查设置里的模型/key): {e}")
    if _ask_ck and (answer or "").strip():
        try:
            _c2 = _con()
            try:
                _c2.execute("INSERT OR REPLACE INTO ask_cache(owner,k,day,data) VALUES(?,?,?,?)",
                            (me, _ask_ck, _dt.date.today().isoformat(),
                             json.dumps({"answer": answer, "sources": srcs}, ensure_ascii=False)))
                _c2.commit()
            finally:
                _c2.close()
        except Exception:
            pass
    return {"answer": answer, "sources": srcs}


@app.get("/api/settings")
def get_settings(authorization: str = Header(None)):
    """返回当前 AI 配置(key 打码)。需登录态。"""
    _me(authorization)
    cfg = LLM.load_cfg()
    key = cfg.get("llm_key", "")
    return {
        "llm_provider": cfg.get("llm_provider", "deepseek"),
        "llm_base_url": cfg.get("llm_base_url", ""),
        "llm_model": cfg.get("llm_model", ""),
        "llm_fast_model": cfg.get("llm_fast_model", ""),
        "has_key": bool(key),
        "key_masked": (key[:5] + "…" + key[-4:]) if len(key) > 12 else ("已设置" if key else ""),
        "ocr_url": cfg.get("ocr_url", ""),   # 回填 OCR 地址(09-DEF-05)
    }


@app.post("/api/settings")
def save_settings(cfg: dict = Body(...), authorization: str = Header(None)):
    _me(authorization)   # P0-2:写配置必须登录(单一全局配置,防未授权改整站 AI 接口)
    cur = LLM.load_cfg()
    for k in ("llm_provider", "llm_base_url", "llm_model", "llm_fast_model"):
        if k in cfg:
            cur[k] = cfg[k]
    # key 只在传了非空值时更新(避免打码值覆盖真 key)
    if cfg.get("llm_key"):
        cur["llm_key"] = cfg["llm_key"]
    for _k in ("ocr_url",):  # OCR服务器地址(客户有百度强OCR填地址即用)
        if _k in cfg:
            cur[_k] = (cfg[_k] or "").strip()
    LLM.save_cfg(cur)
    return {"ok": True}


@app.post("/api/settings/test")
def test_settings(authorization: str = Header(None)):
    _me(authorization)   # P0-2:测试接口同样需登录
    return LLM.test_key()


@app.post("/api/embed")
def embed(authorization: str = Header(None)):
    """给还没嵌入的页补算向量(首次会加载模型,稍慢)。
    ★单飞锁:后台嵌入线程也用 _BG_EMBED_LOCK。若不加锁,手动 embed 会和后台线程同时各加载一份
    bge-m3(2.3G×2)→ 8G 机内存翻倍颠簸死(2026-08-29 事故:手动 embed 把 load 顶到 186)。
    正在嵌入时直接返回 busy,不再起第二份。"""
    _me(authorization)   # 写向量需登录
    if not _BG_EMBED_LOCK.acquire(blocking=False):
        return {"embedded_pages": 0, "busy": True, "detail": "后台正在嵌入,稍后自动完成"}
    try:
        con = _con()
        try:
            n = S.embed_pending(con)   # 按机器内存动态分档(embed_profile)
            return {"embedded_pages": n}
        finally:
            con.close()
    finally:
        _BG_EMBED_LOCK.release()


# ----------------------------- 入库任务(带进度)---------------------------
# 内存里的任务进度表。job_id -> 进度 dict。前端轮询 /api/job/{id} 画进度条。
JOBS: dict = {}
_job_lock = threading.Lock()
_job_seq = 0


def _new_job(total_files: int, backend: str) -> str:
    global _job_seq
    with _job_lock:
        _job_seq += 1
        jid = f"job{_job_seq}"
    JOBS[jid] = {
        "id": jid, "phase": "queued", "backend": backend,
        "files_total": total_files, "file_index": 0, "current_file": None,
        "page": 0, "page_total": 0,
        "results": [], "embedded_pages": 0, "error": None,
        "started_at": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    return jid


def _warm_owner_caches(owner):
    """A3:入库后台预热 —— 重建文库归类 + 星海(默认 medium grain=chunk14)缓存,下次打开秒开。"""
    if not owner:
        return
    try:
        con = _con()
        try:
            try:
                _doc_topics_cached(con)   # 文库归类(全局缓存)
            except Exception as e:
                print("[warm-owner] topics:", e)

            def _build():
                g = S.chunk_graph(con, chunk_pages=14, k=6, clusters=14, owner=owner)
                mine = _my_ids(con, owner)
                keep = {n["id"] for n in g["nodes"] if n.get("doc_id") in mine}
                g["nodes"] = [n for n in g["nodes"] if n["id"] in keep]
                g["edges"] = [e for e in g["edges"] if e["source"] in keep and e["target"] in keep]
                return g
            _db_cached(con, owner, "starmap:14:6:14", _build)   # 星海(默认档)
        finally:
            con.close()
    except Exception as e:
        print("[warm-owner]", e)


def _run_ingest_job(jid: str, saved: list, backend: str, dpi: int, owner: str = None):
    job = JOBS[jid]
    job["owner"] = owner
    con = _con()
    try:
        export_root = I.DEFAULT_EXPORT if backend == "unlimited" else None
        bk = B.make_backend(backend, export_root)
        job["phase"] = "ingesting"
        for fi, path in enumerate(saved):
            job["file_index"] = fi + 1
            job["current_file"] = os.path.basename(path)
            job["page"], job["page_total"] = 0, 0

            def cb(done, total, _job=job):
                _job["page"], _job["page_total"] = done, total

            r = I.process_any(con, bk, path, I.DEFAULT_VAULT, dpi,
                              force=True, progress_cb=cb)
            row = con.execute(
                "SELECT id, pages FROM documents WHERE source_path=?", (path,)).fetchone()
            if owner and row:   # 数据归属登录用户(多租户隔离)
                con.execute("UPDATE documents SET owner=? WHERE source_path=? AND (owner IS NULL OR owner=?)", (owner, path, owner))
                con.commit()
                try:
                    _etxt = "\n".join(r[0] for r in con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no LIMIT 6", (row[0],)))
                    ENT.extract_doc_entities(con, row[0], owner, _etxt)
                except Exception:
                    pass
            job["results"].append({"file": os.path.basename(path), "status": r,
                                   "doc_id": row[0] if row else None,
                                   "pages": row[1] if row else 0})
        bk.finalize(I.DEFAULT_VAULT)
        if os.environ.get("AUTO_EMBED", "1") == "1":
            job["phase"] = "embedding"
            try:
                job["embedded_pages"] = S.embed_pending(con)
            except Exception as e:
                print(f"[job {jid}] 自动嵌入跳过: {e}")
        _oks = [x for x in job.get("results", []) if x.get("status") == "ok"]
        if job.get("results") and not _oks:
            job["phase"] = "error"
            job["error"] = "所有文件都没能入库(格式不支持/内容为空/识别失败)"
        else:
            job["phase"] = "done"
            if owner:   # A3:入库成功 → 后台预热星海/文库缓存(不阻塞任务返回)
                threading.Thread(target=_warm_owner_caches, args=(owner,), daemon=True).start()
        job["finished_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    except Exception as e:
        job["phase"] = "error"
        job["error"] = str(e)
    finally:
        con.close()


@app.post("/api/upload")
async def upload(
    files: list[UploadFile] = File(...),
    backend: str = Query("auto"),
    dpi: int = Query(200),
    authorization: str = Header(None),
):
    """上传 PDF → 起后台入库任务,立刻返回 job_id;前端轮询 /api/job/{id} 看进度。数据归属登录用户。"""
    owner = _me(authorization)
    if backend not in BACKENDS:
        raise HTTPException(400, f"未知后端 {backend},可选 {BACKENDS}")

    # 落盘要在 async 上下文里 await 读取
    saved = []
    for f in files:
        if not (f.filename or "").lower().endswith(I.DOC_EXTS):
            continue
        dest = os.path.join(_owner_updir(owner), os.path.basename(f.filename))
        with open(dest, "wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append(dest)
    if not saved:
        raise HTTPException(400, f"没有可入库文档(支持 {'/'.join(I.DOC_EXTS)})")

    jid = _new_job(len(saved), backend)
    threading.Thread(target=_run_ingest_job, args=(jid, saved, backend, dpi, owner),
                     daemon=True).start()
    return {"job_id": jid, "files_total": len(saved)}


def _fetch_url(url: str, owner=None) -> str:
    """把网址变成本地文件: 视频站(B站/抖音/YouTube等)用yt-dlp拉, 其余直链按类型落盘。按 owner 分目录。"""
    import re as _re
    import urllib.request as _u
    _updir = _owner_updir(owner)
    import socket as _sock, ipaddress as _ipa
    try:  # SSRF 防护(P2-2):拒绝内网/回环/元数据地址
        _host = _re.sub(r"^https?://", "", url).split("/")[0].split(":")[0].split("@")[-1]
        _ip = _ipa.ip_address(_sock.gethostbyname(_host))
        if _ip.is_private or _ip.is_loopback or _ip.is_link_local or _ip.is_reserved or _ip.is_multicast:
            raise HTTPException(400, "不允许抓取内网/本地地址")
    except HTTPException:
        raise
    except Exception:
        pass
    vid_sites = ("bilibili.com", "b23.tv", "youtube.com", "youtu.be", "douyin.com",
                 "ixigua.com", "v.qq.com", "xiaoyuzhoufm.com")
    if any(h in url for h in vid_sites):
        try:
            import yt_dlp
        except Exception:
            raise HTTPException(400, "当前版本暂不支持视频链接抓取(缺 yt-dlp)。可直接粘贴网页/文章链接。")
        # ★ffmpeg 路径:优先用打进包的 _MEIPASS/bin(officecli 同款定位),回落系统 PATH。
        #   (旧代码硬编码 /home/kb/brain/bin 服务器路径→客户端 Mac 上必崩,视频永远抓不了)
        import sys as _sys2
        _binroot = os.path.join(getattr(_sys2, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "bin")
        opts = {"outtmpl": os.path.join(_updir, "%(title).60s.%(ext)s"),
                "format": "bv*[height<=720]+ba/b[height<=720]/b",
                "merge_output_format": "mp4", "quiet": True, "noplaylist": True,
                "max_filesize": 800 * 1024 * 1024}
        if os.path.isfile(os.path.join(_binroot, "ffmpeg")) or os.path.isfile(os.path.join(_binroot, "ffmpeg.exe")):
            opts["ffmpeg_location"] = _binroot   # 打包内有就用它;否则不设→yt_dlp 自己找 PATH
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=True)
            pth = y.prepare_filename(info)
            base = os.path.splitext(pth)[0]
            for ext in (".mp4", ".mkv", ".webm", ".m4a", ".mp3"):
                if os.path.exists(base + ext):
                    return base + ext
            return pth
    req = _u.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    r = _u.urlopen(req, timeout=15)
    ct = (r.headers.get("Content-Type") or "").split(";")[0].strip()
    ext = os.path.splitext(url.split("?")[0])[1].lower()
    if not ext or len(ext) > 6:
        ext = {"text/html": ".html", "application/pdf": ".pdf", "image/png": ".png",
               "image/jpeg": ".jpg", "image/webp": ".webp", "audio/mpeg": ".mp3",
               "video/mp4": ".mp4", "text/plain": ".txt"}.get(ct, ".html")
    name = _re.sub(r"[^\w\u4e00-\u9fff.-]", "_", os.path.basename(url.split("?")[0]) or "网页")[:60]
    if not name.lower().endswith(ext):
        name += ext
    dest = os.path.join(_updir, name)
    with open(dest, "wb") as f:
        f.write(r.read(300 * 1024 * 1024))
    return dest


@app.post("/api/upload_url")
def upload_url(payload: dict = Body(...), authorization: str = Header(None)):
    """扔个网址进来 → 下载 → 走同一条入库job管线(前端照常轮询job)。数据归属登录用户。"""
    owner = _me(authorization)
    url = (payload.get("url") or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(400, "请给一个 http(s) 链接")
    jid = _new_job(1, "auto")
    def _go(jid=jid, url=url, owner=owner):
        job = JOBS[jid]
        try:
            job["phase"] = "ingesting"
            job["current_file"] = "下载中: " + url[:50]
            path = _fetch_url(url, owner)
            _run_ingest_job(jid, [path], "auto", 200, owner)
        except Exception as e:
            job["phase"] = "error"
            job["error"] = "抓取失败: " + str(e)[:200]
    threading.Thread(target=_go, daemon=True).start()
    return {"job_id": jid, "files_total": 1}


@app.get("/api/job/{job_id}")
def job_status(job_id: str, authorization: str = Header(None)):
    me = _me(authorization)
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "没有这个任务")
    if job.get("owner") and job["owner"] != me:
        raise HTTPException(404, "没有这个任务")
    return job


# 前端静态构建挂在 /app(存在才挂,构建前不影响 API)
_DIST = os.path.join(ROOT, "web", "frontend", "dist")
if os.path.isdir(_DIST):
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse as _FR
    # SPA 入口 index.html 永不缓存 → 每次都取到最新构建(带 hash 的 assets 仍可长缓存)
    # 必须在 mount 之前注册,才能优先于 StaticFiles 命中这些精确路径
    def _spa_index():
        return _FR(os.path.join(_DIST, "index.html"), media_type="text/html",
                   headers={"Cache-Control": "no-store, must-revalidate"})
    app.add_api_route("/app", _spa_index, include_in_schema=False)
    app.add_api_route("/app/", _spa_index, include_in_schema=False)
    app.add_api_route("/app/index.html", _spa_index, include_in_schema=False)
    app.mount("/app", StaticFiles(directory=_DIST, html=True), name="frontend")
# 自有安装包下载中心(微信同步助手三平台包等):/dl/<文件名>
_DL_DIR = os.path.join(os.environ.get("BRAIN_DATA", "/home/kb/brain"), "downloads")
if os.path.isdir(_DL_DIR):
    from fastapi.staticfiles import StaticFiles as _SF2
    app.mount("/dl", _SF2(directory=_DL_DIR), name="downloads")


@app.get("/api/model_status")
def model_status():
    """首启模型下载进度(Windows 瘦身版:大模型首次启动下载,下完全离线)。
    Mac 全打进包 → 检测都在 → 立即 done。前端 ModelDownload.jsx 轮询此端点。"""
    try:
        import model_bootstrap as _mb
        return _mb.start_if_needed()
    except Exception as e:
        # 任何异常都不能卡死首屏:报 done 让 App 正常进入(模型缺了到用时再懒下载兜底)
        return {"modules": {}, "overall_pct": 100, "done": True, "eta": "", "speed": "", "error": str(e)}


@app.get("/go/wechat-export")
def _go_wechat_export():
    """指路牌:跳转到第三方微信导出工具官网。我们只给指针、不托管安装包。
    目标可在 settings.json 的 wechat_tool_url 改,改完立即生效、前端无需重发版。"""
    cfg = LLM.load_cfg()
    url = (cfg.get("wechat_tool_url") or "https://daochu.qingxia.cn/").strip()
    return RedirectResponse(url, status_code=302)


if __name__ == "__main__":
    import uvicorn
    # 本机产品默认 127.0.0.1;服务器(T430)用 WEB_HOST=0.0.0.0 供局域网访问
    uvicorn.run(app, host=os.environ.get("WEB_HOST", "127.0.0.1"),
                port=int(os.environ.get("WEB_PORT", "8200")))

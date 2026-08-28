#!/usr/bin/env python3
"""
Unlimited-OCR 本地入库工具
==========================

选一个文件夹 → 自动读取里面所有 PDF → 逐页转成文本 → 同时写入:
  1) 本地 SQLite 库(带全文检索,可秒搜)   → library.db
  2) Obsidian 风格 markdown(每份 PDF 一个 .md,每页一个小节) → vault/

处理策略(默认 auto 后端):每页先抽 PDF 文字层(数字版秒出),
抽不到(扫描件)才走本地轻量 OCR。以后有 GPU / 大内存,可切到
百度 Unlimited-OCR 后端(见 backends.py 与 gpu_notebook/)。

用法:
  python ingest.py                       # 弹出文件夹选择框,选完即开跑
  python ingest.py ~/some/folder         # 直接处理指定文件夹
  python ingest.py ~/f --backend rapidocr
  python ingest.py ~/f --backend unlimited   # 导出图片给免费 GPU notebook
  python ingest.py --search 关键词           # 在本地库里全文检索
  python ingest.py --stats                   # 查看库里已入库统计
"""
from __future__ import annotations
import argparse
import datetime as _dt
import hashlib
import os
import re
try:
    import pysqlite3 as sqlite3   # 内置 sqlite>=3.34,支持 trigram 分词(系统 sqlite 3.26 不支持,写 pages_fts 会崩)
except Exception:
    import sqlite3
import subprocess
import sys
import glob

import backends as B

HOME = os.path.expanduser("~")
ROOT = os.path.join(HOME, "unlimited-ocr")
# 路径可用环境变量覆盖:同一套代码,本机跑用默认,T430/服务器跑指到大盘 /home
DATA_ROOT = os.environ.get("BRAIN_DATA", ROOT)
DEFAULT_DB = os.environ.get("BRAIN_DB", os.path.join(DATA_ROOT, "library.db"))
DEFAULT_VAULT = os.environ.get("BRAIN_VAULT", os.path.join(DATA_ROOT, "vault"))
DEFAULT_EXPORT = os.environ.get("BRAIN_EXPORT", os.path.join(DATA_ROOT, "gpu_export"))


# ----------------------------- 本地数据库 ----------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY,
    source_path TEXT UNIQUE,
    filename    TEXT,
    pages       INTEGER,
    backend     TEXT,
    file_hash   TEXT,
    ingested_at TEXT,
    owner       TEXT
);
CREATE TABLE IF NOT EXISTS pages (
    id      INTEGER PRIMARY KEY,
    doc_id  INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    page_no INTEGER,
    method  TEXT,
    text    TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts
    USING fts5(text, content='pages', content_rowid='id');
-- 触发器:pages 变动时同步全文索引
CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
    INSERT INTO pages_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, text) VALUES('delete', old.id, old.text);
END;
"""


def db_connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")   # 撞锁等 30s 而非报错
    con.execute("PRAGMA journal_mode=WAL")      # 边写边读不互锁(批处理+web并发)
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    # ★★全新客户端一次建全 106 的全部业务表(45张),避免运行时一个个撞 no such table/column。
    #   schema_full.sql 与本模块同目录(冻结后在 _MEIPASS)。
    try:
        _base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        _sf = os.path.join(_base, "schema_full.sql")
        if not os.path.exists(_sf):
            _sf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema_full.sql")
        if os.path.exists(_sf):
            con.executescript(open(_sf, encoding="utf-8").read())
    except Exception:
        pass
    # 老库迁移:早期建的 documents 没 owner 列(106 后加的),补上
    try:
        con.execute("ALTER TABLE documents ADD COLUMN owner TEXT")
    except Exception:
        pass
    return con


def file_hash(path: str) -> str:
    """按 路径+大小+修改时间 生成指纹,用于跳过没变过的文件(快,不读全文件)。"""
    st = os.stat(path)
    h = hashlib.sha1()
    h.update(path.encode())
    h.update(str(st.st_size).encode())
    h.update(str(int(st.st_mtime)).encode())
    return h.hexdigest()


def already_ingested(con, path, fhash) -> bool:
    row = con.execute(
        "SELECT file_hash FROM documents WHERE source_path=?", (path,)
    ).fetchone()
    return row is not None and row[0] == fhash


# ----------------------------- 处理一份 PDF --------------------------------
def process_pdf(con, backend: B.BaseBackend, pdf_path: str, vault_dir: str,
                render_dpi: int, force: bool = False, progress_cb=None, open_path=None):
    import fitz

    fhash = file_hash(pdf_path)
    if not force and already_ingested(con, pdf_path, fhash):
        print(f"  ⏭  已入库,跳过: {os.path.basename(pdf_path)}")
        return "skipped"

    try:
        doc = fitz.open(open_path or pdf_path)  # azw3 转出的 epub 用 open_path
    except Exception as e:
        print(f"  ⚠️  打不开,跳过: {os.path.basename(pdf_path)} ({e})")
        return "error"

    n = len(doc)
    print(f"  📄 {os.path.basename(pdf_path)}  ({n} 页)")

    # 旧记录先清掉(文件变了要重来)
    con.execute("DELETE FROM documents WHERE source_path=?", (pdf_path,))
    cur = con.execute(
        "INSERT INTO documents(source_path,filename,pages,backend,file_hash,ingested_at)"
        " VALUES(?,?,?,?,?,?)",
        (pdf_path, os.path.basename(pdf_path), n, backend.name, fhash,
         _dt.datetime.now().isoformat(timespec="seconds")),
    )
    doc_id = cur.lastrowid

    method_counts: dict[str, int] = {}
    md_parts = [
        "---",
        f"source: {pdf_path}",
        f"pages: {n}",
        f"backend: {backend.name}",
        f"ingested: {_dt.datetime.now().isoformat(timespec='seconds')}",
        "---",
        "",
        f"# {os.path.splitext(os.path.basename(pdf_path))[0]}",
        "",
    ]

    for i in range(n):
        page = doc[i]
        try:
            text, method = backend.markdown_for_page(page, i, doc, render_dpi)
        except Exception as e:
            text, method = f"<!-- 第 {i+1} 页处理失败: {e} -->", "error"
        method_counts[method] = method_counts.get(method, 0) + 1
        con.execute(
            "INSERT INTO pages(doc_id,page_no,method,text) VALUES(?,?,?,?)",
            (doc_id, i + 1, method, text),
        )
        md_parts.append(f"## Page {i + 1}")
        md_parts.append("")
        md_parts.append(text if text.strip() else "*(本页无文本)*")
        md_parts.append("")
        sys.stdout.write(f"\r     进度 {i+1}/{n}")
        sys.stdout.flush()
        if progress_cb:
            try:
                progress_cb(i + 1, n)
            except Exception:
                pass
    print()  # 换行
    doc.close()

    # 写 markdown
    os.makedirs(vault_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    md_path = os.path.join(vault_dir, stem + ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_parts))

    con.commit()
    summary = ", ".join(f"{k}×{v}" for k, v in method_counts.items())
    print(f"     ✅ 入库完成  [{summary}]  → {os.path.relpath(md_path, HOME)}")
    return "ok"


# ----------------------------- 处理 Office / 文本 --------------------------
def process_office(con, pdf_path: str, vault_dir: str, force: bool = False,
                   progress_cb=None):
    """Word/PPT/Excel/Markdown/TXT → 提取文本单元入库(结构同 process_pdf)。"""
    import extract as X

    fhash = file_hash(pdf_path)
    if not force and already_ingested(con, pdf_path, fhash):
        print(f"  ⏭  已入库,跳过: {os.path.basename(pdf_path)}")
        return "skipped"
    try:
        units = X.extract_units(pdf_path)
    except Exception as e:
        print(f"  ⚠️  提取失败,跳过: {os.path.basename(pdf_path)} ({e})")
        return "error"
    if not units:
        print(f"  ⚠️  无文本,跳过: {os.path.basename(pdf_path)}")
        return "error"

    n = len(units)
    method0 = units[0][2]
    print(f"  📄 {os.path.basename(pdf_path)}  ({n} 单元, {method0})")
    con.execute("DELETE FROM documents WHERE source_path=?", (pdf_path,))
    cur = con.execute(
        "INSERT INTO documents(source_path,filename,pages,backend,file_hash,ingested_at)"
        " VALUES(?,?,?,?,?,?)",
        (pdf_path, os.path.basename(pdf_path), n, method0, fhash,
         _dt.datetime.now().isoformat(timespec="seconds")))
    doc_id = cur.lastrowid

    md_parts = ["---", f"source: {pdf_path}", f"pages: {n}", f"backend: {method0}",
                f"ingested: {_dt.datetime.now().isoformat(timespec='seconds')}", "---", "",
                f"# {os.path.splitext(os.path.basename(pdf_path))[0]}", ""]
    for (u_no, text, method) in units:
        con.execute("INSERT INTO pages(doc_id,page_no,method,text) VALUES(?,?,?,?)",
                    (doc_id, u_no, method, text))
        md_parts += [f"## Page {u_no}", "", text if text.strip() else "*(空)*", ""]
        if progress_cb:
            try:
                progress_cb(u_no, n)
            except Exception:
                pass
    os.makedirs(vault_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    with open(os.path.join(vault_dir, stem + ".md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md_parts))
    con.commit()
    print(f"     ✅ 入库完成  [{method0}×{n}]")
    return "ok"


def process_image(con, backend, img_path, vault_dir, render_dpi, force=False, progress_cb=None):
    """单张图片 → RapidOCR 识别成一页文本入库(截图/照片/扫描单页)。"""
    fhash = file_hash(img_path)
    if not force and already_ingested(con, img_path, fhash):
        print(f"  ⏭  已入库,跳过: {os.path.basename(img_path)}")
        return "skipped"
    # 用内置 RapidOCR 识别(auto/rapidocr/t430 都回落到本地引擎,保证图片总能识别)
    try:
        import numpy as np
        from PIL import Image
        ocr = B.RapidOCRBackend()._engine_lazy()
        im = Image.open(img_path).convert("RGB")
        result, _ = ocr(np.array(im))
        text = "\n".join(item[1] for item in (result or []))
        method = "ocr:rapidocr" if text.strip() else "ocr:rapidocr(empty)"
    except Exception as e:
        text, method = f"<!-- 图片 OCR 失败: {e} -->", "error"
    con.execute("DELETE FROM documents WHERE source_path=?", (img_path,))
    cur = con.execute(
        "INSERT INTO documents(source_path,filename,pages,backend,file_hash,ingested_at) VALUES(?,?,?,?,?,?)",
        (img_path, os.path.basename(img_path), 1, "rapidocr", fhash, _dt.datetime.now().isoformat(timespec="seconds")))
    doc_id = cur.lastrowid
    con.execute("INSERT INTO pages(doc_id,page_no,method,text) VALUES(?,?,?,?)", (doc_id, 1, method, text))
    os.makedirs(vault_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(img_path))[0]
    with open(os.path.join(vault_dir, stem + ".md"), "w", encoding="utf-8") as f:
        f.write(f"---\nsource: {img_path}\npages: 1\nbackend: rapidocr\n---\n\n# {stem}\n\n{text}\n")
    con.commit()
    if progress_cb:
        try: progress_cb(1, 1)
        except Exception: pass
    print(f"  🖼  图片 OCR 入库: {os.path.basename(img_path)} ({len(text)} 字)")
    return "ok"


def process_any(con, backend, path, vault_dir, render_dpi, force=False, progress_cb=None):
    """按扩展名分发:Kindle azw3 先转 epub;Office/文本走提取;其余走 fitz。"""
    ext = os.path.splitext(path)[1].lower()
    # ★音/视频 → 转写(SenseVoice ASR + 画面OCR)入库。media_ingest 重(sherpa),延迟 import;
    #   模型/ffmpeg 缺失时 media_ingest 内部优雅降级(返回 error,不崩)。
    try:
        import media_ingest as _MI
        if ext in _MI.AUDIO_EXTS or ext in _MI.VIDEO_EXTS:
            return _MI.process_media(con, path, vault_dir, force=force, progress_cb=progress_cb)
    except ImportError:
        pass   # media_ingest 或 sherpa 没打包 → 音视频走后面(当PDF会失败,但不崩整个流程)
    if ext in IMG_EXTS:
        # 单张图片 → 直接 OCR 识别成一页文本入库
        return process_image(con, backend, path, vault_dir, render_dpi, force=force, progress_cb=progress_cb)
    if ext in OFFICE_EXTS:
        return process_office(con, path, vault_dir, force=force, progress_cb=progress_cb)
    if ext in CONVERT_EXTS:
        import mobi
        import shutil
        fhash = file_hash(path)
        if not force and already_ingested(con, path, fhash):
            print(f"  ⏭  已入库,跳过: {os.path.basename(path)}")
            return "skipped"
        tmpdir = None
        try:
            print(f"  🔄 转换 Kindle 格式: {os.path.basename(path)}")
            tmpdir, epub = mobi.extract(path)
            return process_pdf(con, backend, path, vault_dir, render_dpi,
                               force=True, progress_cb=progress_cb, open_path=epub)
        except Exception as e:
            print(f"  ⚠️  azw3 转换失败,跳过: {os.path.basename(path)} ({e})")
            return "error"
        finally:
            if tmpdir and os.path.isdir(tmpdir):
                shutil.rmtree(tmpdir, ignore_errors=True)
    return process_pdf(con, backend, path, vault_dir, render_dpi, force=force,
                       progress_cb=progress_cb)


# ----------------------------- 文件夹选择器 --------------------------------
def choose_folder_mac() -> str | None:
    """弹出 macOS 原生文件夹选择框。"""
    script = 'POSIX path of (choose folder with prompt "选择包含 PDF 的文件夹:")'
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


# fitz(PyMuPDF)原生能打开的:走 process_pdf 逐页(含扫描件 OCR)
# fitz 原生也能打开单张图片当"1页文档",无文本层 → 走 OCR 识别
IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".gif", ".heic")
FITZ_EXTS = (".pdf", ".epub", ".mobi", ".fb2", ".xps", ".cbz") + IMG_EXTS
# Kindle KF8:fitz 打不开,先用 mobi 包转 epub 再走 fitz
CONVERT_EXTS = (".azw3", ".azw")
# Office / 文本 / 数据 / 网页 / 邮件:走 extract.py 提取
OFFICE_EXTS = (".docx", ".pptx", ".xlsx", ".xlsm", ".md", ".markdown", ".txt",
               ".html", ".htm", ".csv", ".json", ".eml", ".mbox")
# ★音/视频扩展名(与 media_ingest.AUDIO_EXTS/VIDEO_EXTS 一致;直接字面量,避免 import media_ingest
#   触发 sherpa 加载)。process_any 里对这些走 media_ingest.process_media(转写入库)。
#   ★T430→106 迁移时丢了这段接线,导致音视频入库断链;此处补回(不回退其它代码)。
_MEDIA_EXTS = (".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma", ".amr",
               ".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".ts")
DOC_EXTS = FITZ_EXTS + CONVERT_EXTS + OFFICE_EXTS + _MEDIA_EXTS


def find_docs(folder: str) -> list[str]:
    out = []
    for ext in DOC_EXTS:
        out += glob.glob(os.path.join(folder, "**", "*" + ext), recursive=True)
    return sorted(set(out))


# ----------------------------- 搜索 / 统计 ---------------------------------
def cmd_search(con, query: str, limit: int = 20):
    rows = con.execute(
        """SELECT d.filename, p.page_no,
                  snippet(pages_fts, 0, '「', '」', ' … ', 12) AS snip
           FROM pages_fts
           JOIN pages p ON p.id = pages_fts.rowid
           JOIN documents d ON d.id = p.doc_id
           WHERE pages_fts MATCH ?
           ORDER BY rank LIMIT ?""",
        (query, limit),
    ).fetchall()
    if not rows:
        print(f"没找到匹配「{query}」的内容。")
        return
    print(f"命中 {len(rows)} 条:\n")
    for fn, pno, snip in rows:
        print(f"  📄 {fn}  第 {pno} 页")
        print(f"     {snip.strip()}\n")


def cmd_import_md(con, md_dir: str):
    """把 Unlimited-OCR(云端/服务器)产出的 markdown 灌进本地库,
    以便和本地入库的内容一起全文检索。识别 frontmatter 与 ## Page N 分节。"""
    mds = sorted(glob.glob(os.path.join(md_dir, "**", "*.md"), recursive=True))
    print(f"发现 {len(mds)} 个 markdown")
    n_ok = 0
    for md in mds:
        with open(md, encoding="utf-8") as f:
            raw = f.read()
        # 解析 frontmatter
        source, pages, backend = md, 0, "unlimited-ocr"
        m = re.match(r"^---\n(.*?)\n---\n", raw, re.S)
        body = raw
        if m:
            fm = m.group(1)
            body = raw[m.end():]
            for line in fm.splitlines():
                if line.startswith("source:"):
                    source = line.split(":", 1)[1].strip()
                elif line.startswith("backend:"):
                    backend = line.split(":", 1)[1].strip()
        # 按 ## Page N 切页
        parts = re.split(r"^##\s+Page\s+(\d+)\s*$", body, flags=re.M)
        page_texts = []
        if len(parts) >= 3:
            for i in range(1, len(parts), 2):
                page_texts.append((int(parts[i]), parts[i + 1].strip()))
        else:
            page_texts.append((1, body.strip()))

        fhash = "imported:" + hashlib.sha1(raw.encode()).hexdigest()[:16]
        con.execute("DELETE FROM documents WHERE source_path=?", (source,))
        cur = con.execute(
            "INSERT INTO documents(source_path,filename,pages,backend,file_hash,ingested_at)"
            " VALUES(?,?,?,?,?,?)",
            (source, os.path.basename(source), len(page_texts), backend, fhash,
             _dt.datetime.now().isoformat(timespec="seconds")),
        )
        doc_id = cur.lastrowid
        for pno, txt in page_texts:
            con.execute(
                "INSERT INTO pages(doc_id,page_no,method,text) VALUES(?,?,?,?)",
                (doc_id, pno, "unlimited-ocr", txt),
            )
        n_ok += 1
        print(f"  ✅ {os.path.basename(md)}  {len(page_texts)} 页")
    con.commit()
    print(f"\n导入完成:{n_ok} 份。用 --search 关键词 检索。")


def cmd_stats(con):
    d = con.execute("SELECT COUNT(*), COALESCE(SUM(pages),0) FROM documents").fetchone()
    print(f"本地库:{d[0]} 份文档,共 {d[1]} 页")
    for name, cnt in con.execute(
        "SELECT method, COUNT(*) FROM pages GROUP BY method ORDER BY 2 DESC"
    ):
        print(f"  {name}: {cnt} 页")


# ----------------------------- 主入口 --------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Unlimited-OCR 本地入库工具")
    ap.add_argument("folder", nargs="?", help="要处理的文件夹(留空则弹出选择框)")
    ap.add_argument("--backend", default="auto",
                    choices=["auto", "text", "rapidocr", "t430", "unlimited"],
                    help="OCR 后端(默认 auto:文字层优先,扫描件本地 OCR 兜底;"
                         "t430=扫描页走 T430 常驻的百度 Unlimited-OCR)")
    ap.add_argument("--db", default=DEFAULT_DB, help="本地数据库路径")
    ap.add_argument("--vault", default=DEFAULT_VAULT, help="markdown 输出目录")
    ap.add_argument("--export", default=DEFAULT_EXPORT, help="unlimited 后端图片导出目录")
    ap.add_argument("--dpi", type=int, default=200, help="扫描件渲染 DPI")
    ap.add_argument("--force", action="store_true", help="强制重处理(忽略已入库)")
    ap.add_argument("--search", metavar="关键词", help="在本地库全文检索")
    ap.add_argument("--stats", action="store_true", help="查看入库统计")
    ap.add_argument("--import-md", metavar="目录", dest="import_md",
                    help="把云端/服务器产出的 markdown 导入本地库(如从 ModelScope 下回的 vault_out)")
    args = ap.parse_args()

    con = db_connect(args.db)

    if args.search:
        cmd_search(con, args.search)
        return
    if args.stats:
        cmd_stats(con)
        return
    if args.import_md:
        cmd_import_md(con, os.path.expanduser(args.import_md))
        return

    folder = args.folder or choose_folder_mac()
    if not folder:
        print("没有选择文件夹,退出。")
        return
    folder = os.path.expanduser(folder)
    if not os.path.isdir(folder):
        print(f"不是有效文件夹:{folder}")
        return

    pdfs = find_docs(folder)
    print(f"\n📂 {folder}")
    print(f"   找到 {len(pdfs)} 个文档,后端={args.backend}\n")
    if not pdfs:
        print(f"这个文件夹(含子目录)里没有可入库文档({'/'.join(DOC_EXTS)})。")
        return

    export_root = args.export if args.backend == "unlimited" else None
    backend = B.make_backend(args.backend, export_root)

    stats = {"ok": 0, "skipped": 0, "error": 0}
    for p in pdfs:
        try:
            r = process_any(con, backend, p, args.vault, args.dpi, force=args.force)
        except Exception as e:
            try:
                con.rollback()
            except Exception:
                pass
            print(f"  ⚠️ 跳过(异常): {os.path.basename(p)} — {e}")
            r = "error"
        stats[r] = stats.get(r, 0) + 1

    fin = backend.finalize(args.vault)
    print(f"\n———— 全部完成 ————")
    print(f"新入库 {stats['ok']}  跳过 {stats['skipped']}  失败 {stats['error']}")
    print(f"本地库:{args.db}")
    print(f"markdown:{args.vault}")
    if fin:
        print(f"待 GPU 处理的图片清单:{fin}")
        print("下一步:把 gpu_export/ 传到免费 GPU notebook 跑 Unlimited-OCR"
              "(见 gpu_notebook/README)")
    print("\n搜一下试试:  python ingest.py --search 你的关键词")


if __name__ == "__main__":
    main()

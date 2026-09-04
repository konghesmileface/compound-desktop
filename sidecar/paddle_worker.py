#!/usr/bin/env python3
"""第二大脑 高精 OCR worker —— 独立进程(自带 paddle 环境,与主 sidecar 的 torch 环境隔离)。

由主 sidecar(sidecar_main.py)在高精版客户端里拉起:compound-paddle --host 127.0.0.1 --port <端口>
协议同 T430:POST /ocr/image (multipart file=图片) → {"markdown": "..."};GET /health。
引擎:PaddleOCR PP-StructureV3(版面+文字+表格+公式,纯 CPU)。首次请求才加载(会下模型到缓存)。
"""
import os
import sys
import io
import argparse
import threading

from fastapi import FastAPI, UploadFile, File


def _cache_dir() -> str:
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/Compound")
    elif sys.platform.startswith("win"):
        base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Compound")
    else:
        base = os.path.expanduser("~/.compound")
    d = os.path.join(base, "paddle")
    os.makedirs(d, exist_ok=True)
    return d


# paddle 模型:优先用打进包的离线模型(区域无关、海外/国内都开箱即用),否则落用户数据目录。
_bundled_pdx = os.path.join(getattr(sys, "_MEIPASS", ""), "paddle_models") if getattr(sys, "frozen", False) else ""
if _bundled_pdx and os.path.isdir(_bundled_pdx):
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", _bundled_pdx)
else:
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", _cache_dir())
# ★不硬编码国内 BOS 源(会坑海外微信客户)。模型已打进包→通常不下载;
#   万一回落下载,paddlex 默认源(海外可达);国内用户可自设 PADDLE_PDX_MODEL_SOURCE=BOS。

app = FastAPI(title="Compound 高精 OCR (PP-StructureV3)")
_engine = None
_lock = threading.Lock()


def _engine_lazy():
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                from paddleocr import PPStructureV3
                # ★完整高精 PP-StructureV3(方案第二节):识别+表格SLANeXt+公式PP-FormulaNet+版面 全开。
                #   建议 16G 内存(方案已注明)。仅方向分类/去扭曲/图表识别这几个预处理关掉(不在方案清单、省资源)。
                _engine = PPStructureV3(
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_chart_recognition=False,
                )
    return _engine


def _md_of(result) -> str:
    md = getattr(result, "markdown", None)
    if isinstance(md, dict):
        return (md.get("markdown_texts") or md.get("text")
                or "\n".join(str(v) for v in md.values() if isinstance(v, str)))
    if isinstance(md, str):
        return md
    return ""


@app.get("/health")
def health():
    return {"status": "ok", "engine": "paddle-ppstructurev3", "loaded": _engine is not None}


@app.post("/ocr/image")
def ocr_image(file: UploadFile = File(...)):
    # ★同步 def(不是 async):FastAPI 会在线程池里跑,绝不在主事件循环线程做 paddle 阻塞推理。
    #   （原来是 async def,paddle 的同步 predict 直接堵主线程,与其内部线程/导入互锁→死锁,
    #     实测 mac2 macOS12:PPStructureV3 首次推理卡死、0%CPU、OCR 永不返回。)
    import numpy as np
    from PIL import Image
    raw = file.file.read()
    arr = np.array(Image.open(io.BytesIO(raw)).convert("RGB"))
    with _lock:
        parts = [_md_of(r) for r in _engine_lazy().predict(arr)]
    return {"markdown": "\n\n".join(p for p in parts if p).strip()}


def main():
    # ★双保险:切到中性临时目录再跑,绝不在含 numpy 打包文件的目录里(否则 import numpy 报
    #   "from its source directory"→OCR 500,高精OCR全废)。
    try:
        import tempfile
        os.chdir(tempfile.gettempdir())
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8791)
    args = ap.parse_args()
    # ★启动即在"干净主线程"预加载 PP-StructureV3(uvicorn/asyncio 还没起)。这正是 CI 里能成功
    #   构建模型的同一上下文(普通脚本主线程)。避免首次请求时在 async 事件循环/线程池上下文里
    #   初始化 paddle→线程/导入互锁死锁。预热后首个请求也秒回。失败不致命,请求时还会再试。
    try:
        print("[paddle] 预加载 PP-StructureV3 引擎中(首次约需 30-90s)…", flush=True)
        _engine_lazy()
        print("[paddle] 引擎预加载完成", flush=True)
    except Exception as _e:
        print(f"[paddle] 预加载失败(请求时再试): {_e}", flush=True)
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    # ★PyInstaller 冻结包必须最先 freeze_support():paddlex/paddleocr(PP-StructureV3)推理时会起
    #   multiprocessing 子进程,子进程会重入冻结的 compound-paddle 二进制。没有 freeze_support 时,
    #   子进程不会走 mp 引导、而是从头重跑 main()→父进程等子进程结果→永久死锁(实测 mac2 macOS12:
    #   PPStructureV3 构造函数卡住、0% CPU、内存不涨、/health 都不响应、OCR 永不返回)。
    #   必须在任何可能 spawn 的代码之前。sidecar_main.py 早有此处理(所以主 sidecar 正常)。
    import multiprocessing
    multiprocessing.freeze_support()
    main()

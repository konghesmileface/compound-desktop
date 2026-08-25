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


# paddle 模型缓存落用户数据目录(持久,不重复下载)
os.environ.setdefault("PADDLE_PDX_CACHE_HOME", _cache_dir())
# 模型下载源用百度 BOS(国内可靠;默认 HF 常连不上)
os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "BOS")

app = FastAPI(title="Compound 高精 OCR (PP-StructureV3)")
_engine = None
_lock = threading.Lock()


def _engine_lazy():
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                from paddleocr import PPStructureV3
                # ★用 mobile 轻量模型:server 大模型在 8GB 机 OOM;mobile 仍比 rapidocr 新/准,
                #   加版面结构。表格识别默认关(表格模型重,可 PADDLE_TABLE=1 打开,需 ≥16GB)。
                kw = dict(
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_chart_recognition=False,
                    use_formula_recognition=False,
                    text_detection_model_name="PP-OCRv5_mobile_det",
                    text_recognition_model_name="PP-OCRv5_mobile_rec",
                )
                if os.environ.get("PADDLE_TABLE") != "1":
                    kw["use_table_recognition"] = False
                _engine = PPStructureV3(**kw)
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
async def ocr_image(file: UploadFile = File(...)):
    import numpy as np
    from PIL import Image
    raw = await file.read()
    arr = np.array(Image.open(io.BytesIO(raw)).convert("RGB"))
    with _lock:
        parts = [_md_of(r) for r in _engine_lazy().predict(arr)]
    return {"markdown": "\n\n".join(p for p in parts if p).strip()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8791)
    args = ap.parse_args()
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()

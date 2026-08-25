#!/usr/bin/env python3
"""第二大脑 桌面客户端 —— 本机后端 sidecar 入口。

由 Tauri 壳启动:compound-sidecar --host 127.0.0.1 --port <随机端口>
- 数据落用户可写目录(Mac: ~/Library/Application Support/Compound/brain)
- 模型缓存进数据目录,默认走 hf-mirror(国内可达),首次语义检索时按需下载
- 复用 web/app.py 的 FastAPI app(扁平 import,与 106 运行时一致)
"""
import os
import sys
import argparse


def _data_dir() -> str:
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/Compound")
    elif sys.platform.startswith("win"):
        base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Compound")
    else:
        base = os.path.expanduser("~/.compound")
    d = os.path.join(base, "brain")
    os.makedirs(d, exist_ok=True)
    return d


def _spawn_paddle_worker():
    """高精版:若同级打了 compound-paddle worker 二进制,拉起它并设 PADDLE_OCR_URL。
    轻量版没这个二进制 → 直接跳过,paddle 后端不可用。"""
    import subprocess
    import socket
    exe = "compound-paddle.exe" if sys.platform.startswith("win") else "compound-paddle"
    base = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    candidates = [
        os.path.join(base, "..", "compound-paddle", exe),   # 打包:Resources/compound-paddle/
        os.path.join(base, "compound-paddle", exe),
        os.path.join(base, "dist", "compound-paddle", exe),  # dev
    ]
    worker = next((p for p in candidates if os.path.exists(p)), None)
    if not worker:
        return  # 轻量版
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    try:
        subprocess.Popen([worker, "--host", "127.0.0.1", "--port", str(port)],
                         cwd=os.path.dirname(worker))
        os.environ["PADDLE_OCR_URL"] = f"http://127.0.0.1:{port}"
        print(f"[sidecar] 高精 paddle worker 已拉起 :{port}", flush=True)
    except Exception as e:
        print(f"[sidecar] paddle worker 启动失败: {e}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8200)
    ap.add_argument("--selftest", action="store_true",
                    help="冻结包自检:import 重依赖(torch/嵌入/OCR/sklearn)确认打进去了")
    args = ap.parse_args()

    if args.selftest:
        ok = True
        for mod in ("torch", "sentence_transformers", "rapidocr_onnxruntime",
                    "sklearn.cluster", "sklearn.neighbors", "fitz", "docx",
                    "pptx", "openpyxl", "jieba", "cv2", "onnxruntime", "numpy"):
            try:
                __import__(mod)
                print(f"  OK  {mod}")
            except Exception as e:
                ok = False
                print(f"  FAIL {mod}: {type(e).__name__}: {e}")
        print("SELFTEST", "PASS" if ok else "FAIL")
        sys.exit(0 if ok else 1)

    data = _data_dir()
    # 后端数据/库位置(ingest.py 读 BRAIN_DATA → library.db 落这里)
    os.environ.setdefault("BRAIN_DATA", data)
    # 嵌入模型:与 106 一致用 bge-m3;缓存进数据目录;国内镜像。首次语义检索按需下载。
    os.environ.setdefault("EMBED_MODEL", "BAAI/bge-m3")
    os.environ.setdefault("HF_HOME", os.path.join(data, "hf"))
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", os.path.join(data, "hf"))
    # 本机后端只监听回环
    os.environ.setdefault("WEB_HOST", args.host)
    os.environ.setdefault("WEB_PORT", str(args.port))

    # 让扁平的后端模块可被 import(冻结后 PyInstaller 已收集;源码运行时加当前目录)
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    # 高精版:先拉起 paddle worker 并设 PADDLE_OCR_URL,这样 app.py 计算 BACKENDS 时能列出 paddle
    _spawn_paddle_worker()

    import uvicorn
    import app as _app  # web/app.py(扁平化到此目录)
    uvicorn.run(_app.app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

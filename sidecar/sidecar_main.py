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


def _seed_downloads(data_dir):
    """把打进包的「微信同步助手」安装包铺到 BRAIN_DATA/downloads,
    app.py 的 /dl 挂载即可就地发包(客户端离线下载,不用去云端)。"""
    import shutil
    srcs = []
    if getattr(sys, "frozen", False):
        srcs.append(os.path.join(getattr(sys, "_MEIPASS", ""), "downloads"))
    srcs.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads"))
    src = next((s for s in srcs if os.path.isdir(s)), None)
    if not src:
        return
    dst = os.path.join(data_dir, "downloads")
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(src):
        d = os.path.join(dst, f)
        if not os.path.exists(d):
            try:
                shutil.copy2(os.path.join(src, f), d)
            except Exception:
                pass


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
        for mod in ("torch", "sentence_transformers", "rapidocr",
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
    # 微信同步助手安装包铺到 downloads(app.py /dl 就地发,离线下载)
    _seed_downloads(data)
    # 嵌入模型 bge-m3:优先用打进包的离线模型(_internal/models/bge-m3);没打进才回落下载。
    bundled = None
    if getattr(sys, "frozen", False):
        cand = os.path.join(getattr(sys, "_MEIPASS", ""), "models", "bge-m3")
        if os.path.isdir(cand):
            bundled = cand
    if not bundled:
        here0 = os.path.dirname(os.path.abspath(__file__))
        cand = os.path.join(here0, "models", "bge-m3")
        if os.path.isdir(cand):
            bundled = cand
    os.environ.setdefault("EMBED_MODEL", bundled or "BAAI/bge-m3")
    # 模型已打进包(区域无关、离线);缓存目录中性。★不硬编码国内镜像(会坑海外用户)——
    #   万一要回落下载,默认走 huggingface.co(海外可达);国内用户可自行设 HF_ENDPOINT=hf-mirror.com。
    os.environ.setdefault("HF_HOME", os.path.join(data, "hf"))
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

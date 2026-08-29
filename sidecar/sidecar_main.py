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
        import glob as _glob
        ok = True
        # A) 重依赖能 import(缺=ImportError 运行时崩)
        for mod in ("torch", "sentence_transformers", "rapidocr",
                    "sklearn.cluster", "sklearn.neighbors", "fitz", "docx",
                    "pptx", "openpyxl", "jieba", "cv2", "onnxruntime", "numpy", "certifi"):
            try:
                __import__(mod)
                print(f"  OK  import {mod}")
            except Exception as e:
                ok = False
                print(f"  FAIL import {mod}: {type(e).__name__}: {e}")
        # B) ★数据文件真打进包了没(模块能 import ≠ 数据在)。这是历史踩坑:cacert/模型/安装包
        #    缺了 import 照样过,却在用户机上哑火。缺任一 → SELFTEST FAIL → CI 构建失败,不流到用户。
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        def _need(label, path, is_dir=False):
            nonlocal ok
            good = os.path.isdir(path) if is_dir else os.path.isfile(path)
            print(f"  {'OK  ' if good else 'FAIL'} 数据:{label}")
            if not good:
                ok = False
            return good
        _need("cacert.pem(CA证书=所有https命根)", os.path.join(base, "certifi", "cacert.pem"))
        _need("schema_full.sql(空DB建全45表)", os.path.join(base, "schema_full.sql"))
        if _need("bge-m3 模型目录", os.path.join(base, "models", "bge-m3"), is_dir=True):
            w = (_glob.glob(os.path.join(base, "models", "bge-m3", "*.safetensors"))
                 + _glob.glob(os.path.join(base, "models", "bge-m3", "pytorch_model.bin")))
            print(f"  {'OK  ' if w else 'FAIL'} 数据:bge-m3 权重文件")
            ok = ok and bool(w)
        n_onnx = len(_glob.glob(os.path.join(base, "rapidocr", "**", "*.onnx"), recursive=True))
        print(f"  {'OK  ' if n_onnx else 'FAIL'} 数据:rapidocr onnx 模型({n_onnx} 个)")
        ok = ok and n_onnx > 0
        n_dl = len(_glob.glob(os.path.join(base, "downloads", "*")))
        print(f"  {'OK  ' if n_dl else 'FAIL'} 数据:微信助手安装包({n_dl} 个)")
        ok = ok and n_dl > 0
        # ★音视频入库:SenseVoice ASR + Mac ffmpeg(缺了音视频转文字入库跑不了)
        _sv = os.path.join(base, "models", "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17", "model.int8.onnx")
        print(f"  {'OK  ' if os.path.isfile(_sv) else 'FAIL'} 数据:SenseVoice ASR 模型")
        ok = ok and os.path.isfile(_sv)
        _ff = os.path.join(base, "bin", "ffmpeg" + (".exe" if sys.platform == "win32" else ""))
        print(f"  {'OK  ' if os.path.isfile(_ff) else 'FAIL'} 数据:ffmpeg 二进制")
        ok = ok and os.path.isfile(_ff)
        for _mn, _mp in (("silero VAD", os.path.join(base, "models", "silero_vad.onnx")),
                         ("3dspeaker 声纹", os.path.join(base, "models", "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx")),
                         ("pyannote 分割", os.path.join(base, "models", "sherpa-onnx-pyannote-segmentation-3-0", "model.onnx"))):
            print(f"  {'OK  ' if os.path.isfile(_mp) else 'FAIL'} 数据:{_mn}")
            ok = ok and os.path.isfile(_mp)
        # sherpa_onnx / edge_tts 能 import(音视频ASR / 一生旁白)
        for _m2 in ("sherpa_onnx", "edge_tts"):
            try:
                __import__(_m2); print(f"  OK  import {_m2}")
            except Exception as e:
                ok = False; print(f"  FAIL import {_m2}: {e}")
        # ★真加载 VAD+recognizer(不只 import):silero 版本与 sherpa 不匹配会在此暴露(报 Unsupported
        #   silero vad model),而不是等用户机音频入库时静默失败。历史坑:sherpa≥1.11.2 + 新silero 组合
        #   在 macOS12 崩;必须 sherpa==1.11.1 + silero v4。CI 构建时就卡住,不流到用户。
        try:
            import sherpa_onnx as _so
            _vc = _so.VadModelConfig(); _vc.silero_vad.model = os.path.join(base, "models", "silero_vad.onnx")
            _vc.sample_rate = 16000
            _so.VoiceActivityDetector(_vc, buffer_size_in_seconds=180)
            _svm = os.path.join(base, "models", "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17")
            _so.OfflineRecognizer.from_sense_voice(
                model=os.path.join(_svm, "model.int8.onnx"),
                tokens=os.path.join(_svm, "tokens.txt"), use_itn=True)
            print("  OK  sherpa VAD+SenseVoice 真加载(silero/模型版本匹配)")
        except Exception as e:
            ok = False; print(f"  FAIL sherpa 加载(silero版本不匹配?): {e}")
        # ★HEIC/HEIF(iPhone 默认照片):pillow-heif + 原生 libheif 必须在冻结包里真能工作,
        #   否则用户导 iPhone 照片入库报 "cannot identify image file"(裸 PIL 打不开)。
        #   真编码→再解码一张,验证 libheif 打进包且可用(只 import 不够,原生库缺了在此才暴露)。
        try:
            import io as _io
            from PIL import Image as _Img
            from pillow_heif import register_heif_opener as _rho
            _rho()
            _buf = _io.BytesIO()
            _Img.new("RGB", (8, 8), (1, 2, 3)).save(_buf, format="HEIF")
            _buf.seek(0)
            _Img.open(_buf).convert("RGB").load()
            print("  OK  pillow-heif HEIC 编解码(libheif 已打包)")
        except Exception as e:
            ok = False; print(f"  FAIL pillow-heif HEIC(libheif 没打进包?): {e}")
        # C) onnxruntime 真能加载(catch .so 符号/minos 问题;CI 上 import 成功即基本 OK)
        try:
            import onnxruntime as _ort
            print(f"  OK  onnxruntime {_ort.__version__}(providers={_ort.get_available_providers()})")
        except Exception as e:
            ok = False
            print(f"  FAIL onnxruntime 加载: {e}")
        print("SELFTEST", "PASS" if ok else "FAIL")
        sys.exit(0 if ok else 1)

    # ★★CA 证书(所有 https 校验的根):冻结包必须指向打进包的 cacert.pem,否则 DeepSeek/云端/下载
    #   全报证书错(self signed / verify failed)。SSL_CERT_FILE 一设,Python ssl 全局默认就用它。
    try:
        _base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        _ca = os.path.join(_base, "certifi", "cacert.pem")
        if not os.path.exists(_ca):
            import certifi as _cf
            _ca = _cf.where()
        if os.path.exists(_ca):
            os.environ["SSL_CERT_FILE"] = _ca
            os.environ["REQUESTS_CA_BUNDLE"] = _ca
            print(f"[ca] SSL_CERT_FILE={_ca}")
        else:
            print("[ca] 警告:找不到 cacert.pem,https 校验可能失败")
    except Exception as _e:
        print(f"[ca] CA 设置异常: {_e}")

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
    # ★模型已打进包→强制离线加载:不设的话 sentence_transformers/huggingface_hub 会联网校验,
    #   慢 + 无网/无CA时直接加载失败 → 嵌入起不来 → 分析中卡0%。打进包就该纯本地。
    if bundled:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
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
    # ★PyInstaller 冻结包必须先 freeze_support():否则任何库(torch/sentence_transformers/tokenizers)
    #   起 multiprocessing 子进程时,子进程会重入冻结二进制并带 -c/-B/-S 参数,被 argparse 当未知参数崩
    #   (报 unrecognized arguments: -c from multiprocessing.resource_tracker)。必须在最前面。
    import multiprocessing
    multiprocessing.freeze_support()
    # 冻结包里禁用 tokenizers 多进程并行(会 fork 触发上面的重入 + 无谓开销),单机嵌入用不上。
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    main()

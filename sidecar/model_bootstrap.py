# -*- coding: utf-8 -*-
"""首启模型下载(Windows 瘦身版)。

Windows 安装器受 32 位 makensis ~2GB mmap 硬限,大模型(bge-m3 2.3G / SenseVoice 0.9G)
不打进包,首次启动时下载到 BRAIN_DATA/models,下完后全部离线可用。
前端 ModelDownload.jsx 轮询 /api/model_status 显示进度;Mac 全打进包 → 检测到都在 → 立即 done。

模块 key 与 ModelDownload.jsx 的 MODULES 对齐:bge-m3 / sensevoice / speaker。
"""
import os
import sys
import glob
import time
import shutil
import tarfile
import tempfile
import threading
import urllib.request

BASE = os.environ.get("BRAIN_DATA", os.path.expanduser("~/brain"))
_MEI = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

_SENSE = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
_SEG = "sherpa-onnx-pyannote-segmentation-3-0"

# ★下载源:优先阿里云 OSS(国内可达+快,海外也可达;github/HF 在中国被墙)。
#   我们把模型 tar 托管到 worldmonitor-downloads 桶(公读);海外/OSS挂了再回落 github/HF。
_OSS = "https://worldmonitor-downloads.oss-cn-shanghai.aliyuncs.com/compound-models/"

# 每个模块:est=预估字节(算总进度用);check_any=只要任一文件在(打包目录或数据目录)就算已就绪
# kind=tar → 下 urls(按序试,先成先用)的 tar 解到 models/;extra=附带的单文件(url,落地名)
SPECS = {
    "bge-m3": {
        "est": 2_100_000_000,
        "check_any": [os.path.join("bge-m3", "model.safetensors"),
                      os.path.join("bge-m3", "pytorch_model.bin")],
        "kind": "tar",
        "urls": [_OSS + "compound-bge-m3.tar.gz"],   # HF 多文件仓不便直链,仅托管 OSS
    },
    "sensevoice": {
        "est": 1_100_000_000,
        "check_any": [os.path.join(_SENSE, "model.int8.onnx")],
        "kind": "tar",
        "urls": [_OSS + "compound-sense-voice.tar.gz",
                 "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/%s.tar.bz2" % _SENSE],
        "extra": [],   # silero_vad 已随包打进(Windows 也保留),无需再下
    },
    "speaker": {
        "est": 50_000_000,
        "check_any": [os.path.join(_SEG, "model.onnx")],
        "kind": "tar",
        "urls": ["https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/%s.tar.bz2" % _SEG],
        "extra": [("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
                   "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx")],
    },
}

_ST = {"started": False, "done": False, "error": None, "modules": {},
       "overall_pct": 0, "eta": "", "speed": "", "_t0": 0.0, "_bytes0": 0}
_LOCK = threading.Lock()


def _model_roots():
    return [os.path.join(_MEI, "models"), os.path.join(BASE, "models")]


def _present(rel):
    for root in _model_roots():
        if os.path.exists(os.path.join(root, rel)):
            return True
    return False


def _module_present(key):
    return any(_present(c) for c in SPECS[key]["check_any"])


def all_present():
    return all(_module_present(k) for k in SPECS)


def _dir_bytes(path):
    tot = 0
    for r, _, fs in os.walk(path):
        for f in fs:
            try:
                tot += os.path.getsize(os.path.join(r, f))
            except Exception:
                pass
    return tot


def _fmt_eta(sec):
    if sec <= 0 or sec != sec:
        return ""
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    if h:
        return "%d 小时 %d 分" % (h, m)
    if m:
        return "%d 分 %d 秒" % (m, s)
    return "%d 秒" % s


def _download(url, dst_file, on_bytes):
    """流式下载单文件,每块回调已增字节数(用于全局进度)。"""
    tmp = dst_file + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "compound-desktop"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)
            on_bytes(len(chunk))
    os.replace(tmp, dst_file)


def _download_first(urls, dst_file, on_bytes):
    """按序试多个镜像(OSS 优先,github/HF 回落),先成先用。全挂才抛。"""
    last = None
    for u in urls:
        try:
            _download(u, dst_file, on_bytes)
            return u
        except Exception as e:
            last = e
    raise last or RuntimeError("no url")


def _do_tar(spec, models_dir, on_bytes):
    os.makedirs(models_dir, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(suffix=".tar", delete=False).name
    try:
        _download_first(spec["urls"], tmp, on_bytes)
        with tarfile.open(tmp, "r:*") as tf:   # 自动识别 gz/bz2
            tf.extractall(models_dir)
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
    for eurl, ename in spec.get("extra", []):
        _download(eurl, os.path.join(models_dir, ename), on_bytes)


def _do_hf(spec, models_dir, key):
    """bge-m3:snapshot_download 到 models/bge-m3;起个轮询线程按目录大小报 pct。"""
    dest = os.path.join(models_dir, spec["dest"])
    os.makedirs(dest, exist_ok=True)
    est = spec["est"]
    stop = {"v": False}

    def _poll():
        while not stop["v"]:
            got = _dir_bytes(dest)
            with _LOCK:
                _ST["modules"][key] = {"pct": min(99, int(got * 100 / est)), "done": False}
            _recompute()
            time.sleep(1.0)

    t = threading.Thread(target=_poll, daemon=True)
    t.start()
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id=spec["repo"], local_dir=dest,
                          allow_patterns=["*.safetensors", "*.json", "*.model", "*.txt", "*Pooling*"])
    finally:
        stop["v"] = True


def _recompute():
    """按已下字节 / 缺失模块总预估字节 算全局 pct + 速度 + ETA。"""
    total_est = sum(SPECS[k]["est"] for k in SPECS if k in _ST["modules"] and not _module_present(k)) or 1
    got = 0
    for k in SPECS:
        m = _ST["modules"].get(k)
        if not m:
            continue
        if _module_present(k) or m.get("done"):
            got += SPECS[k]["est"]
        else:
            got += SPECS[k]["est"] * (m.get("pct", 0) / 100.0)
    pct = min(99, int(got * 100 / (sum(SPECS[k]["est"] for k in SPECS) or 1)))
    _ST["overall_pct"] = 100 if _ST["done"] else pct
    el = time.time() - (_ST["_t0"] or time.time())
    if el > 2:
        speed = (got - _ST["_bytes0"]) / el
        if speed > 0:
            _ST["speed"] = "%.1f MB/s" % (speed / 1e6)
            remain = (sum(SPECS[k]["est"] for k in SPECS) - got)
            _ST["eta"] = _fmt_eta(remain / speed)


def _worker():
    models_dir = os.path.join(BASE, "models")
    os.makedirs(models_dir, exist_ok=True)
    _ST["_t0"] = time.time()
    _ST["_bytes0"] = 0
    got_acc = {"v": 0}

    def on_bytes(n):
        got_acc["v"] += n

    try:
        for key, spec in SPECS.items():
            if _module_present(key):
                with _LOCK:
                    _ST["modules"][key] = {"pct": 100, "done": True}
                continue
            with _LOCK:
                _ST["modules"][key] = {"pct": 0, "done": False}
            _recompute()
            if spec["kind"] == "tar":
                base_got = got_acc["v"]
                # 边下边按已下字节 / 该模块预估 报 pct
                stop = {"v": False}

                def _poll(k=key, sp=spec, bg=base_got):
                    while not stop["v"]:
                        cur = got_acc["v"] - bg
                        with _LOCK:
                            _ST["modules"][k] = {"pct": min(99, int(cur * 100 / sp["est"])), "done": False}
                        _recompute()
                        time.sleep(0.8)

                tp = threading.Thread(target=_poll, daemon=True)
                tp.start()
                try:
                    _do_tar(spec, models_dir, on_bytes)
                finally:
                    stop["v"] = True
            elif spec["kind"] == "hf":
                _do_hf(spec, models_dir, key)
            with _LOCK:
                _ST["modules"][key] = {"pct": 100, "done": True}
            _recompute()
        _ST["done"] = True
        _ST["overall_pct"] = 100
    except Exception as e:
        _ST["error"] = str(e)


def start_if_needed():
    """幂等:首次调用若有缺失模块就起后台下载线程。返回当前状态。"""
    with _LOCK:
        if _ST["started"]:
            return status()
        # 全在(Mac 打包 / 已下过)→ 直接 done
        for k in SPECS:
            _ST["modules"][k] = {"pct": 100, "done": True} if _module_present(k) else {"pct": 0, "done": False}
        if all_present():
            _ST["started"] = True
            _ST["done"] = True
            _ST["overall_pct"] = 100
            return status()
        _ST["started"] = True
    threading.Thread(target=_worker, daemon=True).start()
    return status()


def status():
    return {"modules": dict(_ST["modules"]), "overall_pct": _ST["overall_pct"],
            "eta": _ST["eta"], "speed": _ST["speed"], "done": _ST["done"],
            "error": _ST["error"]}

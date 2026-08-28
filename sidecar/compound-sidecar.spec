# PyInstaller spec: 把第二大脑后端(compound-brain)冻成 onedir 二进制,供 Tauri sidecar 内嵌。
# 用法(各平台各跑一次): .venv/bin/pyinstaller compound-sidecar.spec
# 产物: dist/compound-sidecar/ (含 compound-sidecar 可执行 + 库)
# 瘦身版:不打嵌入模型(bge-m3 2.3G),首次语义检索时按 hf-mirror 下载。OCR(rapidocr onnx)已打进。
# 蓝本:WM kb-sidecar.spec(rapidocr datas / torch upx=False / onedir / certifi 均沿用)。
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

here = os.path.abspath(".")

datas = []
binaries = []
# ★全 schema(客户端启动建全 106 的全部业务表,避免空DB逐个撞 no such table/column)
_sf = os.path.join(here, "schema_full.sql")
if os.path.isfile(_sf):
    datas.append((_sf, "."))
# ★officecli 二进制(officecli.ai 单文件原生,专业排版 PPT/Word/Excel;非Docker,离线无依赖)。
#   打进 bin/,generate.py _resolve_occ 找 _MEIPASS/bin/officecli 调用;缺则回落 python-pptx。
#   ★平台专属:仓库里的是 Intel x86_64;arm/win 各自二进制需另放(缺则该平台自动回落)。
_occ = os.path.join(here, "bin", "officecli")
if os.path.isfile(_occ):
    datas.append((_occ, "bin"))
# ★iOS 历史导入模块(sidecar/wxsync:import_iphone/config/status/uploader)。app.py 的
#   /api/iphone/import 端点把 _MEIPASS/wxsync 加进 sys.path 后 import import_iphone 执行。
_wxs = os.path.join(here, "wxsync")
if os.path.isdir(_wxs):
    for _f in os.listdir(_wxs):
        if _f.endswith(".py"):
            datas.append((os.path.join(_wxs, _f), "wxsync"))
# ★opencv-python-headless:collect_submodules('cv2') 会在 cv2.gapi 崩(AttributeError),
#   改为显式收 cv2 的动态库 + 数据(.so + config),并作为 plain hidden import,交给内置 hook 处理其余。
try:
    binaries += collect_dynamic_libs("cv2")
    datas += collect_data_files("cv2")
except Exception:
    pass
# 随包数据:嵌入/OCR/证书。★rapidocr 必须收 datas(内置 onnx 检测/识别模型+config.yaml),
# 否则 frozen 包里 rapidocr 目录缺失,内置 OCR 静默失效。★certifi:CA 证书,否则 https 验证失败。
# ★jieba:词典 dict.txt 必须随包。
for pkg in ("sentence_transformers", "transformers", "tokenizers",
            "rapidocr", "certifi", "jieba"):
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass
# ★★强制打进 certifi 的 cacert.pem 到已知路径(certifi/cacert.pem)。collect_data_files 有时收不到,
#   冻结包无 CA → 所有 https 证书校验失败(DeepSeek/云端/下载全连不通)。sidecar_main 启动设 SSL_CERT_FILE 指向它。
try:
    import certifi as _certifi_mod
    datas.append((_certifi_mod.where(), "certifi"))
except Exception:
    pass

# ★bge-m3 嵌入模型(2.3G):CI 在构建前下到 models/bge-m3,打进包→离线开箱即用。
#   没下(本机快速构建)则跳过,运行时回落 hf-mirror 下载。
_bge = os.path.join(here, "models", "bge-m3")
if os.path.isdir(_bge):
    for root, _, files in os.walk(_bge):
        for f in files:
            full = os.path.join(root, f)
            datas.append((full, os.path.relpath(root, here)))

# ★音视频入库模型(~1.2G):SenseVoice ASR + silero VAD + pyannote分割 + 3dspeaker声纹。
#   CI 从 sherpa-onnx 官方 releases 下到 models/(与 T430 实测同版本);media_ingest 从 _MEIPASS/models 找。
#   没下则跳过(运行时模型缺失 media_ingest 优雅降级)。
for _mv in ("sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17",
            "sherpa-onnx-pyannote-segmentation-3-0"):
    _mp = os.path.join(here, "models", _mv)
    if os.path.isdir(_mp):
        for root, _, files in os.walk(_mp):
            for f in files:
                datas.append((os.path.join(root, f), os.path.relpath(root, here)))
for _mf in ("silero_vad.onnx", "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"):
    _fp = os.path.join(here, "models", _mf)
    if os.path.isfile(_fp):
        datas.append((_fp, "models"))
# ★ffmpeg(Mac Intel 静态二进制):音视频抽音轨用。CI 从 evermeet.cx 下到 bin/ffmpeg;
#   缺则 media_ingest 回落系统 which('ffmpeg')。
_ff = os.path.join(here, "bin", "ffmpeg")
if os.path.isfile(_ff):
    datas.append((_ff, "bin"))

# ★微信同步助手安装包(WxSync .dmg/.exe):打进包,客户端 sidecar /dl 就地发(离线下载,不出本地)。
#   CI 构建前从 106 下载中心拉到 downloads/。本机快速构建没拉则跳过。
_dl = os.path.join(here, "downloads")
if os.path.isdir(_dl):
    for f in os.listdir(_dl):
        if not f.startswith("."):
            datas.append((os.path.join(_dl, f), "downloads"))

hiddenimports = ["cv2"]  # cv2 走上面显式收库,这里只作 plain hidden import(不 collect_submodules 免 gapi 崩)
for pkg in ("sentence_transformers", "transformers", "sklearn",
            "fastapi", "uvicorn", "uvicorn.protocols", "uvicorn.lifespan",
            "uvicorn.loops.auto", "anyio", "fitz", "docx", "pptx", "openpyxl",
            "rapidocr", "onnxruntime", "PIL", "certifi",
            "jieba", "requests", "numpy", "sklearn.utils._typedefs",
            "sklearn.cluster", "sklearn.neighbors", "sklearn.feature_extraction.text",
            "sherpa_onnx", "soundfile", "edge_tts", "media_ingest"):   # ★音视频入库 + 一生旁白TTS
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        hiddenimports.append(pkg)

a = Analysis(
    ["sidecar_main.py"],
    pathex=[here],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PySide2", "PySide6", "IPython", "pytest", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="compound-sidecar",
    debug=False,
    strip=False,
    upx=False,      # torch 的 .so upx 压了会崩
    console=True,   # 需 stdio 供 Tauri 读日志
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="compound-sidecar",
)

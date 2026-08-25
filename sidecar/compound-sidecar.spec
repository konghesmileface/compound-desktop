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

# ★bge-m3 嵌入模型(2.3G):CI 在构建前下到 models/bge-m3,打进包→离线开箱即用。
#   没下(本机快速构建)则跳过,运行时回落 hf-mirror 下载。
_bge = os.path.join(here, "models", "bge-m3")
if os.path.isdir(_bge):
    for root, _, files in os.walk(_bge):
        for f in files:
            full = os.path.join(root, f)
            datas.append((full, os.path.relpath(root, here)))

# ★微信同步助手(client/wxsync,纯标准库):打进包。iPhone 备份导入 + 桌面实时增量同步。
_wx = os.path.join(here, "wxsync")
if os.path.isdir(_wx):
    for f in os.listdir(_wx):
        if f.endswith((".py", ".txt")):
            datas.append((os.path.join(_wx, f), "wxsync"))

hiddenimports = ["cv2"]  # cv2 走上面显式收库,这里只作 plain hidden import(不 collect_submodules 免 gapi 崩)
for pkg in ("sentence_transformers", "transformers", "sklearn",
            "fastapi", "uvicorn", "uvicorn.protocols", "uvicorn.lifespan",
            "uvicorn.loops.auto", "anyio", "fitz", "docx", "pptx", "openpyxl",
            "rapidocr", "onnxruntime", "PIL", "certifi",
            "jieba", "requests", "numpy", "sklearn.utils._typedefs",
            "sklearn.cluster", "sklearn.neighbors", "sklearn.feature_extraction.text"):
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

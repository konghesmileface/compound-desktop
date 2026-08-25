# PyInstaller spec: 把高精 OCR worker(PaddleOCR PP-StructureV3)冻成 onedir 二进制。
# 独立于主 sidecar(paddle 与 torch 依赖冲突,故分开进程/分开打包)。
# 用法(仅高精版,从 .paddlevenv 跑): .paddlevenv/bin/pyinstaller compound-paddle.spec
# 产物: dist/compound-paddle/compound-paddle
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files, collect_dynamic_libs

here = os.path.abspath(".")
datas, binaries, hiddenimports = [], [], []

# paddle / paddlex / paddleocr:整包收(大量动态 import + 模型配置 yaml + .so)
for pkg in ("paddle", "paddlex", "paddleocr"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass

# ★PP-StructureV3 模型打进包(区域无关、海外/国内离线开箱即用):CI 构建前下到 paddle_models/。
#   运行时 paddle_worker 设 PADDLE_PDX_CACHE_HOME 指向包内 paddle_models,不联网。
_pm = os.path.join(here, "paddle_models")
if os.path.isdir(_pm):
    for root, _, files in os.walk(_pm):
        for f in files:
            full = os.path.join(root, f)
            datas.append((full, os.path.join("paddle_models", os.path.relpath(root, _pm))))

# opencv(paddle 装的是 contrib 版)+ fastapi/uvicorn 栈
try:
    binaries += collect_dynamic_libs("cv2")
    datas += collect_data_files("cv2")
except Exception:
    pass
hiddenimports += ["cv2"]
for pkg in ("fastapi", "uvicorn", "uvicorn.protocols", "uvicorn.lifespan",
            "uvicorn.loops.auto", "anyio", "PIL", "numpy", "scipy", "sklearn",
            "shapely", "pyclipper", "skimage", "lxml", "premailer", "certifi",
            "python_multipart", "multipart"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        hiddenimports.append(pkg)

a = Analysis(
    ["paddle_worker.py"],
    pathex=[here],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PySide2", "PySide6", "IPython", "pytest",
              "notebook", "torch", "sentence_transformers"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="compound-paddle",
    debug=False, strip=False, upx=False, console=True,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="compound-paddle")

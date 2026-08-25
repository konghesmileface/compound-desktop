"""
可插拔 OCR 后端。

设计原则:每份 PDF 逐页处理,统一返回 (markdown_text, method)。
- text     : 直接抽 PDF 文字层(数字版 PDF,秒出、零误差、不联网)
- rapidocr : 本地轻量 OCR(扫描件兜底,纯 CPU、离线、免费)
- auto     : 先抽文字层,抽不到再走本地 OCR —— 默认后端
- unlimited: 把需要 OCR 的页导出成图片 + manifest,交给免费 GPU notebook
             跑 baidu/Unlimited-OCR(整文档单上下文),再回灌入库

以后有 GPU 了,把 unlimited 后端从"导出模式"换成"直连服务模式"即可,上层不变。
"""
from __future__ import annotations
import io
import os
import json

# 一页文字层字符数低于此值,判定为图片/扫描页,需要走 OCR。
# 扫描件通常抽出 0 字符,数字版即使稀疏也有几十字,20 能干净区分。
TEXT_MIN_CHARS = 20


def render_png(page, dpi: int = 200) -> bytes:
    """把一页 PDF 渲染成 PNG 字节。"""
    pix = page.get_pixmap(dpi=dpi)
    return pix.tobytes("png")


class BaseBackend:
    name = "base"

    def markdown_for_page(self, page, page_index: int, doc, render_dpi: int = 200):
        """返回 (markdown_text: str, method: str)。"""
        raise NotImplementedError

    def finalize(self, out_dir: str) -> str | None:
        """整批处理结束后的收尾钩子(默认无操作)。返回一个提示路径或 None。"""
        return None


class TextBackend(BaseBackend):
    """只抽文字层。适合数字版 PDF。"""
    name = "text"

    def markdown_for_page(self, page, page_index, doc, render_dpi=200):
        txt = page.get_text("text").strip()
        return txt, "text-layer"


class RapidOCRBackend(BaseBackend):
    """本地轻量 OCR。纯 CPU / 离线 / 免费,中英文都行。首次调用才加载模型。"""
    name = "rapidocr"

    def __init__(self):
        self._engine = None

    def _engine_lazy(self):
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self._engine = RapidOCR()
        return self._engine

    def markdown_for_page(self, page, page_index, doc, render_dpi=200):
        import numpy as np
        from PIL import Image

        png = render_png(page, render_dpi)
        img = Image.open(io.BytesIO(png)).convert("RGB")
        arr = np.array(img)
        result, _ = self._engine_lazy()(arr)
        if not result:
            return "", "ocr:rapidocr(empty)"
        # result: [[points, text, score], ...],按识别顺序拼接
        lines = [item[1] for item in result]
        return "\n".join(lines), "ocr:rapidocr"


class PaddleBackend(BaseBackend):
    """本地高精 OCR = PaddleOCR PP-StructureV3(版面+表格+公式+文字)。
    ★进程隔离:paddle 与 torch 依赖冲突,故 paddle 跑在独立 worker 二进制(自带 paddle 环境),
    这里只做 HTTP 客户端调本机 worker(PADDLE_OCR_URL)。轻量版没打 worker→不可用。
    协议同 T430(POST /ocr/image multipart → {"markdown": ...})。"""
    name = "paddle"

    def __init__(self, url: str | None = None, timeout: int = 300):
        self.url = (url or os.environ.get("PADDLE_OCR_URL", "http://127.0.0.1:8791")).rstrip("/")
        self.timeout = timeout

    def markdown_for_page(self, page, page_index, doc, render_dpi=200):
        import urllib.request
        png = render_png(page, render_dpi)
        boundary = "----compoundpaddleboundary7MA4YWxkTrZu0gW"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"p{page_index+1}.png\"\r\nContent-Type: image/png\r\n\r\n"
        ).encode() + png + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            self.url + "/ocr/image", data=body, method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=self.timeout) as r:
                md = json.load(r).get("markdown", "")
            return (md, "ocr:paddle-ppstructurev3") if md else ("", "ocr:paddle(empty)")
        except Exception as e:
            return (f"<!-- 高精 paddle worker 不可达({e});确认 {self.url}/health -->",
                    "paddle-unreachable")


class AutoBackend(BaseBackend):
    """默认后端:每页先抽文字层,抽不到(扫描件)再走本地 OCR。"""
    name = "auto"

    def __init__(self, ocr_backend: BaseBackend | None = None):
        self.text = TextBackend()
        self._ocr = ocr_backend  # 延迟创建,避免没扫描件时也加载 OCR 模型

    def _ocr_lazy(self):
        if self._ocr is None:
            self._ocr = RapidOCRBackend()
        return self._ocr

    def markdown_for_page(self, page, page_index, doc, render_dpi=200):
        txt = page.get_text("text").strip()
        if len(txt) >= TEXT_MIN_CHARS:
            return txt, "text-layer"
        # 图片/扫描页 —— 本地 OCR 兜底;若 OCR 没装好,优雅降级不崩
        try:
            return self._ocr_lazy().markdown_for_page(page, page_index, doc, render_dpi)
        except Exception as e:
            return (f"<!-- 本页是扫描件/图片,本地 OCR 未就绪({e});"
                    f"可用 ModelScope/T430 的 Unlimited-OCR 处理此页 -->",
                    "needs-ocr")


class UnlimitedOCRExportBackend(BaseBackend):
    """
    百度 Unlimited-OCR 后端(免费 GPU 路线)。

    本机没 GPU,所以这里做"导出模式":把每页(或仅需 OCR 的页)渲染成 PNG,
    连同 manifest 写到 export 目录。你再用免费 GPU notebook(ModelScope/Colab)
    跑 baidu/Unlimited-OCR,产出的 markdown 回灌到库里。

    以后有 GPU 了,把这里改成 HTTP 直连你的推理服务即可,上层调用不变。
    """
    name = "unlimited"

    def __init__(self, export_root: str, only_image_pages: bool = True):
        self.export_root = export_root
        self.only_image_pages = only_image_pages
        self.manifest = []
        os.makedirs(export_root, exist_ok=True)

    def markdown_for_page(self, page, page_index, doc, render_dpi=300):
        txt = page.get_text("text").strip()
        # 数字版页可选择直接用文字层,省 GPU 额度
        if self.only_image_pages and len(txt) >= TEXT_MIN_CHARS:
            return txt, "text-layer"

        stem = os.path.splitext(os.path.basename(doc.name))[0]
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in stem)[:60]
        img_name = f"{safe}__p{page_index + 1:04d}.png"
        img_path = os.path.join(self.export_root, img_name)
        with open(img_path, "wb") as f:
            f.write(render_png(page, render_dpi))
        self.manifest.append({
            "source_pdf": doc.name,
            "page": page_index + 1,
            "image": img_name,
        })
        # 占位:实际文本由 notebook 跑完后回灌
        return f"<!-- 待 Unlimited-OCR 识别: {img_name} -->", "unlimited:exported"

    def finalize(self, out_dir: str):
        path = os.path.join(self.export_root, "manifest.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f, ensure_ascii=False, indent=2)
        return path


DEFAULT_T430_URL = os.environ.get("T430_OCR_URL", "http://172.16.11.199:8100")


class T430Backend(BaseBackend):
    """
    百度 Unlimited-OCR 直连后端(T430 局域网常驻服务)。

    数字版页直接抽文字层(秒出、免算力),扫描/图片页渲染成 PNG POST 到
    T430 的 /ocr/image,拿回 Unlimited-OCR 识别的 markdown —— 局域网自动回库,
    不用像 ModelScope 那样手动下载。服务地址走环境变量 T430_OCR_URL 覆盖。
    """
    name = "t430"

    def __init__(self, url: str | None = None, only_image_pages: bool = True,
                 timeout: int = 600):
        self.url = (url or DEFAULT_T430_URL).rstrip("/")
        self.only_image_pages = only_image_pages
        self.timeout = timeout

    def markdown_for_page(self, page, page_index, doc, render_dpi=200):
        txt = page.get_text("text").strip()
        if self.only_image_pages and len(txt) >= TEXT_MIN_CHARS:
            return txt, "text-layer"
        try:
            png = render_png(page, render_dpi)
            md = self._post_image(png, f"p{page_index + 1:04d}.png")
            return md, "unlimited-ocr@t430"
        except Exception as e:
            return (f"<!-- 本页需 OCR,但 T430 服务不可达({e});"
                    f"确认 {self.url}/health 可访问、服务已起 -->", "t430-unreachable")

    def _post_image(self, png_bytes: bytes, filename: str) -> str:
        import urllib.request

        boundary = "----t430ocrboundary7MA4YWxkTrZu0gW"
        pre = (f"--{boundary}\r\n"
               f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
               f"Content-Type: image/png\r\n\r\n").encode()
        body = pre + png_bytes + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            self.url + "/ocr/image", data=body, method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        # 局域网直连:绕开 Mac 上的 HTTP_PROXY(否则 172.16.x 也被代理吞掉)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=self.timeout) as r:
            payload = json.load(r)
        return payload.get("markdown", "")


def make_backend(name: str, export_root: str | None = None) -> BaseBackend:
    name = (name or "auto").lower()
    if name == "text":
        return TextBackend()
    if name == "rapidocr":
        return RapidOCRBackend()
    if name == "paddle":
        return PaddleBackend()
    if name == "auto":
        return AutoBackend()
    if name == "t430":
        return T430Backend()
    if name == "unlimited":
        if not export_root:
            raise ValueError("unlimited 后端需要 export_root")
        return UnlimitedOCRExportBackend(export_root)
    raise ValueError(f"未知后端: {name}(可选 text/rapidocr/paddle/auto/t430/unlimited)")

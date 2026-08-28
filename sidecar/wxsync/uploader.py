# -*- coding: utf-8 -*-
"""
上传器
======

把一段"与X的对话" txt 以 multipart 文件形式 POST 到后端
    POST /api/upload?backend=auto   Authorization: Bearer <token>
后端已有解析器认 微信_与X.txt 格式,会自动:解析→认人→bge-m3嵌入→入库。

后端返回 {"job_id": "...", "files_total": N},可用 /api/job/{id} 轮询后端侧进度。
本模块只负责"把 txt 送上去",不阻塞等后端解析完。

只用标准库(urllib)手搓 multipart,避免给客户端引入 requests 依赖。
"""

import json
import mimetypes  # noqa: F401  (保留:未来传二进制附件时用)
import urllib.request
import urllib.error
import uuid


def _multipart(fields: dict, files: dict):
    """
    构造 multipart/form-data body。
    fields: 普通字段(这里用不到,留扩展)。
    files:  {form_name: (filename, bytes_content)}。
    返回 (content_type, body_bytes)。
    """
    boundary = "----wxsync" + uuid.uuid4().hex
    crlf = b"\r\n"
    buf = []
    for name, val in (fields or {}).items():
        buf.append(b"--" + boundary.encode())
        buf.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        buf.append(b"")
        buf.append(str(val).encode("utf-8"))
    for form_name, (filename, content) in files.items():
        if isinstance(content, str):
            content = content.encode("utf-8")
        buf.append(b"--" + boundary.encode())
        buf.append((f'Content-Disposition: form-data; name="{form_name}"; '
                    f'filename="{filename}"').encode("utf-8"))
        buf.append(b"Content-Type: text/plain; charset=utf-8")
        buf.append(b"")
        buf.append(content)
    buf.append(b"--" + boundary.encode() + b"--")
    buf.append(b"")
    body = crlf.join(buf)
    content_type = f"multipart/form-data; boundary={boundary}"
    return content_type, body


def upload_chat_txt(cfg, filename: str, content: str) -> dict:
    """
    上传一个聊天 txt。成功返回后端 JSON({job_id, files_total});失败抛异常。

    cfg      config.Config
    filename 形如 "微信_与老王.txt"(后端解析器据此认人)
    content  txt 全文
    """
    # upload 接口带 backend 查询参数
    url = cfg.upload_url + f"?backend={cfg.get('upload_backend', 'auto')}"
    content_type, body = _multipart(
        fields={}, files={"files": (filename, content)})

    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", content_type)
    for k, v in cfg.auth_header.items():
        req.add_header(k, v)

    # 绕系统/clash 代理直连后端(参考 relay_agent 踩坑)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=cfg.http_timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"raw": raw}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        raise RuntimeError(f"上传 HTTP {e.code}: {detail}") from e
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"上传失败: {e}") from e


def ingest_wechat_messages(cfg, messages, batch: int = 2000) -> dict:
    """把结构化微信消息批量发到 /api/wechat/ingest(iOS 历史 与 桌面实时共用)。
    服务端按 会话+时间(到分)+正文 的内容指纹统一去重 → 两条通道重叠也只入一次。
    每条 message: {session_name, ts, sender_name, sender_id, text}。
    返回累计 {ingested, dup, sessions}。失败抛异常。"""
    url = cfg.wechat_ingest_url
    headers = {"Content-Type": "application/json", **cfg.auth_header}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    total = {"ingested": 0, "dup": 0, "sessions": 0}
    for i in range(0, len(messages), batch):
        chunk = messages[i:i + batch]
        body = json.dumps({"messages": chunk}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        for k, v in headers.items():
            req.add_header(k, v)
        try:
            with opener.open(req, timeout=cfg.http_timeout) as resp:
                r = json.loads(resp.read().decode("utf-8"))
            total["ingested"] += int(r.get("ingested") or 0)
            total["dup"] += int(r.get("dup") or 0)
            total["sessions"] = max(total["sessions"], int(r.get("sessions") or 0))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:300]
            raise RuntimeError(f"入库 HTTP {e.code}: {detail}") from e
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"入库失败: {e}") from e
    return total

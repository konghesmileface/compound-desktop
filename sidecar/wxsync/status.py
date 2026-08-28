# -*- coding: utf-8 -*-
"""
状态上报模块
===========

统一把客户端当前状态 POST 给后端,让网页端能显示:
- 每个聊天/文档的入库进度条(处于哪个状态 + 百分比)
- 一个全局"正在实时拿微信聊天"的动态徽章(心跳新鲜=亮)

两类上报:
1. report_ingest(...)  → POST /api/ingest/status   入库进度(iPhone 导入、实时上传都用)
2. beat(...)           → POST /api/realtime/heartbeat  实时同步心跳(realtime_poll 定时打)

接口精确规格见 docs/WECHAT_SYNC_INTEGRATION.md。
本模块对网络错误"软失败":状态上报失败不该中断主流程(导入/同步),
只打印告警。所有函数都吞异常并返回 bool 表示是否成功。
"""

import json
import time
import urllib.request
import urllib.error

# 入库状态机枚举(和 docs/WECHAT_SYNC_INTEGRATION.md 完全一致)
# 前端进度条按这个顺序推进;failed 是终态之一。
STATES = [
    "queued",             # 已排队,等待上传
    "uploading",          # 正在上传文件到后端
    "parsing",            # 后端解析微信 txt(还原对话)
    "matching_contacts",  # 认人(识别对话对象)
    "embedding",          # bge-m3 嵌入 + 建索引
    "done",               # 完成
    "failed",             # 失败(终态)
]

# 各状态对应的"建议百分比"(前端没有更细粒度时的兜底展示值)
STATE_PERCENT = {
    "queued": 0,
    "uploading": 20,
    "parsing": 45,
    "matching_contacts": 65,
    "embedding": 85,
    "done": 100,
    "failed": 100,
}


def _post_json(url: str, payload: dict, headers: dict, timeout: int = 15) -> bool:
    """POST 一个 JSON,成功返回 True。失败只告警不抛。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    # 客户端一律绕代理直连后端(参考 relay_agent 踩坑:clash 会拦)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        print(f"[status] 上报 HTTP {e.code}: {url}")
    except Exception as e:  # noqa: BLE001
        print(f"[status] 上报失败(忽略): {e}")
    return False


class StatusReporter:
    """封装 config + 账号,给导入/实时模块共用。"""

    def __init__(self, cfg):
        self.cfg = cfg

    # ---------------- 入库进度 ---------------- #
    def report_ingest(self, job_id: str, contact: str, state: str,
                      percent: int = None, message: str = "",
                      job_backend_id: str = None) -> bool:
        """
        上报某个聊天/文档的入库进度。

        job_id       客户端生成的稳定 ID(一个聊天=一个 job,便于前端聚合进度条)
        contact      联系人/会话名(如 "老王"),前端进度条标题
        state        STATES 之一
        percent      0-100;不传就用 STATE_PERCENT 兜底
        message      附加说明(可选,失败原因等)
        job_backend_id 后端 /api/upload 返回的 job_id(如果有,便于后端关联)
        """
        if state not in STATES:
            print(f"[status] 未知状态 {state},仍照发")
        if percent is None:
            percent = STATE_PERCENT.get(state, 0)
        payload = {
            "job_id": job_id,
            "account": self.cfg.account,
            "source": "wechat",
            "contact": contact,
            "state": state,
            "percent": int(percent),
            "message": message,
            "backend_job_id": job_backend_id,
            "ts": int(time.time()),
        }
        return _post_json(self.cfg.ingest_status_url, payload,
                          self.cfg.auth_header, self.cfg.http_timeout)

    # ---------------- 实时心跳 ---------------- #
    def beat(self, running: bool, pending: int = 0, last_synced: int = 0,
             note: str = "") -> bool:
        """
        实时同步心跳。realtime_poll 每个轮询周期打一次。
        前端据此点亮"正在实时同步"徽章(心跳新鲜=亮,超时=灭)。

        running      当前实时轮询是否在跑
        pending      当前缓冲区里待上传的消息条数
        last_synced  最后一次成功上传的 unix 时间戳
        note         状态说明(如"微信未运行,已跳过")
        """
        payload = {
            "account": self.cfg.account,
            "source": "wechat",
            "running": bool(running),
            "pending": int(pending),
            "last_synced": int(last_synced),
            "note": note,
            "ts": int(time.time()),
        }
        return _post_json(self.cfg.heartbeat_url, payload,
                          self.cfg.auth_header, self.cfg.http_timeout)

    def query_toggle(self) -> bool:
        """
        问后端"用户在网页上有没有关掉实时开关"。
        用 GET /api/realtime/status 拿 enabled 字段。
        网络失败时返回本地 config 的值(降级,别误停)。
        """
        url = self.cfg.realtime_status_url + f"?account={self.cfg.account}"
        req = urllib.request.Request(url, method="GET")
        for k, v in self.cfg.auth_header.items():
            req.add_header(k, v)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=self.cfg.http_timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return bool(data.get("enabled", self.cfg.realtime_enabled))
        except Exception as e:  # noqa: BLE001
            print(f"[status] 查询实时开关失败,沿用本地配置: {e}")
            return bool(self.cfg.realtime_enabled)


if __name__ == "__main__":
    from config import load_config
    r = StatusReporter(load_config())
    print("测试上报入库进度…")
    r.report_ingest("test-job-1", "老王", "uploading", 20, "自测")
    print("测试打心跳…")
    r.beat(running=True, pending=3, last_synced=int(time.time()))

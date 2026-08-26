"""
可插拔 LLM 客户端(BYO:用户自填服务商 + key)。
配置存 settings.json(设置页写入),支持 OpenAI 兼容接口:DeepSeek / OpenAI / Ollama 本地。
"""
from __future__ import annotations
import os
import json
import time
import urllib.request
import urllib.error

BRAIN = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(BRAIN, "settings.json")

# 每家预置 (接口地址, 质量模型, 快模型)。★接口地址已联网核实(2026-08);模型名尽量用稳定别名/确定可用的,
#   用户只需选厂商+填 key 即最优开箱;两档都可在设置里自由覆盖(未来出新模型自己填名字,不改代码)。
PROVIDER_DEFAULTS = {
    "deepseek": ("https://api.deepseek.com", "deepseek-v4-pro", "deepseek-v4-flash"),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-max", "qwen-flash"),          # 稳定别名,自动跟最新代
    "doubao": ("https://ark.cn-beijing.volces.com/api/v3", "doubao-pro-32k", "doubao-lite-32k"),      # ★豆包多需填「接入点ID」,见设置提示
    "kimi": ("https://api.moonshot.cn/v1", "kimi-k2.5", "kimi-k2.5"),
    "zhipu": ("https://open.bigmodel.cn/api/paas/v4", "glm-4.6", "glm-4.5-flash"),
    "openai": ("https://api.openai.com/v1", "gpt-5", "gpt-5-mini"),
    "claude": ("https://api.anthropic.com/v1", "claude-sonnet-4-6", "claude-haiku-4-5"),              # OpenAI 兼容层
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-pro", "gemini-2.5-flash"),
    "siliconflow": ("https://api.siliconflow.cn/v1", "deepseek-ai/DeepSeek-V3.2", "Qwen/Qwen3-8B"),
    "hunyuan": ("https://api.hunyuan.cloud.tencent.com/v1", "hunyuan-t1-latest", "hunyuan-lite"),
    "ollama": ("http://127.0.0.1:11434/v1", "llama3", "llama3"),
}


def load_cfg() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cfg(cfg: dict):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def resolved():
    """返回 (provider, base_url, 质量模型, key)。质量模型=默认模型(交付物/深度用)。"""
    cfg = load_cfg()
    prov = cfg.get("llm_provider", "deepseek")
    d = PROVIDER_DEFAULTS.get(prov, PROVIDER_DEFAULTS["deepseek"])
    base = (cfg.get("llm_base_url") or d[0]).rstrip("/")
    model = cfg.get("llm_model") or d[1]      # 用户覆盖 > 预置质量模型
    key = cfg.get("llm_key", "")
    return prov, base, model, key


def quality_model():
    """质量模型(交付物/深度分析):就是默认模型。"""
    return resolved()[2]


def fast_model():
    """快模型(批量抽取/交互问答:省成本+秒回)。用户覆盖 > 每家预置快模型 > 回落质量模型。
    ★写死只当便捷默认;用户可在设置里填任何模型名(未来新模型无需改代码)。"""
    cfg = load_cfg()
    prov = cfg.get("llm_provider", "deepseek")
    d = PROVIDER_DEFAULTS.get(prov, PROVIDER_DEFAULTS["deepseek"])
    fast = cfg.get("llm_fast_model") or (d[2] if len(d) > 2 else None)
    return fast or None   # None → chat() 回落到质量模型


def chat(messages, temperature: float = 0.4, max_tokens: int = 2000, model: str = None) -> str:
    """带"空返回重试":deepseek-v4-flash 会间歇性返回空字符串(~25%),
    直接用会击穿"今日发现/连接发现"。这里最多试 3 次,空/异常都重试,轻微退避。"""
    prov, base, dmodel, key = resolved()
    model = model or dmodel
    if not key and prov != "ollama":
        raise RuntimeError("未配置 AI key,请到「设置」页填写")
    url = base + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    # 以客户网络为主:直连(ProxyHandler({})=不塞任何代理),用 certifi 证书库正常校验
    # (冻结包里系统 CA 路径可能是空的,不显式给 certifi 会连合法证书都验不过)。
    # ★绝不做免校验回落:若客户本地代理/加速器拦截 TLS 导致校验失败,如实报错,由客户处理。
    import ssl as _ssl
    try:
        import certifi as _certifi
        _ctx = _ssl.create_default_context(cafile=_certifi.where())
    except Exception:
        _ctx = _ssl.create_default_context()
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=_ctx))
    last_err = "empty"
    for attempt in range(3):
        try:
            # ★换任何模型都不崩:空返回多半是推理模型把 max_tokens 花在思考上了,
            #   每次重试自动加倍 token(推理/非推理自适应,调用方不用管模型类型)
            mt = min(max(max_tokens, 2000) * (2 ** attempt), 16000)
            payload = {"model": model, "messages": messages,
                       "temperature": temperature, "max_tokens": mt}
            # ★thinking:disabled 是 DeepSeek 专属参数(flash 默认开思考会吃空 tokens)。
            #   只对 DeepSeek 的 flash 下发,绝不发给别家(否则别家 API 可能 400)。
            if prov == "deepseek" and "flash" in (model or "").lower():
                payload["thinking"] = {"type": "disabled"}
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            # 质量/大输出调用给更长超时(推理模型 + 长文本正常就要 1-3 分钟,别掐断);小输出/交互 90s 够。
            to = 180 if mt >= 6000 else 90
            with opener.open(req, timeout=to) as r:
                data = json.load(r)
            content = ((data.get("choices") or [{}])[0].get("message", {}) or {}).get("content") or ""
            if content.strip():
                return content
            last_err = "空返回(max_tokens=%d)" % mt
        except urllib.error.HTTPError as e:
            # 模型名下线/不存在 → 明确引导用户去设置改,而不是含糊报错(便捷默认哪天失效也能自愈)
            try:
                emsg = e.read().decode("utf-8", "ignore")[:300]
            except Exception:
                emsg = str(e)
            if e.code in (400, 404) and ("model" in emsg.lower() or "not found" in emsg.lower() or "does not exist" in emsg.lower()):
                raise RuntimeError("模型「%s」不可用(可能已下线/名称有变)。请到「设置」填写当前可用的模型名。原始信息:%s" % (model, emsg))
            last_err = "%s %s" % (e.code, emsg)
        except Exception as e:
            last_err = e
        time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(_friendly_err(last_err))


def _friendly_err(err) -> str:
    """把技术错误翻成客户看得懂的人话(绝不把 Python/SSL 原文丢给用户)。"""
    s = str(err); low = s.lower()
    if "certificate_verify_failed" in low or "self signed certificate" in low or "ssl" in low:
        return ("连不上 AI 服务:你电脑上的代理 / 加速器(如 Clash、云翼加速)拦截了到 AI 的加密连接。"
                "请先关闭代理 / 加速器,或把 api.deepseek.com 设为直连,再点「测试连通」。")
    if "timed out" in low or "timeout" in low:
        return "连接 AI 服务超时。请检查网络是否正常,或稍后再试。"
    if any(k in low for k in ("connection refused", "getaddrinfo", "name or service",
                              "failed to establish", "urlopen error", "network is unreachable")):
        return "连不上 AI 服务。请确认你的网络能正常上网、能访问 AI 服务地址(公司网 / 校园网可能屏蔽),再试。"
    if "401" in s or "403" in s or "unauthorized" in low or ("invalid" in low and "key" in low):
        return "AI key 无效或没有权限。请到「设置」检查 key 是否填对、账户是否还有余额。"
    if "空返回" in s or "empty" in low or "max_tokens" in low:
        return "AI 暂时没返回内容,请稍后重试;若一直这样,换一个模型名再试。"
    return "AI 连接失败,请检查网络和 key 后重试。"


def test_key() -> dict:
    """测试当前配置能否连通。"""
    try:
        out = chat([{"role": "user", "content": "回复:ok"}], max_tokens=10)
        return {"ok": True, "reply": out[:40]}
    except Exception as e:
        return {"ok": False, "error": str(e)}

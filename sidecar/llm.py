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

# ★settings.json(含 AI key)存数据目录(BRAIN_DATA),不能写包内:冻结包只读安装会崩,
#   且写进包里重装即丢配置。回落本文件目录仅为源码直跑时。
BRAIN = os.environ.get("BRAIN_DATA") or os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(BRAIN, "settings.json")
_SETTINGS_PATH_OLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")  # 旧位置(包内),仅兼容读

# 每家预置 (接口地址, 质量模型, 快模型)。★接口地址已联网核实(2026-08);模型名尽量用稳定别名/确定可用的,
#   用户只需选厂商+填 key 即最优开箱;两档都可在设置里自由覆盖(未来出新模型自己填名字,不改代码)。
PROVIDER_DEFAULTS = {
    "deepseek": ("https://api.deepseek.com", "deepseek-v4-pro", "deepseek-v4-flash"),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-max", "qwen-flash"),          # 稳定别名,自动跟最新代
    "doubao": ("https://ark.cn-beijing.volces.com/api/v3", "doubao-seed-2-1-pro-260628", "doubao-seed-2-0-mini-260428"),  # ★火山方舟:模型名要带准确版本号,旧doubao-pro-32k已下线;去控制台复制
    "kimi": ("https://api.moonshot.cn/v1", "kimi-k2.5", "kimi-k2.5"),
    "zhipu": ("https://open.bigmodel.cn/api/paas/v4", "glm-4.6", "glm-4.5-flash"),
    "openai": ("https://api.openai.com/v1", "gpt-5", "gpt-5-mini"),
    "claude": ("https://api.anthropic.com/v1", "claude-sonnet-4-6", "claude-haiku-4-5"),              # OpenAI 兼容层
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-pro", "gemini-2.5-flash"),
    "siliconflow": ("https://api.siliconflow.cn/v1", "deepseek-ai/DeepSeek-V3.2", "Qwen/Qwen3-8B"),
    "hunyuan": ("https://api.hunyuan.cloud.tencent.com/v1", "hunyuan-t1-latest", "hunyuan-lite"),
    "ollama": ("http://127.0.0.1:11434/v1", "llama3", "llama3"),
}


# ★★每账号独立设置(含 AI key):按"当前账号"读写 settings_<owner>.json,不同账号互不干扰。
#   当前账号=线程本地上下文,由 app._me()(每个鉴权接口都调)/后台分析循环 设置。
#   load_cfg/resolved/fast_model 都走这里→签名不变、自动变成每账号。
import threading as _thr
_ctx = _thr.local()

def set_owner(owner):
    """设置当前线程的账号上下文(app._me 里调,后台分析每个 owner 前调)。"""
    _ctx.owner = str(owner or "")

def get_owner():
    return getattr(_ctx, "owner", "") or ""

def _owner_path(owner):
    import re as _re
    safe = _re.sub(r"[^0-9A-Za-z_.\-]", "_", str(owner))[:64] or "_"
    return os.path.join(BRAIN, "settings_%s.json" % safe)

def _write_cfg(path, cfg):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def load_cfg() -> dict:
    owner = get_owner()
    if owner:
        p = _owner_path(owner)
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
        # ★新账号(无自己的设置文件)=空,绝不继承别人的 key。
        #   不做全局→账号自动迁移(否则"新账号先登录"会把机主 key 继承过去,正是要避免的)。
        #   现有机主账号更新后需重新填一次 key(一次性;换来彻底隔离)。
        return {}
    # 无 owner 上下文(极少见:未鉴权/后台未设 owner)→ 读全局兼容
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        pass
    try:
        with open(_SETTINGS_PATH_OLD, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cfg(cfg: dict):
    owner = get_owner()
    _write_cfg(_owner_path(owner) if owner else SETTINGS_PATH, cfg)


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


# ★最近一次 LLM 结果状态(给前端透出:后台建卡/情报静默失败时,前端能显示"AI欠费"而非无限转圈)。
#   kind: "" 正常 / "quota" 余额不足 / "auth" key无效 / "network" 连不上 / "other";msg 是人话。
LAST_LLM = {"ok": True, "kind": "", "msg": "", "ts": 0}

def _classify_kind(friendly: str) -> str:
    if "余额不足" in friendly or "额度" in friendly: return "quota"
    if "key 无效" in friendly or "没有权限" in friendly: return "auth"
    if "连不上" in friendly or "超时" in friendly or "网络" in friendly: return "network"
    return "other"

def _note_llm(ok: bool, friendly: str = ""):
    import time as _t
    LAST_LLM.update(ok=ok, kind=("" if ok else _classify_kind(friendly)), msg=("" if ok else friendly), ts=int(_t.time()))


def chat(messages, temperature: float = 0.4, max_tokens: int = 2000, model: str = None, cfg_override: dict = None) -> str:
    """带"空返回重试":deepseek-v4-flash 会间歇性返回空字符串(~25%),
    直接用会击穿"今日发现/连接发现"。这里最多试 3 次,空/异常都重试,轻微退避。
    ★cfg_override:测试连通时前端传当前填的 key/model/provider/base_url,免"必须先保存才能测"。"""
    if cfg_override:
        prov = cfg_override.get("llm_provider") or "deepseek"
        _d = PROVIDER_DEFAULTS.get(prov, PROVIDER_DEFAULTS["deepseek"])
        base = (cfg_override.get("llm_base_url") or _d[0]).rstrip("/")
        dmodel = cfg_override.get("llm_model") or _d[1]
        key = cfg_override.get("llm_key") or ""
    else:
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
            _choice = (data.get("choices") or [{}])[0]
            content = (_choice.get("message", {}) or {}).get("content") or ""
            # ★finish_reason=length=输出被 max_tokens 掐断。推理模型(如 v4-pro)思考会吃掉大半
            #   tokens,剩下半截 JSON 非空但不可用(实测画像:3000 tokens 被思考吃 2641,正文截断
            #   →上层 json.loads 炸→误报「检查模型/key」)。截断同样要重试加倍,别当成功返回;
            #   最后一轮仍截断则原样返回(尽力而为,不比旧行为差)。
            if content.strip() and (_choice.get("finish_reason") != "length" or attempt == 2):
                _note_llm(True)   # ★成功→清除欠费/错误标记(前端恢复正常)
                return content
            last_err = ("输出被截断" if content.strip() else "空返回") + "(max_tokens=%d)" % mt
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
    # ★快模型被限流(429 / rate limit / too many requests)→自动回落质量模型重试一次。
    #   火山 doubao mini 快模型常 429,而 build_intel(承诺雷达)/建卡等后台任务都用快模型,
    #   不回落就静默失败→承诺雷达永远填不满(实测 mac2 卡在 24/39)。质量模型有余量、能跑通。
    #   仅当本次用的不是默认质量模型时回落,避免死循环(回落调用 model==dmodel 不会再回落)。
    _le = str(last_err).lower()
    if model != dmodel and ("429" in _le or "too many request" in _le or "rate limit" in _le or "rate_limit" in _le):
        try:
            return chat(messages, temperature=temperature, max_tokens=max_tokens, model=dmodel, cfg_override=cfg_override)
        except Exception:
            pass
    _friendly = _friendly_err(last_err)
    _note_llm(False, _friendly)   # ★记下最近失败原因,供 /api/analysis_status 透出到前端
    raise RuntimeError(_friendly)


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
    # ★余额不足/额度用尽:各家 LLM 欠费返回 402 或 insufficient_balance/insufficient_quota/quota exceeded 等。
    #   必须在 401 之前判(有的家欠费也回 401),否则会被误报成"key 无效"或最后兜底的"网络失败",坑用户。
    if ("402" in s or "insufficient" in low or "quota" in low or "balance" in low
            or "exceeded your current" in low or "欠费" in s or "余额不足" in s or "arrears" in low):
        return ("你的 AI 账户余额不足 / 额度已用尽。key 没问题、不用改 —— 请到你的 AI 服务商平台"
                "(如 DeepSeek / 通义 / 你填的那家)充值或提升额度后,再继续使用。")
    if "429" in s or "too many request" in low or "rate limit" in low or "rate_limit" in low or "requests per" in low or "tpm" in low or "rpm" in low:
        return ("AI 模型额度 / 并发已用尽(服务商返回 429)。这不是慢,是该模型暂时拒绝了请求 —— "
                "多为这个模型的免费额度 / 并发上限用完(不一定是账户欠费,换个模型往往还能用)。"
                "已自动回落到你的质量模型继续;若仍失败,请到你的 AI 服务商平台给该模型充值 / 提额,或在「设置」换一个模型。")
    if "401" in s or "403" in s or "unauthorized" in low or ("invalid" in low and "key" in low):
        return "AI key 无效或没有权限。请到「设置」检查 key 是否填对、账户是否还有余额。"
    if "空返回" in s or "empty" in low or "max_tokens" in low:
        return "AI 暂时没返回内容,请稍后重试;若一直这样,换一个模型名再试。"
    return "AI 连接失败,请检查网络和 key 后重试。"


def test_key(cfg_override: dict = None) -> dict:
    """测试连通。cfg_override 有值=测前端当前填的配置(不用先保存);无=测已保存配置。"""
    try:
        out = chat([{"role": "user", "content": "回复:ok"}], max_tokens=10, cfg_override=cfg_override or None)
        return {"ok": True, "reply": out[:40]}
    except Exception as e:
        return {"ok": False, "error": str(e)}

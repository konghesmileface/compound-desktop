"""深度聊天情报(P0 杀手级功能统一抽取层)。
对每个微信联系人聊天,用最强模型(跟随设置)一次抽出:
承诺(带时间锚)/ 数字台账 / 供给信号 / 需求信号 / 履约事件 / 雷区 / 暖场话题。
按 msgcount 缓存(表 chat_intel)。上层四个功能都是它的视图:
  1. 承诺雷达      = 跨人聚合 commitments,按到期排序
  2. 数字台账      = per 联系人 numbers
  3. 供需撮合雷达  = supply × demand 跨人配对(再过一次 LLM 精配)
  4. 见面简报+履约 = briefing 组合 + reliability 统计
"""
import json
import re
import datetime as _dt
import llm as LLM

try:
    from owner_ctx import is_owner as _is_owner
except Exception:
    def _is_owner(name, con=None, owner=None):
        n = (name or "").strip()
        return n.startswith("我")

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_intel (
    username TEXT,
    contact  TEXT,
    doc_id   INTEGER,
    msgcount INTEGER,
    day      TEXT,
    data     TEXT,
    PRIMARY KEY (username, contact)
);
"""


def ensure(con):
    con.executescript(SCHEMA)


_KEYS = ("commitments", "numbers", "supply", "demand", "reliability", "landmines", "warm_topics")


def build_intel(contact, chat_text, oname=""):
    """一次抽全一个联系人的结构化情报。返回 dict 或 None。oname=账号本人显示名(动态识别,通用于任何客户)。"""
    me = oname or "用户本人"
    sysp = (
        "你是用户的第二大脑。账号本人是「" + me + "」(用户本人),对方是联系人「%s」。不要猜测用户本人的身份或职业,把TA当作已知的固定主体。"
        "基于用户本人与联系人「%s」的微信聊天记录,抽取**结构化情报**。"
        "只依据聊天原文,绝不编造;没有的项给空数组。"
        "日期尽量规范成 YYYY-MM-DD(能从上下文/聊天时间戳推断就推;若原话是相对时间如『下周四/月底』,结合聊天时间戳换算成具体日期;实在推不出才留空)。\n"
        "★who 字段只能填两个值之一:`我`(指账号本人「" + me + "」,以第一人称发言或以本人名署名的一方)或 `对方`。绝不要填具体人名。\n"
        "只输出 JSON:\n"
        "{"
        '"commitments":[{"who":"我 或 对方","what":"承诺/答应要做的事","due":"YYYY-MM-DD或空","done":false,"quote":"原话片段"}],'
        '"numbers":[{"item":"什么(额度/报价/期限/利率/点差/返点/费率等)","value":"具体数值(带单位,利率/点差统一bp)","date":"YYYY-MM-DD或空","context":"一句话背景"}],'
        '"supply":[{"what":"手上有什么可出/可提供(资产/额度/资源/货)","detail":"要素:金额/期限/价位等","who":"我 或 对方","date":""}],'
        '"demand":[{"what":"在找什么/有什么需求","detail":"要素","who":"我 或 对方","date":""}],'
        '"reliability":[{"event":"一次承诺是否兑现","kept":true,"delay_days":0}],'
        '"landmines":["雷区/敏感话题/聊崩过的点(下次见面别踩)"],'
        '"warm_topics":["可暖场的近期话题(对方最近关心或提过的事)"]'
        "}"
    ) % (contact, contact)
    try:
        ct = chat_text or ""
        sample = ct if len(ct) <= 8200 else (ct[:2000] + "\n…(中间略)…\n" + ct[-6000:])
        # ★flash 快模型 + 大 max_tokens:pro 推理模型每条 1-2 分钟,646 联系人跑不完(radar 缓存永远填不满);
        # 结构化抽取 flash 足够,速度快一个量级。
        out = LLM.chat([{"role": "system", "content": sysp},
                        {"role": "user", "content": sample}],
                       temperature=0.2, max_tokens=8000, model=LLM.fast_model())
        m = re.search(r"\{.*\}", out, re.S)
        if not m:
            return None
        d = json.loads(m.group(0))
        for k in _KEYS:
            if not isinstance(d.get(k), list):
                d[k] = []
        return d
    except Exception:
        return None


def _wechat_docs(con, owner, limit=None):
    # ★铁律:分析必须铺满全部聊天,不设隐形上限(limit=None=全量;SQLite LIMIT -1=不限)
    return con.execute(
        "SELECT id, filename FROM documents WHERE owner=? AND filename LIKE '微信_与%' "
        "ORDER BY pages DESC LIMIT ?", (owner, limit if limit else -1)).fetchall()


def all_intel(con, owner, refresh=False, limit=None, generate=True):
    """为所有微信联系人生成/取情报(按 msgcount 缓存,聊天没长新内容就复用)。
    generate=False:只返回已缓存的(秒回,绝不在请求里同步跑 LLM);缺的交给后台回填。
    ★雷达等交互视图必须用 generate=False,否则 646 联系人逐个 build_intel 会把请求卡死。"""
    ensure(con)
    day = _dt.date.today().isoformat()
    try:
        import owner_ctx as _oc
        oname = _oc.resolve_owner_name(con, owner)
    except Exception:
        oname = ""
    out = []
    for did, fn in _wechat_docs(con, owner, limit):
        contact = fn.replace("微信_与", "").replace(".txt", "")
        if not refresh and not generate:
            # 只读缓存:一次查询,不读全部页、不算 mc、不跑 LLM
            row = con.execute("SELECT data FROM chat_intel WHERE username=? AND contact=?",
                              (owner, contact)).fetchone()
            if row:
                out.append({"contact": contact, "doc_id": did, **json.loads(row[0])})
            continue
        pages = con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no", (did,)).fetchall()
        text = "\n".join(p[0] for p in pages)
        mc = text.count("\n")
        if not refresh:
            row = con.execute("SELECT msgcount, data FROM chat_intel WHERE username=? AND contact=?",
                              (owner, contact)).fetchone()
            if row and row[0] == mc:
                d = json.loads(row[1])
                out.append({"contact": contact, "doc_id": did, **d})
                continue
        intel = build_intel(contact, text, oname)
        if intel:
            con.execute("INSERT OR REPLACE INTO chat_intel(username,contact,doc_id,msgcount,day,data) "
                        "VALUES(?,?,?,?,?,?)", (owner, contact, did, mc, day, json.dumps(intel, ensure_ascii=False)))
            con.commit()
            out.append({"contact": contact, "doc_id": did, **intel})
    return out


# ---------------- 视图 ----------------

def _days_to(due):
    try:
        return (_dt.date.fromisoformat(due) - _dt.date.today()).days
    except Exception:
        return None


import hashlib as _hl

STALE_DAYS = 60   # 逾期超过 60 天 = 太老,默认折叠(几年前的旧承诺不刷屏)


def _commit_key(owner, contact, what):
    return _hl.md5(("%s|%s|%s" % (owner, contact, what)).encode("utf-8")).hexdigest()[:16]


def _ensure_dismiss(con):
    con.execute("CREATE TABLE IF NOT EXISTS commit_dismissed(username TEXT, key TEXT, ts TEXT, PRIMARY KEY(username,key))")


def dismiss_commitment(con, owner, key):
    """用户点「已了结/清除」某条承诺:只标记忽略,绝不删聊天记录。"""
    _ensure_dismiss(con)
    con.execute("INSERT OR REPLACE INTO commit_dismissed(username,key,ts) VALUES(?,?,?)",
                (owner, key, _dt.date.today().isoformat()))
    con.commit()
    return {"ok": True, "key": key}


def commitments_radar(con, owner, refresh=False):
    """承诺雷达:跨人聚合所有未完成承诺,分'我欠的/等对方的',按到期紧迫排序。
    带时间维度:stale=太老(逾期>60天)默认折叠;可点清除(commit_dismissed)。"""
    _ensure_dismiss(con)
    dismissed = {r[0] for r in con.execute("SELECT key FROM commit_dismissed WHERE username=?", (owner,)).fetchall()}
    intel = all_intel(con, owner, refresh=refresh, generate=bool(refresh))
    mine, theirs = [], []
    for it in intel:
        for c in it.get("commitments", []):
            if c.get("done"):
                continue
            what = c.get("what", "")
            key = _commit_key(owner, it["contact"], what)
            if key in dismissed:
                continue   # 用户已清除
            dt = _days_to(c.get("due", ""))
            item = {"contact": it["contact"], "doc_id": it["doc_id"], "key": key,
                    "what": what, "due": c.get("due", ""),
                    "days_to": dt, "quote": c.get("quote", ""),
                    "stale": bool(dt is not None and dt < -STALE_DAYS)}
            # ★用 is_owner 判归属:who 可能被抽成"孔贺/对方(孔贺)"等,startswith("我")会漏→本人承诺错分到"等对方"(P0-2)
            (mine if _is_owner(c.get("who")) else theirs).append(item)
    keyf = lambda x: (x["days_to"] if x["days_to"] is not None else 9999)
    mine.sort(key=keyf)
    theirs.sort(key=keyf)
    active = [x for x in mine + theirs if not x["stale"]]
    return {"mine": mine, "theirs": theirs,
            "overdue": [x for x in active if x["days_to"] is not None and x["days_to"] < 0],
            "active_count": len(active),
            "stale_count": sum(1 for x in mine + theirs if x["stale"])}


def number_ledger(con, owner, refresh=False):
    """数字台账:每个联系人的报价/额度/期限等结构化数字。"""
    intel = all_intel(con, owner, refresh=refresh, generate=bool(refresh))
    out = []
    for it in intel:
        nums = it.get("numbers", [])
        if nums:
            out.append({"contact": it["contact"], "doc_id": it["doc_id"], "numbers": nums})
    out.sort(key=lambda x: -len(x["numbers"]))
    return {"ledgers": out}


import hashlib as _hl2


def supply_demand_matches(con, owner, refresh=False):
    """供需撮合雷达:收集所有供给/需求信号 → LLM 精配成可牵线的机会。
    ★修(P0-1):落缓存(同输入=同结果,治非确定性)+ 硬禁自己配自己 + 大 max_tokens + 解析失败重试。"""
    intel = all_intel(con, owner, refresh=refresh, generate=bool(refresh))
    supply, demand = [], []
    for it in intel:
        for s in it.get("supply", []):
            supply.append({"contact": it["contact"], **s})
        for d in it.get("demand", []):
            demand.append({"contact": it["contact"], **d})
    base = {"supply_count": len(supply), "demand_count": len(demand), "supply": supply, "demand": demand}
    if not (supply and demand):
        return {"matches": [], **base}
    # 内容指纹:供需没变就复用上次结果(秒回 + 结果稳定,不再同输入一次空一次满)
    sig = _hl2.md5(json.dumps([supply, demand], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    con.execute("CREATE TABLE IF NOT EXISTS matches_cache(username TEXT, sig TEXT, data TEXT, PRIMARY KEY(username,sig))")
    if not refresh:
        r = con.execute("SELECT data FROM matches_cache WHERE username=? AND sig=?", (owner, sig)).fetchone()
        if r:
            return {"matches": json.loads(r[0]), **base}
    # ★两阶段(2026-08-18):全量信号>1300条一把喂LLM会超长返空——先向量粗筛跨人候选对,再LLM精配。
    _cand = None
    try:
        import semantic as _SEM
        import numpy as _np
        _texts = [("%s %s" % (x.get("what", ""), x.get("detail", "")))[:120] for x in supply] + \
                 [("%s %s" % (x.get("what", ""), x.get("detail", "")))[:120] for x in demand]
        _vecs = _SEM.get_model().encode(_texts, normalize_embeddings=True, batch_size=64)
        _sv = _np.asarray(_vecs[:len(supply)], dtype=_np.float32)
        _dv = _np.asarray(_vecs[len(supply):], dtype=_np.float32)
        _sims = _sv @ _dv.T
        _cand = []
        for si in range(len(supply)):
            for di in _np.argsort(-_sims[si])[:5]:
                sc = float(_sims[si][int(di)])
                if sc < 0.45:
                    break
                if supply[si]["contact"] == demand[int(di)]["contact"]:
                    continue
                _cand.append((sc, si, int(di)))
        _cand.sort(reverse=True)
        _cand = _cand[:220]
    except Exception:
        _cand = None
    if _cand:
        _lines = []
        for _rk, (_sc, _si, _di) in enumerate(_cand):
            _s0, _d0 = supply[_si], demand[_di]
            _lines.append("%d. 供[%s] %s(%s) ↔ 需[%s] %s(%s)" % (
                _rk + 1, _s0["contact"], _s0.get("what", ""), (_s0.get("detail") or "")[:40],
                _d0["contact"], _d0.get("what", ""), (_d0.get("detail") or "")[:40]))
        prompt = (
            "下面是候选的供需配对(已按语义相似度粗筛,双方均为不同联系人)。逐条判断哪些是**真正能牵线的撮合机会**:"
            "要素(品种/金额/期限/价位)对得上或接近才算。**最多返回 40 条最有把握的**(按把握从高到低排),confidence 用 高/中/低。只输出 JSON:"
            '{"matches":[{"supply_from":"联系人A","supply":"A有什么","demand_from":"联系人B","demand":"B找什么","why":"为什么能对上","confidence":"高/中/低"}]}\n\n'
            + "\n".join(_lines))
    else:
        prompt = (
            "下面是从微信聊天里抽出的『供给信号』和『需求信号』(各带来自哪个联系人)。"
            "找出**能牵线的撮合机会**:某个联系人手上有的,正好另一个**不同的**联系人在找,要素(金额/期限/价位/类型)对得上或接近。\n"
            "★硬性规则:supply_from 和 demand_from **必须是两个不同的联系人**,绝不允许同一个人的供给配自己的需求(那不叫撮合)。\n"
            "宁缺毋滥,但只要跨人且要素靠谱就给,confidence 用 高/中/低 表达把握。只输出 JSON:"
            '{"matches":[{"supply_from":"联系人A","supply":"A有什么","demand_from":"联系人B","demand":"B找什么","why":"为什么能对上","confidence":"高/中/低"}]}\n\n'
            "供给:\n" + json.dumps(supply[:250], ensure_ascii=False) +
            "\n\n需求:\n" + json.dumps(demand[:250], ensure_ascii=False))
    matches, parsed = [], False
    for attempt in range(2):   # flash(thinking关)+ 8000 tokens;解析失败重试一次
        try:
            out = LLM.chat([{"role": "system", "content": "你是精明的撮合中介,只给靠谱的跨人牵线建议,绝不把一个人的供需自己配自己。"},
                            {"role": "user", "content": prompt}], temperature=0.3, max_tokens=8000, model=LLM.fast_model())
            _i = out.find("{")
            _txt = out[_i:] if _i >= 0 else ""
            _got = None
            if _txt:
                try:
                    _got = json.loads(re.search(r"\{.*\}", _txt, re.S).group(0)).get("matches", []) or []
                except Exception:
                    _j = _txt.rfind("},")   # 被截断:砍到最后一个完整 match 对象再闭合
                    if _j > 0:
                        try:
                            _got = json.loads(_txt[:_j + 1] + "]}").get("matches", []) or []
                        except Exception:
                            _got = None
            if _got is not None:
                matches = _got
                parsed = True
                break
        except Exception as _e:
            matches = []
            try:
                import traceback
                open("/tmp/match_debug.log", "a").write("EXC attempt%d: %s\n" % (attempt, traceback.format_exc()[-600:]))
            except Exception:
                pass
    if not parsed:
        try:
            open("/tmp/match_debug.log", "a").write("NOPARSE out[:400]=%r\n" % (out[:400] if "out" in dir() else "<no out>"))
        except Exception:
            pass
    # 代码侧兜底:剔除同人配对
    matches = [x for x in matches if (x.get("supply_from") or "") != (x.get("demand_from") or "")]
    # ★去重:同一"供给方×需求方"只保留一条(最佳置信度)——治同两人因多档利率/金额反复出现刷屏
    _crank = {"高": 3, "中": 2, "低": 1}
    _best = {}
    for _x in matches:
        _k = ((_x.get("supply_from") or ""), (_x.get("demand_from") or ""))
        if _k not in _best or _crank.get(_x.get("confidence"), 0) > _crank.get(_best[_k].get("confidence"), 0):
            _best[_k] = _x
    matches = list(_best.values())
    # ★只有 LLM 真正跑成功才落缓存;调用失败(如 key 欠费 402)的空结果绝不缓存,否则充值后也不自愈
    if parsed:
        con.execute("INSERT OR REPLACE INTO matches_cache(username,sig,data) VALUES(?,?,?)",
                    (owner, sig, json.dumps(matches, ensure_ascii=False)))
        con.commit()
    return {"matches": matches, **base}


def reliability_profile(intel_item):
    """单个联系人的履约信用:承诺数/兑现数/平均拖延。"""
    rel = intel_item.get("reliability", [])
    total = len(rel)
    kept = sum(1 for r in rel if r.get("kept"))
    delays = [r.get("delay_days", 0) for r in rel if r.get("kept") is False or (r.get("delay_days") or 0) > 0]
    avg_delay = round(sum(delays) / len(delays), 1) if delays else 0
    return {"total": total, "kept": kept, "broken": total - kept, "avg_delay": avg_delay}


def briefing(con, owner, contact, refresh=False):
    """见面前简报:面向即将发生的这次互动,组合关系卡+未了结+雷区+暖场+履约。"""
    ensure(con)
    row = con.execute("SELECT doc_id, data FROM chat_intel WHERE username=? AND contact=?",
                      (owner, contact)).fetchone()
    if not row:
        # 没缓存就现抽
        docs = con.execute("SELECT id FROM documents WHERE owner=? AND filename=?",
                           (owner, "微信_与" + contact + ".txt")).fetchone()
        if not docs:
            return {"contact": contact, "found": False}
        did = docs[0]
        pages = con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no", (did,)).fetchall()
        text = "\n".join(p[0] for p in pages)
        try:
            import owner_ctx as _oc
            _on = _oc.resolve_owner_name(con, owner)
        except Exception:
            _on = ""
        intel = build_intel(contact, text, _on) or {k: [] for k in _KEYS}
        mc = text.count("\n")
        con.execute("INSERT OR REPLACE INTO chat_intel(username,contact,doc_id,msgcount,day,data) VALUES(?,?,?,?,?,?)",
                    (owner, contact, did, mc, _dt.date.today().isoformat(), json.dumps(intel, ensure_ascii=False)))
        con.commit()
    else:
        did = row[0]
        intel = json.loads(row[1])
    open_commit = [c for c in intel.get("commitments", []) if not c.get("done")]
    return {
        "contact": contact, "doc_id": did, "found": True,
        "open_commitments": open_commit,
        "landmines": intel.get("landmines", []),
        "warm_topics": intel.get("warm_topics", []),
        "key_numbers": intel.get("numbers", [])[:6],
        "reliability": reliability_profile(intel),
    }

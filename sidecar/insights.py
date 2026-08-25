"""P1/P2 洞察层:大部分是对已抽数据(聊天时间戳+发送方 / 关系卡 / chat_intel / 实体图)的**计算**,
少量用 LLM 收尾。全部按需算,不额外常驻抽取。
P1: 关系降温预警 / 人情待还 / 沉默线索复活 / 帮我回这条(拟稿)
P2: 关系资产负债表 / 业务全景(按事聚合) / 沟通体检
"""
import json
import re
import datetime as _dt
import llm as LLM

_TS = re.compile(r"\[(\d{4}-\d{2}-\d{2})[ T]?(\d{2}:\d{2})?")


def _parse_chat(text):
    """把一段聊天文本解析成 [(date, is_me, content)]。格式 [YYYY-MM-DD HH:MM] 我/对方/名: 内容。"""
    msgs = []
    for line in (text or "").splitlines():
        m = _TS.match(line.strip())
        if not m:
            continue
        try:
            d = _dt.date.fromisoformat(m.group(1))
        except Exception:
            continue
        rest = line.split("]", 1)[-1].strip()
        is_me = rest.startswith("我") or rest.startswith("我:") or rest.startswith("我：")
        content = rest.split(":", 1)[-1].split("：", 1)[-1].strip() if (":" in rest or "：" in rest) else rest
        msgs.append((d, is_me, content))
    return msgs


def _group_set(con, owner):
    """群 / 裸@chatroom 的联系人名集合(关系型洞察要把它们排除,只算 1对1)。根因A。"""
    g = set()
    try:
        for fn, in con.execute(
            "SELECT d.filename FROM documents d LEFT JOIN doc_kind k ON k.owner=d.owner AND k.doc_id=d.id "
            "WHERE d.owner=? AND d.filename LIKE '微信_与%' "
            "AND (COALESCE(k.is_group,0)=1 OR d.filename LIKE '%@chatroom%' OR d.filename LIKE '%@openim%')",
            (owner,)).fetchall():
            g.add(fn.replace("微信_与", "").replace(".txt", ""))
    except Exception:
        pass
    return g


def _contact_docs(con, owner, limit=None):
    # ★只取 1对1(is_group=0),群/裸@chatroom 不进关系型洞察(降温/资产负债表/沟通体检/沉默)。根因A
    return con.execute(
        "SELECT d.id, d.filename FROM documents d "
        "LEFT JOIN doc_kind k ON k.owner=d.owner AND k.doc_id=d.id "
        "WHERE d.owner=? AND d.filename LIKE '微信_与%' AND COALESCE(k.is_group,0)=0 "
        "AND d.filename NOT LIKE '%@chatroom%' AND d.filename NOT LIKE '%@openim%' "
        "ORDER BY d.pages DESC LIMIT ?", (owner, limit if limit else -1)).fetchall()


def _load_chats(con, owner, limit=None):
    """{contact: {doc_id, msgs, text}}。"""
    out = {}
    for did, fn in _contact_docs(con, owner, limit):
        contact = fn.replace("微信_与", "").replace(".txt", "")
        pages = con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no", (did,)).fetchall()
        text = "\n".join(p[0] for p in pages)
        out[contact] = {"doc_id": did, "msgs": _parse_chat(text), "text": text}
    return out


# ---------------- 结果缓存(全量分析~40s,不能每次点tab都算)----------------
# 签名=微信文档数+总页数:入库新聊天/长新消息就失效重算;进程内存缓存,重启即清。
_res_cache = {}


def _data_sig(con, owner):
    r = con.execute("SELECT COUNT(*), COALESCE(SUM(pages),0) FROM documents "
                    "WHERE owner=? AND filename LIKE '微信_与%'", (owner,)).fetchone()
    return "%s:%s" % (r[0], r[1])


def _cached(fn):
    """两级缓存:进程内存(最快)→ DB表 insights_cache(重启不丢,部署后无需预热)→ 真算。"""
    def wrap(con, owner, *a, **k):
        sig = _data_sig(con, owner)
        key = (fn.__name__, owner)
        hit = _res_cache.get(key)
        if hit and hit[0] == sig:
            return hit[1]
        con.execute("CREATE TABLE IF NOT EXISTS insights_cache(owner TEXT, name TEXT, sig TEXT, data TEXT, PRIMARY KEY(owner,name))")
        row = con.execute("SELECT sig, data FROM insights_cache WHERE owner=? AND name=?", (owner, fn.__name__)).fetchone()
        if row and row[0] == sig:
            try:
                v0 = json.loads(row[1])
                _res_cache[key] = (sig, v0)
                return v0
            except Exception:
                pass
        v = fn(con, owner, *a, **k)
        _res_cache[key] = (sig, v)
        try:
            con.execute("INSERT OR REPLACE INTO insights_cache(owner,name,sig,data) VALUES(?,?,?,?)",
                        (owner, fn.__name__, sig, json.dumps(v, ensure_ascii=False)))
            con.commit()
        except Exception:
            pass
        return v
    wrap.__name__ = fn.__name__
    return wrap


def _today():
    return _dt.date.today()


# ---------------- P1.1 关系降温预警(看节奏变化率,不是绝对天数)----------------
@_cached
def cooling_alerts(con, owner):
    chats = _load_chats(con, owner)
    alerts = []
    for contact, c in chats.items():
        msgs = c["msgs"]
        if len(msgs) < 6:
            continue
        dates = sorted(d for d, _, _ in msgs)
        # 历史典型间隔(相邻消息天数差的中位数)
        gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
        gaps = [g for g in gaps if g >= 0]
        if not gaps:
            continue
        gaps_sorted = sorted(gaps)
        median_gap = gaps_sorted[len(gaps_sorted) // 2] or 1
        last_gap = (_today() - dates[-1]).days
        # 近期主动性:最后20条里谁发得多
        recent = msgs[-20:]
        me_recent = sum(1 for _, im, _ in recent if im)
        them_recent = len(recent) - me_recent
        # 降温分:当前沉默相对历史节奏的倍数
        ratio = last_gap / max(median_gap, 1)
        # ★只报"近期才变冷、还救得回"的(7~180天);几年前的死关系不是降温是断了,别刷屏。根因P1-3
        if ratio >= 3 and 7 <= last_gap <= 180:
            level = "严重" if (ratio >= 6 and last_gap >= 30) else "注意"
            if median_gap <= 2:
                reason = f"以前联系很频繁,已 {last_gap} 天没动静"
            else:
                reason = f"平时约 {median_gap} 天一聊,已 {last_gap} 天没联系"
            if them_recent == 0 and me_recent > 0:
                reason += ";最近都是你在发、对方没回"
            alerts.append({"contact": contact, "doc_id": c["doc_id"], "level": level,
                           "last_gap": last_gap, "median_gap": median_gap, "ratio": round(ratio, 1),
                           "reason": reason, "msgcount": len(msgs)})
    alerts.sort(key=lambda a: -a["ratio"])
    return {"alerts": alerts}


# ---------------- P2.1 关系资产负债表 ----------------
@_cached
def relationship_balance(con, owner, window_days=90):
    chats = _load_chats(con, owner)
    today = _today()
    warming, cooling, fading, fresh, core = [], [], [], [], []
    total_recent = 0
    per_contact = []
    for contact, c in chats.items():
        msgs = c["msgs"]
        if not msgs:
            continue
        dates = [d for d, _, _ in msgs]
        recent = sum(1 for d in dates if (today - d).days <= window_days)
        prior = sum(1 for d in dates if window_days < (today - d).days <= window_days * 2)
        first_seen = min(dates)
        last_seen = max(dates)
        total_recent += recent
        per_contact.append({"contact": contact, "doc_id": c["doc_id"], "recent": recent, "prior": prior,
                            "total": len(msgs), "last_gap": (today - last_seen).days,
                            "is_new": (today - first_seen).days <= window_days})
    for p in per_contact:
        share = round(p["recent"] / total_recent * 100, 1) if total_recent else 0
        p["share"] = share
        if p["is_new"] and p["recent"] > 0:
            fresh.append(p)
        elif p["prior"] > 0 and p["recent"] == 0:
            fading.append(p)
        elif p["recent"] > p["prior"] * 1.5 and p["recent"] >= 3:
            warming.append(p)
        elif p["prior"] > 0 and p["recent"] < p["prior"] * 0.5:
            cooling.append(p)
        if p["recent"] >= 5:
            core.append(p)
    for lst in (warming, cooling, fading, fresh, core):
        lst.sort(key=lambda x: -x["recent"])
    return {"window_days": window_days, "warming": warming[:10], "cooling": cooling[:10],
            "fading": fading[:10], "fresh": fresh[:10], "core": core[:10],
            "time_spent": sorted(per_contact, key=lambda x: -x["recent"])[:10]}


# ---------------- P2.2 业务全景(按事/项目聚合,不只按人)----------------
@_cached
def business_panorama(con, owner):
    # 从 kb_entities 取项目/产品/机构类实体,按"事"聚合涉及的联系人
    # 非人物、非地点的实体(公司/机构/项目/产品/业务/合同/其他)按"事"聚合涉及的联系人
    rows = con.execute(
        "SELECT e.norm, e.name, e.etype, d.filename FROM kb_entities e "
        "JOIN documents d ON d.id=e.doc_id "
        "LEFT JOIN doc_kind k ON k.owner=e.owner AND k.doc_id=e.doc_id "
        "WHERE e.owner=? AND d.filename LIKE '微信_与%' AND COALESCE(k.is_group,0)=0 "
        "AND (e.etype IS NULL OR e.etype NOT IN ('人','地点')) AND length(e.norm)>=2", (owner,)).fetchall()
    topics = {}
    for norm, name, etype, fn in rows:
        contact = fn.replace("微信_与", "").replace(".txt", "")
        t = topics.setdefault(norm, {"name": name, "etype": etype, "contacts": set()})
        t["contacts"].add(contact)
    # 涉及多方的"事"(共享实体)最有全景价值
    out = []
    for norm, t in topics.items():
        if len(t["contacts"]) >= 2:
            out.append({"topic": t["name"], "etype": t["etype"],
                        "contacts": sorted(t["contacts"]), "contact_count": len(t["contacts"])})
    out.sort(key=lambda x: -x["contact_count"])
    return {"topics": out[:20]}


# ---------------- P2.3 沟通体检 ----------------
@_cached
def communication_checkup(con, owner):
    chats = _load_chats(con, owner)   # 已排除群
    i_went_cold, they_wait, you_chase, they_chase = [], [], [], []
    today = _today()
    analyzed = 0
    for contact, c in chats.items():
        msgs = c["msgs"]
        if len(msgs) < 4:
            continue
        analyzed += 1
        last_d, last_me, _ = msgs[-1]
        gap = (today - last_d).days
        # ① 对方最后一条在等我回(近期未回 2~45 天)
        if not last_me and 2 <= gap <= 45:
            they_wait.append({"contact": contact, "doc_id": c["doc_id"], "waiting_days": gap})
        # 近期(最后20条)方向性
        recent = msgs[-20:]
        me_r = sum(1 for _, im, _ in recent if im)
        them_r = len(recent) - me_r
        # ② 我对这个人变冷:近期消息不少但我几乎不发(还在联系但我退出了)
        if len(recent) >= 8 and me_r <= 1 and gap <= 120:
            i_went_cold.append({"contact": contact, "doc_id": c["doc_id"], "ratio": round(them_r / max(len(recent), 1), 2)})
        # ③ 你在追TA:近期你发得明显多、对方回得少(单向投入,可能热脸贴冷屁股)
        elif len(recent) >= 8 and me_r >= them_r * 2.2 and me_r >= 5 and gap <= 90:
            you_chase.append({"contact": contact, "doc_id": c["doc_id"], "me": me_r, "them": them_r})
        # ④ TA在追你:对方发得明显多、你回得少(你可能在冷落一个热络的人)
        elif len(recent) >= 8 and them_r >= me_r * 2.2 and them_r >= 5 and gap <= 90:
            they_chase.append({"contact": contact, "doc_id": c["doc_id"], "me": me_r, "them": them_r})
    they_wait.sort(key=lambda x: x["waiting_days"])   # 由近及远
    you_chase.sort(key=lambda x: -(x["me"] - x["them"]))
    they_chase.sort(key=lambda x: -(x["them"] - x["me"]))
    overview = {"analyzed": analyzed, "waiting": len(they_wait), "cold": len(i_went_cold),
                "you_chase": len(you_chase), "they_chase": len(they_chase)}
    return {"they_wait": they_wait[:12], "i_went_cold": i_went_cold[:12],
            "you_chase": you_chase[:12], "they_chase": they_chase[:12], "overview": overview}


# ---------------- P1.2 人情待还 ----------------
@_cached
def favors_to_repay(con, owner):
    # 从关系卡的 favors + chat_intel 的 warm_topics 组合(排除群:人情是1对1的事)。根因A
    groups = _group_set(con, owner)
    # 每个联系人的最后联系天数(用于按时间排序)——取 doc_kind.last_date
    last_days = {}
    try:
        for fn, ld in con.execute(
            "SELECT d.filename, k.last_date FROM documents d JOIN doc_kind k ON k.owner=d.owner AND k.doc_id=d.id "
            "WHERE d.owner=? AND d.filename LIKE '微信_与%'", (owner,)).fetchall():
            ct = fn.replace("微信_与", "").replace(".txt", "")
            try:
                last_days[ct] = (_today() - _dt.date.fromisoformat(ld)).days
            except Exception:
                pass
    except Exception:
        pass
    rows = [(c, d) for c, d in con.execute("SELECT contact, data FROM relationship_cards WHERE username=?", (owner,)).fetchall() if c not in groups]
    warm = {}
    try:
        for contact, data in con.execute("SELECT contact, data FROM chat_intel WHERE username=?", (owner,)).fetchall():
            try:
                warm[contact] = json.loads(data).get("warm_topics", [])
            except Exception:
                pass
    except Exception:
        pass
    out = []
    for contact, data in rows:
        try:
            d = json.loads(data)
        except Exception:
            continue
        favors = d.get("favors") or []
        if favors:
            out.append({"contact": contact, "favors": favors, "warm_topics": warm.get(contact, [])[:3],
                        "last_days": last_days.get(contact)})
    out.sort(key=lambda x: -len(x["favors"]))
    return {"items": out}


# ---------------- P1.3 沉默线索复活 ----------------
@_cached
def dormant_leads(con, owner):
    # 从 chat_intel:未完成承诺 / 供给 / 需求,且该联系人已久未联系
    today = _today()
    chats = _load_chats(con, owner)   # 已排除群
    groups = _group_set(con, owner)
    last_seen = {}
    for contact, c in chats.items():
        ds = [d for d, _, _ in c["msgs"]]
        if ds:
            last_seen[contact] = (today - max(ds)).days
    out = []
    try:
        for contact, data in con.execute("SELECT contact, data FROM chat_intel WHERE username=?", (owner,)).fetchall():
            if contact in groups:
                continue   # 群不算沉默"线索"
            gap = last_seen.get(contact)
            if gap is None or gap < 21:
                continue
            try:
                d = json.loads(data)
            except Exception:
                continue
            leads = []
            for c in (d.get("commitments") or []):
                if not c.get("done"):
                    leads.append("未了结:" + (c.get("what") or ""))
            for s in (d.get("supply") or []):
                leads.append("有:" + (s.get("what") or ""))
            for dm in (d.get("demand") or []):
                leads.append("找:" + (dm.get("what") or ""))
            if leads:
                out.append({"contact": contact, "silent_days": gap, "leads": leads[:4]})
    except Exception:
        pass
    out.sort(key=lambda x: -x["silent_days"])
    return {"items": out}


# ---------------- P1.4 帮我回这条(带历史+学说话风格拟稿)----------------
def draft_reply(con, owner, contact, incoming):
    doc = con.execute("SELECT id FROM documents WHERE owner=? AND filename=?",
                      (owner, "微信_与" + contact + ".txt")).fetchone()
    history = ""
    my_lines = []
    if doc:
        pages = con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no", (doc[0],)).fetchall()
        text = "\n".join(p[0] for p in pages)
        history = text[-6000:]
        for _, im, ct in _parse_chat(text):
            if im and ct:
                my_lines.append(ct)
    style = " / ".join(my_lines[-30:][:20]) if my_lines else ""
    sysp = (
        "你要帮用户回复微信消息。请**模仿用户本人的说话风格**(用词、语气、分寸感、常用口头语),"
        "结合用户和「%s」的历史聊天,给出 3 个可直接发送的回复草稿:一个稳妥得体、一个更热络、一个更简短干脆。"
        "别用 AI 腔,别太客气生硬,像这个人自己会说的话。只输出 JSON:"
        '{"drafts":[{"tone":"稳妥","text":"..."},{"tone":"热络","text":"..."},{"tone":"简短","text":"..."}]}'
    ) % contact
    user = ("【我平时的说话片段(模仿这个风格)】\n" + style +
            "\n\n【最近聊天历史】\n" + history +
            "\n\n【对方刚发来的消息】\n" + incoming +
            "\n\n请给我 3 个回复草稿。")
    try:
        out = LLM.chat([{"role": "system", "content": sysp}, {"role": "user", "content": user}],
                       temperature=0.6, max_tokens=900)
        m = re.search(r"\{.*\}", out, re.S)
        if m:
            return {"drafts": json.loads(m.group(0)).get("drafts", [])}
    except Exception:
        pass
    return {"drafts": []}

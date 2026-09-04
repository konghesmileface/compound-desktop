"""关系情报卡(P0.1 聊天分析杀手锏)。
对每个微信联系人的聊天记录,用 LLM 提炼一张活档案:
身份 / 关键事实 / open loops(未了结的事)/ 人情账本 / 关系走势 / 一句话总结,带出处文档。
"""
import json
import re
import hashlib as _hl
import datetime as _dt
import llm as LLM


def loop_key(contact, text):
    """未了结事项的稳定指纹(用户「删除」某条待了结时用,只标记忽略绝不删聊天)。"""
    return _hl.md5(((contact or "") + "|" + (text or "")).encode("utf-8")).hexdigest()[:16]


def dismiss_loop(con, owner, contact, text):
    con.execute("CREATE TABLE IF NOT EXISTS loop_dismissed(username TEXT, key TEXT, PRIMARY KEY(username,key))")
    con.execute("INSERT OR REPLACE INTO loop_dismissed(username,key) VALUES(?,?)", (owner, loop_key(contact, text)))
    con.commit()
    return {"ok": True}


def dismiss_reach(con, owner, contact):
    """把某人从「该联系了」提醒里移除(不想联系的客户,别老提醒)。只影响提醒,卡片/聊天都在。"""
    con.execute("CREATE TABLE IF NOT EXISTS reach_dismissed(username TEXT, contact TEXT, PRIMARY KEY(username,contact))")
    con.execute("INSERT OR REPLACE INTO reach_dismissed(username,contact) VALUES(?,?)", (owner, contact))
    con.commit()
    return {"ok": True}

SCHEMA = """
CREATE TABLE IF NOT EXISTS relationship_cards (
    username TEXT,
    contact  TEXT,
    doc_id   INTEGER,
    day      TEXT,
    msgcount INTEGER,
    data     TEXT,
    PRIMARY KEY (username, contact)
);
"""


def ensure(con):
    con.executescript(SCHEMA)


def _pjson(out):
    """容错解析 LLM 输出的 JSON(去 markdown 围栏、取最外层{}、修尾逗号)——弱模型也不崩。"""
    if not out:
        return None
    s = re.sub(r"```(?:json)?", "", out).strip()
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        return None
    for cand in (m.group(0), re.sub(r",\s*([}\]])", r"\1", m.group(0))):
        try:
            return json.loads(cand)
        except Exception:
            continue
    return None


try:
    from owner_ctx import OWNER_PROFILE as _OWNER_PROFILE, OWNER_NAME as _OWNER_NAME
except Exception:
    _OWNER_PROFILE, _OWNER_NAME = "账号本人是用户本人。", "用户"

_CARD_SYS = (
    "你是用户的第二大脑。" + _OWNER_PROFILE +
    "\n基于下面用户(孔贺)与联系人「%s」的微信聊天%s,提炼一张关于**这位联系人**的**关系情报卡**。"
    "\n★铁律:卡片主角是联系人「%s」,不是孔贺。identity / traits / summary 的主语必须是这位联系人;"
    "孔贺只作为参照方(如『和孔贺是同业』)。绝不要把孔贺本人写成卡片主角,也绝不猜测孔贺是谁。"
    "\n事实要具体、来自聊天原文,绝不编造;拿不准的项给空数组/空串,不要硬凑。只输出 JSON:\n"
    '{"identity":"这位联系人是谁:职务、机构、和孔贺怎么认识或什么关系(一两句,主语是联系人)",'
    '"traits":"此人特点:性格 / 沟通风格 / 做事靠不靠谱 / 和TA打交道要注意什么(从聊天推断,一两句,没依据就空串)",'
    '"facts":["值得记住的关键事实(TA在办的事/偏好/重要信息/住址电话等)"],'
    '"open_loops":["未了结的事:谁答应了什么还没做"],'
    '"favors":["人情账本:TA帮过孔贺的/孔贺欠TA的/TA欠孔贺的"],'
    '"dynamics":"这段关系近况一句话","summary":"一句话概括孔贺和这位联系人的关系"}'
)


def _card_one(contact, text):
    return _pjson(LLM.chat([{"role": "system", "content": _CARD_SYS % (contact, "记录", contact)},
                            {"role": "user", "content": text}], temperature=0.3, max_tokens=8000))


def _card_chunk(contact, chunk, i, n):
    sysp = ("这是用户与「%s」聊天的第 %d/%d 段。只抽出这一段里的:关键事实、未了结的事、人情往来、重要数字/报价。"
            "来自原文不编造,没有给空数组。只输出JSON:"
            '{"facts":[],"open_loops":[],"favors":[],"numbers":[]}') % (contact, i, n)
    return _pjson(LLM.chat([{"role": "system", "content": sysp},
                            {"role": "user", "content": chunk}], temperature=0.2, max_tokens=8000))


def _card_merge(contact, partials):
    material = json.dumps(partials, ensure_ascii=False)
    return _pjson(LLM.chat(
        [{"role": "system", "content": _CARD_SYS % (contact, "分段提炼材料", contact)},
         {"role": "user", "content": "下面是从全部聊天分段提炼的材料,去重后合并成一张完整关系卡:\n" + material}],
        temperature=0.3, max_tokens=8000))


def build_card(contact, chat_text, deep=False):
    """默认 deep=False:快模型(flash)单次,~2s出卡,批量可行。
    deep=True(「深度分析」按需):推理pro + 长聊天map-reduce,质量好但~53s/次。
    ★聊得越多=关系越重要,重点的人点深度分析。"""
    ct = chat_text or ""
    try:
        if deep:
            if len(ct) <= 9000:
                d = _card_one(contact, ct)   # _card_* 用默认模型(设置里的pro)+ max8000
            else:
                chunks = [ct[i:i + 9000] for i in range(0, len(ct), 8000)]
                partials = [p for p in (_card_chunk(contact, ch, i + 1, len(chunks))
                                        for i, ch in enumerate(chunks)) if p]
                if not partials:
                    return None
                d = _card_merge(contact, partials) if len(partials) > 1 else partials[0]
                if not d:
                    d = {"identity": "", "dynamics": "", "summary": "", "facts": [], "open_loops": [], "favors": []}
                    for p in partials:
                        for k in ("facts", "open_loops", "favors"):
                            d[k].extend(p.get(k) or [])
        else:
            sample = ct if len(ct) <= 9000 else (ct[:2000] + "\n…(中间略)…\n" + ct[-7000:])
            d = _pjson(LLM.chat([{"role": "system", "content": _CARD_SYS % (contact, "记录", contact)},
                                 {"role": "user", "content": sample}],
                                temperature=0.3, max_tokens=2000, model=LLM.fast_model()))
        if not d:
            return None
        for k in ("facts", "open_loops", "favors"):
            if not isinstance(d.get(k), list):
                d[k] = []
        return d
    except Exception:
        return None


def _last_time_from_text(text):
    tms = re.findall(r"\[(\d{4}-\d{2}-\d{2})", text or "")
    if not tms:
        return "", None
    lt = max(tms)
    try:
        return lt, (_dt.date.today() - _dt.date.fromisoformat(lt)).days
    except Exception:
        return lt, None


def _last_time(con, did):
    """只读最后一页算最后联系时间(避免读全部页)。"""
    r = con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no DESC LIMIT 1", (did,)).fetchone()
    return _last_time_from_text(r[0] if r else "")


def all_cards(con, owner, refresh=False, limit=40, generate=True):
    """为用户所有微信聊天文档生成/取关系卡(按消息数缓存)。
    generate=False:只返回已缓存的(秒回,不触发LLM);缺的交给后台warm。"""
    ensure(con)
    con.execute("CREATE TABLE IF NOT EXISTS card_hidden(username TEXT, contact TEXT, PRIMARY KEY(username,contact))")
    con.execute("CREATE TABLE IF NOT EXISTS loop_dismissed(username TEXT, key TEXT, PRIMARY KEY(username,key))")
    con.execute("CREATE TABLE IF NOT EXISTS reach_dismissed(username TEXT, contact TEXT, PRIMARY KEY(username,contact))")
    hidden = {r[0] for r in con.execute("SELECT contact FROM card_hidden WHERE username=?", (owner,)).fetchall()}
    loop_dismissed = {r[0] for r in con.execute("SELECT key FROM loop_dismissed WHERE username=?", (owner,)).fetchall()}
    reach_dismissed = {r[0] for r in con.execute("SELECT contact FROM reach_dismissed WHERE username=?", (owner,)).fetchall()}
    kinds = {}   # doc_id -> (is_group, last_date):群/对话判定 + 真实最后联系日期
    try:
        for r in con.execute("SELECT doc_id, is_group, last_date FROM doc_kind WHERE owner=?", (owner,)).fetchall():
            kinds[r[0]] = (bool(r[1]), r[2] or "")
    except Exception:
        pass
    day = _dt.date.today().isoformat()
    # ★缓存键改用"消息条数"(各页 text 换行和),不用页数:pages 受分页策略波动,重新入库同样内容
    #   分页边界变→缓存键变→卡被重建甚至掉出显示(用户实测"人脉卡变少")。消息数稳定。
    docs = con.execute(
        "SELECT d.id, d.filename, "
        "(SELECT COALESCE(SUM(1 + LENGTH(text) - LENGTH(REPLACE(text, char(10), ''))),0) FROM pages WHERE doc_id=d.id) AS mcnt "
        "FROM documents d WHERE d.owner=? AND d.filename LIKE '微信_与%' "
        "ORDER BY mcnt DESC LIMIT ?", (owner, limit)).fetchall()
    cards = []
    for did, fn, pagecount in docs:
        contact = fn.replace("微信_与", "").replace(".txt", "")
        if contact in hidden:
            continue   # 用户删过的卡:不再展示,也不重新生成
        pagecount = pagecount or 0   # 缓存键=消息条数(变了才重生成),不受分页波动
        row = None
        if not refresh:
            row = con.execute(
                "SELECT day, data, msgcount FROM relationship_cards WHERE username=? AND contact=?",
                (owner, contact)).fetchone()
        if row and row[2] == pagecount:
            k = kinds.get(did)
            if k and k[1]:   # 用 doc_kind 全页扫出的真实最后联系日期(治页序乱)
                lt = k[1]
                try:
                    da = (_dt.date.today() - _dt.date.fromisoformat(k[1])).days
                except Exception:
                    da = None
            else:
                lt, da = _last_time(con, did)
            tags = [r[0] for r in con.execute(   # 自动标签=聊天里抽出的机构/项目(实体回填后有)
                "SELECT name FROM kb_entities WHERE doc_id=? AND owner=? "
                "AND etype IN ('公司','机构','项目','产品','地点') ORDER BY mentions DESC LIMIT 6",
                (did, owner)).fetchall()]
            is_group = k[0] if k else (contact.endswith("@chatroom") or contact.endswith("@openim"))
            cards.append({"contact": contact, "doc_id": did, "last_time": lt, "days_ago": da,
                          "tags": tags, "is_group": is_group, "msgcount": row[2], **json.loads(row[1])})
            continue
        if not generate:
            continue   # 只读缓存模式:缺的跳过,交给后台 warm
        # build_card 只用前 12000 字,读前 40 页足够(避免读太阳花那种上千页)
        pages = con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no LIMIT 40", (did,)).fetchall()
        text = "\n".join(p[0] for p in pages)
        lt, da = _last_time_from_text(text)
        card = build_card(contact, text)
        if card:
            con.execute("INSERT OR REPLACE INTO relationship_cards(username,contact,doc_id,day,msgcount,data) "
                        "VALUES(?,?,?,?,?,?)", (owner, contact, did, day, pagecount, json.dumps(card, ensure_ascii=False)))
            con.commit()
            cards.append({"contact": contact, "doc_id": did, "last_time": lt, "days_ago": da,
                          "msgcount": pagecount, **card})
    # 用户「删除」过的未了结事项:不再展示(只隐藏,聊天原文分毫不动)
    if loop_dismissed:
        for c in cards:
            ol = c.get("open_loops") or []
            if ol:
                c["open_loops"] = [o for o in ol if loop_key(c["contact"], o) not in loop_dismissed]
    # 从「该联系了」提醒里移除过的人:打标记,前端不再提醒(卡片仍在)
    for c in cards:
        c["reach_hidden"] = c["contact"] in reach_dismissed
    # 有 open_loops / favors 的排前面(最有价值)
    cards.sort(key=lambda c: (len(c.get("open_loops") or []) + len(c.get("favors") or []), c.get("msgcount", 0)), reverse=True)
    return cards

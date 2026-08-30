"""doc_kind 生成:判定每个微信会话是「群」还是「1:1对话」+ 全页扫出真实最后联系日期。
对齐 106 dockind3.py(106 靠脚本跑,客户端单机→bg-analyze 自驱增量生成)。纯正则、无 LLM、便宜。
relationship 卡片(all_cards)用它做群判定 + 准确的"上次联系"日期(治页序乱)。"""
import re
from collections import Counter

WX = re.compile(r'^\[(\d{4}-\d{2}-\d{2})[ T]\d{2}:\d{2}(?::\d{2})?\]\s*([^:：]{1,24}?)[:：]')
DATE = re.compile(r'\[(\d{4}-\d{2}-\d{2})')


def _has_name(x):
    # 含中文或字母才算真实发言人名(排除纯日期/数字/符号)
    return any(('一' <= ch <= '鿿') or ch.isalpha() for ch in x)


def ensure_table(con):
    con.execute("CREATE TABLE IF NOT EXISTS doc_kind(owner TEXT, doc_id INTEGER, is_group INTEGER, last_date TEXT, PRIMARY KEY(owner,doc_id))")


def _resolve_user_name(con, owner, docs):
    """本人名 = 除「我」外出现在最多会话里的真实发言人名(如"孔贺"),从数据识别、不硬编码。"""
    docfreq = Counter()
    senders = {}
    for did, _fn in docs:
        sd = set()
        for (t,) in con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no LIMIT 30", (did,)):
            for line in (t or "").split("\n"):
                m = WX.match(line)
                if m:
                    who = m.group(2).strip()
                    if _has_name(who):
                        sd.add(who)
        senders[did] = sd
        for x in sd:
            docfreq[x] += 1
    cand = [(x, n) for x, n in docfreq.most_common(8) if x not in ("我", "(我)") and _has_name(x)]
    user_name = cand[0][0] if cand else ""
    return set(["我", "(我)", user_name]), senders


def ensure_doc_kind(con, owner, only_missing=True):
    """为 owner 的微信会话增量生成 doc_kind。only_missing=True 时只补还没有的(便宜、可每轮调)。
    返回本次新增/更新的条数。"""
    ensure_table(con)
    docs = con.execute(
        "SELECT id, filename FROM documents WHERE owner=? AND filename LIKE '微信_与%'", (owner,)).fetchall()
    if not docs:
        return 0
    if only_missing:
        have = {r[0] for r in con.execute("SELECT doc_id FROM doc_kind WHERE owner=?", (owner,)).fetchall()}
        todo = [(did, fn) for did, fn in docs if did not in have]
        if not todo:
            return 0
    else:
        todo = docs
    # 本人名要用全量 docs 识别(样本足才准),不只用 todo
    USER, senders = _resolve_user_name(con, owner, docs)
    n = 0
    for did, fn in todo:
        contact = fn.replace("微信_与", "").replace(".txt", "")
        non_user = senders.get(did, set()) - USER
        is_group = 1 if (len(non_user) > 1 or contact.endswith("@chatroom") or contact.endswith("@openim")) else 0
        last = ""
        for (t,) in con.execute("SELECT text FROM pages WHERE doc_id=?", (did,)):
            for m in DATE.findall(t or ""):
                if m > last:
                    last = m
        con.execute("INSERT OR REPLACE INTO doc_kind(owner,doc_id,is_group,last_date) VALUES(?,?,?,?)",
                    (owner, did, is_group, last))
        n += 1
    con.commit()
    return n

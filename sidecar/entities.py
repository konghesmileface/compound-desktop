"""实体级知识图谱(task #22)。
从文档抽取关键命名实体(人/公司/项目/合同/地点)→ kb_entities 表;
跨文档共享同一实体 = 实体级跨时间链接(比文档级 cosine 更可解释);
HippoRAG-lite:查询/一篇文档时,沿共享实体 1-2 跳扩展到相关文档,零/少 LLM。
"""
import json
import re
import llm as LLM

SCHEMA = """
CREATE TABLE IF NOT EXISTS kb_entities (
    id INTEGER PRIMARY KEY,
    doc_id INTEGER NOT NULL,
    owner TEXT,
    name TEXT NOT NULL,
    norm TEXT NOT NULL,
    etype TEXT,
    mentions INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_kbent_norm  ON kb_entities(norm);
CREATE INDEX IF NOT EXISTS idx_kbent_doc   ON kb_entities(doc_id);
CREATE INDEX IF NOT EXISTS idx_kbent_owner ON kb_entities(owner);
"""

# 抽实体时排除的泛称(避免"公司/我们/项目"这种噪声)
_STOP = {"公司", "我们", "项目", "合同", "对方", "他", "她", "客户", "本公司", "甲方", "乙方", "the", "we"}


def ensure_schema(con):
    con.executescript(SCHEMA)


def _norm(name):
    """实体消解:归一大小写/空白/注册商标符/括号变体,让 GIPS=GIPS®、X=X(LES) 合并。"""
    s = (name or "").strip().lower()
    s = re.sub(r"[（(][^）)]*[）)]", "", s)      # 去括号及内容,如 (LES)
    s = re.sub(r"[®™©\s\-_.,、·/]", "", s)        # 去商标符/空白/常见分隔
    return s


def extract_doc_entities(con, doc_id, owner, text):
    """LLM 抽取一篇文档的关键命名实体,写入 kb_entities(先清该 doc 旧实体)。返回实体数。"""
    ensure_schema(con)
    sample = (text or "")[:7000]   # 抽关键机构/项目取前7000字足够,更快
    if not sample.strip():
        return 0
    sysp = ("从下面文档/聊天记录里**尽可能全**地抽取**关键命名实体**:人名、公司/银行/机构名、"
            "项目/产品/业务名(如'同业存单''惠民贷''投标')、合同/协议名、地点。"
            "聊天里对方提到的**每一个具体公司、银行、机构、项目、人名都要抽出来**,这是构建人脉关联的关键;"
            "但排除泛称(如'公司''项目''对方''我们''老板')。"
            "每个给 name(照抄原文,规范全称)和 type(人/公司/机构/项目/产品/合同/地点/其他)。"
            '只输出JSON:{"entities":[{"name":"武汉交通银行","type":"公司"},{"name":"同业存单","type":"产品"}]}')
    # ★绕开 llm.py(它有 max(mt,2000) 地板 + 空返回翻倍到8000,而 flash 会硬生成到 max_tokens 不停,
    #   导致 finish=length、时间正比 max_tokens、一篇几十秒)。这里直连 API、max_tokens=600、单次、容错解析。
    import urllib.request
    ents = []
    try:
        prov, base, dmodel, key = LLM.resolved()
        model = LLM.fast_model() or dmodel
        # ★用户选最高质量:开 thinking(规范全称+最全,建人脉图最准)。max_tokens 给足 6000,
        #   否则思考吃空 content(实测 finish=length、content空)。约47s/篇。
        body = json.dumps({"model": model,
                           "messages": [{"role": "system", "content": sysp}, {"role": "user", "content": sample}],
                           "temperature": 0.1, "max_tokens": 6000}).encode("utf-8")
        req = urllib.request.Request(base + "/chat/completions", data=body,
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
                                     method="POST")
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open(req, timeout=150) as r:   # 推理慢,给足超时
            out = ((json.load(r).get("choices") or [{}])[0].get("message", {}) or {}).get("content") or ""
        # 容错解析:直接正则抽 name/type 对(截断也能提取,不依赖完整JSON)
        for mm in re.finditer(r'"name"\s*:\s*"([^"]{1,40})"\s*,\s*"type"\s*:\s*"([^"]{0,12})"', out):
            ents.append({"name": mm.group(1), "type": mm.group(2)})
        if not ents:  # 兜底:整段JSON
            m = re.search(r"\{.*\}", out, re.S)
            if m:
                try:
                    ents = json.loads(m.group(0)).get("entities") or []
                except Exception:
                    ents = []
    except Exception:
        ents = []
    con.execute("DELETE FROM kb_entities WHERE doc_id=?", (doc_id,))
    seen = {}
    for e in ents:
        nm = (e.get("name") or "").strip()
        nr = _norm(nm)
        if not nm or len(nm) > 40 or len(nr) < 2 or nr in _STOP:
            continue
        if nr in seen:
            seen[nr]["m"] += 1
            continue
        seen[nr] = {"name": nm, "type": (e.get("type") or "").strip(), "m": 1}
    for nr, v in seen.items():
        con.execute("INSERT INTO kb_entities(doc_id,owner,name,norm,etype,mentions) VALUES(?,?,?,?,?,?)",
                    (doc_id, owner, v["name"], nr, v["type"], v["m"]))
    con.commit()
    return len(seen)


def backfill(con, owner=None, limit=None, progress=None):
    """给还没抽实体的文档批量抽取(跳过 card:/已抽过的)。"""
    ensure_schema(con)
    q = ("SELECT d.id, d.owner FROM documents d "
         "WHERE (d.backend IS NULL OR d.backend NOT LIKE 'card:%') "
         "AND NOT EXISTS(SELECT 1 FROM kb_entities e WHERE e.doc_id=d.id)")
    args = []
    if owner:
        q += " AND d.owner=?"
        args.append(owner)
    q += " ORDER BY d.id DESC"
    if limit:
        q += " LIMIT %d" % int(limit)
    docs = con.execute(q, args).fetchall()
    done = 0
    for did, own in docs:
        txt = "\n".join(r[0] for r in con.execute(
            "SELECT text FROM pages WHERE doc_id=? ORDER BY page_no LIMIT 40", (did,)))
        n = extract_doc_entities(con, did, own, txt)
        done += 1
        if progress:
            progress(done, len(docs), did, n)
    return done, len(docs)


def entity_links(con, owner, limit=12):
    """跨文档共享实体 = 实体级链接。返回 [{entity,etype,count,docs:[{id,filename,date}]}]。"""
    ensure_schema(con)
    rows = con.execute(
        "SELECT e.norm, MAX(e.name), MAX(e.etype), COUNT(DISTINCT e.doc_id) c "
        "FROM kb_entities e JOIN documents d ON d.id=e.doc_id "
        "WHERE e.owner=? AND length(e.norm)>=2 "
        "GROUP BY e.norm HAVING c>=2 ORDER BY c DESC, e.norm LIMIT ?", (owner, limit)).fetchall()
    out = []
    for norm, name, etype, c in rows:
        docs = con.execute(
            "SELECT DISTINCT d.id, d.filename, d.ingested_at FROM kb_entities e "
            "JOIN documents d ON d.id=e.doc_id WHERE e.norm=? AND e.owner=? "
            "ORDER BY d.ingested_at LIMIT 12", (norm, owner)).fetchall()
        if len(docs) < 2:
            continue
        out.append({"entity": name, "etype": etype, "count": c,
                    "docs": [{"id": r[0], "filename": r[1], "date": r[2]} for r in docs]})
    return out


def expand_via_entities(con, doc_id, owner, hops=2, cap=20):
    """HippoRAG-lite:从一篇文档的实体出发,沿共享实体扩展到相关文档 id 列表。"""
    ensure_schema(con)
    seed = {r[0] for r in con.execute("SELECT DISTINCT norm FROM kb_entities WHERE doc_id=?", (doc_id,))}
    seen_docs = {doc_id}
    frontier = set(seed)
    ent_seen = set()
    for _ in range(hops):
        if not frontier:
            break
        qs = ",".join("?" * len(frontier))
        rows = con.execute(
            "SELECT DISTINCT doc_id, norm FROM kb_entities WHERE owner=? AND norm IN (%s)" % qs,
            [owner] + list(frontier)).fetchall()
        ent_seen |= frontier
        frontier = set()
        for did, _nrm in rows:
            if did not in seen_docs:
                seen_docs.add(did)
                for r in con.execute("SELECT DISTINCT norm FROM kb_entities WHERE doc_id=?", (did,)):
                    if r[0] not in ent_seen:
                        frontier.add(r[0])
        if len(seen_docs) >= cap:
            break
    seen_docs.discard(doc_id)
    return list(seen_docs)[:cap]

"""
语义层:给每页算向量,产出"文档间语义相似"的图(星系图的燃料)。

- 嵌入后端可插拔(默认本地 sentence-transformers 多语模型,CPU 可跑、免费)。
- 向量存进同一个 library.db 的 page_embeddings 表(float32 BLOB)。
- 文档向量 = 其页向量均值;图的连线 = 文档间余弦相似 top-k 过阈值。
  连线有语义含义 = 图不是孤点坟墓(见 DESIGN.md 防坟墓核心)。

命令行:
    python semantic.py embed          # 给未嵌入的页补算向量
    python semantic.py graph          # 打印图的节点/连线数
环境变量:
    EMBED_MODEL   嵌入模型(默认 paraphrase-multilingual-MiniLM-L12-v2)
    BRAIN_DB      库路径(见 ingest.py)
"""
from __future__ import annotations
import os
import sys
import numpy as np

EMBED_MODEL = os.environ.get("EMBED_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
RERANK_MODEL = os.environ.get("RERANK_MODEL", "")  # 空=不重排;设为 BAAI/bge-reranker-v2-m3 开启
RETRIEVE_CANDIDATES = int(os.environ.get("RETRIEVE_CANDIDATES", "40"))  # 重排前的粗召回数
_model = None
_reranker = None

import re as _re
_DET = _re.compile(r"<\|det\|>.*?<\|/det\|>", _re.S)
_PAGE = _re.compile(r"<PAGE>")


def clean_ocr(text: str) -> str:
    """剥掉百度 Unlimited-OCR 的版面标记 <|det|>type [coords]<|/det|> 和 <PAGE>。"""
    if not text:
        return text
    t = _DET.sub("", text)
    t = _PAGE.sub("", t)
    # 收拢多余空行
    t = _re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

EMB_SCHEMA = """
CREATE TABLE IF NOT EXISTS page_embeddings (
    page_id INTEGER PRIMARY KEY REFERENCES pages(id) ON DELETE CASCADE,
    dim     INTEGER,
    vec     BLOB
);
"""


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        m = EMBED_MODEL
        # EMBED_MODEL 若是本地路径(首启下载点)但模型还没下好/缺失 → 兜底回落 HF 仓库名,
        # 让 sentence-transformers 自己下(不让语义功能彻底死)。
        if os.path.sep in m and not (
                os.path.isfile(os.path.join(m, "config.json")) or
                os.path.isfile(os.path.join(m, "modules.json"))):
            m = "BAAI/bge-m3"
        _model = SentenceTransformer(m)
    return _model


def get_reranker():
    """交叉编码重排模型(bge-reranker-v2-m3)。未配置则返回 None。"""
    global _reranker
    if not RERANK_MODEL:
        return None
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder(RERANK_MODEL, max_length=512)
    return _reranker


def ensure_schema(con):
    con.executescript(EMB_SCHEMA)


def _to_blob(v) -> bytes:
    return np.asarray(v, dtype=np.float32).tobytes()


def _from_blob(b: bytes, dim: int) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32, count=dim)


def _phys_ram_gb() -> float:
    """物理内存(GB),跨平台零依赖。macOS/Linux 都支持 SC_PHYS_PAGES;取不到给个保守 8。"""
    try:
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / (1024 ** 3)
    except Exception:
        return 8.0


def embed_profile() -> dict:
    """★按机器实际内存动态分档嵌入参数(2026-08-29 用户令:别写死拖慢强机)。
    老 8G Mac 温柔(小批+限量+节流,保机器不冻);现代 16/32/64G 全速。环境变量可覆盖任一项。"""
    gb = _phys_ram_gb()
    if gb <= 10:          # 8G 档:护机器第一,慢但不冻(load 186 事故那台)
        p = {"batch": 8,  "max_pages": 24,  "throttle": 0.3}
    elif gb <= 20:        # 16G 档
        p = {"batch": 24, "max_pages": 96,  "throttle": 0.05}
    elif gb <= 40:        # 32G 档
        p = {"batch": 48, "max_pages": 192, "throttle": 0.0}
    else:                 # 64G+ 强机:全速
        p = {"batch": 96, "max_pages": 384, "throttle": 0.0}
    # 环境变量覆盖(调优/特殊机型)
    try:
        if os.environ.get("EMBED_BATCH"):     p["batch"] = int(os.environ["EMBED_BATCH"])
        if os.environ.get("EMBED_MAX_PAGES"): p["max_pages"] = int(os.environ["EMBED_MAX_PAGES"])
        if os.environ.get("EMBED_THROTTLE"):  p["throttle"] = float(os.environ["EMBED_THROTTLE"])
    except Exception:
        pass
    return p


def embed_pending(con, batch: int = None, char_limit: int = 1400,
                  max_pages: int = None, throttle: float = None) -> int:
    """给还没有向量的页算嵌入(已归一)。返回新嵌入页数。

    ★参数按机器内存动态分档(embed_profile);不传则自动取档(2026-08-29 真机 8G load 186 空转事故根修):
    - batch:bge-m3(2.3G)一次 encode 太多段的激活内存会顶爆小内存机 → macOS swap → 单批永跑不完永不
      commit、page_embeddings 卡死不动(空转真相=颠簸)。8G 用 8,强机用到 96。
    - max_pages:每次只嵌一小段 → 调用短返回快,让外层循环 sleep 给机器喘气,不一口气占死。
    - throttle:批间小睡,弱机用 0.3s 喘气,强机 0 全速。
    """
    prof = embed_profile()
    if batch is None:     batch = prof["batch"]
    if max_pages is None: max_pages = prof["max_pages"]
    if throttle is None:  throttle = prof["throttle"]
    ensure_schema(con)
    _sql = ("""SELECT p.id, p.text FROM pages p
               LEFT JOIN page_embeddings e ON e.page_id = p.id
               WHERE e.page_id IS NULL AND length(trim(p.text)) > 0""")
    if max_pages:
        _sql += " LIMIT %d" % int(max_pages)
    rows = con.execute(_sql).fetchall()
    if not rows:
        return 0
    model = get_model()
    n = 0
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        texts = [clean_ocr(r[1] or "")[:char_limit] for r in chunk]
        vecs = model.encode(texts, normalize_embeddings=True)
        for (pid, _), v in zip(chunk, vecs):
            con.execute(
                "INSERT OR REPLACE INTO page_embeddings(page_id, dim, vec) VALUES(?,?,?)",
                (pid, int(len(v)), _to_blob(v)))
        con.commit()
        n += len(chunk)
        if throttle:
            import time as _t; _t.sleep(throttle)
    return n


def doc_vectors(con, owner=None) -> dict:
    """每文档向量 = 其页向量均值(再归一)。返回 {doc_id: (filename, vec)}。owner 指定时只取该用户文档(P1-2:在自己子集内算近邻)。"""
    _sql = ("""SELECT p.doc_id, d.filename, e.dim, e.vec
           FROM page_embeddings e
           JOIN pages p ON p.id = e.page_id
           JOIN documents d ON d.id = p.doc_id""")
    if owner is not None:
        rows = con.execute(_sql + " WHERE d.owner=?", (owner,)).fetchall()
    else:
        rows = con.execute(_sql).fetchall()
    acc: dict = {}
    for doc_id, fn, dim, blob in rows:
        acc.setdefault(doc_id, [fn, []])[1].append(_from_blob(blob, dim))
    out = {}
    for doc_id, (fn, vs) in acc.items():
        m = np.mean(np.stack(vs), axis=0)
        nrm = np.linalg.norm(m)
        out[doc_id] = (fn, m / nrm if nrm > 0 else m)
    return out


def similar_docs(con, doc_id: int, topk: int = 8, owner=None) -> list:
    dv = doc_vectors(con, owner)
    if doc_id not in dv:
        return []
    _, v0 = dv[doc_id]
    sims = [(did, fn, float(np.dot(v0, v)))
            for did, (fn, v) in dv.items() if did != doc_id]
    sims.sort(key=lambda x: -x[2])
    return [{"doc_id": d, "filename": f, "score": round(s, 3)}
            for d, f, s in sims[:topk]]


def graph(con, topk: int = 6, threshold: float = 0.35, owner=None) -> dict:
    """节点=文档,连线=文档间语义相似 top-k(去重、过阈值)。喂给星系图。owner 指定时只在自己文档子集内算(P1-2)。"""
    dv = doc_vectors(con, owner)
    # ★文档视图=知识库文档;微信聊天(每会话一个 txt)有专门的「仅聊天」主题星系,不在这里刷屏
    ids = [d for d in dv.keys() if not (dv[d][0] or "").startswith("微信_与")]
    if not ids:
        ids = list(dv.keys())   # 万一全是微信(纯聊天账号)则不过滤,避免空图
    pages = {r[0]: r[1] for r in con.execute("SELECT id, pages FROM documents")}
    try:
        topics = doc_topics(con, clusters=8, owner=owner)
    except Exception:
        topics = {}
    cnames = {}
    nodes = []
    for did in ids:
        ti, tn = topics.get(did, (0, "其它"))
        cnames[ti] = tn
        nodes.append({"id": did, "label": dv[did][0], "size": pages.get(did, 1), "cluster": ti})
    vecs = {did: dv[did][1] for did in ids}
    seen: set = set()
    edges = []
    for did in ids:
        sims = sorted(
            ((oid, float(np.dot(vecs[did], vecs[oid]))) for oid in ids if oid != did),
            key=lambda x: -x[1])
        for oid, s in sims[:topk]:
            if s < threshold:
                break
            key = tuple(sorted((did, oid)))
            if key in seen:
                continue
            seen.add(key)
            edges.append({"source": key[0], "target": key[1], "weight": round(s, 3)})
    ncl = (max(cnames) + 1) if cnames else 0
    return {"nodes": nodes, "edges": edges, "cluster_names": [cnames.get(i, "簇" + str(i + 1)) for i in range(ncl)]}


_STOP = set(("的 了 和 与 在 是 有 我 你 他 她 它 也 就 都 及 等 这 那 之 其 或 而 以 并 "
             "我们 你们 他们 可以 一种 一个 以及 对于 通过 进行 因此 但是 如果 所以 这个 "
             "这些 那些 这样 一些 部分 内容 主要 通常 例如 如下 其中 由于 不同 相关 一般 "
             "第 页 章 节 图 表 the a an of to and in for on is are be this that with as by "
             "from at or it its their which will can may we you they be been being have has "
             "learning module chapter reading readings section curriculum program level "
             "volume volumes edition institute rights reserved copyright www com http https "
             "cfa cfauk standards exam candidate practice question questions i ii iii iv v "
             "vi vii viii ix x xi xii figure table exhibit page pages inc ltd "
             "det header title text image parsing welcome era one shot "
             "not material cover herein such expressly itself which these those "
             "may will can should would could been being have has had are was were "
             "our your his her their its any all more most other than then also "
             # 英文碎词/噪声(书籍虚词,做簇名无意义)
             "non long lon longshuang editor editors written well does select selected "
             "covers cover include included including based using used per via about into "
             "over under between within without however therefore moreover thus hence "
             # 微信聊天口水/时间词(非主题)
             "一年 一手 一下 一起 一点 以上 以下 打招呼 时候 现在 已经 还是 这么 那么 "
             "什么 怎么 没有 就是 这边 那边 知道 觉得 应该 可能 感觉 收到 谢谢 好的 下次 天前 "
             # OCR失败/扫描书水印占位词(无真实正文,不当主题)
             "文本 识别 未含 可识别 无可 文字 提取 扫描 空白 未能 无法 图内 本页 跳过 "
             "此页 原书 库加微 加微 入库 本书 电子书 下载 免费 版权 关注 公众").split())


def _wechat_stop(con=None, owner=None):
    """微信语料专用停用词:表情/占位名 + 动态本人名变体(通用,不硬编码任何客户)。"""
    stop = set()
    try:
        import chat_topics as _ct
        stop |= set(_ct._EMOJI_STOP) | set(_ct._NAME_STOP) | set(_ct._STOP)   # 含通用填充词(现在/今天/您好/那个…)
        if con is not None and owner is not None:
            import owner_ctx as _oc
            stop |= _ct._owner_variants(_oc.resolve_owner_name(con, owner))
    except Exception:
        pass
    return stop


def _name_clusters(chunks, labels, ncl, top=3, extra_stop=None):
    """每个簇用 TF-IDF(jieba 分词)取 top 关键词命名。失败退化为 簇N。
    extra_stop:微信正文里的表情/占位/本人名(剥掉才不会出现『孔贺·ok·银行』这种)。"""
    import re
    _META = re.compile(r'^\s*\[[^\]]*\]\s*[^:：\n]{1,24}[:：]')   # 微信 [时间] 发言人:
    _BRK = re.compile(r'\[[^\]]{1,6}\]')                          # [表情]/[图片] 占位
    xs = extra_stop or set()
    docs = [""] * ncl
    for i, ch in enumerate(chunks):
        docs[labels[i]] += " " + (ch[5] or "")
    try:
        import jieba
        from sklearn.feature_extraction.text import TfidfVectorizer

        def tok(s):
            s = re.sub(r"<\|.*?\|>", " ", s)          # 剥 OCR <|det|> 等标记
            s = re.sub(r"\[[\d, ]+\]", " ", s)         # 剥坐标 [12, 34]
            s = "\n".join(_BRK.sub(" ", _META.sub(" ", ln)) for ln in s.split("\n"))  # 剥微信发言人前缀+表情
            out = []
            for w in jieba.lcut(s):
                w = w.strip()
                if len(w) >= 2 and w.lower() not in _STOP and w not in xs and w.lower() not in xs and not w.isdigit() \
                        and re.search(r"[一-龥A-Za-z]", w):
                    out.append(w.lower())
            return out

        vec = TfidfVectorizer(tokenizer=tok, preprocessor=lambda x: x,
                              token_pattern=None, max_features=6000)
        X = vec.fit_transform(docs)
        terms = np.array(vec.get_feature_names_out())
        names = []
        for c in range(ncl):
            row = X[c].toarray().ravel()
            order = row.argsort()[::-1]
            cjk, asc = [], []
            for j in order:
                if row[j] <= 0:
                    break
                term = str(terms[j])
                (cjk if re.search(r"[一-龥]", term) else asc).append(term)
                if len(cjk) >= top:
                    break
            if cjk:
                names.append(" · ".join((cjk + asc)[:top]))   # 优先中文词命名
            elif asc:
                names.append("英文书籍 · " + asc[0])            # 纯英文簇=英文书籍,不堆 editor/written 虚词
            else:
                names.append(f"簇{c + 1}")
        return names
    except Exception:
        return [f"簇{c + 1}" for c in range(ncl)]


# 检索缓存:把所有页向量堆成矩阵放内存,查询=一次矩阵乘法(秒级)。
_RET = {"count": -1, "mat": None, "meta": None}


def _build_ret_cache(con):
    rows = con.execute(
        """SELECT p.id, p.doc_id, d.filename, p.page_no, e.dim, e.vec, p.text
           FROM page_embeddings e
           JOIN pages p ON p.id = e.page_id
           JOIN documents d ON d.id = p.doc_id""").fetchall()
    mats, meta, byid = [], [], {}
    for r, (pid, doc_id, fn, pno, dim, blob, text) in enumerate(rows):
        mats.append(_from_blob(blob, dim))
        meta.append((pid, doc_id, fn, pno, text or ""))
        byid[pid] = r
    _RET["mat"] = np.stack(mats).astype(np.float32) if mats else None
    _RET["meta"] = meta
    _RET["byid"] = byid
    _RET["count"] = len(rows)


def _fts_candidates(con, query: str, limit: int) -> list:
    """稀疏召回:FTS5(trigram 分词后中文子串匹配强)。返回 [(page_id, bm25), ...]。"""
    q = (query or "").strip().replace('"', ' ')
    if len(q) < 3:
        return []
    try:
        rows = con.execute(
            "SELECT rowid, bm25(pages_fts) FROM pages_fts WHERE pages_fts MATCH ? "
            "ORDER BY bm25(pages_fts) LIMIT ?", ('"' + q + '"', limit)).fetchall()
        if not rows:  # 短语没命中就退化成任一词命中(OR)
            toks = [t for t in q.split() if t]
            if toks:
                rows = con.execute(
                    "SELECT rowid, bm25(pages_fts) FROM pages_fts WHERE pages_fts MATCH ? "
                    "ORDER BY bm25(pages_fts) LIMIT ?", (" OR ".join('"' + t + '"' for t in toks), limit)).fetchall()
        return [(int(pid), float(rank)) for pid, rank in rows]
    except Exception:
        return []


def retrieve(con, query: str, topk: int = 8) -> list:
    """混合检索:稠密(bge-m3)+ 稀疏(FTS)RRF 融合 → 交叉编码重排 → top-k。"""
    cnt = con.execute("SELECT COUNT(*) FROM page_embeddings").fetchone()[0]
    if _RET["count"] != cnt or _RET["mat"] is None:
        _build_ret_cache(con)
    mat, meta, byid = _RET["mat"], _RET["meta"], _RET.get("byid", {})
    if mat is None:
        return []
    qv = get_model().encode([query], normalize_embeddings=True)[0].astype(np.float32)
    sims = mat @ qv
    rk = get_reranker()
    ncand = max(topk, RETRIEVE_CANDIDATES) if rk is not None else max(topk, 20)
    # RRF 融合:稠密排名 + 稀疏排名(倒数秩,互补召回)
    K = 60
    rrf = {}
    for rank, i in enumerate(int(x) for x in np.argsort(-sims)[:ncand]):
        rrf[i] = rrf.get(i, 0.0) + 1.0 / (K + rank)
    for rank, (pid, _b) in enumerate(_fts_candidates(con, query, ncand)):
        r = byid.get(pid)
        if r is not None:
            rrf[r] = rrf.get(r, 0.0) + 1.0 / (K + rank)
    fused = sorted(rrf, key=lambda i: rrf[i], reverse=True)[:ncand]
    cand = []
    for i in fused:
        pid, doc_id, fn, pno, text = meta[i]
        cand.append({"doc_id": doc_id, "filename": fn, "page_no": pno,
                     "text": clean_ocr(text), "score": round(float(sims[i]), 3),
                     "_rrf": round(rrf[i], 5)})
    if rk is not None and cand:
        pairs = [(query, c["text"][:1000]) for c in cand]
        rscores = rk.predict(pairs)
        for c, s in zip(cand, rscores):
            c["cos"] = c["score"]
            c["score"] = round(float(1.0 / (1.0 + np.exp(-float(s)))), 3)  # sigmoid → 0..1
        cand.sort(key=lambda c: c["score"], reverse=True)
    else:
        cand.sort(key=lambda c: c["_rrf"], reverse=True)
    cand = cand[:topk]
    for c in cand:
        c["text"] = c["text"][:700]
        c.pop("_rrf", None)
    return cand


def doc_topics(con, clusters: int = 12, owner=None) -> dict:
    """把每份文档自动归到一个学科主题(文档向量聚类 + TF-IDF 命名)。
    返回 {doc_id: (topic_idx, topic_name)}。owner 指定时只算该用户文档(P2-1:主题词不跨账号)。"""
    _w = " WHERE d.owner=?" if owner is not None else ""
    rows = con.execute(
        """SELECT p.doc_id, d.filename, e.dim, e.vec, substr(p.text,1,200)
           FROM page_embeddings e
           JOIN pages p ON p.id = e.page_id
           JOIN documents d ON d.id = p.doc_id""" + _w +
        " ORDER BY p.doc_id, p.page_no", ((owner,) if owner is not None else ())).fetchall()
    acc = {}
    for doc_id, fn, dim, blob, ts in rows:
        v = _from_blob(blob, dim)
        if doc_id not in acc:
            acc[doc_id] = [fn, [], ""]
        acc[doc_id][1].append(v)
        if len(acc[doc_id][2]) < 240:
            acc[doc_id][2] += " " + (ts or "")
    ids = list(acc.keys())
    if not ids:
        return {}
    vecs = []
    for i in ids:
        m = np.mean(np.stack(acc[i][1]), axis=0); nrm = np.linalg.norm(m)
        vecs.append(m / nrm if nrm > 0 else m)
    mat = np.stack(vecs).astype(np.float32)
    ncl = min(clusters, len(ids))
    try:
        from sklearn.cluster import KMeans
        labels = list(KMeans(n_clusters=ncl, n_init=4, random_state=0).fit_predict(mat)) \
            if len(ids) >= ncl else [0] * len(ids)
    except Exception:
        labels = [0] * len(ids); ncl = 1
    chunks_like = [(ids[i], acc[ids[i]][0], 0, 0, None, acc[ids[i]][2]) for i in range(len(ids))]
    names = _name_clusters(chunks_like, labels, ncl, extra_stop=_wechat_stop(con, owner))
    return {ids[i]: (int(labels[i]), names[labels[i]]) for i in range(len(ids))}


def chunk_graph(con, chunk_pages: int = 12, k: int = 6, clusters: int = 14, owner=None) -> dict:
    """
    星海模式:把每份文档按 chunk_pages 页切块 → 每块一颗星(几千颗)。
    块向量=块内页向量均值;kNN(余弦)连成网;KMeans 聚类给簇上色。
    像 X 上那种密集知识星系。
    """
    _w = " WHERE d.owner=?" if owner is not None else ""
    rows = con.execute(
        """SELECT p.doc_id, d.filename, p.page_no, e.dim, e.vec, substr(p.text,1,200)
           FROM page_embeddings e
           JOIN pages p ON p.id = e.page_id
           JOIN documents d ON d.id = p.doc_id""" + _w +
        " ORDER BY p.doc_id, p.page_no", ((owner,) if owner is not None else ())).fetchall()
    if not rows:
        return {"nodes": [], "edges": []}

    # 按文档切连续页块;顺带留一小段文本给聚类命名
    chunks = []          # (doc_id, filename, p_start, p_end, vec, text_sample)
    cur_doc, fname, buf, pstart, pend, tbuf = None, None, [], None, None, ""
    for doc_id, filename, page_no, dim, blob, tsample in rows:
        v = _from_blob(blob, dim)
        if doc_id != cur_doc or len(buf) >= chunk_pages:
            if buf:
                m = np.mean(np.stack(buf), axis=0); nrm = np.linalg.norm(m)
                chunks.append((cur_doc, fname, pstart, pend, m / nrm if nrm > 0 else m, tbuf))
            cur_doc, fname, buf, pstart, tbuf = doc_id, filename, [], page_no, ""
        buf.append(v); pend = page_no
        if len(tbuf) < 240:
            tbuf += " " + (tsample or "")
    if buf:
        m = np.mean(np.stack(buf), axis=0); nrm = np.linalg.norm(m)
        chunks.append((cur_doc, fname, pstart, pend, m / nrm if nrm > 0 else m, tbuf))

    M = len(chunks)
    mat = np.stack([c[4] for c in chunks]).astype(np.float32)

    # 聚类上色
    ncl = min(clusters, M) if M else 1
    try:
        from sklearn.cluster import KMeans
        labels = list(KMeans(n_clusters=ncl, n_init=4, random_state=0).fit_predict(mat)) if M >= ncl else [0] * M
    except Exception:
        labels = [0] * M; ncl = 1
    cluster_names = _name_clusters(chunks, labels, ncl, extra_stop=_wechat_stop(con, owner))

    # kNN 连线(归一向量 → 点积=余弦)
    edges, seen = [], set()
    try:
        from sklearn.neighbors import NearestNeighbors
        kk = min(k + 1, M)
        nn = NearestNeighbors(n_neighbors=kk, metric="cosine").fit(mat)
        _, idx = nn.kneighbors(mat)
        for i in range(M):
            for j in idx[i][1:]:
                a, b = (i, int(j)) if i < j else (int(j), i)
                if (a, b) in seen:
                    continue
                seen.add((a, b)); edges.append({"source": a, "target": b})
    except Exception:
        pass

    deg = {}
    for e in edges:
        deg[e["source"]] = deg.get(e["source"], 0) + 1
        deg[e["target"]] = deg.get(e["target"], 0) + 1

    nodes = []
    for i, (doc_id, filename, ps, pe, _v, _t) in enumerate(chunks):
        nodes.append({
            "id": i, "doc_id": doc_id, "cluster": int(labels[i]),
            "size": 1 + min(deg.get(i, 0), 10),
            "label": f"{filename} · P{ps}-{pe}",
        })
    return {"nodes": nodes, "edges": edges, "cluster_names": cluster_names,
            "clusters": ncl}


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ingest as I
    cmd = sys.argv[1] if len(sys.argv) > 1 else "embed"
    con = I.db_connect(I.DEFAULT_DB)
    if cmd == "embed":
        print(f"嵌入模型={EMBED_MODEL},库={I.DEFAULT_DB}")
        n = embed_pending(con)
        print(f"新嵌入 {n} 页。")
    elif cmd == "graph":
        g = graph(con)
        print(f"图:{len(g['nodes'])} 节点,{len(g['edges'])} 连线")
        for e in g["edges"][:20]:
            print(f"  {e['source']} — {e['target']}  相似 {e['weight']}")
    else:
        print("用法: python semantic.py [embed|graph]")
    con.close()

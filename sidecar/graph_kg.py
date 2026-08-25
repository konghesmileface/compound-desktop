"""人脉图谱:联系人↔联系人关联(共享实体的二部图投影)+ 人脉枢纽 + 关系路径。
纯 SQLite(kb_entities)+ NetworkX,几十个联系人 CPU 毫秒级。
- 两个联系人聊天里出现同一个实体(公司/人/项目/话题)→ 连一条边
- 边权 = Adamic-Adar(稀有共享比大众共享更强)
- 关系分% = Jaccard(共享实体 / 各自实体并集)
- 人脉枢纽 = betweenness 介数中心性(连接不同圈子的桥梁)
- 关系路径 = A 通过 B 认识 C(最短路 + 每跳的共享实体做 why)
参考图谱调研:LightRAG抽取 + HippoRAG式PPR + 人-人投影(Adamic-Adar)。
"""
import math
import networkx as nx

# 太泛的实体不作为"关联证据"(会把所有人连成一团)
_STOP = {"", "微信", "老板", "老师", "公司", "银行", "我", "你", "他", "谢谢", "好的"}
# 实例主人本人的称呼(生产版应从用户画像/昵称动态取;这里按当前实例主人=孔贺)
_SELF = {"孔总", "孔贺", "孔", "孔生"}


def _contact_entities(con, owner):
    """{联系人: set(实体norm)},只取微信联系人文档的实体;附带 norm->显示名、联系人->doc_id。"""
    # ★只取 1对1 联系人(is_group=0):群/裸@chatroom 不当"人"进人脉图,否则枢纽/路径被群号污染(根因A)
    rows = con.execute(
        "SELECT d.filename, e.norm, e.name, d.id, e.etype FROM kb_entities e "
        "JOIN documents d ON d.id=e.doc_id "
        "LEFT JOIN doc_kind k ON k.owner=e.owner AND k.doc_id=e.doc_id "
        "WHERE e.owner=? AND d.filename LIKE '微信_与%' "
        "AND COALESCE(k.is_group,0)=0 "
        "AND d.filename NOT LIKE '%@chatroom%' AND d.filename NOT LIKE '%@openim%'", (owner,)).fetchall()
    cmap, disp, docid, etype = {}, {}, {}, {}
    for fn, norm, name, did, et in rows:
        contact = fn.replace("微信_与", "").replace(".txt", "")
        docid[contact] = did
        if not norm or norm in _STOP or norm in _SELF:
            continue
        cmap.setdefault(contact, set()).add(norm)
        disp[norm] = name or norm
        if et:
            etype[norm] = et
    return cmap, disp, docid, etype


def _build(con, owner):
    cmap, disp, docid, etype = _contact_entities(con, owner)
    ent_owners = {}          # 实体 -> 拥有它的联系人集合(Adamic-Adar 的 k_z)
    for c, ents in cmap.items():
        for e in ents:
            ent_owners.setdefault(e, set()).add(c)
    # 过滤"太泛"的实体:出现在 >=40%(或>=8个)联系人里的,多半是用户本人/地点/泛词
    # ——它们把不相干的人连成一团,不作为关联证据
    nC = max(1, len(cmap))
    thresh = max(8, int(nC * 0.4))
    common = {e for e, owners in ent_owners.items() if len(owners) >= thresh}
    if common:
        for c in cmap:
            cmap[c] -= common
        ent_owners = {e: o for e, o in ent_owners.items() if e not in common}
    contacts = list(cmap.keys())
    edges = []
    for i in range(len(contacts)):
        for j in range(i + 1, len(contacts)):
            a, b = contacts[i], contacts[j]
            shared = cmap[a] & cmap[b]
            if not shared:
                continue
            aa = 0.0
            for e in shared:
                k = len(ent_owners[e])
                aa += 1.0 / math.log(k + 1e-9) if k > 1 else 1.0
            union = len(cmap[a] | cmap[b])
            jac = len(shared) / union if union else 0.0
            shared_sorted = sorted(shared, key=lambda e: len(ent_owners[e]))  # 稀有的排前
            edges.append((a, b, aa, jac, shared_sorted))
    return cmap, disp, ent_owners, edges, docid, etype


def rel_graph(con, owner):
    """人脉关系网:节点(联系人)+ 边(关联+why)+ 人脉枢纽。"""
    cmap, disp, ent_owners, edges, docid, etype = _build(con, owner)
    G = nx.Graph()
    for c in cmap:
        G.add_node(c)
    for a, b, aa, jac, shared in edges:
        G.add_edge(a, b, weight=aa)
    # 人脉枢纽:betweenness(桥梁)为主,degree 为辅
    bet = nx.betweenness_centrality(G) if G.number_of_nodes() >= 3 else {n: 0.0 for n in G}
    deg = dict(G.degree())
    hubs = sorted(
        ({"name": n, "betweenness": round(bet.get(n, 0.0), 4), "degree": deg.get(n, 0)} for n in G.nodes()),
        key=lambda h: (-h["betweenness"], -h["degree"]))
    # 社区检测:把人按"圈子"聚类(贪心模块度),每个圈子用度数最高的人命名
    node_comm, communities = {}, []
    try:
        comms = list(nx.community.greedy_modularity_communities(G)) if G.number_of_edges() > 0 else []
    except Exception:
        comms = []
    if not comms:
        comms = [set(G.nodes())] if G.number_of_nodes() else []
    comms.sort(key=len, reverse=True)
    for i, cset in enumerate(comms):
        members = sorted(cset, key=lambda n: -deg.get(n, 0))
        cname = members[0] if members else ("圈子%d" % i)
        communities.append({"id": i, "name": cname, "count": len(cset)})
        for n in cset:
            node_comm[n] = i
    eout = []
    for a, b, aa, jac, shared in sorted(edges, key=lambda x: -x[2]):
        eout.append({
            "a": a, "b": b,
            "strength": round(aa, 3),
            "score": round(min(jac * 100 * 2.5, 100), 1),   # 归一化到 0-100 好看
            "shared": [disp.get(e, e) for e in shared[:6]],
            "shared_count": len(shared),
        })
    nodes = [{"name": c, "kind": "person", "entity_count": len(cmap[c]), "degree": deg.get(c, 0),
              "doc_id": docid.get(c), "community": node_comm.get(c, 0)} for c in cmap]
    nodes.sort(key=lambda n: -n["degree"])
    # 机构/项目枢纽节点(Obsidian 式二部图):被 >=3 个联系人共享的实体成为一颗"机构星",
    # 连到它旗下的人 —— 让"这几个人都围着浦发/某项目"一眼可见。取连接力最强的前 28 个。
    ent_nodes, ent_links = [], []
    # 只把「机构/项目/产品」做成枢纽星:城市/地点(上海/深圳)当枢纽没意义,反而糊成一团
    _HUB_TYPES = {"公司", "机构", "组织", "项目", "产品", "部门", "平台"}
    hub_ents = sorted(((e, os) for e, os in ent_owners.items()
                       if len(os) >= 3 and etype.get(e) in _HUB_TYPES),
                      key=lambda x: -len(x[1]))[:24]
    from collections import Counter as _Ct
    for e, os in hub_ents:
        members = [m for m in os if m in cmap]
        if len(members) < 3:
            continue
        comm = _Ct(node_comm.get(m, 0) for m in members).most_common(1)[0][0]
        ename = "◆" + (disp.get(e, e))
        ent_nodes.append({"name": ename, "kind": "entity", "label": disp.get(e, e),
                          "degree": len(members), "community": comm, "member_count": len(members)})
        for m in members:
            ent_links.append({"a": ename, "b": m, "kind": "entity"})
    return {"nodes": nodes + ent_nodes, "edges": eout, "ent_links": ent_links,
            "hubs": hubs[:8], "communities": communities,
            "contact_count": len(cmap), "edge_count": len(eout), "entity_node_count": len(ent_nodes)}


def path_between(con, owner, a, target):
    """A 通过谁认识 C:最短路 + 每跳共享实体。"""
    cmap, disp, ent_owners, edges, docid, _et = _build(con, owner)
    G = nx.Graph()
    sm = {}
    for aa, b, w, jac, shared in edges:
        G.add_edge(aa, b, weight=1.0 / (w + 0.1))
        names = [disp.get(e, e) for e in shared[:5]]
        sm[(aa, b)] = names
        sm[(b, aa)] = names
    if a not in G or target not in G:
        return {"path": [], "why": [], "found": False}
    try:
        path = nx.shortest_path(G, a, target, weight="weight")
    except Exception:
        return {"path": [], "why": [], "found": False}
    why = [{"from": path[i], "to": path[i + 1], "shared": sm.get((path[i], path[i + 1]), [])}
           for i in range(len(path) - 1)]
    return {"path": path, "why": why, "found": len(path) > 1}


def chat_galaxy(con, owner, topk=6, min_sim=0.30):
    """探索·仅聊天:全部 1:1 联系人按聊天内容相似度连成语义星系(用现成页向量,零 LLM,覆盖全部)。
    每个联系人=其聊天页向量均值;两两余弦相似;每人连最像的 top-K(且>min_sim);贪心模块度聚社区。"""
    import numpy as np
    try:
        from semantic import doc_vectors
    except Exception:
        return {"nodes": [], "edges": [], "communities": []}
    dv = doc_vectors(con, owner)   # {doc_id: (filename, 归一向量)}
    meta = {}
    for did, fn, pg, isg in con.execute(
        "SELECT d.id, d.filename, d.pages, COALESCE(k.is_group,0) FROM documents d "
        "LEFT JOIN doc_kind k ON k.owner=d.owner AND k.doc_id=d.id "
        "WHERE d.owner=? AND d.filename LIKE '微信_与%'", (owner,)).fetchall():
        ct = fn.replace("微信_与", "").replace(".txt", "")
        if isg or ct.endswith("@chatroom") or ct.endswith("@openim"):
            continue
        meta[did] = (ct, pg or 0)
    items = [(did, meta[did][0], dv[did][1]) for did in meta if did in dv]
    if len(items) < 2:
        return {"nodes": [], "edges": [], "communities": [], "contact_count": len(items)}
    dids = [it[0] for it in items]
    names = [it[1] for it in items]
    M = np.stack([it[2].astype(np.float32) for it in items])
    sim = M @ M.T
    N = len(items)
    G = nx.Graph()
    for nm in names:
        G.add_node(nm)
    for i in range(N):
        order = np.argsort(-sim[i])
        cnt = 0
        for j in order:
            if j == i:
                continue
            if sim[i][j] < min_sim:
                break
            a, b = names[i], names[j]
            if not G.has_edge(a, b):
                G.add_edge(a, b, weight=float(sim[i][j]))
            cnt += 1
            if cnt >= topk:
                break
    try:
        comms = list(nx.community.greedy_modularity_communities(G)) if G.number_of_edges() > 0 else []
    except Exception:
        comms = []
    if not comms:
        comms = [set(G.nodes())]
    comms.sort(key=len, reverse=True)
    deg = dict(G.degree())
    node_comm, communities = {}, []
    for ci, cs in enumerate(comms):
        members = sorted(cs, key=lambda n: -deg.get(n, 0))
        communities.append({"id": ci, "name": (members[0] if members else ("簇%d" % ci)), "count": len(cs)})
        for n in cs:
            node_comm[n] = ci
    docid_of = {names[i]: dids[i] for i in range(N)}
    pages_of = {names[i]: meta[dids[i]][1] for i in range(N)}
    nodes = [{"name": nm, "doc_id": docid_of[nm], "community": node_comm.get(nm, 0),
              "degree": deg.get(nm, 0), "msgcount": pages_of.get(nm, 0)} for nm in names]
    eout = [{"a": u, "b": v, "strength": round(d["weight"], 3)} for u, v, d in G.edges(data=True)]
    return {"nodes": nodes, "edges": eout, "communities": communities,
            "contact_count": N, "edge_count": len(eout)}

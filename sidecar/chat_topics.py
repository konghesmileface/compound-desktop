"""探索·仅聊天(方案A):把全部微信聊天内容按语义聚成主题星系。
每颗星=一段聊天(page);KMeans 聚主题;PCA 预置坐标(秒开、无白闪、不遥远);jieba 提关键词给簇起真名。
用现成的 page_embeddings,零 LLM,覆盖全部聊天数据。
"""
import re
import numpy as np
from collections import Counter
try:
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    _SK = True
except Exception:
    _SK = False
try:
    import jieba
    jieba.initialize()
    _JB = True
except Exception:
    _JB = False
from semantic import _from_blob

# 聊天里没信息量的高频词(不能当主题名)
_STOP = set("""的 了 是 我 你 他 她 它 们 这 那 有 在 和 就 都 不 也 要 会 说 吧 啊 呢 吗 嗯 哦 好 对 没 来 去 到 给 把 被 让 呀 哈 嘛 咯 哟
一个 这个 那个 一下 一起 一样 一点 知道 时候 现在 已经 可能 应该 什么 怎么 我们 你们 他们 问题 时间 这样 东西 感觉 不是 就是 还有 然后
因为 所以 但是 如果 可以 没有 方便 麻烦 谢谢 客气 收到 图片 表情 视频 语音 撤回 消息 链接 一条 上午 下午 晚上 今天 明天 昨天 需要
可能 觉得 大家 直接 主要 就是 而且 或者 还是 这边 那边 之前 之后 这次 有点 一直 目前 情况 方面 部分 相关 进行 通过 目前 现在""".split())


_META = re.compile(r'^\s*\[[^\]]*\]\s*[^:：\n]{1,24}[:：]')   # [时间] 发言人:
_BRACKET = re.compile(r'\[[^\]]{1,6}\]')   # 微信表情/占位 [偷笑][图片]…
# ★微信系统样板话(视频号/小程序/引用/转账等)——重复千百遍会顶成假主题名,整段清掉
_SYSLINE = re.compile(
    r'当前版本[^。\n]*?(不支持|无法)[^。\n]*|请(升级|在手机|前往)[^。\n]*|该(内容|消息|链接)[^。\n]*(查看|支持|显示)[^。\n]*'
    r'|(视频号|小程序|公众号|收藏|转账|微信红包|安全提示|文件过期)[^。\n]*|以上是打招呼的内容|发送.*名片|拍了拍')
# 系统样板话里的高频残词(个别没被整段清掉的兜底)
_SYS_WORD = set("支持 升级 版本 展示 显示 查看 内容 链接 视频号 小程序 公众号 转账 收藏 打招呼 名片 过期 安全 提示 手机".split())
# ★不再硬编码任何人名——本人名由 owner_ctx 从数据动态识别,联系人名按簇动态传入(通用于任何客户)
_NAME_STOP = set("引用 抱拳".split())   # 这两个是微信表情名,非人名
# 微信表情名 + 聊天噪声/填充词(不是话题)
_EMOJI_STOP = set("""偷笑 破涕为笑 捂脸 呲牙 憨笑 微笑 发呆 得意 流泪 害羞 闭嘴 大哭 尴尬 发怒 调皮 龇牙 惊讶 难过 冷汗 抓狂 愉快
白眼 傲慢 惊恐 流汗 悠闲 疑问 疯了 敲打 再见 擦汗 抠鼻 鼓掌 坏笑 哈欠 鄙视 委屈 快哭了 阴险 亲亲 可怜 强 弱 握手 胜利 抱拳
勾引 拳头 差劲 爱你 飞吻 发抖 怄火 转圈 磕头 挥手 激动 献吻 嘿哈 奸笑 机智 皱眉 吃瓜 加油 旺柴 打脸 翻白眼 让我看看 叹气 苦涩
裂开 哈哈 哈哈哈 哈哈哈哈 呵呵 嘿嘿 嘻嘻 emm Emm ok OK NO no lt gt amp nbsp msg img appmsg 好滴 好嘞 好的 好呀 咱们 自己 朋友 开始 聊天
版本 文件 企业 收到 客气 谢谢 麻烦 方便 没事 不用 群聊 验证 请求 邀请 看看 不能 最近 内容 一会 这么 那么 怎么样 应该 觉得 时候
wxid xml html http https www com cn url src href span div style class type name data span href
appid appmsg arg args names fromusername tousername msgtype content title des thumburl weburl finderfeed appinfo mmreader sdkver sdk ver version scene sourceusername sourcedisplayname
当前 目前 这边 那边 一下 一些 有些 之类 等等 之类的
添加 加入 好友 昵称 备注 转账 红包 名片 位置 拍了拍 撤回 系统 通知 提醒 分享 卡片 小程序 公众 服务 号 链接 网页""".split())


def _owner_variants(oname):
    """由识别出的本人名派生称呼变体(姓+总/董/总监/老板等)——通用:任何姓氏都适用,不硬编码。"""
    v = set()
    if not oname:
        return v
    v.add(oname)
    surname = oname[0]   # 中文姓氏基本单字
    for t in ("总", "董", "总监", "老板", "总经理", "经理", "工", "总裁"):
        v.add(surname + t)
    return v


def _cluster_name(texts, contact_names=None, topn=3):
    """从一簇聊天的**正文**(去掉[时间]发言人:前缀)提话题关键词做主题名。"""
    if not _JB:
        return "主题"
    stop = set(_STOP) | set(_NAME_STOP) | set(_EMOJI_STOP) | set(_SYS_WORD) | set(contact_names or set())
    cnt = Counter()
    for t in texts[:500]:
        for line in (t or "").split("\n"):
            body = _SYSLINE.sub(" ", _BRACKET.sub("", _META.sub("", line)))   # 剥发言人前缀+表情占位+系统样板话,只留正文
            for w in jieba.cut(body):
                w = w.strip()
                if len(w) < 2 or len(w) > 6:
                    continue
                if not re.search(r'[一-鿿A-Za-z]', w):
                    continue
                # ★过滤纯小写拉丁噪声词(qq/tc/hy/bizid 这类缩写/代码/字段名)——中文业务聊天的主题名
                #   应是中文;纯小写英文几乎都是噪声。保留全大写缩写(AAA评级/CFA)与中文。
                if re.fullmatch(r'[a-z]+', w):
                    continue
                if w in stop:
                    continue
                cnt[w] += 1
    # 去掉被更长词包含的短词(如已选"同业存单"就不再要"存单")
    picked = []
    for w, _ in cnt.most_common(30):
        if any((w in p or p in w) for p in picked):
            continue
        picked.append(w)
        if len(picked) >= topn:
            break
    return " · ".join(picked) if picked else "其他"


import json as _json

_warming = set()   # 正在后台命名的 (owner,k),防重复起线程


def _db_path(con):
    try:
        for _seq, name, f in con.execute("PRAGMA database_list"):
            if name == "main" and f:
                return f
    except Exception:
        pass
    return None


def _ensure_name_cache(con):
    con.execute("CREATE TABLE IF NOT EXISTS chat_topic_names(owner TEXT, k INTEGER, sig TEXT, names TEXT, PRIMARY KEY(owner,k))")


def _names_sig(con, owner):
    n = con.execute("SELECT COUNT(*) FROM page_embeddings e JOIN pages p ON p.id=e.page_id "
                    "JOIN documents d ON d.id=p.doc_id WHERE d.owner=? AND d.filename LIKE '微信_与%'", (owner,)).fetchone()[0]
    return str(n)


def _gen_llm_names(ctexts, jieba_names, oself):
    """每簇抽样本喂 flash,起一个人能看懂的真主题名。返回 {ci: name}。"""
    try:
        import llm as LLM
    except Exception:
        return {}
    out = {}
    for ci, texts in ctexts.items():
        snips = []
        for t in list(texts)[:60]:
            for line in (t or "").split("\n"):
                body = _SYSLINE.sub(" ", _BRACKET.sub("", _META.sub("", line))).strip()
                if len(body) >= 5 and not body.isdigit():
                    snips.append(body)
            if len(snips) >= 14:
                break
        if not snips:
            continue
        sample = " / ".join(snips[:14])[:1400]
        sysp = ("下面用「/」分隔的是同一语义簇里的多段微信聊天片段。给这一簇起一个 **4到12字的中文主题名**,"
                "精准概括它们**共同在聊什么**(业务/事务/话题);若主要是与某个人的往来,可点出那个人或关系。"
                "不要用『聊天/消息/其他/未知』这种空话,不要标点、不要解释、不要引号,只输出名字本身。"
                "关键词参考:" + (jieba_names.get(ci, "") or ""))
        try:
            r = LLM.chat([{"role": "system", "content": sysp}, {"role": "user", "content": sample}],
                         temperature=0.3, max_tokens=2000, model=LLM.fast_model())
            nm = (r or "").strip().splitlines()[0] if r else ""
            nm = nm.strip(" 　。.,、\"'“”《》[]()").strip()[:16]
            if nm and nm not in (oself or set()):
                out[ci] = nm
        except Exception:
            pass
    return out


def _warm_names(path, owner, kk, sig, ctexts, jieba_names, oself):
    key = (owner, kk)
    try:
        names = _gen_llm_names(ctexts, jieba_names, oself)
        if not names:
            return
        try:
            import pysqlite3 as s2
        except Exception:
            import sqlite3 as s2
        c2 = s2.connect(path); c2.execute("PRAGMA busy_timeout=30000")
        _ensure_name_cache(c2)
        c2.execute("INSERT OR REPLACE INTO chat_topic_names(owner,k,sig,names) VALUES(?,?,?,?)",
                   (owner, kk, sig, _json.dumps({str(a): b for a, b in names.items()}, ensure_ascii=False)))
        c2.commit(); c2.close()
    finally:
        _warming.discard(key)


def chat_topic_galaxy(con, owner, k=16):
    if not _SK:
        return {"nodes": [], "edges": [], "communities": [], "error": "no sklearn"}
    rows = con.execute(
        "SELECT p.id, p.doc_id, d.filename, p.text, e.dim, e.vec "
        "FROM page_embeddings e JOIN pages p ON p.id=e.page_id JOIN documents d ON d.id=p.doc_id "
        "WHERE d.owner=? AND d.filename LIKE '微信_与%'", (owner,)).fetchall()
    if len(rows) < 8:
        return {"nodes": [], "edges": [], "communities": []}
    pids, dids, fns, texts, vecs = [], [], [], [], []
    for pid, did, fn, text, dim, blob in rows:
        pids.append(pid); dids.append(did)
        fns.append(fn.replace("微信_与", "").replace(".txt", ""))
        texts.append(text or "")
        vecs.append(_from_blob(blob, dim))
    M = np.stack(vecs).astype(np.float32)
    N = len(pids)
    kk = int(min(k, max(3, N // 60)))
    labels = KMeans(n_clusters=kk, n_init=4, random_state=42).fit(M).labels_
    # 布局:簇中心排成环,簇内局部 PCA 散开成有机一团(预置坐标→秒开)
    positions = np.zeros((N, 2), dtype=np.float32)
    ctexts = {ci: [] for ci in range(kk)}
    for i in range(N):
        ctexts[int(labels[i])].append(texts[i])
    R = 1000
    rng = np.random.RandomState(7)
    for ci in range(kk):
        idx = np.where(labels == ci)[0]
        ang = (ci / kk) * 2 * np.pi
        cx, cy = np.cos(ang) * R, np.sin(ang) * R
        if len(idx) >= 3:
            p2 = PCA(n_components=2).fit_transform(M[idx])
            p2 = p2 / (np.abs(p2).max() + 1e-6) * 240
        else:
            p2 = rng.randn(len(idx), 2) * 40
        for j, i in enumerate(idx):
            positions[i] = [cx + p2[j][0], cy + p2[j][1]]
    # 本人名(动态识别,通用)——不能当话题名
    try:
        from owner_ctx import resolve_owner_name
        oname = resolve_owner_name(con, owner)
    except Exception:
        oname = ""
    # 每簇涉及的联系人名(不能当话题名)
    cnames = {ci: set() for ci in range(kk)}
    for i in range(N):
        cnames[int(labels[i])].add(fns[i])
    sizes = Counter(labels.tolist())
    oself = _owner_variants(oname)
    jieba_names = {ci: _cluster_name(ctexts[ci], cnames[ci] | oself, 3) for ci in range(kk)}
    # ★优先用 LLM 起的"真主题名"(缓存,数据没变就复用);缺就先用关键词名,并后台生成好供下次
    llm_names = {}
    try:
        _ensure_name_cache(con)
        sig = _names_sig(con, owner)
        row = con.execute("SELECT sig, names FROM chat_topic_names WHERE owner=? AND k=?", (owner, kk)).fetchone()
        if row and row[0] == sig:
            llm_names = {int(a): b for a, b in _json.loads(row[1]).items()}
        else:
            key = (owner, kk); path = _db_path(con)
            if path and key not in _warming:
                _warming.add(key)
                import threading
                threading.Thread(target=_warm_names,
                                 args=(path, owner, kk, sig, {ci: list(ctexts[ci]) for ci in range(kk)}, dict(jieba_names), set(oself)),
                                 daemon=True).start()
    except Exception:
        pass
    communities = [{"id": ci, "name": llm_names.get(ci) or jieba_names[ci],
                    "count": int(sizes.get(ci, 0))} for ci in range(kk)]
    # 簇中心(前端在这里飘主题名)
    centers = []
    for ci in range(kk):
        ang = (ci / kk) * 2 * np.pi
        centers.append({"cluster": ci, "name": communities[ci]["name"],
                        "x": float(np.cos(ang) * R), "y": float(np.sin(ang) * R), "count": int(sizes.get(ci, 0))})
    nodes = [{"id": "p%d" % pids[i], "label": fns[i][:12], "doc_id": dids[i],
              "cluster": int(labels[i]), "x": float(positions[i][0]), "y": float(positions[i][1])}
             for i in range(N)]
    return {"nodes": nodes, "edges": [], "communities": communities,
            "centers": centers, "contact_count": N, "node_count": N}

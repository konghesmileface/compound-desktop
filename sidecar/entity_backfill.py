# 微信聊天实体抽取回填:pages>=2 且还没实体的会话,LLM 抽人/机构/项目→kb_entities(点亮仅聊天球图)。
import sys, datetime
sys.path.insert(0, "/opt/compound-brain")
try:
    import pysqlite3 as s
except Exception:
    import sqlite3 as s
import entities as ENT
OWNER = "18201972547"
con = s.connect("/opt/compound-brain/library.db"); con.execute("PRAGMA busy_timeout=30000")
ENT.ensure_schema(con)
docs = con.execute(
    "SELECT d.id, d.filename FROM documents d WHERE d.owner=? AND d.backend='wechat' AND d.pages>=2 "
    "AND NOT EXISTS(SELECT 1 FROM kb_entities e WHERE e.doc_id=d.id) ORDER BY d.pages ASC", (OWNER,)).fetchall()
print("待抽实体 %d 个微信会话" % len(docs), flush=True)
done = tot = 0
for i, (did, fn) in enumerate(docs):
    pages = con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no LIMIT 15", (did,)).fetchall()
    text = "\n".join(p[0] for p in pages)
    try:
        n = ENT.extract_doc_entities(con, did, OWNER, text)
        tot += n; done += 1
        if done % 10 == 0:
            print("进度 %d/%d 累计实体%d" % (i + 1, len(docs), tot), flush=True)
    except Exception as e:
        print("ERR %s: %s" % (fn, e), flush=True)
print("DONE docs=%d entities=%d" % (done, tot), flush=True)

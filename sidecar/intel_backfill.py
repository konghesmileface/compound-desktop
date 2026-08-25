# chat_intel 回填:pages>=3 的实质会话,pro 抽承诺/数字/供需,跳过已缓存,逐个提交。单进程。
import sys, json, datetime, time
sys.path.insert(0, "/opt/compound-brain")
try:
    import pysqlite3 as s
except Exception:
    import sqlite3 as s
import chat_intel as INTEL

OWNER = "18201972547"
con = s.connect("/opt/compound-brain/library.db")
con.execute("PRAGMA busy_timeout=30000")
con.execute("CREATE TABLE IF NOT EXISTS chat_intel(username TEXT,contact TEXT,doc_id INTEGER,msgcount INTEGER,day TEXT,data TEXT,PRIMARY KEY(username,contact))")

docs = con.execute(
    "SELECT id, filename, pages FROM documents WHERE owner=? AND backend='wechat' AND pages>=3 ORDER BY pages DESC",
    (OWNER,)).fetchall()
print("待处理 %d 个会话" % len(docs), flush=True)

done = skip = err = 0
for i, (did, fn, pg) in enumerate(docs):
    contact = fn[4:-4]  # 去 "微信_与" 前缀 + ".txt"
    row = con.execute("SELECT msgcount FROM chat_intel WHERE username=? AND contact=?", (OWNER, contact)).fetchone()
    if row and row[0] == pg:
        skip += 1
        continue
    pages = con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no", (did,)).fetchall()
    text = "\n".join(p[0] for p in pages)
    if len(text) > 12000:  # 太长取首尾(承诺/近况多在近期)
        text = text[:2000] + "\n...(中间略)...\n" + text[-9000:]
    try:
        d = INTEL.build_intel(contact, text)
    except Exception as e:
        err += 1
        print("ERR [%d/%d] %s: %s" % (i + 1, len(docs), contact, e), flush=True)
        continue
    if d:
        con.execute("INSERT OR REPLACE INTO chat_intel(username,contact,doc_id,msgcount,day,data) VALUES(?,?,?,?,?,?)",
                    (OWNER, contact, did, pg, datetime.date.today().isoformat(), json.dumps(d, ensure_ascii=False)))
        con.commit()
        done += 1
        if done % 5 == 0:
            print("进度 %d/%d (done=%d skip=%d err=%d)" % (i + 1, len(docs), done, skip, err), flush=True)

print("DONE done=%d skip=%d err=%d" % (done, skip, err), flush=True)

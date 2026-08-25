# 向量嵌入回填:给所有还没嵌入的页算向量(CPU MiniLM,每64页提交)。补微信聊天的语义问答。
import sys
sys.path.insert(0, "/opt/compound-brain")
try:
    import pysqlite3 as s
except Exception:
    import sqlite3 as s
import semantic as SEM
con = s.connect("/opt/compound-brain/library.db"); con.execute("PRAGMA busy_timeout=60000")
print("开始嵌入所有待嵌入页...", flush=True)
n = SEM.embed_pending(con, batch=64)
print("DONE 本次新嵌入 %d 页" % n, flush=True)

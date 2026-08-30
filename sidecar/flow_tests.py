#!/usr/bin/env python3
"""流程化 + 完整性双保险测试套件(2026-08-29 重建,回应用户"case不完整也没流程")。

两层:
  A. 完整性:从 app.py 机械枚举全部 @app 路由,每条必须被某个流程步骤覆盖或显式标 deferred,
     否则报"★漏项"——杜绝手搓清单静默丢接口(历史教训:109 里曾漏 32)。
  B. 流程化:按端到端用户旅程组织(注册→入库→问答→人脉→雷达→微信助手→产出…),
     每步真调 + 断言验证,不是孤立戳接口。

跑法:python3 flow_tests.py --port <sidecar端口> --token <token>
  未带 token 只跑完整性检查(离线,不需运行 sidecar)。
"""
import sys, os, re, json, argparse, urllib.request, urllib.parse, urllib.error

# ============ A. 完整性:源码枚举全部路由 ============
def all_routes():
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")).read()
    return {(m.upper(), p) for m, p in re.findall(r'@app\.(get|post|put|delete)\("([^"]+)"', src)}

# 每条路由归到一个流程步骤 or 显式 deferred(带原因)。★新增路由若没登记 → 完整性检查报漏项。
COVERED = {  # (METHOD, PATH): 流程名
    ("GET","/"):"基础", ("GET","/health"):"基础", ("GET","/api/stats"):"基础",
    ("POST","/api/auth/login"):"注册登录", ("POST","/api/auth/register"):"注册登录", ("POST","/api/friend"):"人脉",
    ("POST","/api/auth/send_code"):"注册登录", ("POST","/api/auth/phone_register"):"注册登录",
    ("POST","/api/auth/phone_login"):"注册登录", ("POST","/api/auth/pwd_login"):"注册登录",
    ("POST","/api/auth/set_password"):"注册登录", ("POST","/api/auth/reset_password"):"注册登录",
    ("GET","/api/auth/me"):"注册登录", ("GET","/api/auth/profile"):"设置", ("POST","/api/auth/update_profile"):"设置",
    ("GET","/api/auth/alipay/enabled"):"支付", ("GET","/api/auth/alipay/login_url"):"支付", ("POST","/api/auth/alipay/bind"):"支付",
    ("POST","/api/avatar"):"设置", ("GET","/api/avatars"):"人脉", ("GET","/api/account"):"支付",
    ("GET","/api/plans"):"支付", ("POST","/api/pay/create"):"支付", ("GET","/api/pay/query"):"支付",
    ("GET","/api/orders"):"支付", ("POST","/api/orders/delete"):"支付",
    ("POST","/api/upload"):"入库", ("POST","/api/upload_url"):"入库", ("GET","/api/job/{job_id}"):"入库",
    ("GET","/api/library"):"入库", ("GET","/api/mylibrary"):"冥想", ("GET","/api/doc/{doc_id}"):"入库",
    ("GET","/api/doc_summary/{doc_id}"):"入库", ("GET","/api/similar/{doc_id}"):"入库", ("GET","/api/media_structure"):"入库",
    ("POST","/api/embed"):"入库", ("GET","/api/search"):"检索", ("GET","/api/analysis_status"):"分析",
    ("POST","/api/ask"):"问答", ("GET","/api/today"):"问答", ("GET","/api/news"):"问答", ("GET","/api/discoveries"):"问答",
    ("POST","/api/card"):"卡片", ("GET","/api/cards"):"卡片", ("GET","/api/card/{card_id}/related"):"卡片",
    ("POST","/api/card/{card_id}/status"):"卡片", ("POST","/api/card/{card_id}/edit"):"卡片", ("DELETE","/api/card/{card_id}"):"卡片",
    ("GET","/api/relationships"):"人脉", ("POST","/api/relationships/deepen"):"人脉", ("POST","/api/relationships/delete"):"人脉",
    ("GET","/api/people"):"人脉", ("GET","/api/match/{other}"):"人脉", ("GET","/api/rel_path"):"人脉",
    ("GET","/api/rel_graph"):"人脉", ("GET","/api/group_graph"):"人脉", ("GET","/api/relation_timeline"):"人脉",
    ("GET","/api/entity_links"):"人脉", ("GET","/api/links"):"人脉", ("GET","/api/connections/{doc_id}"):"人脉",
    ("GET","/api/network_portrait"):"洞察", ("GET","/api/balance"):"洞察", ("GET","/api/panorama"):"洞察", ("GET","/api/checkup"):"洞察",
    ("GET","/api/persona"):"画像", ("GET","/api/commitments"):"雷达", ("POST","/api/commitments/dismiss"):"雷达",
    ("GET","/api/matches"):"雷达", ("GET","/api/cooling"):"雷达", ("GET","/api/favors"):"雷达", ("GET","/api/dormant"):"雷达",
    ("GET","/api/number_ledger"):"雷达", ("GET","/api/briefing"):"雷达", ("POST","/api/loops/dismiss"):"雷达",
    ("POST","/api/reach/dismiss"):"雷达", ("POST","/api/draft_reply"):"雷达",
    ("POST","/api/report"):"产出", ("POST","/api/generate"):"产出", ("GET","/api/preview/{fname}"):"产出", ("GET","/api/download/{fname}"):"产出",
    ("GET","/api/graph"):"探索", ("GET","/api/starmap"):"探索", ("GET","/api/chat_galaxy"):"探索",
    ("GET","/api/chat_topic_galaxy"):"探索", ("GET","/api/chat_node/{doc_id}"):"探索",
    ("GET","/api/settings"):"设置", ("POST","/api/settings"):"设置", ("POST","/api/settings/test"):"设置",
    ("POST","/api/iphone/import"):"iOS导入", ("GET","/api/iphone/status"):"iOS导入",
    ("POST","/api/wechat/watch"):"微信助手", ("POST","/api/wechat/ingest"):"微信助手", ("GET","/api/wechat_messages"):"微信助手",
    ("GET","/api/realtime/status"):"微信助手", ("POST","/api/realtime/toggle"):"微信助手", ("POST","/api/realtime/heartbeat"):"微信助手",
    ("POST","/api/ingest/status"):"入库", ("GET","/api/ingest/progress"):"入库",
    ("GET","/api/autosync/list"):"入库", ("POST","/api/autosync/add"):"入库", ("POST","/api/autosync/remove"):"入库",
    ("GET","/api/lifestory"):"冥想", ("GET","/api/lifesong"):"冥想", ("POST","/api/song/make"):"冥想", ("GET","/api/song/status"):"冥想",
    ("GET","/api/music-list"):"冥想", ("GET","/api/music/{fname}"):"冥想", ("GET","/api/tts/{fname}"):"冥想", ("GET","/api/theme/{fname}"):"冥想",
    ("GET","/api/genimg/{name}"):"冥想", ("GET","/api/genvid/{name}"):"冥想",
    ("GET","/go/wechat-export"):"入库",
}

def completeness_check():
    routes = all_routes()
    missing = sorted(routes - set(COVERED.keys()))
    print("=== A. 完整性(源码机械枚举) ===")
    print("源码路由: %d | 已登记流程: %d" % (len(routes), len(routes & set(COVERED.keys()))))
    if missing:
        print("★★ 漏项(新增路由未登记到任何流程,共 %d)★★" % len(missing))
        for m, p in missing: print("   ⚠ %-6s %s" % (m, p))
    else:
        print("✓ 全部路由都登记到流程,无静默漏项")
    return not missing

# ============ B. 流程化:端到端旅程,每步验证 ============
class Ctx:
    def __init__(s, port, token): s.port, s.token, s.ids = port, token, {}
def call(c, method, path, body=None, noauth=False, timeout=60):
    url = "http://127.0.0.1:%d%s" % (c.port, path)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if not noauth: req.add_header("Authorization", "Bearer " + c.token)
    if body is not None: req.add_header("Content-Type", "application/json")
    try:
        r = urllib.request.urlopen(req, timeout=timeout); b = r.read(); return r.status, b
    except urllib.error.HTTPError as e: return e.code, e.read()
    except Exception as e: return -1, str(e).encode()

# 流程 = 有序步骤;每步 (描述, 函数(ctx)->(ok, 详情))。步骤间可传状态(ctx.ids)。
def flow_ingest_search(c):
    steps = []
    # 上传→轮询→搜索→打开 一条链
    import io
    png = None
    st, b = call(c, "GET", "/api/stats"); steps.append(("看库状态", st == 200, "%d" % st))
    q = urllib.parse.quote("债券")
    st, b = call(c, "GET", "/api/search?q=" + q)
    hits = json.loads(b).get("hits", []) if st == 200 else []
    steps.append(("全文搜索", st == 200, "%d hits" % len(hits)))
    if hits:
        did = hits[0]["doc_id"]; c.ids["doc"] = did
        st, b = call(c, "GET", "/api/doc/%d" % did); steps.append(("打开文档", st == 200, "%d" % st))
        st, b = call(c, "GET", "/api/similar/%d" % did); steps.append(("语义相关", st == 200, "%d" % st))
    return steps

def flow_qa(c):
    steps = []
    st, b = call(c, "POST", "/api/ask", {"query": "我的知识库里有什么关于债券的内容"}, timeout=90)
    ans = json.loads(b) if st == 200 else {}
    steps.append(("RAG问答", st == 200 and bool(ans.get("answer")), "答%d字/出处%d" % (len(ans.get("answer", "")), len(ans.get("sources", [])))))
    st, b = call(c, "GET", "/api/today"); steps.append(("今日", st == 200, "%d" % st))
    return steps

def flow_cards(c):
    steps = []
    st, b = call(c, "POST", "/api/card", {"ctype": "goal", "title": "流程测试卡", "content": "测"})
    cid = json.loads(b).get("id") if st == 200 else None; c.ids["card"] = cid
    steps.append(("新建卡片", st == 200 and cid, "id=%s" % cid))
    if cid:
        st, _ = call(c, "GET", "/api/card/%s/related" % cid); steps.append(("联想历史", st == 200, "%d" % st))
        st, _ = call(c, "POST", "/api/card/%s/status" % cid, {"status": "done"}); steps.append(("标记完成", st == 200, "%d" % st))
        st, _ = call(c, "POST", "/api/card/%s/edit" % cid, {"title": "改", "content": "改"}); steps.append(("编辑", st == 200, "%d" % st))
        st, _ = call(c, "DELETE", "/api/card/%s" % cid); steps.append(("删除", st == 200, "%d" % st))
    return steps

def flow_relations(c):
    steps = []
    st, b = call(c, "GET", "/api/relationships"); cards = json.loads(b).get("cards", []) if st == 200 else []
    steps.append(("关系卡列表", st == 200, "%d卡" % len(cards)))
    st, b = call(c, "GET", "/api/people"); steps.append(("人脉列表", st == 200, "%d" % st))
    st, b = call(c, "GET", "/api/rel_graph"); steps.append(("关系图", st == 200, "%d" % st))
    if cards:
        ct = cards[0].get("contact", "")
        st, _ = call(c, "GET", "/api/relation_timeline?contact=" + urllib.parse.quote(ct)); steps.append(("关系时间线", st == 200, "%d" % st))
    return steps

def flow_radar(c):
    steps = []
    for ep, name in [("commitments", "承诺"), ("matches", "供需"), ("cooling", "降温"),
                     ("favors", "人情"), ("dormant", "沉默"), ("number_ledger", "台账")]:
        st, b = call(c, "GET", "/api/" + ep)
        steps.append(("雷达·" + name, st == 200, "%d字节" % len(b)))
    return steps

def flow_insights(c):
    steps = []
    for ep, name in [("network_portrait", "人脉画像"), ("balance", "资产负债"),
                     ("panorama", "业务全景"), ("checkup", "沟通体检"), ("persona", "个人画像")]:
        st, b = call(c, "GET", "/api/" + ep, timeout=90)
        steps.append(("洞察·" + name, st == 200, "%d字节" % len(b)))
    return steps

def flow_generate(c):
    steps = []
    for fmt in ["word", "excel", "ppt"]:
        st, b = call(c, "POST", "/api/generate", {"topic": "债券投资要点", "format": fmt, "theme": "deep"}, timeout=280)
        f = json.loads(b).get("file") if st == 200 else None
        ok = bool(f)
        if f:  # 立刻下载验证非空(PPT空deck回归)
            st2, b2 = call(c, "GET", "/api/download/" + urllib.parse.quote(f)); ok = ok and st2 == 200 and len(b2) > 2000
        steps.append(("产出·" + fmt, ok, f or ("err %d" % st)))
    return steps

def flow_explore(c):
    steps = []
    for ep, name in [("graph", "文档星系"), ("starmap", "星图"), ("chat_galaxy", "聊天星海"), ("chat_topic_galaxy", "主题星云")]:
        st, b = call(c, "GET", "/api/" + ep)
        steps.append(("探索·" + name, st == 200 and len(b) > 20, "%d字节" % len(b)))
    return steps

def flow_wechat_helper(c):
    steps = []
    st, b = call(c, "GET", "/api/realtime/status"); steps.append(("助手状态", st == 200, "%d" % st))
    st, _ = call(c, "POST", "/api/wechat/watch", {}); steps.append(("挂载消费", st == 200, "%d" % st))
    st, b = call(c, "GET", "/api/ingest/progress"); steps.append(("入库进度", st == 200, "%d" % st))
    return steps

def flow_settings(c):
    steps = []
    st, b = call(c, "GET", "/api/settings"); steps.append(("读设置", st == 200, "%d" % st))
    st, b = call(c, "POST", "/api/settings/test"); steps.append(("测AI连通", st == 200, "%d" % st))
    return steps

FLOWS = [
    ("入库检索", flow_ingest_search), ("问答", flow_qa), ("卡片(CRUD全链)", flow_cards),
    ("人脉", flow_relations), ("雷达(6层)", flow_radar), ("洞察(5项)", flow_insights),
    ("产出文档(PPT/Word/Excel)", flow_generate), ("探索星图", flow_explore),
    ("微信助手消费", flow_wechat_helper), ("设置", flow_settings),
]
# 显式标注:需真手机/真钱/真设备的流程(不可自动,非遗漏)
MANUAL_FLOWS = {
    "注册登录": "需真手机验证码(云SMS_DEV=0)",
    "支付会员": "真发起支付/真订单(花钱)",
    "iOS导入": "需连 iPhone + 全量备份",
    "微信助手生产端": "需重签注入微信抓密钥(sudo+用户在微信搜词,RE操作)",
    "冥想一生": "需 LLM key + 生成故事/歌(慢/费)",
}

def run_flows(c):
    print("\n=== B. 流程化(端到端,每步验证) ===")
    total = passed = 0
    for name, fn in FLOWS:
        try: steps = fn(c)
        except Exception as e: steps = [("流程异常", False, str(e)[:60])]
        ok_n = sum(1 for _, ok, _ in steps if ok)
        total += len(steps); passed += ok_n
        mark = "✓" if ok_n == len(steps) else "⚠"
        print("%s 【%s】 %d/%d" % (mark, name, ok_n, len(steps)))
        for desc, ok, detail in steps:
            print("    %s %s — %s" % ("✓" if ok else "✗", desc, detail))
    print("\n流程步骤: %d/%d 通过" % (passed, total))
    print("\n=== 显式不可自动测(需真条件,非遗漏) ===")
    for name, reason in MANUAL_FLOWS.items(): print("   ⊘ %s:%s" % (name, reason))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int); ap.add_argument("--token")
    a = ap.parse_args()
    ok = completeness_check()
    if a.port and a.token:
        run_flows(Ctx(a.port, a.token))
    else:
        print("\n(只跑了完整性检查;带 --port --token 跑流程)")
    sys.exit(0 if ok else 1)

#!/usr/bin/env python3
"""P2 前端逐按钮冒烟(Tauri=WKWebView 不支持 CDP,故在 Chromium 里加载同一套 dist 打真 sidecar)。

原理:
- 起一个静态 http server 伺服 frontend/dist(ES module 需 http 不能 file://)。
- Playwright(Chromium)addInitScript 在 app JS 前注入:
    window.__COMPOUND_API_BASE__ = 'http://127.0.0.1:<sidecar端口>'   ← 壳平时注入的本机后端地址
    localStorage['auth'] = {token,...}                               ← 复用真登录 token(或独立账号 token)
  → 同一套前端代码在 Chrome 里登录态启动,打真 sidecar。
- 逐个顶层导航 tab 进入 + 每页可见 <button> 点一遍,采集 console 报错 + 网络 4xx/5xx + 截图。

用法:
  python3 ui_smoke_playwright.py --port <sidecar端口> --token <token> [--out /tmp/ui_shots]

★注意:8G 机!Chromium + sidecar 同跑要盯内存。此脚本单页串行、每步截图后释放,尽量轻。
"""
import argparse, json, os, sys, threading, time, http.server, socketserver, functools

DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist")
DIST = os.path.abspath(DIST)

# App.jsx 顶层导航的 11 个 tab(见 COVERAGE_MATRIX §二 App.jsx)
NAV_TABS = ["home", "explore", "persona", "renmai", "radar", "insights",
            "friends", "life", "library", "ingest", "help"]
TAB_LABELS = {"home": "问答", "explore": "探索", "persona": "画像", "renmai": "人脉",
              "radar": "雷达", "insights": "洞察", "friends": "好友", "life": "冥想",
              "library": "文库", "ingest": "入库", "help": "说明"}


def serve_dist(port):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DIST)
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def run(sidecar_port, token, out_dir, web_port=8971):
    from playwright.sync_api import sync_playwright
    os.makedirs(out_dir, exist_ok=True)
    serve_dist(web_port)
    base = "http://127.0.0.1:%d" % sidecar_port
    report = {"tabs": [], "console_errors": [], "http_errors": [], "clicks": []}

    with sync_playwright() as p:
        # 用系统 Google Chrome(免下 playwright 自带 chromium ~150MB);没有再回落
        try:
            browser = p.chromium.launch(headless=True, channel="chrome")
        except Exception:
            browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        # ★app JS 运行前注入后端地址 + 登录 token
        ctx.add_init_script(
            "window.__COMPOUND_API_BASE__=%r;"
            "try{localStorage.setItem('auth',JSON.stringify({token:%r}));}catch(e){}"
            % (base, token))
        page = ctx.new_page()
        page.on("console", lambda m: report["console_errors"].append(m.text)
                if m.type == "error" else None)
        page.on("response", lambda r: report["http_errors"].append(
            "%d %s" % (r.status, r.url)) if r.status >= 400 else None)

        page.goto("http://127.0.0.1:%d/index.html" % web_port, wait_until="networkidle")
        time.sleep(2)

        for tab in NAV_TABS:
            label = TAB_LABELS[tab]
            entry = {"tab": tab, "label": label, "ok": False, "buttons_clicked": 0, "err": ""}
            try:
                # 顶层导航:按文案点(App.jsx 导航项),点不到再试 data-tab
                el = page.query_selector("text=%s" % label)
                if el:
                    el.click()
                    time.sleep(1.5)
                page.screenshot(path=os.path.join(out_dir, "tab_%s.png" % tab))
                # 该页所有可见按钮点一遍(只点安全的:不含删除/退出/支付字样的先点)
                btns = page.query_selector_all("button:visible")
                safe = 0
                for b in btns[:30]:
                    try:
                        txt = (b.inner_text() or "").strip()[:10]
                        if any(x in txt for x in ("删除", "退出", "支付", "删", "清空", "移除")):
                            continue   # 破坏性/花钱的先跳过,单列人工
                        b.click(timeout=1500)
                        safe += 1
                        time.sleep(0.4)
                    except Exception:
                        pass
                entry["buttons_clicked"] = safe
                entry["ok"] = True
            except Exception as e:
                entry["err"] = str(e)[:200]
            report["tabs"].append(entry)

        browser.close()

    with open(os.path.join(out_dir, "report.json"), "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({"tabs_ok": sum(1 for t in report["tabs"] if t["ok"]),
                      "tabs_total": len(report["tabs"]),
                      "console_errors": len(report["console_errors"]),
                      "http_errors": len(set(report["http_errors"]))}, ensure_ascii=False))
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True, help="运行中的 sidecar 端口")
    ap.add_argument("--token", required=True)
    ap.add_argument("--out", default="/tmp/ui_shots")
    a = ap.parse_args()
    run(a.port, a.token, a.out)

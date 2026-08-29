# 会话交接 2026-08-29(防闪退丢进度 · 新 session 先读这份)

> 本机 8G Intel Mac 今晚**两次濒临冻死**(load 186),写此文档保底。冻了照此接着干。

## 0. 一句话状态
3 个真机 bug 已修+推 main,**新 DMG 构建中(CI run `33194145983` 轻量版,~35min)**;等它出包→装→按 §5 计划用**独立测试账号**全面复测。

## 1. 机器安全铁律(★最重要,今晚踩两次)
- **8G 内存是硬伤**。bge-m3 嵌入(2.3G)大批量会把机器 swap 到 load 186 濒冻。
- 已修(动态分档,8G 走 batch8/限量24/节流),但**测试全程仍要盯 `vm_stat` 内存 + `uptime` load**,可用<2G 或 load>50 立刻停重活。
- 别同时跑:客户端嵌入 + Chrome/Playwright + 大文件下载。串行来。
- 停客户端松绑:`osascript -e 'quit app "Compound"'` + `pkill -9 -f compound-sidecar`。

## 2. 今晚改了什么(全部已 commit)
| commit | 内容 |
|---|---|
| 80e6fdd | HEIC 入库崩修复(pillow-heif 注册+打包 libheif+selftest 门控) |
| f1d8806 | PPT 产出空 deck(officecli 未 flush 竞态→三处加 close) |
| 97080ac | bge-m3 嵌入拖垮8G机(load186空转)→ `semantic.py embed_profile()` 按物理内存动态分档 + `/api/embed` 加锁鉴权 |
| (本地未推) | `docs/COVERAGE_MATRIX_2026-08-29.md` 全覆盖矩阵(推 docs 会打断 CI,故只本地) |
- **前三个已推 main**(`env -u HTTPS_PROXY -u HTTP_PROXY git -c http.proxy= -c http.version=HTTP/1.1 push origin main`,HTTP2 framing 报错重试即成)。

## 3. 三个 bug 根因速记(防复发)
1. **HEIC**:ingest.py:263 裸 PIL 打不开 HEIF,IMG_EXTS 却列了 .heic=假支持。修=register_heif_opener + pillow-heif 进包。
2. **PPT 空 deck**:officecli create/batch 后文件被后台 resident 只改内存,adaptive 2-10s 才落盘,API 立刻读=空。修=render_*_officecli 加 `close` 触发 flush。
3. **嵌入空转**:bge-m3 + 大批 encode 激活内存顶爆 8G→swap→单批永不 commit→page_embeddings 卡死不动(CPU 烧在换页)。+ /api/embed 无锁,手动触发起第二份模型内存翻倍。修=按内存分档小批+限量+节流+单飞锁。

## 4. 已验证通过(旧 DMG 33161003044,真包)
- 全格式矩阵 23 种(txt/md/html/csv/json/eml/mbox/docx/xlsx/pptx/pdf/epub + png/jpg/bmp/webp/gif OCR + wav/mp3/m4a/mp4/mov 转写)
- RAG 问答(8 跨格式出处)、产出 Word/Excel
- **iOS 历史导入端到端**(39/39 会话含6群,FTS 搜「罗仲平」30 条命中)
- **微信助手实时 handoff**(注入哨兵 3s 入库+心跳)

## 5. 待办:新 DMG 出来后的复测计划(独立测试账号)
> 详版=`docs/COVERAGE_MATRIX_2026-08-29.md`。规模:后端 109 路由 + 前端 39 组件/~425 交互点。
> **数据方向=独立测试账号**(用户拍板):测试全走新注册的测试手机号,真账号 18201972547 不碰。
> ★注意:人脉/雷达/洞察等真数据功能需要该测试账号先导入微信才有内容;或专门造语料。

- **P0 回归**(3 修复必须端到端确认):HEIC 上传出文字 / PPT 立刻下载有幻灯片 / 嵌入 page_embeddings 持续涨+load 不飙+语义搜命中。
- **P1 真数据后端**:逐个打 relationships/commitments/matches/cooling/favors/dormant/number_ledger/balance/panorama/checkup/network_portrait/persona/discoveries/group_graph/relation_timeline/rel_path/graph/starmap/chat_galaxy + report/draft_reply/friend/match/deepen —— 带真数据看真输出(以前只测空态)。
- **P2 前端逐按钮(~425 点)**:★Tauri=WKWebView **不支持 CDP**!测法=在 **Chrome 里加载 `frontend/dist/index.html` + 注入 `window.__COMPOUND_API_BASE__=http://127.0.0.1:<sidecar端口>`**,用 Playwright 驱动同一套 UI 打真 sidecar。工具已就绪(playwright + /Applications/Google Chrome.app + dist 注入点确认)。App.jsx 11 个导航 tab 逐个进,每组件每按钮点一遍。
- **P3 账号/支付真流程**:验证码注册登录/密码/改密码/资料头像/真支付(需云端配合)。

## 6. 关键环境facts(复测要用)
- **sidecar 端口动态随机**(上轮 53790,非文档写死 60380)→ 从 `pgrep -f 'compound-sidecar --host'` 的 `--port` 拿。
- **token**:webview localStorage `~/Library/WebKit/com.compoundtome.desktop/WebsiteData/LocalStorage/tauri_localhost_0.localstorage`,键 `auth`,**UTF-16LE** 存,含 `{token,username,nickname}`。用独立账号则注册新号拿新 token。
- **WEB_PORT**:sidecar_main.py:223 `os.environ.setdefault("WEB_PORT",str(args.port))` 已设成真端口(iphone import 回传/uploader 用它),ps 看不到是进程内设的。
- **认证中心化**:send_code/register 走云端 106,dev_code 云端没返 → 独立账号注册需真手机验证码,或查 sms_codes 表/让用户提供。
- **BRAIN_DATA/库**:`~/Library/Application Support/Compound/brain/library.db`(pages.method 分类,documents 无 method 列)。产出物在 `.../brain/generated/`。日志 `~/Library/Logs/com.compoundtome.desktop/compound-sidecar.log`(★注意区分旧构建残留日志行,看行号是否在最近一次 `Uvicorn running` 之后)。
- **DMG 下载**:走 clash(`gh run download`,clash 只隧道不篡改);`env -u HTTPS_PROXY` 直连反被本机 mitmproxy 拦。旧包在 `~/Downloads/compound-dmg2/Compound_0.1.0_x64.dmg`。
- **装包**:`hdiutil attach` → `cp -R /Volumes/Compound/Compound.app /Applications/` → `open -a Compound`。

## 7. 真库当前污染(待清)
真账号 18201972547 库里 doc1-36 是本轮测试垃圾(SENTINEL*/ocr_test/audio_test/生成物/`微信_与助手实时测试群`),doc37+ 是真实 iOS 微信(45会话含6群)。**改用独立账号后真库不再加污染**;这批旧垃圾要不要清由用户定(见对话,倾向清)。

## 7.5 新 DMG(build 33194145983)复测结果(2026-08-29 深夜)
新包=`~/Downloads/compound-dmg3/compound-mac-intel-lite/Compound_0.1.0_x64.dmg`(koly✓,selftest PASS 含 `OK pillow-heif HEIC 编解码`)。测法=挂副本库(`/tmp/compound-test-brain`=真库拷贝)跑新 sidecar(端口59000),真库不碰。
- **★P0 三修复全部端到端验证通过**:
  - HEIC:上传 t.heic → doc71 **status ok**(旧包 error),OCR 出「紫金矿业债券投资测试 OCR FIX VERIFY 2026」✓
  - PPT:生成后**立刻下载 = 9 张幻灯片**(旧包 = 0 空 deck)✓
  - 嵌入:**load 全程 4.5–8.3(旧包 186!)+ page_embeddings 39→47→55 持续爬(旧包卡死)**✓ 机器不再冻、能进展。慢(8G+bge-m3 物理极限,~8页/批,283页要~1.5hr)但达标。
- **P1 部分**:cooling ✅ 真数据(林深见鹿 降温严重 178天);relationships/commitments/favors/dormant/people/number_ledger **空——因为「分析」intel pass 没跑**(chat_intel/relationship_cards/persona_cache=0,kb_entities=42),非bug。这些要 LLM 逐会话分析,8G 上慢。analysis_status:embed~9-17%/intel 0%/entities 部分。
- **P2 被并发拖垮不可信**:驱动机制单独验过 OK(Chrome 加载 dist,页面「第二大脑」渲染正常);但**嵌入占 201%CPU 时跑 Chrome→click 超时(机器卡,非UI bug)**。
- **★★核心结论:8G 机上无法「一边分析/嵌入一边测前端」,俩抢资源全卡。P1/P2 完整跑必须等分析完成(嵌入~1.5hr + intel LLM pass 数十分钟+DeepSeek费)或换强机。**
- 待续:让分析跑完再干净跑 P1(真数据洞察)+ P2(425按钮 CDP)。测试 sidecar 已停,副本 `/tmp/compound-test-brain` 可复用(嵌到 ~55)。

## 7.7 白天续:重建含 bg-analyzer 的新版 + flow_tests 套件 + 真机验证(2026-08-29 白天)
- **新增真机 bug(用户在 B 走流程发现)**:
  1. 微信助手下载处漏「抓密钥」步 + 抓密钥无进度 → 改 WechatSync/Guide(客户端)+ panel.py 进度横幅(助手,commit 5be5bec 已推)
  2. Windows 打包连修 4 坑:Unicode print(reconfigure utf-8)→ 前端 VITE_TAURI 内联 env Windows cmd 不认(移到 workflow env)→ NSIS 装不了 2.3G bge-m3(单文件)→ **NSIS 2GB 总包硬限**(改用 MSI/WiX,★不瘦身破坏 Mac/Windows 一致性——用户令:Mac 用 DMG 无大小限,Windows 该换装包器不该瘦身)。Windows 仍在磨。
  3. **★承诺雷达/人脉图谱不自动分析**:客户端只有 bg-embed 后台驱动,intel/entities 无驱动 + 打开页 refresh=0 只读缓存不生成 + 雷达页根本没「重新分析」按钮 + 没配 AI key 时无引导 → 加 `_start_bg_analyzer` 后台线程(app.py),自动逐会话 build_intel + extract_doc_entities,节流幂等,只在配了 key 时跑。
- **★flow_tests.py 测试套件**(回应"case不完整也没流程"):A 完整性=源码机械枚举 109 路由逐条登记流程/deferred,漏一个亮红(已抓出我漏的 auth/login/register/friend);B 流程化=10 条端到端旅程每步验证 + 5 条 deferred。跑法 `python3 flow_tests.py --port <口> --token <token>`。
- **★新版(33238855139,含全部修复+bg-analyzer)已装 B 并验证**:
  - bg-analyzer **真机生效**:导入微信后 承诺雷达 0→64%、人脉图谱 0→22% **自动爬升**(无需手点)。用户"为什么没进度"问题**修复确认**。
  - flow_tests 对新版 B:完整性 109/109 + 流程 **33/37 通过**。雷达有真数据了(承诺5015字节)。4 个未过=个人画像空(需 persona 生成)+ 产出文档×3 err-1(150s超时,harness 非产品——手测 PPT 9张幻灯片是好的,并发+连续3生成超时;下轮调大 timeout)。
- **待续(用户令,构建好继续测)**:助手包传 106+客户端再构建(带最新助手,106 SSH 曾被拦需用户);Windows MSI 出包后装 Win 机测;flow_tests 产出 timeout 调大。★数据在:A 测试库 `/tmp/compound-test-brain`,B 真客户端 `~/Applications/Compound.app`(端口每次随机,lsof/ps 找 --port)。

## 8. 测试方法论教训(用户两次点破,必记)
1. 按「产品全功能清单」搭 case,不是「上轮待办清单」(漏了微信助手)。
2. 「旧包测过 ≠ 新包测过」,每功能当前包重测。
3. 测试数据必须隔离(独立账号),不堆真库,可重置,不污染不重复。

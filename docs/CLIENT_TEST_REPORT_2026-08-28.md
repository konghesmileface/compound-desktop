# 客户端真机测试报告 第二轮(2026-08-28)

**测法(严格按用户令)**:装 DMG 到 /Applications 启动**真客户端**(Tauri 壳自己拉起 sidecar,端口 60380),
**空数据新库**(旧 63M 测试库已备份挪走),复用 webview 里的真实登录 token 打真客户端的 sidecar API。
**不是**本机抽临时 sidecar,**不是**源码直跑。真机 = macOS 12.7.6 / Intel(x86_64)。

---

## 一、验证通过(真客户端 + 空数据)

| 区 | 测项 | 结果 | 证据 |
|----|------|------|------|
| A | 注册流程(send_code/phone_register/auth/me) | ✅ | DEV 码注册通,token 有效,auth/me 返回身份 |
| A | 账户(试用/订阅) | ✅ | account 返回 tier/days_left/active |
| B~M | **34/35 GET 端点空态无崩溃** | ✅ | stats/today/library/people/relationships/commitments/matches/favors/cooling/dormant/balance/panorama/checkup/discoveries/news/cards/graph/starmap/chat_galaxy/chat_topic_galaxy/settings/plans/orders/avatars/network_portrait/links… 全 200 |
| D | persona 空态 | ✅ | 400"知识库还是空的,先去入库"(友好引导,非崩溃) |
| K.3 | 文档入库 txt/md | ✅ | 2 文档 status ok,method text/markdown |
| — | **bge-m3 嵌入** | ✅ | embedded 2/2 真产出向量(空库首次) |
| J/C | 全文搜索 FTS | ✅ | 搜"紫金矿业"命中 test_note.md |
| C | 语义搜索 | ✅ | 搜"债券投资"命中 test_doc.txt |
| K-URL | 网页入库 | ✅ | example.com 抓取 doc_id ok,method text-layer |
| P.1 | 卡片 CRUD 全流程 | ✅ | 新建 id4/改状态 done/编辑/列表/删除/删后空,逐步验证 |
| L | 设置保存 | ✅ | saveSettings {ok:true} |

---

## 二、★真机测出并已修的 3 个 bug(CI 测不出的)

> 都是"CI 环境(macos-latest 新系统)≠ 用户 macOS12 Intel"造成的 selftest 盲区。详见
> `PACKAGING_MIGRATION_PITFALLS_2026-08-28.md` §四·补。

### Bug1 — uploads makedirs 写只读包 → 只读位置启动崩(D1)
- app.py:45 `UPLOADS=ROOT/uploads`+模块级 makedirs,冻结客户端从只读位置(DMG/公证.app)启动即
  `OSError: Read-only file system`。修:落 BRAIN_DATA + try。(装 /Applications 可写侥幸不崩,DMG 直跑必崩)

### Bug2 — ★音视频转写在 macOS12 全废(D2)
- sherpa-onnx≥1.11.2 捆绑的 onnxruntime 引用 `MLComputePlan`(新 macOS 符号)→ macOS12.7 `import sherpa_onnx`
  `Symbol not found` 崩。与 onnxruntime 1.19.2 同类坑。且 `except ImportError` 把真错吞了,音频掉进 FITZ 当 PDF
  开,用户只看到"格式不支持"。
- 修:钉 `sherpa-onnx==1.10.46`(1.11.x 无 Intel wheel;1.10.46 是 CI 可用列表里最高的 macOS12 兼容版)
  + silero v4(≤1.11.x 不认新 silero)+ ingest 音视频分支捕获真错不 fall through + selftest 真加载 VAD/SenseVoice。
- **真机 x86_64 macOS12 验证修复组合**:1.10.46+silero v4 → 转写逐字准确("你好，这是第二大脑的音视频入库
  测试…")+ VAD + pyannote/3dspeaker 说话人分离全加载。

### Bug3 — 单图 OCR 崩:rapidocr 新 API 不可解包(D3)
- 上传 PNG → DB 存 `method=error, "cannot unpack non-iterable RapidOCROutput"`。ingest.py process_image 单图路径
  用旧式 `result,_=ocr()` 解包,新 rapidocr 返回 RapidOCROutput 对象(含 .txts)。backends.py 的 PDF 页路径早已
  适配,唯独单图漏。修:与 backends.py 对齐。

**修复状态**:3 个 bug 全部改完 + commit + push + 106 同步。带修复的构建 `33161003044` 构建中,selftest 已加
"真加载 VAD+SenseVoice"门控。修复经真机 x86_64 macOS12 组件级验证,待新 DMG 出包做端到端复测。

---

## 三、待验证(需新构建 or 手机)

| 测项 | 阻塞 | 说明 |
|------|------|------|
| 音视频入库端到端 | 新构建 | 组件级已验证(1.10.46+v4 转写准确);待新 DMG 上传音频端到端 |
| 单图 OCR 端到端 | 新构建 | 引擎已加载(PP-OCRv6),修解包后待新 DMG 复测 |
| 其余文档类型 docx/pdf/pptx/xlsx/html/csv/电子书 | — | 本轮测了 txt/md/png/url,其余类型下轮补(K.1~K.3 逐类) |
| edge-tts 旁白出声 | LLM key+数据 | 需配 key + 一生故事生成后才有旁白 |
| LLM 类(ask/deepen/match/briefing/report/persona生成) | LLM key+数据 | 空库+无 key 测不到真实输出 |
| 产出 PPT/Word/Excel(officecli) | LLM key+数据 | generate 需内容 |
| **iOS 导入 IOS-06→13** | **手机** | 用户回来连 iPhone 测(执行体 wxsync 已确认在包 PKG-07) |

---

## 四、包内完整性(装机前抽查,已确认)
wxsync/*.py(iOS执行体)✓ / SenseVoice+silero+3dspeaker+pyannote 音视频模型 ✓ / ffmpeg 81M ✓ /
officecli 34M ✓ / bge-m3 ✓ / rapidocr PP-OCRv6×3 ✓ / 微信助手安装包×3 ✓。

# 客户端真机测试报告 第三轮 · 全格式矩阵(2026-08-29)

**测法**:装含全部修复的新 DMG(`compound-dmg2`,构建 33161003044)到 /Applications 启动**真客户端**,
sidecar 动态端口(本轮 53790,注:端口每次启动随机,非文档写死的 60380)。复用 webview localStorage
里已登录 token(用户 18201972547)打真客户端 sidecar API。真机 = macOS 12.7.6 / Intel(x86_64),8GB 内存。
**全程盯内存**:整轮稳定在 2.8–3.7G 可用,未复现下午死机。

---

## 一、上一轮 3 个真机 bug — 新包端到端复测全部通过

| Bug | 复测结果 | 证据 |
|-----|---------|------|
| Bug1 uploads 只读崩 | ✅ | 装机启动正常,数据落 BRAIN_DATA |
| Bug2 音视频转写 macOS12 全废 | ✅ | wav(doc17)转写逐字准确,method `asr:sensevoice` |
| Bug3 单图 OCR 解包崩 | ✅ | png(doc16)method `ocr:rapidocr`,识别中英文全对 |

---

## 二、全格式矩阵(每种造带唯一哨兵词的文件 → 上传 → 搜哨兵验证内容真提取)

| 类 | 格式 | doc | 结果 | 验证方式 |
|----|------|-----|------|---------|
| 文本 | txt | 1 | ✅ | 上轮已测 |
| 文本 | md | — | ✅ | 上轮已测 |
| 文本 | html | 18 | ✅ | SENTINELHTML 命中 |
| 文本 | csv | 19 | ✅ | SENTINELCSV 命中 |
| 文本 | json | 20 | ✅ | SENTINELJSON 命中 |
| 邮件 | eml | 21 | ✅ | SENTINELEML 命中(method email) |
| 邮件 | mbox | 22 | ✅ | SENTINELMBOX 命中 |
| Office | docx | 23 | ✅ | SENTINELDOCX 命中 |
| Office | xlsx | 24 | ✅ | SENTINELXLSX 命中 |
| Office | pptx | 25 | ✅ | SENTINELPPTX 命中(officecli 造件) |
| PDF | pdf(文本层) | 26 | ✅ | SENTINELPDF 命中(method text-layer) |
| 电子书 | epub | 31 | ✅ | SENTINELEPUB 命中(fitz) |
| 图片OCR | png | 16 | ✅ | ocr:rapidocr |
| 图片OCR | jpg | 27 | ✅ | ocr:rapidocr |
| 图片OCR | bmp | 28 | ✅ | ocr:rapidocr |
| 图片OCR | webp | 29 | ✅ | ocr:rapidocr |
| 图片OCR | gif | 30 | ✅ | ocr:rapidocr |
| **图片OCR** | **heic** | 35 | ❌→已修 | **见 §三:iPhone 默认照片格式入库崩** |
| 音频 | wav | 17 | ✅ | asr:sensevoice |
| 音频 | mp3 | 33 | ✅ | asr:sensevoice,转写准确 |
| 音频 | m4a | 34 | ✅ | asr:sensevoice,转写准确 |
| 视频 | mp4 | 32 | ✅ | ffmpeg 抽轨 + asr:sensevoice |
| 视频 | mov | 36 | ✅ | ffmpeg 抽轨 + asr:sensevoice |
| 网页URL | url | — | ✅ | 上轮已测 |

**结论**:除 heic 外,所有格式内容提取全部命中哨兵。各提取代码路径(fitz / OCR / ffmpeg+ASR /
extract.py Office+文本 / cupsfilter PDF 文本层)均经多格式实测。

---

## 三、★本轮真机测出并已修的 bug:HEIC(iPhone 默认照片)入库崩

- **现象**:上传 t.heic → DB `<!-- 图片 OCR 失败: cannot identify image file '.../t.heic' -->`,method 记为
  error。`ocr:rapidocr` 计数不含它。
- **根因**:`ingest.py:263` 用裸 `PIL.Image.open()`,打包环境只有 Pillow、无 pillow-heif → 打不开 HEIF。
  而 `IMG_EXTS` 明列 `.heic`(声称支持)→ **假支持**。iPhone 默认拍照就是 HEIC,用户导照片必踩。
- **修复(4 处)**:
  1. `ingest.py` process_image:开图前 `from pillow_heif import register_heif_opener; register_heif_opener()`(try 包裹)
  2. `requirements.txt`:加 `pillow-heif`
  3. `compound-sidecar.spec`:`collect_dynamic_libs("pillow_heif")` 收原生 libheif + hiddenimport
  4. `sidecar_main.py` selftest:真编码→解码一张 HEIF,验证 libheif 打进冻结包(缺则 SELFTEST FAIL,CI 卡住)
- **本地验证**:装 pillow-heif 后,原本崩的 t.heic 成功打开(800×300)。**待新构建出包端到端复测**。

---

## 四、待验证(需条件)

| 测项 | 阻塞 | 说明 |
|------|------|------|
| HEIC 端到端 | 新构建 | 源码已修+本地验证,待新 DMG 复测装机真包 |
| iOS 微信全量导入 IOS-06→13 | 手机 | 等连 iPhone;当前库仅 14 条测试残留微信,非全量 |
| 电子书变体 mobi/azw3/azw/fb2/xps/cbz | — | 本地无法合成合规样件;走 fitz/mobi 同 epub 路径,风险低但未逐一实测(诚实标注) |
| LLM 类(问答/撮合/简报/产出PPT-Word-Excel) | — | key 已配(DeepSeek 连通测试通),下一步测真实输出 |

## 五·B、LLM 功能测试(key 配好后当场测,不需重构建)

| 功能 | 结果 | 证据 |
|------|------|------|
| DeepSeek 连通 | ✅ | /api/settings/test 真回话 |
| RAG 问答 /api/ask | ✅ | 检索 8 跨格式出处,LLM 带引用综合作答,诚实指出是测试样本 |
| 产出 Word /api/generate | ✅ | 真 .docx(Word 2007+),14 段,可下载 |
| 产出 Excel | ✅ | 真 .xlsx,四列结构(维度/关键发现/事实/建议),内容引用测试数据 |
| **产出 PPT** | ❌→已修 | **见 §六:officecli resident 未 flush,前端立刻下载拿到空 deck** |

## 六、★本轮第二个真机 bug:产出文档 officecli 未 flush 竞态(PPT 空 deck)

- **现象**:生成 PPT 立刻下载 → 0 张幻灯片(只有母版/版式)。同文件十几秒后再看磁盘 = 6 张(自动刷补上)。
- **根因**:`generate.py` 三个 `render_*_officecli` 用 `create`+`batch`/`add`/`import` 后**直接 return**,
  未 `close`。officecli 后台 resident 持有文件仅改内存,adaptive 2–10s 才自动落盘。API 在 resident 落盘前
  就把文件读出发给前端 → 空/残缺。PPT 因批量加页耗时短、我下载得快,稳定复现;Word/Excel 同 race,
  测时多走几个来回拖了几秒侥幸刷完,不代表用户不会踩(用户点完立刻下载就中招)。
- **修复**:`generate.py` 加 `_occ_flush(path)`(officecli `close` 触发 flush),三个 render_*_officecli
  落盘前都调用。**本地验证**:create→batch→close→立刻读 = 2 张幻灯片当场就位(之前 0)。
- **待新构建端到端复测**(这次改的是打包内 generate.py,需重构建进包)。

## 七、★★真机 iOS 导入 + 微信助手 + 嵌入(2026-08-29 深夜)

### 7.1 iOS 历史导入 ✅ 端到端通(IOS-06→13)
- iPhone "kong"/iOS 18.6.2 连机+信任 → `idevicebackup2 --full` 备份(峰值~47G,磁盘最低15G安全)→ 抽微信库
  → 认人 → **39/39 会话成功**(含 6 群)→ 入库(文档36→70,微信322页)→ 备份自动清空回收磁盘。
  FTS 搜「罗仲平」30 条命中(真实业务聊天带时间戳),内容完整。
- ★完整性待核:备份已自动删,无法回查手机微信库比对是否 100% 全量;下轮用 keep_backup 留库逐表核。

### 7.2 微信助手(实时同步 handoff)✅ 消费链路通
- wxsync.py(launchd com.wxsync.decrypt)在跑,历史 handoff 已 100% 消费。注入哨兵消息到
  `~/.wxsync/handoff/messages-*.ndjson` → sidecar 消费线程 **3s 内入库**(微信页322→323,搜 SENTINELHELPER 命中,
  成 `微信_与助手实时测试群.txt`)+ 心跳更新。★上轮漏测此功能(误当 iOS 导入=微信覆盖),本轮补。

### 7.3 ★★第三个真 bug:bge-m3 嵌入拖垮 8G 机(load 186 空转)
- **现象**:iOS 导入 322 页微信后,后台嵌入线程 CPU 121%/内存46%,**load 冲到 186**,机器快冻死;
  且 page_embeddings 卡在 39 **不涨**(空转)。
- **根因**:①bge-m3(2.3G)+ 一批 48 页的 encode 激活内存,在 8G 机顶爆物理内存 → macOS 疯狂 swap →
  **单批永远跑不完、永不 commit** → 数字不动(空转真相=颠簸,CPU 烧在换页不在算向量)。②`/api/embed` 端点
  无锁无鉴权,手动触发会和后台线程各加载一份 bge-m3(2.3G×2)→ 内存翻倍(我复现时正是它把 load 顶到 186)。
- **修复(semantic.py + app.py)**:①batch 48→8(峰值内存降,小批能真跑完增量 commit);②embed_pending 加
  max_pages,后台线程每轮只嵌 24 页+批间 0.3s 节流,调用短返回快靠 sleep 给机器喘气,不再一口气占死;
  ③`/api/embed` 加 _BG_EMBED_LOCK 单飞锁+鉴权,正在嵌入返回 busy,杜绝双份模型。
- **待新构建验证**(改的是打包内代码)。★8G 是这机型硬伤,修后能progress+不冻机,但仍慢;云端嵌入是后续选项。

## 五、其它
- DeepSeek key 已配入客户端,`/api/settings/test` 真回话通。**注:LLM 回复自带 emoji(😊),
  与「全站禁 emoji」铁律冲突,产出类 prompt 需兜底清洗(既有待办)**。
- eml/mbox 提取正文正常,尾部几个乱码字符系测试文件本身编码,非提取 bug。

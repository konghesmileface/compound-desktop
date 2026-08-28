# 打包/迁移遗漏 复盘与防复发（2026-08-28）

> 本轮血的教训:**"有前端 UI ≠ 有功能"**。iOS 导入、edge-tts 旁白、音视频入库三块都有完整前端,
> 但打包产物里没有执行代码/依赖/模型,web 端(106)也一直哑火。上一轮测试矩阵把"有前端=✅"当完成,
> 漏检了"打包/部署到底带没带执行体"这一整维,是本次事故根因。此文档钉死每个问题+防复发规则。

---

## 一、问题全景(本轮发现)

### 类别 A:打包漏执行体(前端有、包里没执行代码/依赖/模型)

| # | 功能 | 前端 | 打包缺什么 | 后果 | 状态 |
|---|------|------|-----------|------|------|
| A1 | **iOS 历史导入** | WechatSync.jsx 有按钮+五段动画 | `import_iphone.py` 等 wxsync/*.py 没打进包;sidecar 无 `/api/iphone/*` 端点 | 前端点了没人执行 | ✅已补(sidecar/wxsync/ + 端点 + spec 打包) |
| A2 | **edge-tts 旁白/冥想语音** | 一生故事/冥想有语音 | `edge-tts` 不在 requirements;selftest 不验 | 无声音(try import 静默失败) | ✅已补(requirements + selftest 门控) |
| A3 | **音视频入库** | 入库 tab 可传音视频 | ①ingest 接线丢 ②`sherpa-onnx`/`soundfile` 不在 requirements ③ASR 模型没下没打包 ④无 Mac ffmpeg | 音视频当文档处理失败,转写不出 | ✅已补(接线+requirements+CI下模型+ffmpeg+selftest 门控) |

### 类别 B:T430→106 迁移遗漏(函数名一样、函数体被删)

| # | 文件 | 丢的东西 | 为什么没发现 | 状态 |
|---|------|---------|-------------|------|
| B1 | `ingest.py` | `process_any` 里音视频分支 + `DOC_EXTS += _MEDIA_EXTS` 接线 | **函数名对比看不出来**(函数还在,函数体里的几行被删) | ✅已补回 106 + 客户端 |

> 迁移对比结论:**106 是 T430 的后来超集**(45 vs 17 个 .py,所有共享文件 106 ≥ T430)。
> 后续所有开发都在 106,T430 自迁移后没再动。**唯一 T430 独有、迁移丢的就是 B1**。
> 方法论:光比函数名不够(B1 就漏了),要比**行数 + 函数体 + 关键接线字符串**。

### 类别 C:web 端(106)运行环境缺依赖(部署遗漏)

| # | 缺什么 | 影响的功能 | 后果 | 状态 |
|---|--------|-----------|------|------|
| C1 | 106 `/opt/compound-server/venv` 无 `edge_tts` | 冥想语音 + 一生旁白 | web 端一直无声(静默失败) | ✅已装 edge-tts 7.2.8 + soundfile |
| C2 | 106 venv 无 `sherpa_onnx`/`soundfile` + 无音视频模型 + models 目录都不存在 | 音视频转写入库 | web 端音视频一直转不出 | ✅已装 sherpa-onnx 1.13.6 + 下全模型(经 ghfast 镜像) |

> **注意:T430 venv 本身也没 sherpa_onnx**。说明音视频转写在服务器端**从来没真正跑通过**,
> 只是模型放那儿、代码写好了,`import sherpa_onnx` 在函数内被 `try/except` 吞掉 → 静默降级。
> 用户记忆里"入库过音视频"多半是文件进了库但转写没成。

---

## 二、关键真相(排错时踩过的坑,记下来别再绕)

1. **web/app.py 运行的是父目录的 ingest.py,不是 web/ 下的**
   `web/app.py:32` `ROOT = dirname(dirname(__file__))` = `/opt/compound-brain`,
   `sys.path.insert(0, ROOT)` 后 `import ingest` → 加载 `/opt/compound-brain/ingest.py`。
   web/ 下只有 app.py + 6 个卫星模块(chat_intel/relationships/graph_kg/owner_ctx/chat_topics/song_factory)。
   **补后端共享模块补父目录 `/opt/compound-brain/*.py`,别补错 web/**。

2. **systemd 服务实况**:`WorkingDirectory=/opt/compound-brain/web`,
   `ExecStart=/opt/compound-server/venv/bin/python -m uvicorn app:app --port 8200`,
   `BRAIN_DATA=/opt/compound-brain`(→ media_ingest 的 BASE,模型找 `/opt/compound-brain/models/`)。

3. **静默失败是隐形杀手**:`try: import sherpa_onnx … except ImportError: pass` / edge-tts 的 try 包裹,
   缺依赖时不报错、不崩、直接没结果。**测试若只看"没崩" = 测了个寂寞**。必须验证"有依赖时真出结果"。

4. **国内 106 下 GitHub release 极慢**(5 分钟才 2.9M):用镜像 `https://ghfast.top/https://github.com/...`
   前缀,秒下。ghproxy.com 系已不稳。

5. **改 106 前先备份**:任何 `.py` 改动前 `cp x.py x.py.bak_<用途>_<ts>`;scp 传文件走 md5 校验循环
   (代理会损坏大文件,`tls: bad record MAC`);改完 `ast.parse` 编译检查 + `systemctl restart` + `/health`。

---

## 三、防复发规则(硬约束,写进流程)

### R1 — 每个"需打包执行体"的功能,必须有 selftest 数据门控
`sidecar/sidecar_main.py --selftest` 已加:缺任一数据文件/依赖 → `SELFTEST FAIL` → **CI 构建失败,不流到用户**。
当前门控清单(新增功能必须往这里加一条):
- cacert.pem / schema_full.sql / bge-m3 权重 / rapidocr onnx / 微信助手安装包
- **SenseVoice ASR / ffmpeg / silero VAD / 3dspeaker 声纹 / pyannote 分割**(音视频)
- **import sherpa_onnx / import edge_tts**(音视频 + 旁白)
- onnxruntime 1.19.2 真加载

> 铁律:**"有前端就要有 selftest 门控"**。任何前端按钮背后的执行依赖(二进制/模型/py 模块/pip 包),
> 都要在 selftest 里断言存在,否则视为"没做完"。

### R2 — 新功能三件套必须同时到位,缺一不算完成
1. **执行代码**打进包(spec datas / hiddenimports)
2. **pip 依赖**进 `requirements.txt`
3. **模型/二进制**由 CI 下载步骤拉取 + spec 打包 + selftest 断言

### R3 — 客户端与 web 端(106)双同步,防分叉
任何共享后端改动(ingest/media_ingest/generate/llm/semantic/extract/backends…):
- 客户端:改 `sidecar/*.py` + 提交
- web 端:同步改 `/opt/compound-brain/*.py`(父目录!)+ 装依赖 + 下模型 + 重启
- **两边 diff 到函数体一致**(不能只对函数名)

### R4 — 迁移/对比要比到函数体
比两台机代码用:文件清单 → 行数 → **函数体 diff** → 关键接线字符串 grep(如 `_MEDIA_EXTS`/`process_media`)。
只比函数名会漏 B1 这种"壳在肉没了"的。

### R5 — 测客户端就测打包产物,不测源码(用户铁律)
下最新 CI 产物的 DMG,真机装,不允许用本机抽的临时 sidecar / 源码直跑冒充。

### R6 — 空数据新用户全流程,不用旧库掩盖
从注册登录 → 每个 tab 每个功能,空态/引导/崩溃是重点。旧库会掩盖空态 bug。

---

## 四、本轮修复清单(对应提交)

- `6da65f5` 补齐客户端漏打包:iOS 导入完整链路 + edge-tts + sherpa 音视频依赖
- `17a1c73` 补齐音视频入库:T430 迁移 106 丢的接线 + 模型打包
- 106 web 端:补 ingest.py 音视频接线(带备份/md5/编译校验)+ 装 edge-tts/soundfile/sherpa-onnx + 下全套音视频模型
- CI 轻量版构建 `33155822652` **SELFTEST PASS**(音视频/edge-tts/sherpa 全绿)

---

## 五、遗留/待验证

- [ ] iOS 导入:打包产物真机实测(代码链路已真机验证过 47G→38 会话,现需在 DMG 装机版复测)
- [ ] 音视频入库:106 模型下完后跑一条真音频验证转写出文字
- [ ] 高精版(HD)构建同步验证(与轻量版同改动)
- [ ] **web 端 iOS 导入前端**:架构不同(web 无本地 sidecar 跑 idevicebackup2),需单独设计,当前仅客户端可用
- [ ] 下一轮:空数据新用户 DMG 装机全 tab 复测(见 TEST_MATRIX_AUDIT.md v2)

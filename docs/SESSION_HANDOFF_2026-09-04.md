# Compound 桌面客户端 · 会话交接 2026-09-04

> 承接 SESSION_HANDOFF_2026-09-02.md。本轮 = 三台真机深测(全格式入库 + 微信实时同步 + 高精OCR)+ 一批根因 bug 修复 + 性能去妥协 + 全页面样式彻查 → 发版。

## 一、发版状态(2026-09-04)
- **客户端 HEAD = `ae18ee2`**,工作区干净、全推送。三端构建 `ae18ee2`(高精33780201863 / Mac轻量33780200327 / Win轻量33780200317)。
- **微信助手 = wxsync-helper `4d26cc1`**(独立仓 konghesmileface/wxsync-helper),已打进客户端 `sidecar/downloads/微信同步助手-Windows.exe`(md5 校验=最新构建产物,含分步抓密钥提示)。
- 106 云:画像接口 `/social/persona/mine?full=1` 已上线。
- 发版前一致性核对全过(代码同步/助手最新/106上线)。

## 二、三台机器(★办公网,IP 会随网络变)
| 机器 | 办公网 IP | 家庭网 IP | 版本 | 账号 |
|---|---|---|---|---|
| 本机 Mac | 172.16.17.75(变动) | 192.168.71.108 | Mac 轻量 | 18201972547 |
| mac2(zhaojue / pw qingshi@123) | 172.16.16.172 | 192.168.71.112 | Mac 高精 | 18201972547 |
| Windows(Qingshi / pw qingshi@123) | 172.16.17.175 | 192.168.71.111 | Win 轻量 | 18201972547 |
- ★远程 SSH 必须 no-proxy:`env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY sshpass -p 'qingshi@123' ssh -o StrictHostKeyChecking=no -o ProxyCommand=none ...`(走 clash 频繁掉线)。
- ★Windows 系统 python 用 `py`(非 python);嵌 Python 到 PowerShell 引号会崩→scp .py 文件跑;输出中文 iconv GBK→UTF-8。
- ★DMG 经 gh/clash 下载会损坏:ditto 全量校验(imageinfo 只验头不够);LAN scp 可靠。
- Windows 装:scp setup.exe→`start /wait setup.exe /S`(EXITCODE=0成功,装到 %LOCALAPPDATA%\Compound\compound-desktop.exe,主程序名非 Compound.exe)。
- 不碰凭据测入库法:直接往库 `autosync_folders` 插文件夹(owner=账号)→ bg-autosync 后台自动扫描入库,不需 token。

## 三、本轮修复(23笔,git log e196862..ae18ee2)
### ★微信实时同步消息丢失(Windows 1181→16,最重)= 三层根因
1. `_ingest_wechat_msgs` fp 先于写页(autocommit):写页失败 fp 已提交→永久判重丢失。修:先写页成功才记 fp(83be456)。
2. 每页/每条独立容错(127a73f):坏消息不连累整批。
3. ★主因 `_handoff_watch_loop` 游标先于入库成功就持久化(e5ee11f):读一批游标即前进+入库异常被吞+无条件保存→失败那批永久跳过。修:游标 pending 暂存,入库+commit 成功才 apply。
4. 游标自愈(2c5ff91):库空但游标非0→重置重灌(重装/清库自动恢复,不需人工)。
- 诊断法:Windows 日志 wechat/watch 调用次数(消费器起没起)+ Mac 侧用同 handoff 灌验证 _ingest 逻辑。

### ★高精OCR白装(7b02279):mac2高精PNG入库走rapidocr没走paddle。修:_ocr_image_file 优先 PADDLE_OCR_URL /ocr/image(PP-StructureV3),backend标签动态。

### 姻缘缓存失效(070cf28):match_cache 加双方画像 sig,画像变→自动重算(原永久缓存)。
### CT import(579af1a):bg-analyze chat星系预热漏 import chat_topics→"name CT not defined"→预热失败首次现算慢。
### 发现链接"大脑解读中"永久转圈(e62cbc5):explain 后台异步生成但前端进页只拉一次→加轮询每8s直到补上。
### 承诺雷达/人脉图谱没配key(9907c92):加 needs_key 前端提示"去设置配AI key"(不再干停0%)。
### key无效反馈(73b35bd):Settings保存后自动测key,无效当场提示。
### 联想卡去重(73b35bd):按显示名前端去重(后端norm归一化不一致致重复)。

### 性能去妥协(0079981)★用户铁律:不为老电脑牺牲好机器性能
- 新增 _perf_profile() 按内存分档:好机器(32G+)bg-analyze每轮20个+不歇、autosync 200/轮;老8G才3个+sleep15/90s。ASR让CPU仅老机。embed_profile本就分档。ANALYZE_BATCH 环境变量可覆盖。
- 回退了之前的"8G错峰"(会串行拖累好机)。

### UI/样式(4c08900/996a666/ae18ee2/c2c1bc6)
- 宽屏全页居中:.view padding: max(46px,(100%-1600px)/2)(洞察/雷达/冥想/人脉/画像一次生效);home-view/ms-page 同款。
- 洞察标签云字号 21→16px;日期 input 全加 lang=en(不再"yyyy-mm-日");关系路径 select 深色。
- 全弹框已 max-width+vw 限宽居中(扫描确认无遗漏)。

### Windows体验(fe60f78/0ef6767/f2c0e9c)
- 窗口秒出(壳不等/health,前端Boot门轮询splash);所有子进程CREATE_NO_WINDOW(无cmd黑框);助手下载秒存(拷Downloads+reveal,绕SmartScreen)。
- 换机拉回本人画像(_ensure_my_persona);冥想历史歌同步进度;入库页数据体量说明+iPhone仅Mac提示。

### 四类入库深修(上一轮e196862内,本轮全测通过)
- 视频/语音:流式读音频防OOM+ASR让CPU+diarize>30min跳过+LLM纠错并行+说话人对话块+纪要排版。
- 网页:文本密度自适应正文(去导航)+<title>命名+SPA退取摘要。邮件:_eml/_mbox HTML去标签。
- 文库:首次学科聚类改后台(治堵死)。

## 四、三台入库全测结果(本轮验证通过)
- Windows轻量 + mac2高精:**11格式全过**(pdf/pptx/md/png-OCR/txt/eml×2去HTML/docx/html正文/xlsx结构化/mp4-ASR)。
- 邮件去HTML ✓、网页正文自适应 ✓、Excel结构化 ✓、视频转写带时间戳说话人 ✓。
- mac2高精揪出"高精OCR白装"bug(已修,下次装新版验证 backend=ocr:paddle)。

## 五、明天待办
- **三台装最新版 ae18ee2 验收**:本机Mac轻量+Windows轻量+mac2高精(构建完下载装)。重点复核:
  - Windows宽屏全页居中(洞察/雷达/冥想不再右侧空白)、日期不再yyyy-mm-日、发现链接解读不再永久转圈。
  - mac2高精:图片OCR backend 应=ocr:paddle(不再rapidocr)。
  - 微信实时同步:新装干净入库(游标自愈,不需手动清)。
- 测试账号清理(上线前):106 accounts.db 的 qatest0831a/qaflow0831/bella_test(需用户放行)。
- Mac 助手(dmg×2)本轮未更新(用户令保持),WAL安全网改动只在Win助手。若要Mac助手也更新需跑 build.yml。
- 106 同源对齐:本轮客户端多处改动(match sig/needs_key/_ingest等)未同步106(106是demo,实时同步用得少)。

## 六、关键铁律(累积)
- WKWebView ~60s超时→长请求必异步job+轮询。
- 不为老电脑牺牲好机器性能(按内存档,好机全速)。
- 微信数据完整性:fp后于写页、游标后于入库成功、坏项独立容错。
- 远程Windows:no-proxy + py + scp脚本 + iconv。
- 助手是独立仓 wxsync-helper,改完推送→build-win出exe→下载替换客户端downloads(git跟踪)→客户端构建。

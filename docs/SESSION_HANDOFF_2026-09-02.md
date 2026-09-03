# Compound 桌面客户端 · 会话交接 2026-09-02

> 承接 SESSION_HANDOFF_2026-09-01.md。本轮 = 用户真机深测,连续报 bug 逐个根修 + 106 同源对齐 + 打包完整性根治。

## 一、当前状态
- **运行中的客户端**:Mac A 本机,`/Applications/Compound.app`,build = commit `2f18ff4`(DMG 已装,sidecar 端口见 `/tmp/wf_port.txt`,本轮 = 64105)。账号 = 18201972547。
- **测试数据库**:`~/Library/Application Support/Compound/brain/library.db`(15441 页,微信 5393 页,书 5 本约 9276 页;嵌入用 `pysqlite3`,读库带 trigram)。
- **106 云**:真实 IP `root@106.14.189.104`(别名 `106` 没进 ssh config 会解析成 0.0.0.106,**必须用真实 IP**)。
  - compound-server(:8000)= 账号/社交;compound-brain(:8200,systemd `compound-brain.service`,cwd `/opt/compound-brain/web`)= 第二大脑 + 前端 `/app`。
  - py_compile 用 `/opt/compound-server/venv/bin/python`(系统 python3 是 3.6,不支持 `from __future__ annotations`)。
  - 前端 dist = `/opt/compound-brain/web/frontend/dist`(部署只替换 `assets/`+`index.html`,保留 `albums/lp/showcase`)。

## 二、本轮已修(commit 时间序)
| commit | 修复 | 类别 |
|---|---|---|
| f500dac | chat星系「仅聊天」首次点击空→**异步化**(_cache_peek+bg聚类+前端轮询,躲 WKWebView 60s 超时);问答答案渲染 **markdown**(标题/列表/表格/加粗)保留可点来源角标 | WKWebView超时 / 渲染 |
| 8e23f76 | 匹配弹窗「你」侧渲染**本人 MBTI**(后端早返 my_mbti,前端漏渲染) | 前端漏渲染 |
| ee37496 | 冥想唱片卡**抖动**(vinylspin 缺 from→x 在 0↔13% 来回漂);删好友**二次确认框** | CSS动画 / UX |
| ec1fed5 | 添加好友**支持手机号**(106 friend/request 的 to 就是 ident,手机号用户 ident=手机号,直接可用;保留列所有人) | 功能 |
| fac2106 | 删关系卡**可选同步删聊天记录**(confirmDialog 加复选框;后端 wipe_chat 精确匹配 `微信_与{contact}.txt` 级联删);**修 `deleteCard` 键名冲突**(api.js 两处同名,relationships/delete 被 /api/card/{id} 覆盖→人脉删卡实际调错端点被 .catch 吞→card_hidden 没记→重分析长回来)→改名 `deleteRelCard` | 功能 / 隐藏bug |
| 2f18ff4 | 产出交付物**生成后消失**(api.generate 轮询到 done 返整个 job 包没解包 result→file.title/file 全 undefined→NodeDetail 下载按钮不渲染)→解包 st.result;生成按钮**浮层**(min-width 固定+不透明底,防 reflow 鬼影);**微信聊天优先嵌入**(embed_pending 加 ORDER BY 微信 first,治聊天层卡 5381/5412——31 页新聊天排 4073 书页后) | 前端契约 / CSS / 嵌入顺序 |
| 1aba7ba | **群卡自由提问不知哪个群**(run→api.ask 没传 contact,后端全局检索;后端早支持 contact 限定→前端补传);**供需撮合偶发空 0×0**(冷缓存嵌入数百条+LLM>60s→WKWebView 超时→前端 catch 落 {matches:[]}→显示 0×0)→改异步(先秒返 base 供需计数+后台配对+轮询,新增 chat_intel.supply_demand_base);**唱片卡顿补强**(上次只修水平漂移,漏 transition vs animation 打架+hover 叠 rotate→spinning 时 transition:none + spinning:hover 不叠 rotate) | contact检索 / WKWebView超时 / CSS |
| 8fabacb | 视频抓取 **ffmpeg 硬编码路径**(`/home/kb/brain/bin` 服务器路径→客户端崩)→动态定位 _MEIPASS/bin;**selftest 补全惰性第三方库**(yt_dlp/bs4/soundfile/mobi/edge_tts/…)根治"打包不全面" | 硬编码 / 打包完整性 |

## 三、106 同源对齐(本轮已做并验证)
- app.py 三处对齐:异步 chat_topic_galaxy + `_cache_peek`(补了 `_GEN_JOBS`)、relationships_delete 的 `wipe_chat`。用 patcher(正则锚 ASCII 行,避开中文标点全/半角)。
- 前端 dist 部署最新构建(客户端同一份;本地 dist 无焊死 base,`__COMPOUND_API_BASE__` 运行时注入→同源浏览器 base='' 天然适配 106)。
- brain 重启 active,验证 `/app` 200 / 新 assets 200 / chat_topic_galaxy 无 token 返 401(非 500)。
- ⚠ 未对齐:**matches 异步 + supply_demand_base + embed 微信优先 + ask contact**(1aba7ba 及之后)还没同步到 106,下次一起补。

## 四、待办
- **待构建**:`1aba7ba`+`8fabacb` 两笔(群提问/供需撮合异步/唱片卡顿补强/视频ffmpeg/selftest)还没出客户端包。用户说构建再推。
- **构建后必肉眼复核**:唱片卡顿(点第2张)、生成按钮浮层、供需撮合冷启动不再空。
- **106 补对齐**:matches 异步 / supply_demand_base / embed 微信优先 / ask contact。
- **视频抓取 B站 412 反爬**:yt_dlp 已打包(412 证明在跑),B站需 cookie 或更新 yt_dlp——反爬问题,非打包。普通网页/文章链接正常。
- **测试账号清理**:106 accounts.db 里 `qatest0831a`/`qaflow0831`/`bella_test`(上线前清,需用户放行)。
- mac2 高精 / Windows 轻量装机测(用户令:Mac A 干净再测其他)。

## 五、铁律 / 踩坑(本轮新增)
- **WKWebView ~60s 超时是一类通病**:凡后端单请求可能 >60s(生成/chat星系/供需撮合冷算)必须**异步 job+轮询**,否则前端 catch 落空态,表现"有时没数据/生成失败/首次点空"。已改的:generate / chat_topic_galaxy / matches。
- **打包完整性**:纯 python 惰性 import 进 PYZ(二进制内),**文件系统查不到 ≠ 没打包**(openpyxl/edge_tts/yt_dlp 都在 PYZ)。唯一可靠验证 = 跑打包二进制 `--selftest`。已把所有惰性第三方库塞进 selftest,CI 缺任一即 FAIL。
- **api 对象重复键**:`deleteCard` 曾重名两处,后者静默覆盖前者→功能调错端点被 .catch 吞。改动 api.js 注意查重名。
- **前后端契约**:异步端点返 `{state,result}`,前端务必解包 `result`(生成消失的根因)。
- 唱片/星云等 CSS 动画:WKWebView 里 `transition` 和 `animation` 同属性会每帧插值打架→卡顿,spinning 时须 `transition:none`。
- 好友星云粉线 = **命定星唯一**(契合最高一位,>0)才连一条线,其余漂浮——原始定稿设计(P1-22),StarCloud.jsx 从 M1 至今零改动,别误判"恢复错版本"。

---

## 六、续(2026-09-03):三台装机 + 视频/网页/邮件深修 + Windows 体验

### 三台机器(用户家庭网络,均可达)
| 机器 | IP(家庭网) | 版本 | 已装 |
|---|---|---|---|
| 本机 Mac | 192.168.71.108 | Mac 轻量 | ✅ e196862 |
| mac2(zhaojue,pw qingshi@123) | 192.168.71.112 | Mac 高精 | ✅ e196862 |
| Windows(Qingshi,pw qingshi@123) | 192.168.71.111 | Win 轻量 | ✅ e196862 |
- ★办公网旧 IP 已变:mac2 曾 172.16.16.172、Win 曾 172.16.17.175;换网后走家庭网 192.168.71.x。
- 远程装法:Mac 用 sshpass+scp DMG→挂载 ditto 到 /Applications;Windows scp setup.exe→`start /wait setup.exe /S`(EXITCODE=0 即成功,装到 `%LOCALAPPDATA%\Compound\compound-desktop.exe`,主程序名不是 Compound.exe)。
- ★DMG 经 gh/clash 下载会损坏:必须 ditto 全量校验(imageinfo 只验头不够);LAN 内 scp 可靠。

### 已提交待构建(e196862 之后,`git log e196862..HEAD`)
- fe60f78:换机从云拉回本人画像(_ensure_my_persona,people/match 触发;106 `/social/persona/mine?full=1` 已上线)+ 冥想历史歌同步进度(mylibrary 带 sync{total,done})+ Windows 窗口秒出(壳不再等 /health 才开窗;前端 main.jsx Boot 门轮询 /health 显 splash)
- 0ef6767:Windows 隐藏所有子进程黑框(open_external 改 explorer;sidecar_main 全局给 subprocess 注入 CREATE_NO_WINDOW)
- f2c0e9c:Windows 下载助手秒存(/api/helper/save 拷到 Downloads + Tauri reveal_file 高亮,绕开浏览器 SmartScreen 扫 .exe)
- 用户令"先不构建",这批攒着,下次一起打 + 三台装。

### 本轮(9-2 白天起)四类入库深修(都已在 e196862 里)
- 视频/语音:流式读音频(治整段进内存 OOM 崩)+ ASR 每段 sleep 让 CPU(治满负荷饿死 HTTP→前端误报"网络不稳",实测 sidecar 207% CPU 没崩只是忙)+ diarize>30min 跳过 + LLM 纠错并行5 + 说话人对话块渲染 + AI 纪要清爽排版。
- 网页:文本密度自适应正文(去导航菜单)+ `<title>` 命名 + SPA 退取 title/meta 摘要。
- 邮件:_eml/_mbox HTML 正文去标签(治吐原始 HTML)。
- 网络韧性:Ingest 轮询抖动不再报错、软提示"处理中/别重传"、后端重启引导看文库、大文件等待提示。
- 文库:首次学科聚类改后台(治同步 KMeans 堵死 sidecar→文库空)。

### ★仍需注意
- 视频转写在 8G 上仍慢(29min 视频要不短时间);已流式+让CPU降低崩溃率,但**增量保存未做**(崩了丢全部转写)——可作下一步。
- helper/save 与 boot 门等新端点尚未装到机器上(待构建)。

---

## 七、续(2026-09-03 下午):微信消息丢失根治 + 助手更新 + 待办

### 微信实时同步消息丢失(Windows 1181→2条)真凶=两层
1. `_ingest_wechat_msgs`:autocommit 下先落全部 fp 再写 page,写页失败 fp 已提交→永久判重丢失。已修:先写页、成功才记 fp + 每条 try 容错。
2. ★真正主因(消费器层)`_handoff_watch_loop`:读一批游标立即前进(1862)+ 入库 try/except 吞异常 + 末尾无条件 _handoff_save_cursors → 入库失败那批游标已存到末尾、下次跳过永久丢。已修(commit e5ee11f):游标改 pending 暂存,入库+commit 成功才 cursors.update+持久化;失败不前进下次重读(fp去重防重复)。
- 诊断实锤:Windows 日志 wechat/watch 调用11次(消费器起了)但库只入几条 → 定位到消费器游标层。Mac 上用同一 handoff 灌 1357条零丢失,证明 _ingest 逻辑本身对。
- Windows 恢复:已在 Mac 侧用 handoff 灌满干净库(1357条/24会话/1435行)推回 Windows,现语义问答已跑完(bge-m3 本地不需key)。

### App.jsx 登录即启动 watch(原来只在打开微信页才启动消费器)= commit e5ee11f 内

### 微信助手:只更新了 Windows 版(用户令 Mac 助手保持不动)
- 助手仓库 = konghesmileface/wxsync-helper(独立 git,非本地 wxsync_vN 散目录);CI=build-win.yml(windows-latest,入口 wxsync_tray.py,单文件 exe artifact)。
- 本次 4d26cc1:Windows 抓密钥提示改分步+进度(原来只1句静态闷跑180s)+ sqlcipher_decrypt 加 WAL 合并安全网。
- 新 exe 已替换进客户端 sidecar/downloads/微信同步助手-Windows.exe(commit 4df32fa)。客户端 CI checkout 就带上(downloads/ 在 git 里,无自动拉取步骤)。
- 发布链:助手仓推送→build-win 出 exe artifact→下载替换客户端 downloads/→客户端构建。

### 承诺雷达/人脉图谱没配 key 不跑(设计非bug)
- 语义问答=本地 bge-m3 不需key;intel/entities 每条调LLM,bg-analyze 门控"没key不跑"。
- 已加 needs_key/has_key + 前端黄字提示"去设置配AI key"(commit 9907c92)。

### ★★待办(下次构建带上)
- **需重新构建客户端**:当前正在跑的这批(33733309306等)带了「消息丢失根治+Win助手更新+数据体量说明+iPhone仅Mac」,但**没带** needs_key 提示(9907c92)——用户令下批再打。
- **Windows 干净重测计划**(坐实根因):卸载旧客户端+清 %APPDATA%\Compound + ~\.wxsync(游标/handoff/keys)→装新版→重开助手抓密钥+开实时同步→不手动推,看客户端自己全量入库=证明修对。
- ★远程 Windows SSH 必须 no-proxy:env -u *_proxy + ssh -o ProxyCommand=none(走clash会频繁掉线);Windows 系统 python 用 `py`(非python);嵌 Python 到 PowerShell 引号会崩→scp .py/.ps1 文件跑。
- 三台家庭网IP会变(办公网:mac2=172.16.16.172 win=172.16.17.175;家庭网=192.168.71.x)。

---

## 八、续(2026-09-03 夜):三台入库全测 + 高精OCR真bug + UI批

### 入库全格式测试(autosync 自动扫描法,不碰凭据)
- 测法:直接往库 autosync_folders 插文件夹(owner=账号)→ bg-autosync 后台自动扫描入库。不需token。
- **Windows 轻量:11格式全过**(pdf/pptx/md/png-OCR/txt/eml×2去HTML/docx/html正文/xlsx结构化/mp4-ASR)。邮件去HTML+网页正文自适应验证通过。
- **mac2 高精:11格式全过**,但揪出大bug↓

### ★高精OCR白装(已修 7b02279)
- mac2高精 PNG入库 backend=rapidocr(轻量),没用paddle。真因:_ocr_image_file rapidocr装了就永远return,paddle分支仅rapidocr缺失时走+地址写死8100。
- 修:PADDLE_OCR_URL存在时优先paddle /ocr/image;backend标签动态。

### 微信"人脉卡数量不对"= 其实正确
- 24会话但只7个 pages>=2(其余17个是一两句短会话),关系卡只给够长会话生成→7张正确。非bug。

### bg-analyze CT未定义(已修 579af1a):chat星系预热漏 import chat_topics。

### key无效反馈(已修):Settings保存后自动测key,无效当场提示(不再和"没配key"一样静默)。

### ★UI批(用户Windows宽屏实测,部分待修)
- 图62/64:发现卡片不对齐+底部输入框左右大空白 → home-view已改1600居中(996a666),但洞察/雷达/冥想页用通用.view全宽左对齐、还没加居中包裹(★待修:每个JSX加max-width+auto的wrapper,或.view内层居中)。
- 图65:新建目标日期 type=date 在中文Windows显示"yyyy-mm-日"(WebView2原生本地化,占位符改不了)→★待修:换自定义日期选择或美化。Cards.jsx:104。
- 重复"老男孩":联想历史卡同一人反复展示 → ★待修:去重(Home.jsx 散落模块)。
- "大脑解读中·稍后自动补上":联想卡等LLM生成(key/8G内存相关),补上即消失。
- 8G错峰:嵌入(2.3G模型)与bg-analyze同时跑内存爆(实测95%)→★待做:嵌入进行中时bg-analyze让路。

### 下批构建清单(全部待构建)
needs_key提示 / 游标自愈 / 宽屏空白(home+persona已改,洞察雷达冥想待改) / 标签字号 / CT import / 高精OCR走paddle / key无效反馈 / 【待做:8G错峰、日期选择器、联想去重】

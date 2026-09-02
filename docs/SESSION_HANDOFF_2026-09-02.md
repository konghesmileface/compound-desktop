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

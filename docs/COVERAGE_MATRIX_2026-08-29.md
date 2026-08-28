# 全功能无死角覆盖矩阵(2026-08-29)

> 目的:用户令「全面看所有前后端功能,审计测试 case,增加颗粒度/覆盖度,前后端无死角,一个按钮都不放过」。
> 起因:上一轮漏测**整个微信助手实时同步**(把 iOS 一次性导入误当微信覆盖)。根子=按「上轮待办清单」搭 case,
> 而非「产品全功能清单」;且「旧包测过」被当成「新包测过」。此矩阵按**产品全功能清单**重建。
>
> 规模:后端 **109 路由**;前端 **39 组件 / 约 425 个交互点**(含每个 button/onClick/onChange/图节点/开关)。
>
> 状态图例:
> - ✅ **本轮真包实测**(build 33161003044,带真实数据)
> - △ **仅旧包/仅空态**:之前测过 200 空态,但非本轮、非真实数据 → 必须真包+真数据重测
> - ❌ **完全没测**
> - 🖥️ **后端可能打过,但前端按钮从没真点过**(本轮最大盲区:全走 curl,UI 零点击)

---

## 一、后端 109 路由覆盖

### 1.1 核心入库/检索/问答/产出(本轮重点测过)
| 方法 路径 | 前端入口 | 状态 | 说明 |
|---|---|---|---|
| POST /api/upload | Ingest 选文件/文件夹 | ✅ | 23 格式全测,含 HEIC(修) |
| POST /api/upload_url | Ingest 抓取入库 | △ | 仅旧轮 example.com,本轮没重测 |
| GET /api/job/{id} | Ingest 进度轮询 | ✅ | 多次 |
| GET /api/search | Search/Explore/各处 | ✅ | 大量,FTS 命中验证 |
| GET /api/stats | 全局 | ✅ | |
| POST /api/embed | (后台自动) | ✅ | **测出 8G 空转 bug,已修** |
| POST /api/ask | Ask/Home/Cards/各 chip | ✅ | RAG 8 出处带引用 |
| POST /api/generate | Home/NodeDetail 产PPT/Word/Excel | ✅ | **测出 PPT 空 deck bug,已修** |
| GET /api/download/{f} | 产出物下载 | ✅ | |
| GET /api/preview/{f} | 产出物预览 | ❌ | 没测 |
| GET /api/doc/{id} | Reader 打开文档 | △ | 本轮路径没直测(误用 /api/document) |
| GET /api/doc_summary/{id} | Reader | ❌ | |
| GET /api/similar/{id} | Reader 语义相关 | △ | 旧轮 |
| GET /api/mylibrary | Gallery/Life | ❌ | |
| GET /api/media_structure | Reader 音视频纪要 | ❌ | |

### 1.2 账号/鉴权/支付(本轮基本没测真流程)
| 方法 路径 | 前端入口 | 状态 | 说明 |
|---|---|---|---|
| POST /api/auth/send_code | Auth/Landing 获取验证码 | ❌ | dev_code 云端没返,没跑通注册流 |
| POST /api/auth/phone_register | Auth/Landing 注册 | ❌ | |
| POST /api/auth/phone_login | Auth 验证码登录 | ❌ | |
| POST /api/auth/pwd_login | Auth 密码登录 | ❌ | |
| POST /api/auth/set_password | Settings 保存密码 | ❌ | |
| POST /api/auth/reset_password | Auth 忘记密码 | ❌ | |
| GET /api/auth/me | 全局 | ✅ | 复用 token |
| GET /api/auth/alipay/enabled | Auth | △ | 旧轮(已隐藏支付宝) |
| GET /api/auth/alipay/login_url | Auth 支付宝登录 | ❌ | |
| POST /api/auth/alipay/bind | Auth 绑定 | ❌ | |
| GET /api/auth/profile | Settings | ❌ | |
| POST /api/auth/update_profile | Settings 保存资料 | ❌ | |
| POST /api/avatar | Settings 传头像 | ❌ | |
| GET /api/avatars | StarCloud/Friends | △ | 旧轮空态 |
| GET /api/account | 全局 | △ | 旧轮 |
| GET /api/plans | Settings/Paywall | △ | 旧轮 |
| POST /api/pay/create | Settings/Paywall 支付 | ❌ | 真支付没测 |
| GET /api/pay/query | Paywall 我已支付 | ❌ | |
| GET /api/orders | Paywall | △ | 旧轮 |
| POST /api/orders/delete | Paywall 删订单 | ❌ | |
| GET /api/settings / POST / test | Settings | ✅ | 配 DeepSeek key 通 |

### 1.3 微信/iOS 导入(本轮补测)
| 方法 路径 | 前端入口 | 状态 | 说明 |
|---|---|---|---|
| POST /api/iphone/import | WechatSync 开始导入 | ✅ | 端到端 39/39 会话 |
| GET /api/iphone/status | WechatSync | ✅ | |
| POST /api/wechat/watch | WechatSync 挂载 | ✅ | |
| GET /api/realtime/status | AnalysisStatus/WechatSync | ✅ | |
| POST /api/realtime/toggle | (助手开关) | ❌ | 没测 toggle |
| POST /api/realtime/heartbeat | (助手心跳) | ✅ | 间接 |
| POST /api/wechat/ingest | (handoff消费) | ✅ | 注入哨兵 3s 入库 |
| GET /api/wechat_messages | Reader 加载更早 | ❌ | |
| GET /api/ingest/progress | 全局 | ✅ | |
| POST /api/ingest/status | | ❌ | |
| GET /go/wechat-export | (跳转) | ❌ | |

### 1.4 人脉/关系/雷达/洞察/画像(几乎全靠旧空态,真数据全没测)
| 方法 路径 | 前端入口 | 状态 |
|---|---|---|
| GET /api/relationships | Relationships 重新分析 | △ |
| POST /api/relationships/deepen | (深聊一层) | ❌ |
| POST /api/relationships/delete | 删关系卡 | ❌ |
| POST /api/loops/dismiss | 删待了结 | ❌ |
| POST /api/reach/dismiss | 删该联系 | ❌ |
| GET /api/commitments + dismiss | Radar 承诺雷达 | △/❌ |
| GET /api/matches | Radar 供需撮合 | △ |
| GET /api/cooling | Radar 降温 | △ |
| GET /api/favors | Radar 人情 | △ |
| GET /api/dormant | Radar 沉默线索 | △ |
| GET /api/number_ledger | Radar 数字台账 | △ |
| GET /api/balance | Insights 资产负债 | △ |
| GET /api/panorama | Insights 业务全景 | △ |
| GET /api/checkup | Insights 沟通体检 | △ |
| GET /api/network_portrait | Insights 人脉画像 | △ |
| GET /api/persona | Persona 画像 | △ |
| GET /api/discoveries | DiscoveryBell | △ |
| POST /api/draft_reply | (草拟回复) | ❌ |
| GET /api/group_graph | GroupGraph | ❌ |
| GET /api/relation_timeline | RelationTimeline | ❌ |
| GET /api/rel_path | Relationships 找路径 | ❌ |
| GET /api/rel_graph / entity_links / links / connections | ContactGraph/各图 | ❌ |
| GET /api/graph / starmap | Explore 星图 | △ |
| GET /api/chat_galaxy / chat_topic_galaxy | Explore 星海 | △ |
| GET /api/match/{other} | Friends 匹配报告 | ❌ |
| GET /api/people | Friends/StarCloud | △ |
| POST /api/friend | Friends 加/删好友 | ❌ |
| GET /api/chat_node/{id} | | ❌ |

### 1.5 卡片/报告/冥想/新闻
| 方法 路径 | 前端入口 | 状态 |
|---|---|---|
| POST /api/card | Home/Cards 新建 | ✅(旧轮 CRUD 全流程) |
| GET /api/cards | Cards 列表 | ✅ |
| POST /api/card/{id}/status | Home 标记完成 | ✅ |
| POST /api/card/{id}/edit | Home 编辑 | ✅ |
| DELETE /api/card/{id} | Home 删除 | ✅ |
| GET /api/card/{id}/related | 新建后联想 | △ |
| POST /api/report | ReportPanel 生成 | ❌ |
| GET /api/today | Home | △ |
| GET /api/news | Home 今日新闻 | △ |
| GET /api/lifestory / lifesong | Life 冥想 | ❌ |
| POST /api/song/make + status | Life 生成歌 | ❌ |
| GET /api/music-list / music / tts / theme / genimg / genvid | Gallery/Life 媒体 | ❌ |
| GET /api/mylibrary | Gallery | ❌ |
| GET /api/library | Library | ✅ |

**后端小结**:✅实测 ~28 / △仅旧空态 ~30 / ❌完全没测 ~51。**真实数据下的人脉/雷达/洞察/画像/关系图/冥想/支付/报告,基本是空白。**

---

## 二、前端 39 组件 / ~425 交互点覆盖

**本轮最大盲区:前端按钮我一个都没真点过**(全程 curl 打后端 API,webview UI 零点击)。下表=各组件交互点数,状态一律 🖥️(前端未点),真包出来必须用 CDP 驱动 webview 逐个点。

| 组件 | 交互点 | 关键动作(节选) | 状态 |
|---|---|---|---|
| Home.jsx | 48 | 新建4类卡片/产PPT-Word-Excel/卡片问答/全局问答/今日发现/删对话 | 🖥️ |
| Relationships.jsx | 37 | 重新分析/8种AI chip/找路径/删卡/问TA/见面简报深聊 | 🖥️ |
| Settings.jsx | 28 | 传头像/保存资料/AI厂商/key/测连通/OCR地址/改密码/4种支付 | 🖥️ |
| Auth.jsx | 26 | 验证码/密码/注册/性别星座MBTI/支付宝/忘记密码 | 🖥️ |
| Radar.jsx | 26 | 6个雷达tab/催一下/怎么牵线/开场白/复活/各种排序删除 | 🖥️ |
| Reader.jsx | 15 | 问TA/见面简报/深度分析/产出文档/加载更早/相似展开 | 🖥️ |
| Friends.jsx | 15 | 加/删好友/匹配报告/下载分享/星云列表切换/发现抽屉 | 🖥️ |
| Paywall.jsx | 14 | 年月套餐/支付宝微信/我已支付/删订单/手动打开 | 🖥️ |
| App.jsx | 14 | **11个顶层导航tab**+账户+设置+退出+发现铃 | 🖥️ |
| Landing.jsx | 13 | 下载客户端/登录注册/音乐视频试听 | 🖥️(web) |
| Insights.jsx | 13 | 4个tab/重新生成/标签云问/各联系人点击 | 🖥️ |
| Ingest.jsx | 11 | 选文件夹/文件/抓网址/微信卡/导入来源/Guide | 🖥️ |
| Cards.jsx | 11 | 新建/4类型/保存联想/聊天发送 | 🖥️ |
| NodeDetail.jsx | 9 | 打开阅读/产PPT-Word-Excel/连接跳转 | 🖥️ |
| AskDrawer.jsx | 9 | 快捷按钮/产出文档二级菜单/追问 | 🖥️ |
| Explore.jsx | 43 | 文档/星海/档位/搜索飞向/颜色分组/12项滑杆预设/2D3D/节点点击 | 🖥️ |
| StarCloud.jsx | 8 | 搜好友/核心中圈星尘点选人 | 🖥️ |
| Gallery.jsx | 8 | 唱片/海报点击/播放器/下载 | 🖥️ |
| WechatSync.jsx | 8 | 实时/iPhone tab/开始导入/3平台下载/指南 | 🖥️(部分后端✅) |
| Ask.jsx | 7 | 问答/示例/来源点击 | 🖥️ |
| Life.jsx | 7 | 去配置/导入/生成画像/播放/专辑 | 🖥️ |
| DiscoveryBell.jsx | 8 | 铃铛/清除/问大脑/看聊天 | 🖥️ |
| Library.jsx | 8 | 学科/类型tab/分类/搜索/文档点击 | 🖥️ |
| ContactGraph.jsx | 5 | 机构枢纽/回全景/节点点拖 | 🖥️ |
| GroupGraph.jsx | 5 | 展开关系图/节点 | 🖥️ |
| Onboard.jsx | 5 | 7步引导/下一步/去入库/跳过 | 🖥️ |
| Search.jsx | 3 | 搜索/结果点击 | 🖥️ |
| RelationTimeline.jsx | 3 | 里程碑/翻原文 | 🖥️ |
| Guide.jsx / Help.jsx | 3+3 | 数据源卡/下载/外链 | 🖥️ |
| Persona.jsx | 1 | 重新生成 | 🖥️ |
| Paywall/AnalysisStatus/MoodIcons/ErrorBoundary/ComingSoon/ui/icons | — | 展示/状态类 | — |

---

## 三、下一步:新 DMG 出来后的完整复测计划(按此逐条打勾)

### P0 回归验证(本轮 3 个修复必须端到端确认)
1. HEIC 上传 → 不再 error、OCR 出文字
2. 产出 PPT → 立刻下载就有幻灯片(非空 deck);Word/Excel 同验
3. 嵌入:导入微信后 page_embeddings **持续增长**、机器 load 不飙、语义搜「罗仲平」能命中(不再空转)

### P1 真数据后端(占后端一半的空白)
4. 逐个打 relationships/commitments/matches/cooling/favors/dormant/number_ledger/balance/panorama/checkup/
   network_portrait/persona/discoveries/group_graph/relation_timeline/rel_path/graph/starmap/chat_galaxy —— **带真实微信数据**看真输出(非空态)
5. report/draft_reply/friend/match/deepen/loops.dismiss/reach.dismiss 等写操作

### P2 前端逐按钮(~425 点,CDP 驱动 webview)
6. App 11 个导航 tab 逐个进,不白屏不报错
7. 每组件的每个按钮/开关/下拉/图节点:点了有正确反应(参照上表)
8. 重点全链路:注册→登录→入库→问答→产出→人脉→雷达→洞察→设置→支付

### P3 账号/支付真流程
9. 验证码注册登录 / 密码登录 / 改密码 / 资料头像 / 真支付下单(需云端配合)

> 执行方式待定:P2 的 425 个前端点建议 CDP 自动化 + 关键路径人工验收。
> ★数据隔离(独立测试账号)+ 清真库测试垃圾,仍待用户拍板(见对话)。

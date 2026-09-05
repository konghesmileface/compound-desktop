# 第二大脑桌面客户端 · 全覆盖回归测试用例（交付前 · 细颗粒度）

> 2026-09-06。**逐页拆到每个按钮/输入/下拉/开关/点击/悬浮/拖拽/状态切换/空态/加载态/失败态/边界**。
> 执行时机：当前问题（mac2 大图 OCR 计时、三端最终构建）处理完之后。
> 三端各跑：本机 Mac Intel lite(8G)、mac2 Mac Intel HD(16G)、Windows lite(8G)。★铁律：改完/测完必截图自查，不盲判。
> 每条标 通过/失败（附现象+截图）。用例均对应代码真实元素，非编造。

## 0. 待验证空白区（之前从没测过，重点补）
- [ ] **Apple Silicon（M 芯片）**：客户端仅 x86_64,M 上走 Rosetta,从未验证。免费办法=GitHub macos-15 runner(真 M 芯片)冒烟测 sidecar/入库/OCR(verify-arm64-mac.yml)；GUI 交互 headless 测不了(系统 WebView,风险低)。若 Rosetta 跑不通再出 arm64 原生。
- [ ] **HD 真实微信图 OCR 出结果耗时**：mac2 计时(进行中,已 >50min 未出——若最终出不来,HD 微信图场景定位需重议)。
- [ ] **死代码确认**：Relationships 的 openBrief/deepen/reportContact 当前无 JSX 入口——确认补入口或删除。
- [ ] AI 欠费提示 / 微信助手新向导 / 人脉卡消息数门槛 → 见 §0.5 专项验证

## 0.5 本次交付新增改动 · 专项验证（★必测,这些是本轮改的）

### A. AI 额度 / 欠费提示（llm.py + app.py + AnalysisStatus.jsx）
> 触发方式：设一个**欠费/额度用尽**的 key,或用会返回 402/insufficient 的账号；无欠费账号则临时把 key 改成能连通但欠费的。
- [ ] 主动问答(Home/Ask)欠费 → 回答区提示「**AI 账户余额不足 / 额度已用尽**,请去平台充值」(不再误报"网络失败"或"key无效")
- [ ] key 无效(401)→ 提示「AI key 无效或没有权限」(与欠费区分开)
- [ ] 网络/SSL/超时 → 各自友好文案(不误判成欠费)
- [ ] 后台建卡/情报欠费 → 右下角 AnalysisStatus **红色横幅**「AI 账户余额不足/额度用尽」+ msg + 「充值后会自动继续」
- [ ] 欠费时右下小胶囊变**红色**「AI 余额不足」(不再无限转圈"分析中")
- [ ] 充值/换有效 key 后 → 下一次成功调用 LAST_LLM 清除,横幅/红胶囊**自动消失**恢复正常
- [ ] 三端(本机lite/mac2 HD/Windows)行为一致(llm.py 共用)

### B. 微信助手抓钥匙新向导（wxsync-helper panel.py,三版）
> 三版都测：Windows / Mac Intel / Mac arm64。开助手点「抓取 / 更新密钥」。
- [ ] 顶部**步骤条 ①②③**显示,当前步蓝色高亮脉冲、已完成绿色打勾、未到灰色
- [ ] **大标题 16px** + 说明 14px（字不再小、不再一大段挤）
- [ ] **操作清单**带①②序号卡片(如"退出登录再重登""搜索框搜词点开聊天")
- [ ] Windows 抓取流程：第1步监听→第2步已抓N把(操作清单)→第3步完成绿
- [ ] Mac 抓取流程：第1步准备(临时微信)→第2步弹出登录搜索→第3步完成绿+收尾两步
- [ ] **已有钥匙弹确认**：库里已有钥匙时点抓取 → 弹「检测到已抓过 N 把(长期有效通常无需重抓),确定重新抓取?」；取消=不抓
- [ ] **修跳步**:确认重抓后从**第1步**开始(不再因残留 cand_keys 直接跳第2步)
- [ ] 失败态:红框「这次没抓到钥匙」+ 重试提示
- [ ] 全程遵守禁 emoji(只 ①②③✓ 单色字形)
- [ ] 客户端下载页/内置助手 = 最新向导版(Win 55.8M / Mac Intel 17.7M / arm64 16.8M,今天构建)

### C. 人脉卡"变少"修复 · 消息数门槛（app.py + relationships.py）
> 需要有微信数据的库(mac2 或 Windows 现有 29 会话)。
- [ ] 首次入库后人脉卡数量正常生成(门槛=消息数≥15,非页数)
- [ ] **重新入库同样内容 → 人脉卡数量稳定,不再忽多忽少**(核心:分页波动不再影响)
- [ ] 承诺雷达门槛同步(消息数),重新入库不掉条
- [ ] 群关系图/关系时间线缓存(消息数键)重入库不白重跑 LLM
- [ ] 分析进度百分比稳定(分母=消息数≥15 会话数,不跳)

## 1. 安装 / 启动 / 退出（系统级）
- [ ] Mac：DMG 拖入应用程序，首次启动；Win：setup.exe 全新安装
- [ ] 图标/启动台/开始菜单正常显示（非灰图、可搜到）
- [ ] 启动后 sidecar 自动拉起、/health OK、无需手动干预
- [ ] Windows 首启 ModelDownload：进度环+三模块进度+ETA，下完自动进主界面
- [ ] 重启 app：数据在、不重复入库；退出：sidecar/paddle 进程干净退出无残留
- [ ] 弱网/断网启动：友好提示不白屏
- [ ] 某 tab 组件抛错 → ErrorBoundary 兜底「页面出问题，数据没事」，切页恢复

---
# 一、入库 / 微信 / 状态

## Ingest（入库页）
- [ ] 顶部标题「入库」+ 说明 + 隐私提示条（本地不上传）
- [ ] 空闲态显示「选择要入库的内容」+ 格式副标题；busy 态变「入库进行中…」
- [ ] 点「选择文件夹」→ webkitdirectory 目录选择器（含子文件夹递归）
- [ ] 点「选择文件」→ multiple 文件选择器
- [ ] busy 时「选择文件夹/选择文件/抓取入库」三按钮 disabled
- [ ] 选合法扩展名文件 → 进 uploading，files_total 正确
- [ ] 选全非法扩展名 → toast「没有可入库的文件」不上传
- [ ] 混合文件 → 只保留合法，非法丢弃；扩展名大小写混合仍识别
- [ ] upload 失败 → busy 关，phase=error「上传失败,请重试」
- [ ] 成功 → job_id 写 localStorage 开始轮询
- [ ] 网址框：输入回显；合法 http(s) 点抓取/回车 → ingesting；非链接 → toast「请粘贴 http(s) 链接」；成功清空网址框
- [ ] 网址抓取失败 → phase=error「抓取失败,请检查链接」
- [ ] 进度卡：current_file/阶段中文映射（上传中/排队中/识别中/语义嵌入/出错）；未知 phase 显原值
- [ ] 主进度条=file_index/files_total；files_total=0 不 NaN
- [ ] ingesting 且 page_total>0 显子进度条；embedded_pages>0 显「已嵌入 N 页」
- [ ] job.error → 红色显示；_stalled>3 → 软安抚「已自动重连…不用重传」
- [ ] 轮询 800ms；done/error 停轮询清 JOB_KEY；404(非resumed) → 友好提示去文库看；404(resumed) → toast「上次任务已结束」
- [ ] 网络抖动 → fails++ 不报错，恢复后 fails 归零；组件卸载 clearInterval
- [ ] 刷新页面有 JOB_KEY → 自动 resumed 恢复轮询
- [ ] autosync：挂载拉列表 + 8s 轮询；失败静默
- [ ] 点「+ 添加文件夹」非 Tauri → toast「需在桌面客户端用」；Tauri → invoke pick_folder
- [ ] pick_folder 抛错 → toast「打开选择器失败」；取消 → 静默
- [ ] 添加成功 → toast「已加入定期同步」刷新列表；失败 → toast「添加失败:X」
- [ ] busy 时「+添加文件夹」disabled
- [ ] 列表项：路径(title)+「已同步 N 个」；exists=false 显「⚠文件夹已不存在」；last_scan 有则显时间
- [ ] 点某项「✕」→ autosyncRemove 后刷新（该项消失）；失败静默
- [ ] 数据源卡网格：只渲染 tile≠false；点卡 → 打开对应 Guide；关 Guide 清 guideKey

## WechatSync（微信同步中枢）
- [ ] 标题「微信数据·同步中枢」+ 两 Tab「实时同步/iPhone 导入历史」，默认 live
- [ ] 点两 Tab 切换并高亮；iOS 跑起来自动切 ios Tab + 小红点；完成后红点消失
- [ ] live 徽章按 mode：检测中/导入历史 N%/实时同步中/等待客户端
- [ ] ios 徽章：导入完成(绿)/导入中/未在导入
- [ ] 神经流 canvas：live 粒子流入+脉冲；detect 雷达扫描；waiting 琥珀粒子过不了桥；off 熄灭
- [ ] 新消息 burstKey 变 → 爆发一簇粒子；容器 resize 重绘不变形；卸载清理无泄漏
- [ ] 状态文案随 mode 变（检测/导入N%/实时接收+last_synced+pending N条/通道就绪等待）
- [ ] mode≠live 显「助手还没开?看怎么启动→」点击 onGuide('realtime')
- [ ] 实时入库列表：active 行名+进度条+状态中文；进度=percent优先→STATE_PCT→0；failed 加 fail 样式；recentDone 最多6条「已入库」
- [ ] 下载助手区：三下载按钮（Win/Mac Intel/Mac Apple）；Tauri 保存到下载夹并高亮，网页走 href
- [ ] 四步操作说明，第3步「抓取/更新密钥」高亮 mark「不做这步会同步到空!」
- [ ] iPhone 空闲：手机图标+说明；Windows 显黄警告「仅支持 Mac」
- [ ] iosEnv 检测：检测中/未装工具/已连接+电量%/请连线；电量<60 黄警告
- [ ] 未连手机 →「开始导入」disabled；iosStarting 显「正在启动…」防连点
- [ ] 点开始导入 → toast「开始导入,保持解锁别拔线」；400 → toast「未装 libimobiledevice」；其它 → toast「启动失败」
- [ ] iPhone 进行/完成/失败态：标题变化、百分比、五段管线（连接手机/备份/解析/识别/写入，按 pct 分界高亮）
- [ ] 失败态诊断文案 +「继续导入(断点续传)」（未连显「请先连 iPhone」disabled）
- [ ] 未完成会话列表（最多4条）；完成显「历史已进大脑,可搜索/提问/生成人脉卡」
- [ ] 挂载 wechatWatch 启动消费；4s 轮询三接口；失败静默；卸载 clearInterval

## Guide（数据源分步引导弹窗）
- [ ] 非法 sourceKey 返回 null；合法 → overlay+弹窗
- [ ] 点遮罩/✕ 关闭；点内容 stopPropagation 不关
- [ ] badge(色)+标题；reassure chip / intro / dl 单下载 / dls 多下载 / steps 带序号 / payoff / faq / tip / help 各按字段有无渲染
- [ ] realtime/ios/email/web 四源内容正确（步数、下载按钮、FAQ 条数）
- [ ] syncHref 中文文件名正确编码；Tauri 下载 toast「已保存到下载文件夹」，失败回落 openExternal

## AnalysisStatus（右下角状态胶囊）
- [ ] 无活动+未分析+无欠费 → 不显示；有任一 → 显示
- [ ] 5s 轮询三接口；失败静默；卸载 clearInterval
- [ ] 收起小胶囊：点击展开；文案优先级 欠费>活动>「分析中N%」；欠费红、活动配色、纯分析紫
- [ ] 活动汇总：iOS导入(青)/文件入库(紫)/微信实时(绿,pending>0)；>120s 不新鲜不计入
- [ ] 展开卡：标题+orb+「—」收起；活动列表带进度条(仅iOS有pct)
- [ ] ★**llm_error 红色横幅**（欠费/key无效）：标题+msg+「充值/改key后自动继续」
- [ ] ★欠费时小胶囊变红「AI 余额不足」；改好后自动消失
- [ ] 深挖分析层：每层 label+进度条；pct≥100 打勾；needs_key 显「需配 AI key」黄提示；当前层显 hint
- [ ] st.done → 不渲染分析区

## ModelDownload（首启模型下载）
- [ ] 1.5s 轮询 modelStatus；done 后 1.2s 进主界面；卸载停轮询
- [ ] 进度环按 overall%；中心显整数%（小数四舍五入、缺失显0）
- [ ] 星云 canvas + 90 星尘；resize 重设；卸载清理
- [ ] 文案：标题+「约3.4G」+ ETA/速度（eta 空显「正在连接模型源…」）
- [ ] 三模块（语义2.3G/语音0.9G/说话人0.2G）：图标+名+解锁功能+进度条；done「✓就绪」/active「N%·size」/wait「0%」；缺 key 回落 wait 不崩

---
# 二、人脉 / 雷达 / 发现

## Relationships（人脉卡列表）★消息数门槛修复重点回归
- [ ] cards=null → Thinking 三段；err → 空态「还没有人脉卡」；空数组 → 空态引导入库
- [ ] 标题统计「N 个人·M 件事·K 笔人情」数字准确
- [ ] 点「重新分析」→ spin+「分析中…」disabled；成功刷新；进行中再点无效
- [ ] ★**人脉卡数量正确、重新入库同内容卡数稳定**（消息数门槛，不受分页波动）
- [ ] 「等你了结的事」：空则不渲染；默认近一月；「查看全部N件/只看近一月」切换；按新→旧、无日期沉底
- [ ] 点待了结条(有doc_id)→ onOpen；「✕」删除 stopPropagation+本地隐藏+dismissLoop
- [ ] loopDate 解析「2026年7月10日/2026-07-10/2026.7.10/2026/7/10」，无日期返 null
- [ ] 「该联系了」：days_ago≥14 未隐藏，降序最多8；点条 → onAsk 开场白；「✕」dismissReach；边界 13 天不出现
- [ ] 8 个问答 chip 逐个点 → onAsk 带对应 prompt（逐条核对）
- [ ] 人脉关系网折叠：edge_count=0 不渲染；点标题展开/收起；枢纽最多6；最强关联最多10
- [ ] 关系路径：A/B 下拉；未选 disabled；A=B return；找到显链条+why；未找到「没有关联路径」；失败同空
- [ ] 搜索框：实时过滤(contact/identity/facts/loops)；「✕」清除
- [ ] kind 三段(全部/对话/群聊)互斥；sort 四段(最近/未了结/最多/名字)互斥；组合筛选正确
- [ ] 瀑布流列数 ResizeObserver 1–4 自适应
- [ ] 卡片：「×」删除弹 confirmDialog 含「同步删聊天」checkbox；取消不删；确认动画520ms后消失+toast+deleteRelCard(false/true)；失败仍本地删
- [ ] 点卡头(有doc_id)→onOpen；头像首字符/「?」；deep 徽章；msgcount；identity/traits/tags(最多6)缺则不渲染
- [ ] 点 tag → onAsk「和「tag」有关的人」；open_loops/favors/facts 各最多3条
- [ ] 底部 spark → onAskContact(contact,undefined,is_group)；chat 图标(doc_id有)→onOpen

## ContactGraph（人脉关系网星图）
- [ ] null+无缓存 → loading；失败 → 空态；_graphCache 复用不重复请求；首次成功写缓存
- [ ] entN=0「机构枢纽」按钮不渲染；点切换 showEnt → 菱形机构节点+连线 显/隐；重算力导
- [ ] 「回到全景」→ zoomToFit；fgRef 未就绪不报错
- [ ] 机构菱形(暖金)/人圆(社区色)；半径按 degree；节点呼吸漂移
- [ ] 悬停 → 该点+邻居 alpha=1 其余淡化+辉光+标签；移出恢复
- [ ] 标签条件：scale>1.9 全显 / >0.85 大枢纽显 / 悬停显；机构名截9人名截10
- [ ] 拖拽节点跟随；滚轮缩放；平移禁用；孤立点钉外环
- [ ] 点人节点(doc_id有)→onOpen；机构/无doc_id 不触发
- [ ] 6.5s 定时+onEngineStop zoomToFit；向心力半径470约束；document.hidden 暂停重绘；resize 适配；value≥2 人边流动粒子

## GroupGraph（群关系图）
- [ ] 空/found=false「没解析出成员关系」；members 空「活跃人太少」；mine+pairs 空「没抽出关系」
- [ ] 清单：头「群里N人」；edges 空则无「展开关系图」
- [ ] 「你和谁最熟」(mine 有me才算)按 closeness 高中低排；Badge色+名+role+why
- [ ] 「成员之间」pairs 按 closeness；图例三色
- [ ] 点「展开关系图」→ portal 浮层；遮罩/✕ 关；内部 stopPropagation
- [ ] 浮层力导：只画有连线或「我」；「我」钉中心金色+白环；成员哈希配色；半径按degree；NaN 跳过
- [ ] 悬停高亮邻居；边色/宽/曲率按 closeness；流动粒子(高3中2低0)；tooltip role；边label「熟络度X:why」
- [ ] 拖拽/缩放；onEngineStop zoomToFit；resize；重开重初始化

## RelationTimeline（关系时间线）
- [ ] 空/found=false / months 空 → 各空态
- [ ] 头：phase pill + trajectory（各按有无）
- [ ] 柱状图：高按 sqrt(count)；金色段=mine/count；count=0 无金色；maxc≥1 不除零
- [ ] 悬停柱 title「ym:共N(我x/TA y)」；年份分隔线+标签不重复
- [ ] 里程碑：空则无；虚线+编号圆点；xOfYm 精确/就近/兜底最后；点圆点(doc_id有)→onOpen
- [ ] 下方里程碑列表 编号/date/label；onOpen 有则可点
- [ ] 图例；「翻聊天原文→」(onOpen+docId 有才显)

## Radar（雷达 6 tab）★消息数门槛回归
- [ ] 6 tab(承诺/供需/降温/人情/沉默/台账)互斥；首次进各自懒加载；已加载不重复；各失败置空不白屏
- [ ] localStorage radarHidden 恢复/持久(最多800)；hide 后消失刷新仍隐藏；写异常吞掉
- [ ] 承诺：全空「还没有承诺记录」；overdue 红条；两列「我欠/等对方」计数；stale(逾期60天)折叠
- [ ] dueLabel：逾期/今天/N天后 颜色正确；点条(doc_id)→onOpen；「✕」await dismiss 成功再本地删，失败 toast 保留
- [ ] 「等对方」+onAsk「催一下」；stale 展开/收起
- [ ] 供需：头 supply×demand 计数；空「没找到撮合机会」；每条 confidence+供/需/why；「✕」hide；「怎么牵线」onAsk
- [ ] 台账：空态；每人块头(doc_id可点)；表格 item/value/date/context
- [ ] 降温：空态；near/far 排序互斥；level 严重红；点条/✕/开场白 onAsk
- [ ] 人情：空态；三排序(多/近/远)；每卡 favors+天数+warm_topics chip；✕ hide
- [ ] 沉默：空态；两排序；每条 silent_days+leads；✕ hide；「复活」onAsk

## DiscoveryBell（主动发现）
- [ ] 挂载拉取+60s 轮询；卸载清定时；失败静默
- [ ] badge=unseen；>0 红点数字；>99「99+」；=0 无
- [ ] 去重：同人同type留一条；dismissed 排除
- [ ] 点铃铛开抽屉+1.2s markAllSeen 清零；portal；遮罩/✕关；内部不关
- [ ] feed 空「暂时没有要提醒的事」；有则「全部清除」→ 全 dismiss 清空
- [ ] 每条：type 标签色(reply红/commitment橙/cooling紫/未知兜底)；urgency class；未seen fresh 高亮
- [ ] d.ask →「问大脑」关抽屉+onAsk；d.doc_id →「看聊天」关抽屉+onOpen；「✕」dismissOne
- [ ] 持久化 seen(300)/dismissed(500)；损坏JSON catch 空Set；已dismiss不再出现

## NodeDetail（节点详情）
- [ ] docId=null 返回 null；切换重置+并发拉4接口；alive 守卫防竞态；遮罩/✕关，内部不关
- [ ] 文档节点：扩展名→badge(pdf/docx/pptx/xlsx/md/txt/html/csv/eml/epub…)；未知兜底「文件」
- [ ] 摘要：未到「AI正在读」；error「摘要不可用」；正常显示+topics chip
- [ ] 聊天节点：badge绿「联系人」；卡+intel 都空「后台生成中」；identity/summary/traits/loops/commits(我/TA+due)/facts/nums/favors/landmines/warm_topics/dynamics 各按有无
- [ ] 主动发现连接：loading Thinking；空/error；每条 insight+↳文件 点→onOpenNode；spark「灵感」
- [ ] 相关文档：空不渲染；最多6，score%；点→onOpenNode
- [ ] 「打开阅读」→onOpenReader；PPT/Word/Excel 生成：busy disabled+「深度撰写中」；成功「⬇下载」openExternal；失败提示；扩展名 word→docx/excel→xlsx/其它pptx

---
# 三、问答 / 探索 / 冥想 / 文库

## Home（首页问答）
- [ ] 底部问答框：输入回显；Enter 提交清空+loading；Shift+Enter 换行；空/空格拦截；点「问」同回车；gloading 防重复
- [ ] loading「正在通读知识库…」；成功 renderRich；失败(>8字)显原文，否则「AI调用失败,检查模型/key」
- [ ] 提交后平滑滚到底；追问带最近3轮上下文；线程 localStorage 按账号持久(40条)；切账号看自己线程
- [ ] 线程头「N条」；「清空对话」清空+localStorage；「全屏」portal+expanded+「收起」；全屏底部独立追问框
- [ ] 单条「删除这条」×；回答带 sources「参考来源」(最多6)；点来源→onOpen({id,page})；分数(档案/min99%)
- [ ] GenBar：PPT/Word/Excel 生成 busy disabled+spinner+「深度模型1-2分钟」；成功「下载《标题》.ext」openExternal；失败 toast
- [ ] PPT 4 主题 theme-dot 切换传 gen(fmt,theme)；有 preview → iframe 预览模态(遮罩/×关,内部不关)
- [ ] 「新建目标/日记」卡 → compose 模态(色条/tip)；遮罩/×关，内部不关
- [ ] 目标表单：textarea 聚焦+期限date+为什么input；日记：今日日期+7心情chip(点选/取消,--mood-c色)
- [ ] 空内容保存 → toast「写点内容」；有内容→「保存中…」disabled+成功toast+关闭+刷新；失败 toast
- [ ] 卡片列表：类型徽标/标题/meta/心情脸；未读红点；完成「✓」done样式
- [ ] 删除×弹「确定删除?」；取消不删；确定 deleteCard+关详情+刷新+toast；stopPropagation 不打开
- [ ] 卡详情：loading Thinking；失败「加载失败」+重试；「←返回」；目标「✓标记完成」/「↩恢复进行」toast；「✎编辑」textarea(空拦截)+保存/取消
- [ ] related 有→「知识库里有」rel-card(文件/页/相关%/片段)点→onOpen；空「没找到相关」
- [ ] 卡内问答：回车/Shift+Enter/发送；空/loading拦截；anchor+历史；成功带sources；失败「AI调用失败」；【来源N】→onOpen
- [ ] 今日新闻：有items→「今日新闻·域」；fmtNewsDate(ISO/兜底/空)；点卡 preventDefault+openExternal；无items不渲染
- [ ] 今日发现：null→Thinking；20s兜底置空；空态；有action clickable→askDirect+amodal
- [ ] 链接发现：相似%/标签/跨月跨天；点主体→askDirect；点link-doc→onOpen(a/b)；explain 有(why/get/do)/无(pending轮询8s×15)
- [ ] 实体发现：去重同名；etype/entity/N份/why；点名→askDirect；docs点→onOpen；count>docs 显「共N份」
- [ ] amodal：loading不关；非loading遮罩关；×关；内部不关；成功renderRich+来源+GenBar；rel_ask 自动跑一次

## Ask（独立问答空态）
- [ ] 空态标题+聚焦输入框+placeholder；回车/Shift+Enter/发送；空/loading拦截；4示例卡点→send
- [ ] 发送清空+进对话；loading「翻知识库中」；成功气泡「第二大脑」+renderAnswer；失败「AI调用失败,检查模型/key」
- [ ] sources「参考来源·来自知识库」(最多6)点→onOpen；底部「继续追问」框；带完整历史；自动滚底
- [ ] renderAnswer markdown 表格/#标题/列表/引用/---；renderInline **加粗**/`代码`/【来源N】角标(tooltip)

## AskDrawer（追问抽屉）
- [ ] ×/onClose 关；头「第二大脑·群X/与X」；isGroup 判定(@chatroom/@openim/含群)
- [ ] query 自动run；initialAction=产出文档→展docMenu / 深度分析→跑QUICK / 熟络度→runGraph / 时间线→runTimeline
- [ ] 1:1 chip(见面简报/深度分析/关系走势/产出文档/还有什么跟进)；群 chip(群成员画像/熟络度/群在聊什么/产出文档)；无contact不显chip
- [ ] 点chip→run对应prompt；点「产出文档」展/收docMenu(▾/▴)；runGraph→内联GroupGraph(失败{found:false})；runTimeline→内联RelationTimeline
- [ ] docMenu(群8/1:1 7项)点类型→收起+run；「自定义…」预填+聚焦
- [ ] 底部框回车(非空)run+清空；空不提交；「问」按钮(空disabled)
- [ ] run 带 contact+历史；loading Thinking；成功renderRich+来源chip(过滤空doc_id,最多6,清洗名)；失败(>8)原文,否则「换句话再试」
- [ ] turn 问题去 **/# 前缀；turns 变自动滚底；【来源N】内联去掉(底部chip给出处)

## Search（全库搜索）
- [ ] 输入框聚焦+placeholder；回车 preventDefault+run；空拦截；loading spinner
- [ ] hits=null 不渲染；有结果「N条命中」+卡；0结果空态「换关键词」；异常置空不崩
- [ ] 卡「文件·第N页」+高亮；「」转<mark>；点卡→onOpen

## Explore（3D 星系图）★最复杂
- [ ] loading spinner；空态；标题栏节点数+连线/主题数
- [ ] 点「文档/星海」切模式(先清data防错帧)；星海显档位(粗中细)切换重载(chunk 42/14/5)
- [ ] 搜索命中高亮+flyTo；无命中/失败 toast；清空取消高亮；偏好 localStorage 持久
- [ ] 颜色组面板：展开/收起(handle显前4色)；「语义簇/文件类型」切colorBy；组列表色块/名/数降序；非聊天点组 toggleHidden(节点+连线隐藏)；聊天点组 topicFocus 钻入
- [ ] 调节面板(星海非聊天)：辉光/节点/散开(reheat)/连距 滑杆即时生效；3D/2D 切dims；切预设重置调节值
- [ ] 10 预设点击切换；星云/极光 shader 增删dispose；core/scatter/disk 布局；预设不爆闪白
- [ ] 3D 星海：拖拽旋转/滚轮缩放/进出图暂停恢复autoRotate；中细档自转；悬停tooltip；点节点onOpen(不可拖)；分帧呼吸;document.hidden跳帧
- [ ] 文档 2D：中央「脑」枢纽+类型中枢+文件图标；悬停高亮邻居；点节点飞入+涟漪+onOpen；点分类只聚焦；点脑/空白clearFocus；可拖；搜索高亮走粒子
- [ ] 仅聊天主题星系：点「仅聊天」切换(on)；隐藏文档/星海/档位段；全景钉住+自转；簇心飘主题名+底光呼吸；悬停点亮该簇；点星→onOpen；点主题/空白 focusCluster 钻入(可拖)/复位；右侧组列表钻簇；无数据不崩

## StarCloud（人脉星云）
- [ ] 头像加载成功显示/失败首字母兜底；people 空不崩
- [ ] 三层(核心≤3/中圈≤30/星尘)；核心头像+气泡(名/compat%/MBTI)左右朝向；中圈头像+名；星尘光点
- [ ] 最高compat「命定星」标签；唯一loveKey 粉线；并列最高只认一颗
- [ ] 点节点→onSelect；星尘title；搜索匹配(display/one_liner/mbti/tags)高亮+淡化；清除×
- [ ] rAF 公转+漂浮；粉线每帧更新；「你」居中偏下；70微星背景；聚类配色

## Life（冥想/音乐）
- [ ] 打开写 life_seen+派发事件；加载资格(key/文档/画像)
- [ ] err→空态；无key/无数据/无画像 分别 todo+对应按钮 onGoto(settings/ingest/persona)；三步齐→「谱第一首」
- [ ] 符合+无歌+未first_done 自动谱；手动 makeSong 缺条件跳转；成功 GeneratingLife
- [ ] pollMake done→写first_done+刷库+toast《X》；error toast；idle 停不转圈；5s轮询;402会员墙接管
- [ ] 云同步 syncing 2s刷；无歌「从云同步 done/total」；lifestory 轮询(<90次)
- [ ] 播放器：播放/暂停(唱片转)；换歌重置；时长/进度;拖seek;下载openExternal;环形频谱;歌词高亮滚动/无歌词提示
- [ ] 专辑架(>1首)：vinyl卡点切换spinning换歌；稳定hue；同步中头显进度
- [ ] 卸载清所有timer

## Library（文库）
- [ ] loading Thinking；失败空lib不崩；空「文库空的」；有「N份,自动归类」；reloadKey 重载
- [ ] 搜索(文件名/学科)+×清除；「学科/类型」切by+sel重置；「全部」显所有；点分类高亮only显该类；类型模式色点
- [ ] 文档卡：文件名clamp+title/类型tag色/页数/topic(非未分类)；点→onOpen；0文档「没有匹配」

## Reader（阅读器）
- [ ] meta未到spinner；×onClose；docId变重置重载
- [ ] 普通文档头(文件名/N页/backend/时间)；分页每页(无文本「本页无文本」)；bookish reflow；media renderTranscript
- [ ] pages<total「加载更多(还N页)」loading disabled；targetPage 回溯滚动+高亮1.8s+未加载则续加载
- [ ] 相似文档空不显；有「语义相关N篇」展/收(最多8)点→onOpen+分数%
- [ ] 微信视图：头「与X聊天·N条·最近最上」；contact解析；群判定；加载消息300条；气泡我右对方左带名;日期分割线;占位符chip;图片URL→img
- [ ] wxMsgs<total「加载更早」loading disabled；失败置空不崩；快捷chip(问TA/见面简报/深度分析/产出文档)→onClose+onAskContact(有群标记)；无onAskContact回退onAsk
- [ ] asr纪要：loading Thinking；章节/待办决议/脑图；空section不渲染；reportOpen→ReportPanel

## Gallery（作品集）
- [ ] 失败/加载中/全空：嵌入返null，独立显空态/spinner
- [ ] 有songs「我的专辑」vinyl；有films「我的故事集」海报；vinyl点→Player(song)spinning；poster点→Player(film)
- [ ] Player song：黑胶转+audio autoPlay+歌词([标签]vs内容)；「下载MP3」openExternal
- [ ] Player film：video autoPlay playsInline；遮罩/×/Esc关；内部不关；autoPlay 打断rejection吞掉

---
# 四、设置 / 账号 / 画像 / 好友 / 说明 / 导航

## Settings（设置/账户）
- [ ] 点头像→文件选择器；上传裁256×256+toast「头像已更新」+派发avatar-updated(rail同步);失败toast;未选早返回;空显默认人形
- [ ] 昵称≤16;空保存 toast「昵称不能为空」;性别三按钮互斥;年龄只数字≤3位;星座/MBTI 下拉;自我介绍≤200
- [ ] 手机号有值显/无「—」;「保存资料」成功onNick+toast;中「保存中…」disabled;失败toast;进页getProfile回填(失败回落localStorage)
- [ ] 「退出登录」→onLogout
- [ ] 密码：原/新/确认三框掩码;新<8「至少8位」;score<2「太弱」;不一致「不一致」;合法→setPassword成功toast+清空;原密码错「原密码不对」;其它「修改失败」
- [ ] 强度条4段按score+配色;空不显;弱口令score0;纯数字/字母封顶1;三连重复扣分;要求清单(8位/两类/12位)✓/○;确认「✓一致」/「✕不一致」
- [ ] AI厂商11家卡片;点切换重置质量/快模型默认+hint;key框掩码(占位随厂商,Ollama「无需key」);已存显「当前:掩码」
- [ ] 质量/快模型 ModelCombo:点击展开候选(去重model+fast+alts);选回填收起`on`;手输自由;▾三角旋转;点外部收起
- [ ] 接口地址/OCR地址框(可留空);质量/快模型空保存报红;填全保存→清key框+「验证中」;测通绿✓/无效红/异常绿(未验证);saveSettings失败红
- [ ] 「测试连通」→「测试中…」disabled;通绿/不通红/异常红
- [ ] section=settings 只AI卡;=account 只资料/会员/安全

## Auth（登录/注册）
- [ ] 手机号只数字≤11+autoFocus;非法获取码 toast;合法发码60s倒计时disabled;dev返回码明文toast;429/失败 toast;码框≤6数字+回车提交
- [ ] 验证码登录tab:码<4「请输验证码」;正确直登toast「已登录」+onAuthed;错「验证码错误或过期」;中disabled
- [ ] 密码登录tab:密码框回车;空「请输密码」;错400「手机号或密码不对」;成功toast+onClose;「忘记密码」切forgot
- [ ] 重置:码<4/新密<6 拦截;成功toast「已重置并登录」;错「验证码错误」;按钮「重置密码并登录」
- [ ] 注册tab:昵称≤16空拦截;码<4拦截;性别男/女互斥;年龄数字≤3;星座/MBTI选填;介绍≤200;成功toast(registerOnly走onRegistered);失败「可能已注册」
- [ ] 支付宝按钮 false 短路不显;gate全屏门(Logo+品牌+Form无关闭);弹窗遮罩/×关内部不关
- [ ] AlipayBindModal:手机号/码校验;绑定成功toast「已登录」;400「验证码不对」;其它「绑定失败」

## Onboard（首次引导）
- [ ] 第1步欢迎+图标;「下一步」前进+进度点高亮;第2步「去入库」→onGoto('ingest')+onDone;第3步无副按钮
- [ ] 末步「开始使用」→onDone;「跳过引导」任意步onDone;3进度点;每步色相不同

## Paywall（付费墙/订阅/会员）
- [ ] 套餐默认年度「超值」;点月度切换;价格年199/月29(后端覆盖);支付方式(both才显)微信/支付宝切换主按钮变
- [ ] 「立即开通」→「正在发起…」disabled+payCreate;支付宝open_external+paying轮询3s;微信显二维码;Tauri invoke open_external;402静默;其它toast
- [ ] paying:微信二维码(失败「生成失败」);支付宝「已打开付款页」;「等待到账…」;查到paid→toast「开通成功」+onPaid;「我已完成支付」查询;「重新选择」回choose;卸载clear轮询
- [ ] PaywallModal:expired硬墙不可关;非expired可关(×/遮罩);关闭动画230ms;PERKS 4条
- [ ] TrialBanner:非trial不显;>2天「还剩N天」;≤2天urgent「快到期」;点→onUpgrade
- [ ] MembershipSection:加载中;paid「会员有效」+到期+续费;trial「试用中剩N天」+开通;expired「已过期」;点开通展SubscribeFlow;订单列表(状态/subject/¥/日期);pending可删;已付费删toast「不能删除」

## Persona（画像）
- [ ] 无数据+busy Thinking;空态引导入库;失败静默
- [ ] one_liner;tags有则chip;「重新生成」→「重画中…」disabled;成功/失败toast
- [ ] 职业人脉圈/知识领域(配色+weight条)/思维风格(双向刻度Gauge0-100钳制)/在意什么/正好奇 各按有无渲染;底部统计「X文档+Y卡片(+Z微信)」

## Insights（洞察 4 tab）
- [ ] 默认联系人画像;4tab切换懒加载不重复
- [ ] 画像:loading;统计卡(联系人/已画像);「重新生成」porInflight去重;ContactGraph点→onOpen;narrative markdown;分组(有doc_id可点);标签云(机构/业务/地域前30,字号按人数)点→onAsk;空态;entity_ready=false提示
- [ ] 资产负债表:「近N天vs上期」;升温/降温/流失/新拓组点→onOpen;精力条形图(归一最小4%)点→onOpen;全空空态
- [ ] 业务全景:topics空态;主题+etype+N人+chip;「理一遍」onAsk
- [ ] 沟通体检:5统计overview;对方在等/你冷落/你在追/TA在追组点→onOpen;全空「状况良好」

## Cards（卡片）
- [ ] 列表loading/空/失败;项色点+标题+类型;点选中+cardRelated+退compose;「+新建」清空
- [ ] 类型分段(目标/日记/笔记/任务)+占位变;标题可空;内容空保存早返回;保存成功重置+reload+打开新卡;失败alert
- [ ] 详情:未选空态;cd-content;相关卡(文件/页/相关%/片段)点→onOpen;空不渲染
- [ ] 卡内问答:回车/Shift换行;空/loading拦截;anchor+来源chip(最多5)点→onOpen;失败「AI调用失败」;自动滚底

## Friends（好友/匹配）
- [ ] 未登录「请先登录」;loading Thinking;401 need;其它错空列表不误报;无好友空态+「去添加」;星云/列表切换;WebGL失败ErrorBoundary;resize更新
- [ ] 请求条(reqs>0)+30s轮询;「同意」confirmDialog+friendRespond+toast+reload;「拒绝」直接;失败toast
- [ ] 添加抽屉:搜索(display/one_liner/tags/username);合法手机号不在列表显发送行;无结果空态+清空;每行头像/昵称/MBTI标注/契合%色/一句话
- [ ] 点「+添加」→addFriend「…」;成功(需同意/已好友/自动互加/404未注册/其它失败)各toast;Esc/遮罩关内部不关
- [ ] 列表卡:契合环(conic按compat)+昵称+MBTI+一句话+前3标签;点→MatchReport;删除×stopPropagation+confirmDialog+toast
- [ ] MatchReport:loading;失败;needs_persona引导;正常(双头像+契合%+headline+gap_insight/原型/阴影/雷达图/姻缘/建议各字段);「下载图片分享」html2canvas(onclone修渐变字);关闭

## Help（说明手册）
- [ ] 主线三步(下载/抓密钥/导历史)+耗时;步骤1 SYNC_DL全平台按钮→openExternal;步骤3「iPhone图文」→Guide(ios)
- [ ] 「其他数据导入」网格SOURCES点→Guide;状态徽章4种含义;「每页干什么」10功能说明;关键设置3份(AI/OCR/账号);底部「搞不定帮接」;Guide关闭清key

## App（主导航/全局）
- [ ] 首启模型门:检测中null/未ready显ModelDownload/done进app/异常兜底ready
- [ ] 未登录Landing(+onboard叠加);登录saveAuth进主界面;localStorage恢复
- [ ] 11 tab(问答/探索/画像/人脉/雷达/洞察/好友/冥想/文库/入库/说明)逐个点切换+唯一高亮+图标标签
- [ ] 问答unread角标(>99「99+」/=0无);好友friendReqs角标;冥想新歌nav-dot(打开清除写life_seen);45s/30s/60s轮询
- [ ] 左下用户按钮(头像)→account高亮;齿轮→settings;「退出登录」confirmDialog+saveAuth+toast;改昵称onNick刷新
- [ ] 登录拉account expired弹墙;监听402弹墙(付款后12s忽略滞后402);墙开3s复查变paid关墙+toast;focus复查;试用TrialBanner
- [ ] 支付宝回跳:alipay_token直登/alipay_bind弹绑定/alipay_err toast
- [ ] NodeDetail/AskDrawer(initialAction/isGroup)/Reader({id,page}或id) 打开+关闭清状态;登录即wechatWatch;ErrorBoundary(key=tab);UIHost/UpdateBanner/AnalysisStatus常驻

---
## 执行记录
| 平台 | 日期 | 通过 | 失败 | 备注 |
|---|---|---|---|---|
| 本机 Mac Intel lite 8G | | | | |
| mac2 Mac Intel HD 16G | | | | |
| Windows lite 8G | | | | |
| Apple Silicon（待借机）| | | | 从未测过 |

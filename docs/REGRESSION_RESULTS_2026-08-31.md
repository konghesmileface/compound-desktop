# 回归测试执行结果 2026-08-31(按 REGRESSION_CASES_2026-08-30.md 逐条走)

> 测试账号:qaflow0831(干净空号,不碰本人号 18201972547)。sidecar=本机客户端。
> 记法:每条 case 记 步骤/预期/实际/验证点 → ✅PASS / ❌FAIL / ⛔BLOCKED(原因) / ⚠部分。
> 方法:API 层直调 sidecar 走真流程 + 前端 Chrome+CDP 驱动 UI 交互;数据丰富态在本人号只读参照。

## 环境
- sidecar 端口:见 /tmp/wf_port.txt(随客户端启动变)
- 全局 LLM:deepseek-chat(实测连通 ok)
- 可生成格式:txt/md/csv/json/html/docx/xlsx/png/jpg/webp/bmp/gif/pdf(图片版)/eml/mbox
- ⛔本机无法生成:pptx(无python-pptx)/epub-mobi-azw3(无转换器)/音频有语音(无TTS+需SenseVoice)/视频(无ffmpeg+模型)——这些标 BLOCKED 并说明

---

## TAB1 入库(账号 qaflow0831,doc 195-210)

### 1.1/1.2 选文件/文件夹入库 ✅
- 多文件一次上传→job 轮询→全部入库,文库可见。job 接口字段=phase/file_index/files_total/results。

### 1.3 多格式逐一(15 格式)——逐格式验 method+正文
| 格式 | method | 结果 |
|---|---|---|
| txt/md | (文本) | ✅ 正文对 |
| csv | csv | ✅ 表格转文本对 |
| json | json | ✅ 值提取对 |
| html | html | ✅ 标题+正文对 |
| **eml** | email | ❌ **正文中文乱码**(头部对,正文 UTF-8 变 `������`) |
| **mbox** | email | ❌ **同上,正文中文乱码** |
| docx | docx | ✅ 段落提取对 |
| xlsx | xlsx | ✅ 单元格转文本对 |
| png/jpg/webp/bmp/gif | ocr:rapidocr | ✅ 全部 OCR 正确(89字) |
| pdf(图片版) | (OCR) | ✅ 入库 ok(doc209) |
| pptx / epub/mobi/azw3 | — | ⛔ BLOCKED 本机无生成工具 |
| 音频(带语音)/ 视频 | — | ⛔ BLOCKED 无TTS/ffmpeg/SenseVoice |

> ❌ **BUG-1(真)**:eml/mbox 无 charset 声明时正文中文按非UTF-8解码→乱码。健壮性缺陷,应 UTF-8 兜底。

### 1.4 URL 抓取 + SSRF ✅
- 普通 URL(example.com)→ 入库 ok(doc210)。
- SSRF:内网 `http://127.0.0.1:8000/admin` → job 内拒绝「不允许抓取内网/本地地址」✅(安全)。⚠小注:端点先返200+job_id,拒绝在job异步阶段,非当场400。

### 1.5 OCR 后端 auto ✅ / rapidocr 见下 / t430 ⛔(需T430在线,未测)
### 1.6 音视频解析 ⛔ BLOCKED
### 1.7 autosync:add/list/remove 接口通;⚠已发现与手动上传的文件不去重→重复入库(4→8),用户称已修待复核
### 1.8 微信同步 ⛔ 崩溃风险,待用户手点
### 1.9 iOS 导入 ⛔ 需 iPhone

## TAB2 问答/卡片/产出
### 2.1 卡片 CRUD 全链 ✅(minor bug)
- 4类(goal/diary/note/task)各建成(doc212-215)✅
- 联想历史:card212 联到 7 份相关资料 ✅
- 标记完成 status=done ✅ / 删除 215 → 列表消失 ✅
- 卡片问答:基于库作答、诚实(资料无细节就说无细节)+ 来源 ✅
- ⚠ **BUG-2(小)**:编辑接口忽略传入 title,用 content 派生标题(edit 返回 title=content 值)。
### 2.2 全局问答 ✅
- deepseek-chat 连通;问「磐珏和谁融资」→「上海云图资本 Pre-A,王芳负责」+6来源,正确。
- ⚠ 稳定性:8G机上并发重调用(matches65s+星图+问答同轰)会崩 sidecar;串行则稳。
### 2.5 产出文档 ✅
- 生成 Word:22.8s→ /api/download 下载 HTTP200 7708B 真 docx,14 段落内容丰富(正确综合语料)。PPT/Excel 未逐一(同管线,Word 已证)。
### 2.3/2.4 主动发现模块(today/links/entity)→ 需分析完成,见下 TAB4 段一并

## TAB10 文库 ✅
- 19 文档全列,自动学科分类(王芳·云图·资本 / 孔贺·业务)+ 类型(文本/笔记/其它)分组正常。
- CDP 实测渲染 340 字符、卡片网格正常。

## TAB4 画像 ✅(惊艳)
- /api/persona 6.9s 生成:「金融科技创业者,正为磐珏数科第二大脑推进云图资本Pre-A轮融资,兼具技术产品与资本运作双重角色」——从19份测试文档准确推断,反巴纳姆 ✅。4领域/6标签/3价值观齐。

## TAB3 探索 ✅
- /graph 19节点69边8簇;/starmap 19节点70边14簇。文档全嵌入、力导图有数据。CDP 渲染正常。
- chat_galaxy/chat_topic_galaxy 需聊天数据,本号空(见下)。

## 2.3 主动发现模块 ✅
- /today 4件、/links 8对、/entity_links 12个——跨文档关联+实体聚合都出数据。UI 卡片(本轮修的占位文案+呼吸点)在此渲染。
- ⚠ **BUG-3(小)**:/api/analysis_status 恒显示 0/1 done=0%,但 persona/links/entity 实际都有数据→进度指示器不反映真实进度,会让用户误以为没分析完。

## TAB5/6/7 人脉/雷达/洞察 —— 需聊天数据
- 本测试号只有文档、无微信聊天,故关系卡/承诺/供需/人情/联系人画像等为空。
- 空态渲染:CDP 实测各 tab 不崩、显示空态(见 /tmp/qa_shots)。
- 富数据态:此前用 API 在本人号只读验过有真实数据(承诺mine110/theirs91、人脉69卡、台账62、洞察6组等,见早前记录)。
- ⛔ 端到端富数据流:需微信同步导入聊天(1.8,崩溃风险,待用户手点)。

### 补测:用 /api/wechat/ingest 注入合成聊天(4联系人×~53条)→ 分析层端到端验证
> 方法澄清:合成注入测的是「聊天入库后的分析加工」这半段(不关心数据来源);真微信捕获(1.8)是另半段,需真微信+手点。此法让 TAB5/6/7 在干净号上可测,不碰本人号、不走抓密钥崩溃点。
- 分析器 `pages>=2` 门槛:每会话需满2页(>50条)才跑intel——首次注入4条/人被跳过,补到53条/人才触发(**这是设计,非bug,但值得知道**)。
- 加工结果(全部实测有数据):
  - relationships 4卡 / commitments 我欠3·等对方3·逾期2 / number_ledger 2 / favors 1 / network_portrait 4组 ✅
  - cooling 3 / dormant 2 / checkup(对方等我回2) / balance(fresh4/core4) / discoveries 7 ✅
  - briefing(见面简报全字段) / rel_path(张伟→陈静经共享实体连通) / relation_timeline(3里程碑) / draft_reply(3草稿) ✅
  - ⚠ matches supply2/demand2 但 **matches=0**(投资vs知识系统跨域没配上,合理但记录);panorama=0(需同一事≥2人)
- ⚠ 我几次因**猜参数名**(from/to应是a/b、doc_id应是contact)+中文没URL编码 → 误判"失败",查代码后修正。教训:契约必查代码不猜。

## TAB9 冥想 ✅(本人号18201972547,数据在106)
- 9.1 一生故事 lifestory ✅「深夜的灯」29镜/cinema
- 9.2 一生歌 词稿 lifesong ✅「替两边取暖」;成曲 song/make ✅ status=done「本月已出歌」(月度幂等)
- 9.3 播放/专辑 ✅ mylibrary列出「微光里的河」→ /api/theme 下载 = 真 MP3 4.3MB(MPEG layer III可播)
- ★架构真相:成曲转发106(302key只在服务端),词稿/画像须在106才能成曲。测试号数据只在本地→106无画像→lifesong回落本地→song/make(106)读空报"先生成词稿"。**非bug,是local-only测试号的环境限制;106-backed真账号正常**。

## TAB8 好友/姻缘 ✅
- 加好友 ✅ qaflow0831加qatest0831a → {"ok":true,"friends":["qatest0831a"]}
- 算姻缘 match ✅ 11s出完整契合报告:原型「双引擎」+6维度/共鸣/互补/建议/恋爱视角,准确综合双方画像
- ⚠ 目标账号无画像则不可发现(加不上/match报"没这个人")——属正常(需先有画像)
- ⚠ /api/friends 返回404(好友列表在别端点,minor)

## 账户 / 设置
- 注册 /api/auth/register ✅ / 登录 /api/auth/login ✅(token+ident+tier)/ 错密码正确拒 ✅ / account试用状态 ✅
- ⚠ **BUG:用户名账号 update_profile 不持久**(返回ok回显数据,但users2没写、auth/profile读回空)。手机号账号走users2主流程可能不受影响,待核。
- pwd_login 是手机号账号专用(用户名走login),非bug
- AI设置:全局单例,测改会覆盖真key→只读验证has_key=true,未动

## 最后一批(用户列的"还没测的")
- ✅ **T430 OCR 后端**:T430在线(OCR服务在8100不是8000/8200,之前探错端口)。scan.pdf+backend=t430 → doc method=**unlimited-ocr@t430** 正文正确;T430日志实证"POST /ocr/image 200 OK"。整链路通。★图片走process_image恒rapidocr,backend只对PDF扫描页生效。
- ✅ **支付 pay/create**:生成订单+支付宝pay_url+金额,会话创建正常(未真付)
- ✅ **头像上传 avatar**:JSON dataurl格式上传{ok:True}读回成功(要dataurl不是multipart)
- ✅ **genimg/genvid** 端点存活;**iphone/status** tool_ready=True环境就绪(需插手机才能导入)
- ✅ **前端深度CDP交互**:11 tab 渲染/切换正常、无JS报错;问答实体卡→弹askDirect弹窗、发现铃可点开、卡片可点。雷达97字符=加载中(截图早),探索canvas无文字(正常)。
- ⛔ **仍需外部动作**:iPhone导入(插手机)、支付真完成(真付款)、真·实时增量微信(用户发新消息看秒级流入)——这三个我做不了。

## Bug 修复收尾
- 3个真bug全修:①eml/mbox乱码(extract._safe_body,实测正确)②卡片编辑丢title③改料不持久(UPSERT)。客户端已提交(需重构建生效);106已直改+重启+验证(update_profile UPSERT实测持久)。
- 2个降级为误判(analysis_status聊天专属进度/api/friends前端没调);autosync去重用户已修。


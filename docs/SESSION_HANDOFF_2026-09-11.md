# 第二大脑桌面客户端 · 测试修复交接文档（2026-09-10 → 09-11）

> 本次会话集中真机测试（本机 MacBook Air 轻量版 / mac2 MacBook Pro 高精版 / Windows 轻量版），
> 揪出并修复一批 bug。**0.2.4 已构建全绿并三端装完**；0.2.4 之后又攒了一批修复**待统一构建**。
> 新 session 先读本文件。

---

## 一、机器与账号

| 机器 | 型号/芯片 | 版本 | 登录账号 | 备注 |
|---|---|---|---|---|
| 本机 | MacBook Air (4) · Intel | 0.2.4 轻量版 | 机主 18201972547 | 数据全(785文档)、key/工具齐 |
| mac2 | MacBook Pro (6) · Intel | 0.2.4 高精版(HD) | 机主 18201972547 | 108文档、iPhone 连此机 |
| Windows | Win10 x64 | 0.2.4 轻量版 | 机主 18201972547 | 仅40文档(数据少) |

- 机主账号 **18201972547** 密码 `12345678`；测试号 **13700000001** 密码 `Shiyong@2026`（昵称已改"测试号"）
- 云端 106：root/qingshi@123；mac2：zhaojue/qingshi@123；Windows：Qingshi/qingshi@123
- DeepSeek key 三端已配（本机全局 settings.json / 每账号 settings_账号.json）

---

## 二、修复清单

### A. 已在 0.2.4（已构建+三端已装，无需再动）
| 提交 | 问题 | 真因 |
|---|---|---|
| ec2e426 | 付费墙"退出登录"点了没反应 | 确认框 z-index 210 被付费墙 4000 盖住→提到 9000 |
| c74823e | 发现连接第一次"暂时连不出关联" | pro 推理 67s 超前端 WKWebView 60s 网络超时→改**异步+轮询**(不降级flash) |
| 92ebc76 | 换测试号带出前账号微信 | handoff 被任意登录账号消费→加本机 owner 绑定隔离(handoff_owner.json) |
| 5b0f672 | 冥想新用户卡"谱曲中" | 没画像也显示谱曲(gen.generating对新用户为真)→加 eligible 门槛走引导页 |
| b5c4b94 | 好友头像/用户名不更新 | 显示的是 shared_personas 冻结快照+头像从不上云→实时 display+头像云同步 |
| 6a7d0f8 | AI key 带尾随空格失效 | 粘贴带空格→`Bearer sk-..␣`被判无效key→保存/使用自动 strip |
| 58aa521 | PPT下载跳浏览器/多tab | openExternal 拉起浏览器→改直接存~/Downloads+Finder高亮(/api/save_output) |
| dce7213 | **★后台线程系统性漏 set_owner** | 后台异步线程未 LLM.set_owner→读全局 settings(新机器空)→"未配置key"→PPT生成/卡片/供需/连接解释/一生片全失败。静态审计补齐5处 |

### B. 0.2.4 之后**已提交、待统一构建**（`git log dce7213..HEAD`）
| 提交 | 问题 | 真因/修法 |
|---|---|---|
| 08483ad | **★承诺雷达卡466/保存key无反应/接口30s超时** | `pages`/`page_embeddings` **缺索引**→bg每轮"找没嵌入的微信页"三表JOIN做**2.4亿次操作/轮**→CPU232%饿死所有请求。加 `idx_pages_doc`/`idx_pageemb_page`：查询0.6s、CPU→90%、接口→0.04s。启动时自动建索引 |
| fc721a9 | 说明页"联系我们"藏太深 | 重设计：顶部醒目渐变卡(邮件图标+一键发/复制)+底部简版。邮箱 hekong@spdt.freeqiye.com |
| b0acac3 | 生成PPT后按钮有阴影 | WKWebView 点击残留焦点光圈→`.btn:focus:not(:focus-visible)`重置 |
| bb1876b | 预置模型名过时 | Kimi `kimi-k2.5`→`kimi-k2.6`(2026-08-31下线返404)；智谱 `glm-4.5-flash`→`glm-4.7-flash`(2026-01-30停用)。两处同步(llm.py+Settings.jsx) |
| e520154 | iPhone导入报"未检测到备份工具"即使已装 | macOS GUI app PATH 只有`/usr/bin:/bin:/usr/sbin:/sbin`不含`/usr/local/bin`→shutil.which找不到已装的idevicebackup2。加`_ensure_ios_tools_path()`把brew目录加进PATH |

---

## 三、已直接生效（不用构建，当场处理）
- **索引**：本机+mac2 的 library.db **已直接建好索引**（永久，DB里持久化），承诺雷达/保存已恢复。Windows 数据少危害小，等构建代码自愈
- **测试号残留清理**：本机(639)+mac2(77+旧版又串4)测试号微信数据全清0，机主数据完好；三端 handoff_owner.json=18201972547
- **昵称迁移**：云端已推 18201972547=Kkkk(有头像)/13700000001=测试号(kong→测试号)
- **Windows key**：用户"改key"其实key一直在(PowerShell读BOM显示0是假象)；真因是set_owner后台读全局空。已把本机key复制进Windows全局settings续命
- **mac2 iPhone导入**：从本机打自包含 x86_64 idevice 工具包(6工具+6dylib,@loader_path)→ 传mac2 `~/idevice_bundle` → 建启动器 `~/开启iPhone导入.command`(带PATH重启app)。**用户双击后已成功开始备份**(idevicebackup2进程在跑)

---

## 四、待办（统一构建 + 部署收尾）

### 1. 统一构建（用户测完后）
- 把用户后续新报的问题一起改 → bump 版本(0.2.5) → 构建三端 → 装本机/mac2/Windows
- 已排队5提交(见 B) 会一起进

### 2. **★内置 libimobiledevice（关键，让 iPhone 导入开箱即用）**
- 现状：工具没打进 app，用户要自己装 brew+libimobiledevice(普通用户不会)→ iPhone导入"看得见用不了"
- 方案：把 x86_64 idevice 工具包(见三)打进 app 的 resources(CI构建时带上) + `_ensure_ios_tools_path()` 再加"内置bin目录"到PATH
- **ARM 兼容确认**：app 是单一 x86_64 版，ARM Mac 走 Rosetta 跑；内置 x86_64 idevice 工具同架构、同样 Rosetta 下跑；iPhone 通信走系统 usbmuxd(与架构无关)→ **Intel原生/ARM Rosetta 两边都正常**
- 工具包已备：本机 `/tmp/idevice_bundle` + `/tmp/idevice_bundle.tgz`

### 3. 客户端下载改 OSS（用户要求，已改一半）
- OSS bucket 现成：`worldmonitor-downloads.oss-cn-shanghai.aliyuncs.com`(阿里云上海公读,传模型那个)。凭证在 `~/.ossutilconfig`(本机+106)。python oss2 已验证可上传
- **已改**：官网 `~/unlimited-ocr/web/frontend/src/Landing.jsx` 三个下载链接改成 OSS 直链 `compound-clients/Compound-mac-Intel-lite.dmg` / `-hd.dmg` / `-Windows-lite.exe`(未提交)
- **待做**：构建出新版后→三包传OSS(稳定名)→官网 build+部署106→
- ⚠️ 用户说"先不传,等测完统一构建再传"

### 4. 版本更新提示（已上线,发版时要更新）
- UpdateBanner 完整且已部署(客户端拉 compoundtome.com/latest.json 比对 app_version)。
- **但 latest.json 现在写的是 0.2.0**(比客户端0.2.4还旧)→现在没人被提示
- **发版步骤**：出新版后改 106 的 `BRAIN_DATA/latest.json`(version+notes)→老客户端弹更新提示

### 5. 模型名核查(其余🟡项,可选)
- 已改死掉的(Kimi/智谱)。仍过时但能用(有别名+报错引导): OpenAI `gpt-5`(当代gpt-5.6)、Gemini `gemini-2.5`(当代Gemini3)、豆包`doubao-seed-2-1-pro-260628`(需控制台确认)
- ★模型栏是**自由输入**框,用户可填任何当前有效名;死掉的会报"模型已下线,请去设置改"(非"检查key")

---

## 五、关键真因/教训（会复发的坑）

1. **★后台线程必须 LLM.set_owner(owner)**：任何后台异步线程用LLM,不设owner→读全局settings(新机器空)→误报"未配置key"。老机器有历史全局key所以侥幸。已审计补齐,新增后台LLM线程务必加
2. **★DB建表必须配套建索引**：pages/page_embeddings缺doc_id/page_id索引→bg分析O(N²)全表扫描烧满CPU饿死一切。新表按owner/doc_id查的都要索引
3. **★macOS GUI app PATH受限**：只有`/usr/bin:/bin:/usr/sbin:/sbin`,不含brew目录→shutil.which找不到已装工具。要调外部CLI(idevicebackup2等)必须先补PATH或用绝对路径/内置
4. **PowerShell ConvertFrom-Json读sftp传来的json .Length显示0是BOM假象**,别误判成"数据丢了",python json.load读没问题
5. **ssh进不了macOS图形会话**:`launchctl asuser`被拦、`launchctl setenv`不propagate到open启动的app、直接跑GUI二进制不显示窗口→远程改GUI app的PATH做不到,得从本机会话启动(或内置工具)
6. **Windows sshd频繁连接会限流**(Permission denied),用 SSH ControlMaster 连接复用(建主连接认证一次,scp/sftp复用ControlPath);Windows sftp家目录=C:/Users/用户,用相对路径;iex([IO.File]::ReadAllText(path,UTF8))绕执行策略跑ps1
7. **发现/卡片关联/画像 找不到内容 未必是bug**:先看该机器有没有数据(Windows仅40文档、0国债数据→找不到正常)+嵌入建完没

---

## 六、发版清单（下次统一构建照做）
1. [ ] 收齐用户新报问题一起改
2. [ ] bump `src-tauri/tauri.conf.json` version → 0.2.5
3. [ ] 内置 libimobiledevice 到 app + wire PATH（见四.2）
4. [ ] git commit + push（workflow_dispatch,push不触发构建）
5. [ ] 触发三端构建(gh workflow run:HD 341866410/Mac轻量 341410642/Win 345112824),全绿
6. [ ] 下载三包 → 装本机/mac2(rsync+ditto)/Windows(ControlMaster+sftp+/S静默装)
7. [ ] 三包传 OSS(稳定名 compound-clients/*) + 官网 build+部署106(下载链接已改OSS,记得提交web/app.py+Landing.jsx)
8. [ ] 更新 106 的 latest.json → 0.2.5 + notes（触发老客户端更新提示）
9. [ ] 清理:mac2的~/idevice_bundle+启动器(内置后不需要)、临时包

关联记忆：[[compound_crash_recovery_state_2026-09-10]]

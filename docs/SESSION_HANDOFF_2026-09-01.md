# 会话交接/状态(2026-09-01)—— 闪退防丢,新 session 先读这个

> 本会话极长(深度手测→批量修bug→建好友社交基建→三机并行测)。此文件记录当前全部状态,闪退可直接接上。

## 1. 当前版本 & 构建
- **最新 commit = 68f421e**(compound-desktop main,已推)。之后本地还有几个 doc commit(未推,防触发多余构建)。
- **三平台构建全 success(68f421e)**:Mac Intel 轻量 / Mac Intel 高精 / Windows 轻量。
- **版本设计=5个**(权威 `unlimited-ocr/docs/PACKAGING_PLAN_2026-08-25.md` §二矩阵):
  Mac Intel 轻量✅建 / Mac Intel 高精✅建 / **Mac arm64 轻量❌没建** / Windows 轻量✅建 / **Windows 高精❌没建**。
  arm64 设计上无高精(paddle 在 arm mac 必崩)。缺 2 个 workflow(build-mac-arm、build-windows-hd)=待办,用户说先不急。

## 2. 三机并行测试布局
| 机器 | IP / 登录 | 装的版本 | 状态 |
|---|---|---|---|
| Mac A(本机) | 172.16.17.151 | Mac Intel **轻量** 68f421e | ✅已装运行(sidecar动态端口,本轮54458;/health通;助手v7) |
| mac2 | zhaojue@172.16.16.172 (pw qingshi@123) macOS12.7.6 Intel | Mac Intel **高精** | ⏳下载中(4.8G),待scp+装 |
| Windows | Qingshi@172.16.17.175 (pw qingshi@123) Win10 | Windows **轻量** 68f421e | ⏳待重装最新(428M setup.exe);旧版已装过 |

- 下载中:`/tmp/dl_hd_win.log`(高精+Win 到 ~/Downloads/compound-builds/{mac-hd,windows})。GitHub API 偶发 EOF,失败重试。
- ★Windows SSH 别连太频(MaxStartups 限流,连崩要等冷却)。Mac token 从 webview localStorage `auth` 键(UTF-16LE)取;本轮存 /tmp/mac_tok.txt。

## 3. 本轮修复(D1–D11,全在 68f421e)
DB锁跨LLM根治(autocommit,解:存卡片/资料/头像/群图/关系走势/姻缘)、Tauri下载(openExternal)、媒体URL(apiUrl:冥想/Gallery)、外链(新闻/助手/引导)、删除弹窗透明(实底)、Excel漏行(reset_dimensions)、8G后台节流、微信助手升级不刷新(_seed按大小覆盖)、匹配弹框加宽640。详见 `MASTER_TEST_PLAN_2026-09-01.md` §6。

## 4. ★好友社交基建(新建,68f421e + 云 + 106对齐)
- **云端**:106 compound-server(/opt/compound-server/app.py)加 `/social/*`(shared_personas/friend_reqs/friendships)。手机号加+对方同意+仅好友互取AI画像。已重启验证通。
- **客户端 sidecar**:_share_persona_to_cloud(生成画像后台上传)+ /api/friend/{request,requests,respond,list,remove} 代理云 + match 从云拉好友画像。
- **前端 Friends.jsx**:重写=手机号加好友+收到请求同意/拒绝(同意提示=授权算姻缘,只共享画像)+好友卡算姻缘;去发现池。
- **106 brain 已代码对齐**(/opt/compound-brain/web/app.py 同样3处改;venv编译过;重启通)。★铁律:客户端sidecar与106brain同源,改动两边都落。
- **隐私**:跨用户只共享 AI 汇总画像(非聊天原文);仅互为好友双方可互取。
- **测试账号 B**:`bella_test` / `test1234`(用户名账号,API建非DB写),已配画像,**已给 A(18201972547)发好友请求**→A开客户端「好友」见「好友请求·1」→同意→算姻缘。

## 5. 测试文档(全覆盖)
- `MASTER_TEST_PLAN_2026-09-01.md`:L1-L5级别+8类型+模块×类型矩阵+D1-D11缺陷库+准入准出+历史文档合并(§10-11)+U1-U22用户点名清单(§12)。
- `REGRESSION_CASES_CLIENT_2026-09-01.md`:§2逐页按钮/§3格式矩阵13种/§8端点116全覆盖/§9端到端11流程F1-F11。
- 铁律:走真客户端不走curl;验屏幕真结果;Tauri专项;负载下测;数据对账。

## 6. 关键凭据/路径
- 106: 106.14.189.104 root/Qingshi@321;compound-server :8000 /opt/compound-server;brain :8200 /opt/compound-brain/web;brain用 /opt/compound-server/venv/bin/python(系统python3太老不能py_compile)。
- OSS: worldmonitor-downloads.oss-cn-shanghai(公读),模型 tar 在 compound-models/;106装了ossutil(凭据/root/.ossutilconfig,从wm复制来)。
- 微信助手: 独立仓 ~/wxkeys(konghesmileface/wxsync-helper),最新v7=62ad5b8,三平台包在~/Downloads。

## 7. 下一步(测试执行)
1. mac2 装高精 + Windows 重装轻量(下载完成后)。
2. 我先自动过 L1(selftest)+L2(端点对账)+我能驱动的 U项(createCard不撞锁/下载端点/xlsx全行/好友端点/助手v7)在68f421e上。
3. 用户手点 L3/L4(U1-U22 纯UI项)+ 好友F5(用B账号)。
4. 目标:用户再点点不出新bug。

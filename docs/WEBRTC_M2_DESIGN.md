# M2 WebRTC 直连设计与进度(2026-09-12)

## 目标
在 M1 中转(100% 覆盖)之上加一层 WebRTC 打洞:**能直连就直连(数据不过服务器,省带宽/延迟),打洞失败自动回落 relay 中转,用户全程无感**。这是纯优化——中转已够用,WebRTC 只在成功打洞的连接上卸载流量。

## 拓扑
```
建连(信令走 relay,几秒):
  手机(offerer) --{t:rtc, sub:offer/ice}--> relay --加cid--> 桌面(answerer)
  手机 <--{t:rtc, sub:answer/ice}-- relay <--回显cid-- 桌面
  两端各自向 relay 要 TURN 凭证 {t:turn} → coturn REST 现算的 iceServers
成功(~60-70%): 手机 <== DataChannel "compound" 直连 ==> 桌面   业务数据不过服务器
失败(~30-40%): 手机 <== relay 中转(M1 通道) ==> 桌面           coturn TURN 兜底或纯中转
```

## 已完成并验证(本次)
- **coturn 部署 106**:`/etc/coturn/turnserver.conf`,use-auth-secret + realm compoundtome.com,3478(STUN+TURN over UDP/TCP)active。secret 在 `relay-server/deploy/.turn_secret`(不进 git)+ relay systemd。
- **relay 信令+TURN**(`relay-server/relay_server.py`):转发 `t=rtc` 帧(手机↔桌面),`t=turn` 用 TURN_SECRET 现算 coturn REST 凭证返 iceServers(secret 只在 relay 不下发)。已部署 106 + 重启,向后兼容 M1。
- **手机端 WebRTC 传输**(`compound-mobile/src/channel/webrtc.js` + relay.js + api.js):RTCPeerConnection + DataChannel;`channelFetch` 优先 DataChannel、未就绪走 relay 并后台建直连、直连失败回落 relay。
- **验证**:`compound-mobile/scripts/webrtc_check.py`(playwright 双页,真浏览器 WebRTC + 真 relay 信令)5 项全绿——DataChannel 建立/ICE 打洞/presence/请求往返×3/桌面确收。

## 桌面端 answerer(待实现,进 0.2.8)
桌面 WebRTC **不进 Rust crate、不进 Python aiortc**(打包深坑),跑在**桌面 Tauri 前端 webview JS** 里(客户端常驻开着,webview 原生支持 WebRTC,零新依赖)。前端 answerer 是"哑管道",加解密仍复用 Python phone_link(密钥不出 Python)。

数据流:
1. phone_link.py(已连 relay 的 desktop 端)收到 `t=rtc` 信令 → 存入信令队列。
2. 桌面前端 answerer 组件轮询 `GET /api/phone/rtc/poll` 拿 offer/ice;建 RTCPeerConnection + answer;`POST /api/phone/rtc/signal` 把 answer/ice 经 phone_link → relay 发回手机。
3. DataChannel open 后,前端收到应用帧 `{rid, n, d}` → `POST /api/phone/rtc/exchange {dev, n, d}` → phone_link **复用 `_decrypt`/`_local_call`/`_encrypt`**(和 M1 `_on_req` 同一套)解密+打 localhost FastAPI+加密 → 返回 `{n, d}` → 前端 DataChannel 回 `{rid, n, d}`。

要写的:
- phone_link.py:①`t=rtc` 入信令队列 ②`/api/phone/rtc/poll`(长轮询)③`/api/phone/rtc/signal`(前端→relay)④`/api/phone/rtc/exchange`(dev+n+d→复用解密转发)。offer 帧已带 `dev`(手机端已实现),exchange 按 dev 取 `phone_link.json` devices[].key。
- 桌面前端:`RtcAnswerer` 组件(App 常驻挂载),轮询信令+建 pc+DataChannel→exchange 桥接。webview 最小化被节流时 DataChannel 可能断→检测到断自动让手机回落 relay(已有回落逻辑兜底)。

## 待人工的最后一公里
1. **安全组放行 UDP**:阿里云 106 需放行 UDP 3478、5349、49152-65535(TURN relay 范围)。106 的 `aliyun` cli 未配 AK(`/root/.aliyun/config.json` 缺失)→ 需在阿里云控制台放行,或配 AK 让脚本放行。**不放行则 STUN/TURN 公网不可达,打洞用不了**(但 relay 中转不受影响,功能不降级)。
2. **5349 TLS(turns:)**:letsencrypt privkey 是 600 root、coturn 降权后读不到 → 5349 未起。给 turnserver 用户读权限(setfacl)或复制证书+renew hook。turns: 仅少数强制 TLS 出口网络需要,3478 已够,可后补。
3. **桌面 answerer 实现 + 打进 0.2.8** 桌面客户端。
4. **真机跨网打洞验证**:两台真实设备(手机蜂窝 + 桌面家宽),验证打洞成功率与 TURN 兜底。本机 loopback 只验证了信令+DataChannel 逻辑。

## 协议同步铁律
`t=rtc`/`t=turn` 帧改动必须三处一致:`relay_server.py` + `phone_link.py`(桌面 answerer 落地时)+ `compound-mobile/src/channel/{webrtc,relay}.js`。

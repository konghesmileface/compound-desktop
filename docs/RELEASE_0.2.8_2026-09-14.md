# 复利桌面客户端 0.2.8 发版记录(2026-09-14)

## 整合来源(所有分支已提交工作全captured,一并发)
- main(dfd30e4):stats types + relationships slim 分页 + 通道 gzip + relay ping 宽限 + M1 手机通道 + 新手引导重写
- app-webrtc(b3ef71f):M2 桌面 WebRTC answerer(打洞直连;phone_link 同时含 gzip 与 answerer)
- release-0.2.7(dea81b9+4abb453):CI cryptography x86_64 修复 + 承诺 window/slim
- release-0.2.6(4a1f0a1):老版 Excel .xls 入库修复
- 另一对话新手引导(c72d8bf):已在 main 历史内
不进客户端包(故未含):f34bf16 relay ping / 6c0fcee 信令+coturn = relay 服务端,已单独部署 106。
版本 bump 0.2.8。sidecar 运行时验证:health 200 / stats types / rtc poll / commitments slim 全通。

## 发版策略(机主铁律)
不传 OSS、不动 latest.json、官网下载保持 0.2.6 稳定版。只出 GitHub 产物持续发新版测试,测稳后再传 OSS。

## 本次构建(workflow_dispatch on release-0.2.8)
Build Mac Intel 轻量版 run 34801278810 / Build Windows 轻量版 run 34801282159。HD/mac2 未构建(mac2没开机)。

## iOS/Android 就绪
compound-mobile 13 secrets 全配齐;App 已建(Apple ID 6811590520,com.compoundtome.app,磐珏账号)。tag v* 即出。

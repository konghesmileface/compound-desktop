# 0.2.7 发版说明(2026-09-11)

## 定位
0.2.7 = 0.2.6 稳定版之上,**加入手机 App 支持的桌面端底座**。0.2.6 由另一个对话先发(纯稳定修复,不含手机通道);0.2.7 是本对话的 App 工作线,含手机连接通道 + 公众号入库修复。

> 版本号刻意从 0.2.6 跳过,取 **0.2.7**,避免和 release-0.2.6 分支撞号。

## 本版新增/修复

### 1. 手机连接通道(App M1,新功能)
- 设置 → 账户页新增「手机连接」卡:生成配对二维码、已配设备列表/解绑、中转连接状态。
- sidecar 常驻外连 106 中转(`wss://compoundtome.com/relay`),端到端加密(P-256 ECDH + HKDF + AES-256-GCM),服务器只递密文。
- 手机 App(compound-mobile,独立仓库,壳待做)扫码配对后可随时随地安全访问本机大脑。
- 依赖新增 websockets/cryptography/qrcode(纯 py + 标准 wheel,零打包坑)。
- 验证:桌面侧 E2E 11 项 + 跨实现 8 项 + 生产 relay 全真回归 手机各页 8/8 端点 200,全绿。
- 106 中转已部署上线(/opt/compound-relay,systemd + nginx /relay)。

### 2. 公众号 / 网页入库修复(App M5)
- 修:`/api/upload_url` 抓公众号(mp.weixin)裸 UA 被打「环境异常」验证页 → 完整移动 Safari UA。
- 修:正文提取通用启发式把公众号 `#js_content` 整块误删 → 专用通道直取正文 + 标题,按文章标题命名入库。
- 实测:一篇真公众号文章干净提取 8580 字。普通网页 readability 回归正常。

## latest.json 更新文案(发布时写到 106 的 https://compoundtome.com/latest.json)
```json
{
  "version": "0.2.7",
  "notes": "新增「手机连接」:扫码把手机和你的大脑配对,随时随地安全提问、随手采集(端到端加密,数据仍在你电脑上)。公众号文章链接入库修复。",
  "url": "https://compoundtome.com/#download"
}
```
(字段名以现网 latest.json 现状为准,发布前先 `curl https://compoundtome.com/latest.json` 对齐 schema。)

## 发布步骤(等 0.2.6 三端构建绿 + 发布完、mac runner 额度空出后再做,避免抢额度)
1. `gh workflow run build-mac-intel.yml --ref release-0.2.7`(轻量)
   `gh workflow run build-mac-intel-hd.yml --ref release-0.2.7`(HD)
   `gh workflow run build-windows.yml --ref release-0.2.7`(Win)
2. 三端绿 → 下载产物 → 传 OSS(worldmonitor-downloads/compound-clients/ 稳定名)
3. 更新官网 Landing 下载链接(如指向稳定名则免改)+ 部署 106
4. 更新 106 latest.json → 0.2.7(上面文案)→ 老客户端弹更新提示
5. 合 release-0.2.7 → main(此时 main 版本号才正式到 0.2.7)

## 注意
- ★手机 App 壳(Capacitor)尚未做,手机端还不能上架给真实用户;0.2.7 桌面端带通道是为将来 App 联调就位,对当前桌面用户是纯增量(多一张配对卡,不用就无感)。
- ★协议 compound-e2e-v1 改动必须三处同步:sidecar/phone_link.py + relay-server/relay_server.py + compound-mobile/src/channel/。

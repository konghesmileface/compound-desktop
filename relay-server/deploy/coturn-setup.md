# coturn(STUN/TURN)部署记录 — 106

**已于 2026-09-12 部署**。WebRTC 打洞的 STUN/TURN 基础设施。

## 现状
- 装:`dnf install -y coturn`(Alibaba Cloud Linux 3),二进制 `/usr/bin/turnserver`。
- 配:`/etc/coturn/turnserver.conf`(见下),systemd `coturn` enable + active,监听 3478 UDP+TCP。
- secret:`use-auth-secret` + `static-auth-secret`,值在 `deploy/.turn_secret`(本地,gitignore)与 106 配置 + relay systemd `TURN_SECRET`。relay 用它现算 REST 临时凭证(见 relay_server._turn_iceservers)。

## turnserver.conf 关键项
```
listening-port=3478
tls-listening-port=5349
listening-ip=0.0.0.0
relay-ip=172.19.244.13            # 阿里云内网网卡 IP
external-ip=106.14.189.104/172.19.244.13   # 公网/内网映射(NAT 后必须)
realm=compoundtome.com
use-auth-secret
static-auth-secret=<见 .turn_secret>
min-port=49152
max-port=65535
cert=/etc/letsencrypt/live/compoundtome.com/fullchain.pem
pkey=/etc/letsencrypt/live/compoundtome.com/privkey.pem
```

## 待办(人工)
1. **安全组放行 UDP**(阿里云控制台或配 aliyun cli AK):UDP 3478、5349、49152-65535。不放则公网不可达。
2. **5349 TLS**:coturn 降权后读不到 600 root 的 letsencrypt privkey → 5349 未监听。修:
   `setfacl -m u:turnserver:rx /etc/letsencrypt/live /etc/letsencrypt/archive && setfacl -m u:turnserver:r /etc/letsencrypt/archive/compoundtome.com/privkey*.pem && systemctl restart coturn`
   (certbot renew 后 acl 保留;turns: 非必需,3478 已够)。
3. 外部验证:`turnutils_stunclient -p 3478 compoundtome.com`(装 coturn-utils),或浏览器 trickle-ice 工具填 turn:compoundtome.com:3478 + relay 发的临时凭证。

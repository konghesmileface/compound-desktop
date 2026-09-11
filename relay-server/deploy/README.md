# 中转服务部署(106 = compoundtome.com)

**★已于 2026-09-11 部署上线并全链路验证**(生产 E2E 8项全绿: 真账号→wss://compoundtome.com/relay→配对→加密往返)。
实际部署形态(与下文模板的差异):
- 106 系统 python3 是 3.6.8 太老 → 用 `/usr/bin/python3.11 -m venv /opt/compound-relay/venv`,unit 的 ExecStart 已 sed 成 venv python(websockets 17.1)
- nginx: location /relay 已插入 /etc/nginx/conf.d/compoundtome.conf 的 443 server 块;改前备份 compoundtome.conf.bak_relay_20260911

前提: 106 上已有 python3.8+ 和 `pip3 install websockets`。

```bash
# 1. 传文件
ssh root@106.14.189.104 "mkdir -p /opt/compound-relay"
scp relay-server/relay_server.py root@106.14.189.104:/opt/compound-relay/
scp relay-server/deploy/compound-relay.service root@106.14.189.104:/etc/systemd/system/

# 2. 起服务
ssh root@106.14.189.104 "pip3 install websockets && systemctl daemon-reload && systemctl enable --now compound-relay && systemctl status compound-relay --no-pager"

# 3. nginx 挂 /relay(把 deploy/nginx-relay.conf 的 location 块加进 compoundtome.com 的 443 server 块)
ssh root@106.14.189.104 "nginx -t && systemctl reload nginx"

# 4. 验证(本机): python3 sidecar/test_phone_link_e2e.py --relay wss://compoundtome.com/relay --token <真账号token>
```

改动协议必须三端同步: sidecar/phone_link.py + relay_server.py + compound-mobile/src/channel/。

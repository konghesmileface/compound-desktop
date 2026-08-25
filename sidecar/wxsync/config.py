# -*- coding: utf-8 -*-
"""
wxsync 客户端配置
=================

统一存放:后端地址、登录 token、当前云账号、实时同步开关、轮询间隔、微批阈值等。

配置来源(优先级从高到低):
1. 环境变量(WXSYNC_BACKEND / WXSYNC_TOKEN / ...)
2. 用户配置文件  ~/.wxsync/config.json
3. 代码里的默认值

配置文件示例(~/.wxsync/config.json):
{
    "backend": "http://106.14.189.104:8000",
    "token": "<登录后拿到的 Bearer token>",
    "account": "13800000000",
    "realtime_enabled": true,
    "poll_interval_sec": 5,
    "batch_max_seconds": 45,
    "batch_max_messages": 200
}

注意:token / account 属于敏感信息,配置文件建议 chmod 600。
真实产品里这些值应由桌面客户端登录界面写入,不要硬编码。
"""

import json
import os

# 配置文件默认位置:~/.wxsync/config.json
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".wxsync")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

# 本地同步状态库(游标 / 去重表),和配置放一起
STATE_DB_PATH = os.path.join(CONFIG_DIR, "sync_state.db")

# --------------------------------------------------------------------------- #
# 默认值(可被配置文件 / 环境变量覆盖)
# --------------------------------------------------------------------------- #
_DEFAULTS = {
    # 后端根地址(云服务端 106,或本机 web/app.py 的 http://127.0.0.1:8200)
    "backend": "http://106.14.189.104:8000",
    # 登录后拿到的账号 token(Bearer),没有就走不了上传
    "token": "",
    # 当前云账号 ident(手机号/用户名),用于 msg_id 命名空间和状态上报
    "account": "",
    # 实时同步总开关(用户可随时关)
    "realtime_enabled": True,
    # WAL 轮询间隔(秒)。微信新消息先落 .db-wal,秒级轮询 mtime 即可
    "poll_interval_sec": 5,
    # 微批:攒满这么多秒就上传一次(即使没满条数)
    "batch_max_seconds": 45,
    # 微批:攒满这么多条就立刻上传(即使没到时间)
    "batch_max_messages": 200,
    # 上传接口的 backend 参数(auto=后端自动挑解析后端)
    "upload_backend": "auto",
    # HTTP 超时(秒)
    "http_timeout": 60,
}


class Config:
    """轻量配置对象。读一次文件 + 环境变量,之后当普通属性用。"""

    def __init__(self, data: dict):
        self._data = data

    def __getattr__(self, name):
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name)

    def get(self, key, default=None):
        return self._data.get(key, default)

    # ------- 常用组合地址 ------- #
    @property
    def upload_url(self) -> str:
        return self.backend.rstrip("/") + "/api/upload"

    @property
    def ingest_status_url(self) -> str:
        return self.backend.rstrip("/") + "/api/ingest/status"

    @property
    def heartbeat_url(self) -> str:
        return self.backend.rstrip("/") + "/api/realtime/heartbeat"

    @property
    def realtime_status_url(self) -> str:
        return self.backend.rstrip("/") + "/api/realtime/status"

    @property
    def realtime_toggle_url(self) -> str:
        return self.backend.rstrip("/") + "/api/realtime/toggle"

    @property
    def wechat_ingest_url(self) -> str:
        # iOS 历史导入 与 桌面实时 共用这个入口,服务端按内容指纹统一去重
        return self.backend.rstrip("/") + "/api/wechat/ingest"

    @property
    def auth_header(self) -> dict:
        """给所有需要鉴权的请求加 Authorization。"""
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def to_dict(self) -> dict:
        return dict(self._data)


def _load_file() -> dict:
    """读用户配置文件;不存在返回空字典。"""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:  # noqa: BLE001
            print(f"[config] 读配置文件失败,用默认值:{e}")
    return {}


def _env_override(data: dict) -> dict:
    """环境变量覆盖(WXSYNC_<大写字段名>)。布尔/数字做类型转换。"""
    for key in _DEFAULTS:
        env_key = "WXSYNC_" + key.upper()
        if env_key in os.environ:
            raw = os.environ[env_key]
            default = _DEFAULTS[key]
            if isinstance(default, bool):
                data[key] = raw.lower() in ("1", "true", "yes", "on")
            elif isinstance(default, int):
                try:
                    data[key] = int(raw)
                except ValueError:
                    pass
            else:
                data[key] = raw
    return data


def load_config() -> Config:
    """合并默认值 + 配置文件 + 环境变量,返回 Config 对象。"""
    data = dict(_DEFAULTS)
    data.update(_load_file())
    data = _env_override(data)
    return Config(data)


def save_config(cfg: Config) -> None:
    """把配置写回文件(桌面客户端改设置后调用)。文件权限收紧到 600。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg.to_dict(), f, ensure_ascii=False, indent=2)
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass


if __name__ == "__main__":
    # 打印当前生效配置(token 脱敏),方便排查
    c = load_config()
    d = c.to_dict()
    if d.get("token"):
        d["token"] = d["token"][:6] + "…(已脱敏)"
    print(json.dumps(d, ensure_ascii=False, indent=2))
    print("配置文件:", CONFIG_PATH)
    print("状态库  :", STATE_DB_PATH)

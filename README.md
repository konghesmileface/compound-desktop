# 第二大脑 桌面客户端(compound-desktop)

Tauri v2 桌面壳,打包"第二大脑"全本地客户端。产品架构见 `unlimited-ocr/docs/PACKAGING_PLAN_2026-08-25.md`。

## 构建方式:GitHub Actions(跟 WM 一样,不靠本机凑机器)
- 平台顺序:**Mac Intel(macos-13)→ arm Mac(macos-14)→ Windows(windows-latest)**,一次做完一个系统。
- 构建时仓库临时转 public(避 CI 额度坑),出包后转回 private。

## 里程碑
- **M1(当前)**:Tauri 壳 + 网页 UI(`frontend/`,拷自 unlimited-ocr),CI 出未签名 .app/.dmg,API 先指向云端 106:8200。
- M2:PyInstaller 把 FastAPI 后端(compound-brain)打成 sidecar,壳启动 + /health 自愈,API 切本机。
- M3:OCR(轻量 rapidocr + Intel Mac 高精 paddle)。
- M4:bge-m3(2.3G)嵌入模型打包/按需下载。
- M5:微信助手(8767 控制口)接成网页开关。
- M6:.app/.pkg 一键装 + 真机全测,再横移 arm Mac / Windows。

## 结构
- `frontend/` — React 网页 UI(源自 unlimited-ocr/web/frontend;那边是源头,此处随构建同步)。
- `src-tauri/` — Tauri v2 壳(Rust)。
- `.github/workflows/` — 各平台 CI。

## ★安全
本仓库只放**代码**,`.gitignore` 严禁任何 `*.db`/`uploads`/`vault`/密钥证书进库(构建期会转 public)。

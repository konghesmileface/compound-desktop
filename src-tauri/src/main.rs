// 第二大脑 桌面壳 —— 里程碑1:仅加载打包进壳的网页 UI(API 指向云端,构建期由 VITE_API_BASE 注入)。
// 后续里程碑:启动本机 FastAPI sidecar + /health 自愈,并在此注入 window.__COMPOUND_API_BASE__ 指向本机端口。
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

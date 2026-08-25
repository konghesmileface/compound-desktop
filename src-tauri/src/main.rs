// 第二大脑 桌面壳 —— M2:启动本机 FastAPI sidecar,注入本机 API 地址,进程守护(自愈)。
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs::OpenOptions;
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};

/// 挑一个空闲回环端口(绑 :0 让系统分配)。
fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .ok()
        .and_then(|l| l.local_addr().ok())
        .map(|a| a.port())
        .unwrap_or(8200)
}

/// 定位 sidecar 可执行(onedir 布局:<dir>/compound-sidecar/compound-sidecar)。
/// 优先打包资源目录;dev 回落到仓库内本地构建产物。
fn sidecar_bin(app: &tauri::AppHandle) -> Option<PathBuf> {
    let exe_name = if cfg!(windows) { "compound-sidecar.exe" } else { "compound-sidecar" };
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(res) = app.path().resource_dir() {
        candidates.push(res.join("compound-sidecar").join(exe_name));
    }
    // dev 回落:仓库 sidecar/dist/compound-sidecar/
    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd.join("sidecar/dist/compound-sidecar").join(exe_name));
        candidates.push(cwd.join("../sidecar/dist/compound-sidecar").join(exe_name));
    }
    candidates.into_iter().find(|p| p.exists())
}

/// 用户数据目录(与 sidecar_main.py 的 _data_dir 对齐,放日志)。
fn log_path(app: &tauri::AppHandle) -> PathBuf {
    app.path()
        .app_log_dir()
        .or_else(|_| app.path().app_data_dir())
        .unwrap_or_else(|_| std::env::temp_dir())
        .join("compound-sidecar.log")
}

fn spawn_sidecar(bin: &PathBuf, port: u16, log: &PathBuf) -> std::io::Result<Child> {
    if let Some(parent) = log.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let out = OpenOptions::new().create(true).append(true).open(log)?;
    let err = out.try_clone()?;
    let mut cmd = Command::new(bin);
    cmd.args(["--host", "127.0.0.1", "--port", &port.to_string()])
        .stdout(Stdio::from(out))
        .stderr(Stdio::from(err));
    if let Some(dir) = bin.parent() {
        cmd.current_dir(dir);
    }
    cmd.spawn()
}

struct SidecarState {
    child: Arc<Mutex<Option<Child>>>,
}

fn main() {
    let child_slot: Arc<Mutex<Option<Child>>> = Arc::new(Mutex::new(None));
    let child_for_state = child_slot.clone();

    tauri::Builder::default()
        .manage(SidecarState { child: child_for_state })
        .setup(move |app| {
            let handle = app.handle().clone();
            let port = free_port();
            let base = format!("http://127.0.0.1:{}", port);
            let log = log_path(&handle);

            // 启动 sidecar(拿到即存,供守护线程与退出清理)
            if let Some(bin) = sidecar_bin(&handle) {
                match spawn_sidecar(&bin, port, &log) {
                    Ok(c) => { *child_slot.lock().unwrap() = Some(c); }
                    Err(e) => { eprintln!("sidecar spawn failed: {e}"); }
                }

                // 守护线程:进程若退出则重启(端口不变,前端重试即恢复)。
                let slot = child_slot.clone();
                let bin_c = bin.clone();
                let log_c = log.clone();
                std::thread::spawn(move || loop {
                    std::thread::sleep(Duration::from_secs(3));
                    let mut g = slot.lock().unwrap();
                    let dead = match g.as_mut() {
                        Some(c) => matches!(c.try_wait(), Ok(Some(_)) | Err(_)),
                        None => true,
                    };
                    if dead {
                        if let Ok(c) = spawn_sidecar(&bin_c, port, &log_c) {
                            *g = Some(c);
                        }
                    }
                });
            } else {
                eprintln!("compound-sidecar 未找到(资源目录/开发回落均无)");
            }

            // 主窗口:注入本机 API 地址(api.js 的模块级 fetch 影子会读它)。
            let init = format!("window.__COMPOUND_API_BASE__ = {:?};", base);
            WebviewWindowBuilder::new(&handle, "main", WebviewUrl::default())
                .title("Compound")
                .inner_size(1440.0, 900.0)
                .min_inner_size(1080.0, 720.0)
                .resizable(true)
                .initialization_script(&init)
                .build()?;

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                // 退出时收掉 sidecar,别留孤儿进程。
                if let Some(state) = app.try_state::<SidecarState>() {
                    if let Ok(mut g) = state.child.lock() {
                        if let Some(mut c) = g.take() {
                            let _ = c.kill();
                        }
                    }
                }
            }
        });
}

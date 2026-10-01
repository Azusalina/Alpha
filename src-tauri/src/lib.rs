//! Alpha desktop shell.
//!
//! A Tauri 2 window with a narrow local brain command, no shell/filesystem
//! plugins or renderer workarounds. Spec 9 asks for WebKitGTK to be measured as it
//! is on the target machine, so nothing here tunes the web view in advance
//! (in particular no `WEBKIT_DISABLE_DMABUF_RENDERER` or similar); see
//! docs/DESKTOP_CHECK.md for the measurement procedure and fallbacks.

mod brain_host;
mod runtime_paths;

use brain_host::{BrainHost, HostConfig};
use serde_json::Value;
use std::{path::PathBuf, sync::Arc, time::Duration};
use tauri::Manager;

#[tauri::command]
async fn brain_call<R: tauri::Runtime>(
    window: tauri::WebviewWindow<R>,
    host: tauri::State<'_, Arc<BrainHost>>,
    request: Value,
) -> Result<Value, ()> {
    if window.label() != "main" {
        return Ok(brain_host::error(
            brain_host::request_id(&request),
            "MODEL_UNAVAILABLE",
            "brain command unavailable to this window",
        ));
    }
    let host = host.inner().clone();
    Ok(host.call(request).await)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            // Environment is a trusted desktop-launch configuration, never IPC.
            let (python, root) = if cfg!(debug_assertions) {
                let root = std::env::var_os("ALPHA_BRAIN_ROOT")
                    .map(PathBuf::from)
                    .unwrap_or_else(|| {
                        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                            .parent()
                            .unwrap()
                            .join("back-end-core")
                    });
                (std::env::var_os("ALPHA_BRAIN_PYTHON").unwrap_or_else(|| "python3".into()), root)
            } else {
                runtime_paths::release_paths(
                    &app.path().resource_dir()?.join("brain-runtime"),
                    std::env::var_os("ALPHA_BRAIN_PYTHON"),
                    std::env::var_os("ALPHA_BRAIN_ROOT"),
                )?
            };
            let db = match std::env::var_os("ALPHA_BRAIN_DB") {
                Some(path) => PathBuf::from(path),
                None => app.path().app_local_data_dir()?.join("brain.sqlite3"),
            };
            app.manage(Arc::new(BrainHost::new(HostConfig {
                python,
                root,
                db,
                request_timeout: Duration::from_secs(30),
            })));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![brain_call])
        .build(tauri::generate_context!())
        .expect("error while building the Alpha desktop shell")
        .run(|app, event| {
            if matches!(event, tauri::RunEvent::Exit) {
                tauri::async_runtime::block_on(app.state::<Arc<BrainHost>>().shutdown());
            }
        });
}

#[cfg(test)]
mod ipc_tests;

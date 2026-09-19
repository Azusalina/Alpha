//! Alpha desktop shell.
//!
//! A plain Tauri 2 window around the Vite front end: no commands, no plugins,
//! no environment workarounds. Spec 9 asks for WebKitGTK to be measured as it
//! is on the target machine, so nothing here tunes the web view in advance
//! (in particular no `WEBKIT_DISABLE_DMABUF_RENDERER` or similar); see
//! docs/DESKTOP_CHECK.md for the measurement procedure and fallbacks.

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running the Alpha desktop shell");
}

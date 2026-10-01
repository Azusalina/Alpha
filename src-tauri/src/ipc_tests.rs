use super::*;
use serde_json::json;

#[test]
fn tauri_command_routes_local_main_and_acl_rejects_other_windows_and_remote_origins() {
    let temp = tempfile::TempDir::new().unwrap();
    let host = Arc::new(BrainHost::new(HostConfig {
        python: "python3".into(),
        root: PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .join("back-end-core"),
        db: temp.path().join("brain.sqlite3"),
        request_timeout: Duration::from_secs(10),
    }));
    let app = tauri::test::mock_builder()
        .manage(host.clone())
        .invoke_handler(tauri::generate_handler![brain_call])
        .build(tauri::generate_context!())
        .unwrap();
    let main = tauri::WebviewWindowBuilder::new(&app, "main", Default::default())
        .build()
        .unwrap();
    let other = tauri::WebviewWindowBuilder::new(&app, "other", Default::default())
        .build()
        .unwrap();
    let invoke = |cmd: &str, url: &str, body: Value| tauri::webview::InvokeRequest {
        cmd: cmd.into(),
        callback: tauri::ipc::CallbackFn(0),
        error: tauri::ipc::CallbackFn(1),
        url: url.parse().unwrap(),
        body: tauri::ipc::InvokeBody::Json(body),
        headers: Default::default(),
        invoke_key: tauri::test::INVOKE_KEY.to_string(),
    };
    let local = if cfg!(windows) {
        "http://tauri.localhost"
    } else {
        "tauri://localhost"
    };
    let body = json!({"request":{"schema_version":1,"id":"ipc","method":"health","params":{}}});
    let response = tauri::test::get_ipc_response(&main, invoke("brain_call", local, body.clone()))
        .unwrap()
        .deserialize::<Value>()
        .unwrap();
    assert_eq!(response["ok"], true, "{response}");
    assert_eq!(response["id"], "ipc");
    assert!(
        tauri::test::get_ipc_response(&other, invoke("brain_call", local, body.clone())).is_err()
    );
    assert!(tauri::test::get_ipc_response(
        &main,
        invoke("brain_call", "https://example.invalid", body)
    )
    .is_err());
    assert!(
        tauri::test::get_ipc_response(&main, invoke("plugin:app|name", local, json!({}))).is_err()
    );
    assert!(tauri::test::get_ipc_response(
        &main,
        invoke("plugin:app|tauri_version", local, json!({}))
    )
    .is_ok());
    tauri::async_runtime::block_on(host.shutdown());
}

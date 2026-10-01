fn main() {
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(tauri_build::AppManifest::new().commands(&["brain_call"])),
    )
    .expect("could not build the desktop command ACL")
}

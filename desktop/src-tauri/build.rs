fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&["get_runtime_info", "check_python_worker"]),
    ))
    .expect("failed to build Tauri permissions");
}

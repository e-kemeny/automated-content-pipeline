fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "get_runtime_info",
            "check_python_worker",
            "start_diagnostic_job",
            "get_job_state",
            "start_processing_job",
            "select_source_video",
            "select_output_workspace",
            "get_media_selection",
            "cancel_diagnostic_job",
        ]),
    ))
    .expect("failed to build Tauri permissions");
}

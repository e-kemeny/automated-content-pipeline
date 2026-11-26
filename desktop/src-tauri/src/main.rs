#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod runtime;
mod worker;

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            runtime::get_runtime_info,
            worker::check_python_worker
        ])
        .run(tauri::generate_context!())
        .expect("failed to run Content Pipeline");
}

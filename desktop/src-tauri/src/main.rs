#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod jobs;
mod runtime;
mod worker;

use std::sync::Arc;
use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .manage(Arc::new(jobs::Supervisor::default()))
        .invoke_handler(tauri::generate_handler![
            runtime::get_runtime_info,
            worker::check_python_worker,
            jobs::start_diagnostic_job,
            jobs::get_job_state,
            jobs::cancel_diagnostic_job
        ])
        .build(tauri::generate_context!())
        .expect("failed to build Content Pipeline")
        .run(|app, event| {
            if let tauri::RunEvent::ExitRequested { api, .. } = event {
                let supervisor = app.state::<Arc<jobs::Supervisor>>().inner().clone();
                if supervisor.shutdown() {
                    api.prevent_exit();
                    let app = app.clone();
                    tauri::async_runtime::spawn_blocking(move || {
                        supervisor.wait_stopped();
                        app.exit(0);
                    });
                }
            }
        });
}

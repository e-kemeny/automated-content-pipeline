#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeInfo {
    application_version: String,
    operating_system: &'static str,
    cpu_architecture: &'static str,
    native_runtime_available: bool,
}

fn runtime_info(version: String) -> RuntimeInfo {
    RuntimeInfo {
        application_version: version,
        operating_system: std::env::consts::OS,
        cpu_architecture: std::env::consts::ARCH,
        native_runtime_available: true,
    }
}

#[tauri::command]
pub fn get_runtime_info(app: tauri::AppHandle) -> RuntimeInfo {
    runtime_info(app.package_info().version.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn reports_host_and_supplied_application_version() {
        let info = runtime_info("0.1.0".to_string());
        assert_eq!(info.application_version, "0.1.0");
        assert_eq!(info.operating_system, std::env::consts::OS);
        assert_eq!(info.cpu_architecture, std::env::consts::ARCH);
        assert!(info.native_runtime_available);
    }
}

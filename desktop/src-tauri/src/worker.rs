use serde::{Deserialize, Serialize};
use std::{
    ffi::OsString,
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicU64, Ordering},
        Mutex,
    },
    thread,
    time::{Duration, Instant},
};
use tauri::Manager;

const TIMEOUT: Duration = Duration::from_secs(5);
const OUTPUT_LIMIT: u64 = 65536;
static REQUEST_ID: AtomicU64 = AtomicU64::new(1);
static IN_FLIGHT: Mutex<()> = Mutex::new(());

#[derive(Debug, Serialize)]
pub struct WorkerError {
    code: String,
    message: String,
    stderr: String,
}
fn error(code: &str, message: impl ToString) -> WorkerError {
    WorkerError {
        code: code.into(),
        message: message.to_string(),
        stderr: String::new(),
    }
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct WorkerHealth {
    python_version: String,
    operating_system: String,
    cpu_architecture: String,
    worker_protocol_version: u32,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ProtocolError {
    code: String,
    message: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Response {
    request_id: String,
    protocol_version: u32,
    command: String,
    status: String,
    data: Option<WorkerHealth>,
    error: Option<ProtocolError>,
}

fn validate_response(bytes: &[u8], request_id: &str) -> Result<WorkerHealth, WorkerError> {
    let value: serde_json::Value =
        serde_json::from_slice(bytes).map_err(|e| error("invalid_response", e))?;
    // Require even nullable fields; serde Option alone accepts absent keys.
    let fields = [
        "request_id",
        "protocol_version",
        "command",
        "status",
        "data",
        "error",
    ];
    if !value
        .as_object()
        .is_some_and(|v| v.len() == fields.len() && fields.iter().all(|k| v.contains_key(*k)))
    {
        return Err(error(
            "invalid_response",
            "Missing or unexpected protocol fields",
        ));
    }
    let response: Response =
        serde_json::from_value(value).map_err(|e| error("invalid_response", e))?;
    if response.request_id != request_id
        || response.protocol_version != 1
        || response.command != "health_check"
    {
        return Err(error(
            "invalid_response",
            "Worker response identity/version mismatch",
        ));
    }
    match (response.status.as_str(), response.data, response.error) {
        ("ok", Some(data), None)
            if data.worker_protocol_version == 1
                && !data.python_version.trim().is_empty()
                && !data.operating_system.trim().is_empty()
                && !data.cpu_architecture.trim().is_empty() =>
        {
            Ok(data)
        }
        ("error", None, Some(e)) if !e.code.is_empty() && !e.message.is_empty() => {
            Err(error("worker_error", format!("{}: {}", e.code, e.message)))
        }
        _ => Err(error(
            "invalid_response",
            "Invalid worker status or health data",
        )),
    }
}

fn interpreter(
    override_path: Option<OsString>,
    virtual_env: Option<OsString>,
) -> Result<PathBuf, WorkerError> {
    if let Some(path) = override_path {
        let path = PathBuf::from(path);
        if !path.is_absolute() || !path.is_file() {
            return Err(error(
                "python_missing",
                "CONTENT_PIPELINE_PYTHON must name an existing absolute executable path",
            ));
        }
        return Ok(path);
    }
    if let Some(root) = virtual_env {
        let path = PathBuf::from(root).join(if cfg!(windows) {
            "Scripts/python.exe"
        } else {
            "bin/python"
        });
        if !path.is_absolute() || !path.is_file() {
            return Err(error(
                "python_missing",
                "VIRTUAL_ENV has no valid Python executable",
            ));
        }
        return Ok(path);
    }
    Ok(PathBuf::from(if cfg!(windows) {
        "python.exe"
    } else {
        "python3"
    }))
}

// Own the child until wait completes, including every early-return/error path.
struct ManagedChild(Child);
impl Drop for ManagedChild {
    fn drop(&mut self) {
        if !matches!(self.0.try_wait(), Ok(Some(_))) {
            let _ = self.0.kill();
        }
        let _ = self.0.wait();
    }
}

#[cfg(windows)]
mod job {
    use super::*;
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::{
        Foundation::{CloseHandle, HANDLE},
        System::JobObjects::*,
    };
    pub struct Job(HANDLE);
    impl Job {
        pub fn attach(child: &Child) -> Result<Self, WorkerError> {
            // The non-inheritable handle dies with this process. Windows then kills
            // the worker even if the application closes before the health timeout.
            unsafe {
                let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
                if handle.is_null() {
                    return Err(error("process_guard", std::io::Error::last_os_error()));
                }
                let job = Self(handle);
                let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
                limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                if SetInformationJobObject(
                    handle,
                    JobObjectExtendedLimitInformation,
                    &limits as *const _ as *const _,
                    std::mem::size_of_val(&limits) as u32,
                ) == 0
                    || AssignProcessToJobObject(handle, child.as_raw_handle()) == 0
                {
                    return Err(error("process_guard", std::io::Error::last_os_error()));
                }
                Ok(job)
            }
        }
    }
    impl Drop for Job {
        fn drop(&mut self) {
            unsafe {
                CloseHandle(self.0);
            }
        }
    }
}

fn wait_bounded(
    child: &mut Child,
    timeout: Duration,
) -> Result<std::process::ExitStatus, WorkerError> {
    let start = Instant::now();
    loop {
        if let Some(status) = child.try_wait().map_err(|e| error("process_error", e))? {
            return Ok(status);
        }
        if start.elapsed() >= timeout {
            child.kill().map_err(|e| error("cleanup_failed", e))?;
            child.wait().map_err(|e| error("cleanup_failed", e))?;
            return Err(error(
                "timeout",
                "Python worker exceeded its time limit and was terminated",
            ));
        }
        thread::sleep(Duration::from_millis(10));
    }
}

fn read_limited(pipe: impl Read) -> std::io::Result<Vec<u8>> {
    let mut bytes = Vec::new();
    pipe.take(OUTPUT_LIMIT + 1).read_to_end(&mut bytes)?;
    Ok(bytes)
}

fn execute(
    mut command: Command,
    request: &[u8],
    request_id: &str,
    timeout: Duration,
) -> Result<WorkerHealth, WorkerError> {
    command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000); // CREATE_NO_WINDOW, never a shell
    }
    let mut child = ManagedChild(
        command
            .spawn()
            .map_err(|e| error("python_launch_failed", e))?,
    );
    #[cfg(windows)]
    let process_job = job::Job::attach(&child.0)?;
    let stdout = child
        .0
        .stdout
        .take()
        .ok_or_else(|| error("process_error", "Missing stdout"))?;
    let stderr = child
        .0
        .stderr
        .take()
        .ok_or_else(|| error("process_error", "Missing stderr"))?;
    let out = thread::spawn(move || read_limited(stdout));
    let err = thread::spawn(move || read_limited(stderr));
    let write_result = child
        .0
        .stdin
        .take()
        .ok_or_else(|| error("process_error", "Missing stdin"))
        .and_then(|mut stdin| {
            stdin
                .write_all(request)
                .map_err(|e| error("process_error", e))
        });
    // Dropped stdin signals EOF. The application supplies only a small fixed request.
    let status = if write_result.is_ok() {
        wait_bounded(&mut child.0, timeout)
    } else {
        write_result.map(|_| unreachable!())
    };
    drop(child); // kill/reap before joining readers, including on errors
    #[cfg(windows)]
    drop(process_job);
    let stdout = out
        .join()
        .map_err(|_| error("process_error", "stdout reader failed"))?
        .map_err(|e| error("process_error", e))?;
    let stderr = err
        .join()
        .map_err(|_| error("process_error", "stderr reader failed"))?
        .map_err(|e| error("process_error", e))?;
    let diagnostics = String::from_utf8_lossy(&stderr).into_owned();
    let result = status.and_then(|status| {
        if !status.success() {
            return Err(error(
                "python_exit_failed",
                format!("Python exited with {status}"),
            ));
        }
        if stdout.len() as u64 > OUTPUT_LIMIT || stderr.len() as u64 > OUTPUT_LIMIT {
            return Err(error(
                "invalid_response",
                "Worker output exceeds size limit",
            ));
        }
        validate_response(&stdout, request_id)
    });
    result.map_err(|mut e| {
        e.stderr = diagnostics;
        e
    })
}

fn check(path: &Path) -> Result<WorkerHealth, WorkerError> {
    // Only the shipped worker is executable, not a path/code string supplied by React.
    if std::fs::read(path).map_err(|e| error("worker_missing", e))?
        != include_bytes!("../../worker/worker.py")
    {
        return Err(error(
            "worker_mismatch",
            "Worker resource does not match this application build",
        ));
    }
    let python = interpreter(
        std::env::var_os("CONTENT_PIPELINE_PYTHON"),
        std::env::var_os("VIRTUAL_ENV"),
    )?;
    let id = format!("health-{}", REQUEST_ID.fetch_add(1, Ordering::Relaxed));
    let request =
        serde_json::json!({"request_id": id, "protocol_version": 1, "command": "health_check"})
            .to_string();
    let mut command = Command::new(python);
    command.arg("-I").arg("-B").arg(path);
    execute(command, request.as_bytes(), &id, TIMEOUT)
}

#[tauri::command]
pub async fn check_python_worker(app: tauri::AppHandle) -> Result<WorkerHealth, WorkerError> {
    let path = app
        .path()
        .resolve("worker/worker.py", tauri::path::BaseDirectory::Resource)
        .map_err(|e| error("worker_missing", e))?;
    tauri::async_runtime::spawn_blocking(move || {
        let _guard = IN_FLIGHT
            .try_lock()
            .map_err(|_| error("busy", "Worker health check already running"))?;
        check(&path)
    })
    .await
    .map_err(|e| error("process_error", e))?
}

#[cfg(test)]
mod tests {
    use super::*;
    fn python() -> PathBuf {
        interpreter(
            std::env::var_os("CONTENT_PIPELINE_PYTHON"),
            std::env::var_os("VIRTUAL_ENV"),
        )
        .unwrap()
    }
    fn fixture(code: &str, timeout: Duration) -> Result<WorkerHealth, WorkerError> {
        let mut command = Command::new(python());
        command.args(["-I", "-B", "-c", code]);
        execute(command, b"{}", "test", timeout)
    }
    #[test]
    fn real_worker_health() {
        let result =
            check(&PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../worker/worker.py")).unwrap();
        assert_eq!(result.worker_protocol_version, 1);
        assert!(!result.python_version.is_empty());
    }
    #[test]
    fn missing_interpreter() {
        assert!(interpreter(Some(OsString::from("relative.exe")), None).is_err());
        let command = Command::new("content-pipeline-nonexistent-python-executable");
        assert_eq!(
            execute(command, b"{}", "test", TIMEOUT).unwrap_err().code,
            "python_launch_failed"
        );
    }
    #[test]
    fn invalid_response() {
        for bytes in [b"oops".as_slice(), b"{}", b"[]"] {
            assert_eq!(
                validate_response(bytes, "test").unwrap_err().code,
                "invalid_response"
            );
        }
        assert_eq!(
            fixture("print('not json')", TIMEOUT).unwrap_err().code,
            "invalid_response"
        );
    }
    #[test]
    fn mismatched_response() {
        let response = serde_json::json!({"request_id":"wrong","protocol_version":1,"command":"health_check","status":"ok","data":null,"error":null});
        assert!(validate_response(response.to_string().as_bytes(), "test").is_err());
    }
    #[test]
    fn nonzero_exit_captures_diagnostics() {
        let e = fixture(
            "import sys; print('diagnostic', file=sys.stderr); sys.exit(2)",
            TIMEOUT,
        )
        .unwrap_err();
        assert_eq!(e.code, "python_exit_failed");
        assert!(e.stderr.contains("diagnostic"));
    }
    #[test]
    fn timeout_terminates_and_reaps_real_process() {
        let mut command = Command::new(python());
        command.args(["-I", "-c", "import time; time.sleep(60)"]);
        let mut child = ManagedChild(command.spawn().unwrap());
        let start = Instant::now();
        assert_eq!(
            wait_bounded(&mut child.0, Duration::from_millis(50))
                .unwrap_err()
                .code,
            "timeout"
        );
        assert!(child.0.try_wait().unwrap().is_some());
        assert!(start.elapsed() < Duration::from_secs(3));
    }
    #[test]
    fn timeout_adapter_returns_without_hanging_readers() {
        assert_eq!(
            fixture("import time; time.sleep(60)", Duration::from_millis(50))
                .unwrap_err()
                .code,
            "timeout"
        );
    }
    #[test]
    fn changed_or_missing_worker_rejected() {
        assert_eq!(
            check(Path::new("nonexistent-worker.py")).unwrap_err().code,
            "worker_missing"
        );
        assert_eq!(
            check(&PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("Cargo.toml"))
                .unwrap_err()
                .code,
            "worker_mismatch"
        );
    }
}

#[cfg(test)]
mod lifecycle_tests {
    use super::*;
    #[test]
    fn validates_full_protocol_and_failure_envelope() {
        let valid = serde_json::json!({"request_id":"test","protocol_version":1,"command":"health_check","status":"ok",
            "data":{"pythonVersion":"3.14.0","operatingSystem":"Windows","cpuArchitecture":"AMD64","workerProtocolVersion":1},"error":null});
        assert!(validate_response(valid.to_string().as_bytes(), "test").is_ok());
        for (field, value) in [
            ("protocol_version", serde_json::json!(2)),
            ("command", serde_json::json!("export")),
            ("status", serde_json::json!("unknown")),
            ("data", serde_json::json!({})),
            ("error", serde_json::json!({"code":"bad","message":"bad"})),
        ] {
            let mut invalid = valid.clone();
            invalid[field] = value;
            assert!(validate_response(invalid.to_string().as_bytes(), "test").is_err());
        }
        let failure = serde_json::json!({"request_id":"test","protocol_version":1,"command":"health_check","status":"error",
            "data":null,"error":{"code":"unsupported_version","message":"unsupported"}});
        assert_eq!(
            validate_response(failure.to_string().as_bytes(), "test")
                .unwrap_err()
                .code,
            "worker_error"
        );
    }
    #[test]
    fn interpreter_resolution() {
        let executable = std::env::current_exe().unwrap();
        assert_eq!(
            interpreter(
                Some(executable.clone().into_os_string()),
                Some("missing".into())
            )
            .unwrap(),
            executable
        );
        assert!(interpreter(None, Some("missing".into())).is_err());
        assert_eq!(
            interpreter(None, None).unwrap(),
            PathBuf::from(if cfg!(windows) {
                "python.exe"
            } else {
                "python3"
            })
        );
    }
    #[cfg(windows)]
    #[test]
    fn closing_job_terminates_real_worker() {
        let mut command = Command::new(
            interpreter(
                std::env::var_os("CONTENT_PIPELINE_PYTHON"),
                std::env::var_os("VIRTUAL_ENV"),
            )
            .unwrap(),
        );
        command.args(["-I", "-c", "import time; time.sleep(60)"]);
        let mut child = ManagedChild(command.spawn().unwrap());
        let job = job::Job::attach(&child.0).unwrap();
        assert!(child.0.try_wait().unwrap().is_none());
        drop(job);
        // Windows job-close termination may report exit code zero. Verify that
        // the sleeping process actually exits/reaps without our timeout kill.
        wait_bounded(&mut child.0, Duration::from_secs(2)).unwrap();
        assert!(child.0.try_wait().unwrap().is_some());
    }
}

use crate::worker::{self, error, ManagedChild, WorkerError};
use serde::{Deserialize, Serialize};
use std::{
    io::{BufRead, BufReader, Read, Write},
    path::PathBuf,
    process::{Command, Stdio},
    sync::{mpsc, Arc, Mutex},
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tauri::{Emitter, Manager, State};

const JOB_TIMEOUT: Duration = Duration::from_secs(30);
const LINE_LIMIT: u64 = 4096;
const EVENT_NAME: &str = "diagnostic-job";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum Phase {
    Idle,
    Starting,
    Running,
    Cancelling,
    Completed,
    Cancelled,
    Failed,
}
impl Phase {
    pub fn active(self) -> bool {
        matches!(self, Self::Starting | Self::Running | Self::Cancelling)
    }
}
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Progress {
    pub completed: u32,
    pub total: u32,
}
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Snapshot {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub processing: Option<crate::processing::Processing>,
    pub job_id: Option<String>,
    pub revision: u64,
    pub state: Phase,
    pub stage: String,
    pub started_at: Option<u64>,
    pub finished_at: Option<u64>,
    pub progress: Progress,
    pub error: Option<WorkerError>,
}
struct Inner {
    snapshot: Snapshot,
    closing: bool,
    generation: u64,
    pending_artifacts: Vec<crate::processing::Artifact>,
}
pub struct Supervisor {
    inner: Mutex<Inner>,
    session: u128,
}
fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}
impl Default for Supervisor {
    fn default() -> Self {
        Self {
            inner: Mutex::new(Inner {
                snapshot: Snapshot {
                    processing: None,
                    job_id: None,
                    revision: 0,
                    state: Phase::Idle,
                    stage: "Idle".into(),
                    started_at: None,
                    finished_at: None,
                    progress: Progress {
                        completed: 0,
                        total: 12,
                    },
                    error: None,
                },
                closing: false,
                generation: 0,
                pending_artifacts: vec![],
            }),
            session: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos(),
        }
    }
}
impl Supervisor {
    pub fn snapshot(&self) -> Snapshot {
        self.inner.lock().unwrap().snapshot.clone()
    }
    fn reserve(&self) -> Result<Snapshot, WorkerError> {
        let mut inner = self.inner.lock().unwrap();
        if inner.closing {
            return Err(error("shutting_down", "Application is closing"));
        }
        if inner.snapshot.state.active() {
            return Err(error("job_busy", "A diagnostic job is already active"));
        }
        inner.generation += 1;
        inner.pending_artifacts.clear();
        inner.snapshot = Snapshot {
            processing: None,
            job_id: Some(format!("diagnostic-{}-{}", self.session, inner.generation)),
            revision: inner.snapshot.revision + 1,
            state: Phase::Starting,
            stage: "Starting".into(),
            started_at: Some(now()),
            finished_at: None,
            progress: Progress {
                completed: 0,
                total: 12,
            },
            error: None,
        };
        Ok(inner.snapshot.clone())
    }
    fn cancel(&self, id: &str) -> Result<Snapshot, WorkerError> {
        let mut inner = self.inner.lock().unwrap();
        if inner.snapshot.job_id.as_deref() != Some(id) {
            return Err(error("stale_job", "Job identity no longer matches"));
        }
        if matches!(inner.snapshot.state, Phase::Starting | Phase::Running) {
            inner.snapshot.state = Phase::Cancelling;
            inner.snapshot.stage = "Cancelling".into();
            inner.snapshot.revision += 1;
        }
        Ok(inner.snapshot.clone())
    }
    fn cancelled(&self, id: &str) -> bool {
        let inner = self.inner.lock().unwrap();
        inner.closing
            || inner.snapshot.job_id.as_deref() != Some(id)
            || inner.snapshot.state == Phase::Cancelling
    }
    fn progress(&self, id: &str, message: &Message) -> Option<Snapshot> {
        let mut inner = self.inner.lock().unwrap();
        let s = &mut inner.snapshot;
        if s.job_id.as_deref() != Some(id) || !matches!(s.state, Phase::Starting | Phase::Running) {
            return None;
        }
        s.state = Phase::Running;
        s.stage = message.stage.clone();
        s.progress.completed = message.completed;
        s.revision += 1;
        Some(s.clone())
    }
    fn finish(&self, id: &str, result: Result<(), WorkerError>) -> Snapshot {
        let mut inner = self.inner.lock().unwrap();
        if inner.snapshot.job_id.as_deref() != Some(id) || !inner.snapshot.state.active() {
            return inner.snapshot.clone();
        }
        let artifacts = std::mem::take(&mut inner.pending_artifacts);
        let s = &mut inner.snapshot;
        // Whichever operation acquires this lock first wins the cancellation/finish race.
        // Terminal publication only happens after process and reader cleanup.
        if s.state == Phase::Cancelling {
            s.state = Phase::Cancelled;
            s.error = None;
        } else if let Err(e) = result {
            s.state = Phase::Failed;
            s.error = Some(e);
        } else if s.state != Phase::Running
            || (s.processing.is_none() && s.progress.completed != 12)
            || (s.processing.is_some() && artifacts.is_empty())
        {
            s.state = Phase::Failed;
            s.error = Some(error(
                "invalid_transition",
                "Completion requires all reported checks",
            ));
        } else {
            s.state = Phase::Completed;
            if let Some(p) = &mut s.processing {
                p.artifacts = artifacts;
            }
        }
        s.stage = format!("{:?}", s.state);
        s.finished_at = Some(now().max(s.started_at.unwrap_or_default()));
        s.revision += 1;
        s.clone()
    }
    pub fn shutdown(&self) -> bool {
        let mut inner = self.inner.lock().unwrap();
        if inner.closing {
            return false;
        }
        inner.closing = true;
        if inner.snapshot.state.active() {
            inner.snapshot.state = Phase::Cancelling;
            inner.snapshot.stage = "Cancelling".into();
            inner.snapshot.revision += 1;
            true
        } else {
            false
        }
    }
    pub fn wait_stopped(&self) {
        let start = Instant::now();
        while self.snapshot().state.active()
            && start.elapsed() < JOB_TIMEOUT + Duration::from_secs(2)
        {
            thread::sleep(Duration::from_millis(10));
        }
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct MessageError {
    code: String,
    message: String,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Message {
    protocol_version: u32,
    request_id: String,
    job_id: String,
    command: String,
    sequence: u32,
    event: String,
    stage: String,
    completed: u32,
    total: u32,
    error: Option<MessageError>,
}
#[derive(Default)]
struct Stream {
    sequence: u32,
    completed: u32,
    done: bool,
}
impl Stream {
    fn accept(&mut self, line: &[u8], id: &str) -> Result<Message, WorkerError> {
        let value: serde_json::Value =
            serde_json::from_slice(line).map_err(|e| error("invalid_message", e))?;
        if !value
            .as_object()
            .is_some_and(|v| v.len() == 10 && v.contains_key("error"))
        {
            return Err(error("invalid_message", "Missing event fields"));
        }
        let m: Message = serde_json::from_value(value).map_err(|e| error("invalid_message", e))?;
        if self.done
            || m.protocol_version != 1
            || m.request_id != id
            || m.job_id != id
            || m.command != "diagnostic_job"
            || m.sequence != self.sequence + 1
            || m.sequence > 14
            || m.total != 12
        {
            return Err(error(
                "invalid_message",
                "Event identity/version/order mismatch",
            ));
        }
        let valid = match m.event.as_str() {
            "started" => {
                self.sequence == 0
                    && m.completed == 0
                    && m.stage == "Interpreter"
                    && m.error.is_none()
            }
            "progress" => {
                self.sequence > 0
                    && m.completed == self.completed + 1
                    && m.completed <= 12
                    && m.stage
                        == ["Interpreter", "Protocol", "Checksum"][((m.completed - 1) / 4) as usize]
                    && m.error.is_none()
            }
            "completed" => {
                self.completed == 12
                    && m.completed == 12
                    && m.stage == "Finished"
                    && m.error.is_none()
            }
            "failed" => {
                m.completed == self.completed
                    && m.stage == "Failed"
                    && m.error
                        .as_ref()
                        .is_some_and(|e| !e.code.is_empty() && !e.message.is_empty())
            }
            _ => false,
        };
        if !valid {
            return Err(error(
                "invalid_message",
                "Invalid diagnostic stage/progress",
            ));
        }
        self.sequence = m.sequence;
        self.completed = m.completed;
        self.done = matches!(m.event.as_str(), "completed" | "failed");
        Ok(m)
    }
}

enum Pipe {
    Line(Vec<u8>),
    End,
    Error(String),
}
fn read_events(pipe: impl Read, tx: mpsc::SyncSender<Pipe>) {
    read_events_limit(pipe, tx, LINE_LIMIT)
}
fn read_events_limit(pipe: impl Read, tx: mpsc::SyncSender<Pipe>, limit: u64) {
    let mut reader = BufReader::new(pipe);
    loop {
        let mut line = Vec::new();
        match (&mut reader).take(limit + 1).read_until(b'\n', &mut line) {
            Ok(0) => {
                let _ = tx.send(Pipe::End);
                return;
            }
            Ok(_) if line.len() as u64 > limit || !line.ends_with(b"\n") => {
                let _ = tx.send(Pipe::Error("Oversized or unterminated event".into()));
                return;
            }
            Ok(_) => {
                if tx.send(Pipe::Line(line)).is_err() {
                    return;
                }
            }
            Err(e) => {
                let _ = tx.send(Pipe::Error(e.to_string()));
                return;
            }
        }
    }
}
fn execute_job(
    supervisor: &Supervisor,
    id: &str,
    command: Command,
    timeout: Duration,
    publish: &impl Fn(Snapshot),
) -> Result<(), WorkerError> {
    execute(supervisor, id, command, timeout, publish, None)
}
fn drain_diagnostics(mut pipe: impl Read) -> std::io::Result<Vec<u8>> {
    let mut kept = Vec::new();
    let mut block = [0u8; 8192];
    loop {
        let n = pipe.read(&mut block)?;
        if n == 0 {
            return Ok(kept);
        }
        let take = n.min(65536 - kept.len());
        kept.extend_from_slice(&block[..take]);
    }
}
fn execute(
    supervisor: &Supervisor,
    id: &str,
    mut command: Command,
    timeout: Duration,
    publish: &impl Fn(Snapshot),
    config: Option<&crate::media::Config>,
) -> Result<(), WorkerError> {
    if supervisor.cancelled(id) {
        return Ok(());
    }
    command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = ManagedChild(
        command
            .spawn()
            .map_err(|e| error("python_launch_failed", e))?,
    );
    #[cfg(windows)]
    let process_job = worker::job::Job::attach(&child.0)?;
    let (tx, rx) = mpsc::sync_channel(16);
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
    let processing = config.is_some();
    let out = thread::spawn(move || {
        if processing {
            read_events_limit(stdout, tx, 65536)
        } else {
            read_events(stdout, tx)
        }
    });
    let err = thread::spawn(move || {
        if processing {
            drain_diagnostics(stderr)
        } else {
            worker::read_limited(stderr)
        }
    });
    let mut processing_stream = config.map(|c| crate::processing::Stream::new(&c.mode));
    let result = (|| {
        if supervisor.cancelled(id) {
            return Ok(());
        }
        let request = if let Some(config)=config {serde_json::json!({"request_id":id,"job_id":id,"protocol_version":1,"command":"process_video","config":config})} else {serde_json::json!({"request_id":id,"job_id":id,"protocol_version":1,"command":"diagnostic_job"})}.to_string();
        child
            .0
            .stdin
            .take()
            .ok_or_else(|| error("process_error", "Missing stdin"))?
            .write_all(request.as_bytes())
            .map_err(|e| error("process_error", e))?;
        let start = Instant::now();
        let mut stream = Stream::default();
        let mut eof = false;
        loop {
            if supervisor.cancelled(id) {
                return Ok(());
            }
            if start.elapsed() >= timeout {
                return Err(error("timeout", "Diagnostic job exceeded its time limit"));
            }
            match rx.recv_timeout(Duration::from_millis(20)) {
                Ok(Pipe::Line(line)) => {
                    if let (Some(process), Some(config)) = (&mut processing_stream, config) {
                        let stage = process.accept(&line, id, config)?;
                        let snapshot = {
                            let mut inner = supervisor.inner.lock().unwrap();
                            let s = &mut inner.snapshot;
                            if matches!(s.state, Phase::Starting | Phase::Running) {
                                s.state = Phase::Running;
                                s.stage = stage;
                                s.revision += 1;
                                Some(s.clone())
                            } else {
                                None
                            }
                        };
                        if let Some(s) = snapshot {
                            publish(s)
                        }
                        continue;
                    }
                    let m = stream.accept(&line, id)?;
                    if let Some(e) = &m.error {
                        return Err(error("worker_failed", format!("{}: {}", e.code, e.message)));
                    }
                    if let Some(snapshot) = supervisor.progress(id, &m) {
                        publish(snapshot);
                    }
                }
                Ok(Pipe::Error(e)) => return Err(error("invalid_message", e)),
                Ok(Pipe::End) | Err(mpsc::RecvTimeoutError::Disconnected) => eof = true,
                Err(mpsc::RecvTimeoutError::Timeout) => {}
            }
            if let Some(status) = child.0.try_wait().map_err(|e| error("process_error", e))? {
                if !status.success() {
                    return Err(error(
                        "worker_exit",
                        format!("Diagnostic exited with {status}"),
                    ));
                }
                if eof {
                    return if processing_stream.as_ref().map_or(stream.done, |s| s.done) {
                        Ok(())
                    } else {
                        Err(error("unexpected_exit", "Worker exited without completion"))
                    };
                }
            }
            if eof {
                thread::sleep(Duration::from_millis(10));
            }
        }
    })();
    // Terminal state is not published until the child, descendants and readers are gone.
    drop(child);
    #[cfg(windows)]
    drop(process_job);
    drop(rx); // unblock a reader waiting to send into the bounded channel
    let out_result = out.join();
    let diagnostics = err
        .join()
        .map_err(|_| error("process_error", "stderr reader failed"))?
        .map_err(|e| error("process_error", e))?;
    let result = if out_result.is_err() {
        Err(error("process_error", "stdout reader failed"))
    } else if diagnostics.len() > 65536 {
        Err(error("output_limit", "Diagnostic stderr exceeds limit"))
    } else {
        result
    };
    if result.is_ok() {
        if let Some(stream) = processing_stream {
            if stream.done {
                supervisor.inner.lock().unwrap().pending_artifacts = stream.artifacts;
            }
        }
    }
    result.map_err(|mut e| {
        e.stderr = String::from_utf8_lossy(&diagnostics).into_owned();
        e
    })
}
fn publish(app: &tauri::AppHandle, snapshot: Snapshot) {
    // Full snapshots with a globally increasing revision tolerate reordered delivery.
    if let Err(e) = app.emit_to("main", EVENT_NAME, snapshot) {
        eprintln!("Job event delivery failed: {e}");
    }
}
#[tauri::command]
pub fn get_job_state(supervisor: State<'_, Arc<Supervisor>>) -> Snapshot {
    supervisor.snapshot()
}
#[tauri::command]
pub fn cancel_diagnostic_job(
    app: tauri::AppHandle,
    supervisor: State<'_, Arc<Supervisor>>,
    job_id: String,
) -> Result<Snapshot, WorkerError> {
    let snapshot = supervisor.cancel(&job_id)?;
    publish(&app, snapshot.clone());
    Ok(snapshot)
}
#[tauri::command]
pub fn start_diagnostic_job(
    app: tauri::AppHandle,
    supervisor: State<'_, Arc<Supervisor>>,
) -> Result<Snapshot, WorkerError> {
    let snapshot = supervisor.reserve()?;
    publish(&app, snapshot.clone());
    let supervisor = supervisor.inner().clone();
    let id = snapshot.job_id.clone().unwrap();
    tauri::async_runtime::spawn_blocking(move || {
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            if supervisor.cancelled(&id) {
                return Ok(());
            }
            let path: PathBuf = app
                .path()
                .resolve("worker/worker.py", tauri::path::BaseDirectory::Resource)
                .map_err(|e| error("worker_missing", e))?;
            let command = worker::command_for_worker(&path)?;
            execute_job(&supervisor, &id, command, JOB_TIMEOUT, &|s| {
                publish(&app, s)
            })
        }))
        .unwrap_or_else(|_| Err(error("supervisor_error", "Diagnostic supervisor panicked")));
        publish(&app, supervisor.finish(&id, result));
    });
    Ok(snapshot)
}

#[cfg(test)]
#[path = "jobs_tests.rs"]
mod tests;

#[tauri::command]
pub fn start_processing_job(
    app: tauri::AppHandle,
    supervisor: State<'_, Arc<Supervisor>>,
    selection: State<'_, crate::media::MediaSelection>,
    mode: String,
) -> Result<Snapshot, WorkerError> {
    let selected = selection.0.lock().unwrap().clone();
    let mut config = crate::media::configuration(&selected, &mode, "preflight")?;
    let reserved = supervisor.reserve()?;
    let id = reserved.job_id.unwrap();
    config.workspace = std::path::Path::new(selected.output.as_ref().unwrap())
        .join(format!("content-pipeline-{id}"))
        .to_string_lossy()
        .into();
    let snapshot = {
        let mut inner = supervisor.inner.lock().unwrap();
        inner.snapshot.processing = Some(crate::processing::Processing {
            workspace: config.workspace.clone(),
            mode: mode.clone(),
            artifacts: vec![],
        });
        inner.snapshot.progress.total = 0;
        inner.snapshot.revision += 1;
        inner.snapshot.clone()
    };
    publish(&app, snapshot.clone());
    let supervisor = supervisor.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            if supervisor.cancelled(&id) {
                return Ok(());
            }
            let path = app
                .path()
                .resolve("worker/worker.py", tauri::path::BaseDirectory::Resource)
                .map_err(|e| error("worker_missing", e))?;
            let adapter = path.with_file_name("processing.py");
            if std::fs::read(&adapter).map_err(|e| error("worker_missing", e))?
                != include_bytes!("../../worker/processing.py")
            {
                return Err(error(
                    "worker_mismatch",
                    "Processing adapter differs from this build",
                ));
            }
            let mut command = worker::command_for_worker(&path)?;
            let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../..")
                .canonicalize()
                .map_err(|e| error("pipeline_missing", e))?;
            command.env("CONTENT_PIPELINE_ROOT", root);
            execute(
                &supervisor,
                &id,
                command,
                Duration::from_secs(4 * 60 * 60),
                &|s| publish(&app, s),
                Some(&config),
            )
        }))
        .unwrap_or_else(|_| Err(error("supervisor_error", "Processing supervisor panicked")));
        publish(&app, supervisor.finish(&id, result));
    });
    Ok(snapshot)
}

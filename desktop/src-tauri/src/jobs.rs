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
        inner.snapshot = Snapshot {
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
        let s = &mut inner.snapshot;
        if s.job_id.as_deref() != Some(id) || !s.state.active() {
            return s.clone();
        }
        // Whichever operation acquires this lock first wins the cancellation/finish race.
        // Terminal publication only happens after process and reader cleanup.
        if s.state == Phase::Cancelling {
            s.state = Phase::Cancelled;
            s.error = None;
        } else if let Err(e) = result {
            s.state = Phase::Failed;
            s.error = Some(e);
        } else if s.state != Phase::Running || s.progress.completed != 12 {
            s.state = Phase::Failed;
            s.error = Some(error(
                "invalid_transition",
                "Completion requires all reported checks",
            ));
        } else {
            s.state = Phase::Completed;
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
    let mut reader = BufReader::new(pipe);
    loop {
        let mut line = Vec::new();
        match (&mut reader)
            .take(LINE_LIMIT + 1)
            .read_until(b'\n', &mut line)
        {
            Ok(0) => {
                let _ = tx.send(Pipe::End);
                return;
            }
            Ok(_) if line.len() as u64 > LINE_LIMIT || !line.ends_with(b"\n") => {
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
    mut command: Command,
    timeout: Duration,
    publish: &impl Fn(Snapshot),
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
    let out = thread::spawn(move || read_events(stdout, tx));
    let err = thread::spawn(move || worker::read_limited(stderr));
    let result = (|| {
        if supervisor.cancelled(id) {
            return Ok(());
        }
        let request = serde_json::json!({"request_id":id,"job_id":id,"protocol_version":1,"command":"diagnostic_job"}).to_string();
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
                    return if stream.done {
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

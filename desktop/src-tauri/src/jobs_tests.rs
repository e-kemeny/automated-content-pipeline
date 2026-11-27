use super::*;

fn id(s: &Snapshot) -> &str {
    s.job_id.as_deref().unwrap()
}
fn fixture(code: &str) -> Command {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../worker/worker.py");
    let real = worker::command_for_worker(&path).unwrap();
    let mut command = Command::new(real.get_program());
    // Match the real worker: do not execute work until Rust attaches containment and sends EOF.
    command.args([
        "-I",
        "-B",
        "-c",
        &format!("import sys; sys.stdin.read(); {code}"),
    ]);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    command
}
fn message(id: &str, sequence: u32, event: &str, completed: u32, stage: &str) -> Vec<u8> {
    serde_json::json!({"protocol_version":1,"request_id":id,"job_id":id,"command":"diagnostic_job",
        "sequence":sequence,"event":event,"stage":stage,"completed":completed,"total":12,"error":null}).to_string().into_bytes()
}
#[test]
fn duplicate_start_and_startup_cancellation() {
    let s = Supervisor::default();
    assert_eq!(s.snapshot().state, Phase::Idle);
    let first = s.reserve().unwrap();
    assert_eq!(first.state, Phase::Starting);
    assert!(s.reserve().is_err());
    assert!(s.cancel("wrong").is_err());
    s.cancel(id(&first)).unwrap();
    // A cancelled startup must not even try to spawn an invalid executable.
    execute_job(
        &s,
        id(&first),
        Command::new("missing-python"),
        JOB_TIMEOUT,
        &|_| {},
    )
    .unwrap();
    let terminal = s.finish(id(&first), Ok(()));
    assert_eq!(terminal.state, Phase::Cancelled);
    assert!(terminal.finished_at.is_some());
    let next = s.reserve().unwrap();
    assert_ne!(next.job_id, first.job_id);
    assert!(next.revision > terminal.revision);
}
#[test]
fn ordered_progress_and_terminal_races() {
    let s = Supervisor::default();
    let first = s.reserve().unwrap();
    let mut stream = Stream::default();
    let start = stream
        .accept(
            &message(id(&first), 1, "started", 0, "Interpreter"),
            id(&first),
        )
        .unwrap();
    let running = s.progress(id(&first), &start).unwrap();
    assert_eq!(running.state, Phase::Running);
    assert!(running.revision > first.revision);
    s.cancel(id(&first)).unwrap();
    assert!(s.progress(id(&first), &start).is_none());
    assert_eq!(s.finish(id(&first), Ok(())).state, Phase::Cancelled);
    assert_eq!(
        s.finish(id(&first), Err(error("late", "late"))).state,
        Phase::Cancelled
    );

    let next = s.reserve().unwrap();
    let mut st = Stream::default();
    for n in 0..=12 {
        let m = st
            .accept(
                &message(
                    id(&next),
                    n + 1,
                    if n == 0 { "started" } else { "progress" },
                    n,
                    if n == 0 {
                        "Interpreter"
                    } else {
                        ["Interpreter", "Protocol", "Checksum"][((n - 1) / 4) as usize]
                    },
                ),
                id(&next),
            )
            .unwrap();
        s.progress(id(&next), &m);
    }
    let completed = s.finish(id(&next), Ok(()));
    assert_eq!(completed.state, Phase::Completed);
    assert_eq!(s.cancel(id(&next)).unwrap().revision, completed.revision);
}
#[test]
fn invalid_messages_and_ordering() {
    for raw in [b"oops".as_slice(), b"{}", b"[]"] {
        assert!(Stream::default().accept(raw, "x").is_err());
    }
    assert!(Stream::default()
        .accept(&message("other", 1, "started", 0, "Interpreter"), "x")
        .is_err());
    assert!(Stream::default()
        .accept(&message("x", 2, "progress", 1, "Interpreter"), "x")
        .is_err());
    let mut stream = Stream::default();
    let start = message("x", 1, "started", 0, "Interpreter");
    stream.accept(&start, "x").unwrap();
    assert!(stream.accept(&start, "x").is_err());
    assert!(stream
        .accept(&message("x", 2, "progress", 2, "Interpreter"), "x")
        .is_err());
    assert!(stream
        .accept(&message("x", 2, "completed", 12, "Finished"), "x")
        .is_err());
    let mut wrong: serde_json::Value =
        serde_json::from_slice(&message("x", 2, "progress", 1, "Interpreter")).unwrap();
    wrong["protocol_version"] = serde_json::json!(2);
    assert!(stream.accept(wrong.to_string().as_bytes(), "x").is_err());
}
#[test]
fn real_diagnostic_completes() {
    let s = Supervisor::default();
    let first = s.reserve().unwrap();
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../worker/worker.py");
    let seen = Mutex::new(Vec::new());
    let result = execute_job(
        &s,
        id(&first),
        worker::command_for_worker(&path).unwrap(),
        JOB_TIMEOUT,
        &|v| seen.lock().unwrap().push(v),
    );
    assert!(result.is_ok(), "{result:?}");
    let done = s.finish(id(&first), result);
    assert_eq!(done.state, Phase::Completed);
    assert_eq!(done.progress.completed, 12);
    let seen = seen.lock().unwrap();
    assert_eq!(seen.len(), 14);
    assert!(seen.windows(2).all(|w| w[1].revision > w[0].revision));
}
#[test]
fn real_running_cancellation_and_restart() {
    let s = Supervisor::default();
    let first = s.reserve().unwrap();
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../worker/worker.py");
    let result = execute_job(
        &s,
        id(&first),
        worker::command_for_worker(&path).unwrap(),
        JOB_TIMEOUT,
        &|v| {
            if v.progress.completed == 1 {
                s.cancel(id(&first)).unwrap();
            }
        },
    );
    assert_eq!(s.finish(id(&first), result).state, Phase::Cancelled);
    assert!(s.reserve().is_ok());
}
#[test]
fn crashes_invalid_output_and_unexpected_exit() {
    for (code, expected) in [
        (
            "import sys; sys.stderr.write('diagnostic'); sys.exit(2)",
            "worker_exit",
        ),
        ("print('invalid')", "invalid_message"),
        ("pass", "unexpected_exit"),
        ("print('x'*5000)", "invalid_message"),
    ] {
        let s = Supervisor::default();
        let first = s.reserve().unwrap();
        let result = execute_job(&s, id(&first), fixture(code), JOB_TIMEOUT, &|_| {});
        assert_eq!(result.as_ref().unwrap_err().code, expected);
        assert_eq!(s.finish(id(&first), result).state, Phase::Failed);
    }
}
#[test]
fn timeout_cleanup_and_shutdown() {
    let s = Supervisor::default();
    let first = s.reserve().unwrap();
    let start = Instant::now();
    let result = execute_job(
        &s,
        id(&first),
        fixture("import time; time.sleep(60)"),
        Duration::from_millis(60),
        &|_| {},
    );
    assert_eq!(result.as_ref().unwrap_err().code, "timeout");
    // Includes Windows process creation and cleanup under parallel test load.
    assert!(start.elapsed() < JOB_TIMEOUT);
    assert_eq!(s.finish(id(&first), result).state, Phase::Failed);
    let next = s.reserve().unwrap();
    assert!(s.shutdown());
    assert!(s.cancelled(id(&next)));
    s.finish(id(&next), Ok(()));
    s.wait_stopped();
    assert!(s.reserve().is_err());
}
#[test]
fn line_limits_and_missing_newline() {
    for bytes in [vec![b'x'; 4097], b"{}".to_vec()] {
        let (tx, rx) = mpsc::sync_channel(16);
        read_events(bytes.as_slice(), tx);
        assert!(matches!(rx.recv().unwrap(), Pipe::Error(_)));
    }
}

#[cfg(windows)]
#[test]
fn descendant_is_terminated_on_invalid_output() {
    use windows_sys::Win32::{
        Foundation::{CloseHandle, WAIT_OBJECT_0},
        System::Threading::{OpenProcess, WaitForSingleObject, PROCESS_SYNCHRONIZE},
    };
    let s = Supervisor::default();
    let first = s.reserve().unwrap();
    let code="import subprocess,sys; p=subprocess.Popen([sys.executable,'-I','-c','import time; time.sleep(60)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); print(p.pid,file=sys.stderr,flush=True); print('invalid',flush=True); import time; time.sleep(60)";
    let result = execute_job(&s, id(&first), fixture(code), JOB_TIMEOUT, &|_| {}).unwrap_err();
    assert_eq!(result.code, "invalid_message");
    let pid: u32 = result.stderr.trim().parse().unwrap();
    unsafe {
        let handle = OpenProcess(PROCESS_SYNCHRONIZE, 0, pid);
        if !handle.is_null() {
            let waited = WaitForSingleObject(handle, 2000);
            CloseHandle(handle);
            assert_eq!(waited, WAIT_OBJECT_0);
        } else {
            assert_eq!(std::io::Error::last_os_error().raw_os_error(), Some(87));
        }
    }
}

#[test]
fn premature_completion_is_not_success() {
    let s = Supervisor::default();
    let first = s.reserve().unwrap();
    assert_eq!(s.finish(id(&first), Ok(())).state, Phase::Failed);
}

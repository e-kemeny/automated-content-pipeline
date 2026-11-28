use crate::{
    media::Config,
    worker::{error, WorkerError},
};
use serde::{Deserialize, Serialize};
use std::path::{Component, Path};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Artifact {
    pub path: String,
    pub kind: String,
    pub size_bytes: u64,
    pub sha256: String,
    pub duration_seconds: Option<f64>,
}
#[derive(Clone, Debug, Serialize)]
pub struct Processing {
    pub workspace: String,
    pub mode: String,
    pub artifacts: Vec<Artifact>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Failure {
    code: String,
    message: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Event {
    protocol_version: u32,
    request_id: String,
    job_id: String,
    command: String,
    sequence: u32,
    event: String,
    stage: String,
    completed: u32,
    total: u32,
    error: Option<Failure>,
    artifacts: Vec<Artifact>,
}
pub struct Stream {
    pub done: bool,
    sequence: u32,
    stages: Vec<&'static str>,
    next: usize,
    pub artifacts: Vec<Artifact>,
}
impl Stream {
    pub fn new(mode: &str) -> Self {
        let mut stages = vec![
            "Validating source",
            "Collecting observations and generating shared analysis",
        ];
        if mode == "shorts" || mode == "both" {
            stages.push("Exporting Shorts");
        }
        if mode == "longform" || mode == "both" {
            stages.push("Exporting long-form");
        }
        stages.push("Finalizing outputs");
        Self {
            done: false,
            sequence: 0,
            stages,
            next: 0,
            artifacts: vec![],
        }
    }
    pub fn accept(
        &mut self,
        bytes: &[u8],
        id: &str,
        config: &Config,
    ) -> Result<String, WorkerError> {
        let value: serde_json::Value =
            serde_json::from_slice(bytes).map_err(|e| error("invalid_message", e))?;
        if !value
            .as_object()
            .is_some_and(|v| v.len() == 11 && v.contains_key("error"))
        {
            return Err(error("invalid_message", "Missing processing event fields"));
        }
        let e: Event = serde_json::from_value(value).map_err(|e| error("invalid_message", e))?;
        if self.done
            || e.protocol_version != 1
            || e.request_id != id
            || e.job_id != id
            || e.command != "process_video"
            || e.sequence != self.sequence + 1
            || e.completed != 0
            || e.total != 0
        {
            return Err(error(
                "invalid_message",
                "Invalid processing identity/order/progress",
            ));
        }
        if e.event == "failed" && e.stage == "Failed" && e.artifacts.is_empty() {
            if let Some(f) = e.error {
                if !f.code.is_empty() && !f.message.is_empty() {
                    return Err(error("processing_failed", f.message));
                }
            }
            return Err(error("invalid_message", "Invalid failure"));
        }
        if e.error.is_some() {
            return Err(error("invalid_message", "Unexpected error"));
        }
        match e.event.as_str() {
            "started" | "progress"
                if e.artifacts.is_empty()
                    && (e.event == "started") == (self.sequence == 0)
                    && self.stages.get(self.next) == Some(&e.stage.as_str()) =>
            {
                self.next += 1;
            }
            "completed" if e.stage == "Finished" && self.next == self.stages.len() => {
                validate_artifacts(&e.artifacts, config)?;
                self.artifacts = e.artifacts;
                self.done = true;
            }
            _ => {
                return Err(error(
                    "invalid_message",
                    "Invalid processing stage/terminal outcome",
                ))
            }
        }
        self.sequence = e.sequence;
        Ok(e.stage)
    }
}
pub fn validate_artifacts(rows: &[Artifact], config: &Config) -> Result<(), WorkerError> {
    let expected = match config.mode.as_str() {
        "shorts" => 7,
        "longform" => 3,
        "both" => 8,
        _ => 0,
    };
    if rows.len() != expected || expected == 0 {
        return Err(error("invalid_artifacts", "Incomplete artifact set"));
    }
    let mut seen = std::collections::HashSet::new();
    for row in rows {
        let path = Path::new(&row.path);
        if !path.is_absolute()
            || !path.starts_with(&config.workspace)
            || path.components().any(|c| matches!(c, Component::ParentDir))
            || !seen.insert(&row.path)
            || row.size_bytes == 0
            || row.sha256.len() != 64
            || !row.sha256.bytes().all(|c| c.is_ascii_hexdigit())
        {
            return Err(error("invalid_artifacts", "Unsafe or malformed artifact"));
        }
        crate::media::safe_path(path, false)?;
        if std::fs::metadata(path)
            .map_err(|e| error("invalid_artifacts", e))?
            .len()
            != row.size_bytes
        {
            return Err(error("invalid_artifacts", "Artifact size mismatch"));
        }
        if ["shorts", "longform"].contains(&row.kind.as_str()) {
            if path.extension().and_then(|x| x.to_str()) != Some("mp4")
                || !row
                    .duration_seconds
                    .is_some_and(|n| n.is_finite() && n > 0.0)
            {
                return Err(error("invalid_artifacts", "Invalid output video"));
            }
        } else if !["review", "analysis"].contains(&row.kind.as_str())
            || row.duration_seconds.is_some()
        {
            return Err(error("invalid_artifacts", "Unknown artifact kind"));
        }
    }
    for (kind, count) in [
        ("shorts", if config.mode == "longform" { 0 } else { 5 }),
        ("longform", if config.mode == "shorts" { 0 } else { 1 }),
        ("review", 1),
        ("analysis", 1),
    ] {
        if rows.iter().filter(|r| r.kind == kind).count() != count {
            return Err(error("invalid_artifacts", "Unexpected artifact kinds"));
        }
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    fn config() -> Config {
        Config {
            video: "unused".into(),
            workspace: "unused".into(),
            mode: "both".into(),
            size_bytes: 1,
            modified_ms: 0,
        }
    }
    fn event(sequence: u32, stage: &str) -> Vec<u8> {
        serde_json::json!({"protocol_version":1,"request_id":"x","job_id":"x","command":"process_video","sequence":sequence,"event":if sequence==1{"started"}else{"progress"},"stage":stage,"completed":0,"total":0,"error":null,"artifacts":[]}).to_string().into_bytes()
    }
    #[test]
    fn actual_stage_order_and_no_fake_percentage() {
        let mut s = Stream::new("both");
        for (i, stage) in s.stages.clone().iter().enumerate() {
            assert!(s
                .accept(&event(i as u32 + 1, stage), "x", &config())
                .is_ok());
        }
        assert!(!s.done);
    }
    #[test]
    fn malformed_stale_and_skipped_stages_rejected() {
        for bytes in [
            b"{}".to_vec(),
            event(2, "Validating source"),
            event(1, "Exporting Shorts"),
        ] {
            assert!(Stream::new("both").accept(&bytes, "x", &config()).is_err());
        }
        assert!(Stream::new("both")
            .accept(&event(1, "Validating source"), "other", &config())
            .is_err());
    }
    #[test]
    fn incomplete_outputs_rejected() {
        assert!(validate_artifacts(&[], &config()).is_err());
    }
}

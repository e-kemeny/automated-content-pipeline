use crate::worker::{error, ManagedChild, WorkerError};
use serde::{Deserialize, Serialize};
use std::{
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::Mutex,
    time::{Duration, UNIX_EPOCH},
};
use tauri::{Manager, State};
use tauri_plugin_dialog::DialogExt;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Source {
    pub path: String,
    pub name: String,
    pub size_bytes: u64,
    pub modified_ms: u64,
    pub duration_seconds: f64,
    pub width: u32,
    pub height: u32,
}
#[derive(Clone, Default, Serialize)]
pub struct Selection {
    pub source: Option<Source>,
    pub output: Option<String>,
}
#[derive(Default)]
pub struct MediaSelection(pub Mutex<Selection>);
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub video: String,
    pub workspace: String,
    pub mode: String,
    pub size_bytes: u64,
    pub modified_ms: u64,
}
pub fn safe_path(path: &Path, directory: bool) -> Result<(), WorkerError> {
    if !path.is_absolute()
        || if directory {
            !path.is_dir()
        } else {
            !path.is_file()
        }
    {
        return Err(error(
            "invalid_path",
            "Select an existing local source/folder",
        ));
    }
    for part in path.ancestors() {
        let meta = std::fs::symlink_metadata(part).map_err(|e| error("invalid_path", e))?;
        #[cfg(windows)]
        {
            use std::os::windows::fs::MetadataExt;
            if meta.file_attributes() & 0x400 != 0 {
                return Err(error("invalid_path", "Reparse points (including junctions/cloud placeholders) are not supported; use a local regular path"));
            }
        }
        if meta.is_symlink() {
            return Err(error("invalid_path", "Symlink paths are not supported"));
        }
    }
    Ok(())
}
pub fn validate_source(source: &Source) -> Result<(), WorkerError> {
    safe_path(Path::new(&source.path), false)?;
    let m = std::fs::metadata(&source.path).map_err(|e| error("invalid_source", e))?;
    let modified = m
        .modified()
        .map_err(|e| error("invalid_source", e))?
        .duration_since(UNIX_EPOCH)
        .map_err(|e| error("invalid_source", e))?
        .as_millis() as u64;
    if m.len() != source.size_bytes || modified != source.modified_ms {
        return Err(error("source_changed", "Source changed; select it again"));
    }
    Ok(())
}
fn parse_probe(path: &Path, bytes: &[u8]) -> Result<Source, WorkerError> {
    let data: serde_json::Value =
        serde_json::from_slice(bytes).map_err(|e| error("invalid_video", e))?;
    let duration = data["format"]["duration"]
        .as_str()
        .and_then(|s| s.parse::<f64>().ok())
        .filter(|n| n.is_finite() && *n > 0.0)
        .ok_or_else(|| error("invalid_video", "Invalid video duration"))?;
    let streams = data["streams"]
        .as_array()
        .ok_or_else(|| error("invalid_video", "Missing streams"))?;
    if !streams.iter().any(|s| s["codec_type"] == "audio") {
        return Err(error(
            "invalid_video",
            "This baseline requires an audio stream",
        ));
    }
    let v = streams
        .iter()
        .find(|s| s["codec_type"] == "video")
        .ok_or_else(|| error("invalid_video", "No video stream"))?;
    let dimension = |key: &str| -> Result<u32, WorkerError> {
        v[key]
            .as_u64()
            .and_then(|n| u32::try_from(n).ok())
            .filter(|n| *n > 0)
            .ok_or_else(|| error("invalid_video", "Invalid dimensions"))
    };
    let m = std::fs::metadata(path).map_err(|e| error("invalid_source", e))?;
    Ok(Source {
        path: path.to_string_lossy().into(),
        name: path
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .into(),
        size_bytes: m.len(),
        modified_ms: m
            .modified()
            .map_err(|e| error("invalid_source", e))?
            .duration_since(UNIX_EPOCH)
            .map_err(|e| error("invalid_source", e))?
            .as_millis() as u64,
        duration_seconds: duration,
        width: dimension("width")?,
        height: dimension("height")?,
    })
}
fn probe(path: &Path) -> Result<Source, WorkerError> {
    safe_path(path, false)?;
    let ext = path
        .extension()
        .unwrap_or_default()
        .to_string_lossy()
        .to_lowercase();
    if !["mp4", "mov", "mkv", "webm", "avi", "m4v"].contains(&ext.as_str()) {
        return Err(error("invalid_video", "Unsupported video extension"));
    }
    let before = std::fs::metadata(path).map_err(|e| error("invalid_source", e))?;
    let mut command = Command::new("ffprobe");
    command
        .args([
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height",
            "-of",
            "json",
        ])
        .arg(path)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let mut child = ManagedChild(command.spawn().map_err(|e| error("ffprobe_missing", e))?);
    #[cfg(windows)]
    let guard = crate::worker::job::Job::attach(&child.0)?;
    let stdout = child.0.stdout.take().unwrap();
    let stderr = child.0.stderr.take().unwrap();
    let out = std::thread::spawn(move || crate::worker::read_limited(stdout));
    let err = std::thread::spawn(move || crate::worker::read_limited(stderr));
    let status = crate::worker::wait_bounded(&mut child.0, Duration::from_secs(30));
    drop(child);
    #[cfg(windows)]
    drop(guard);
    let bytes = out
        .join()
        .map_err(|_| error("probe_failed", "Reader failed"))?
        .map_err(|e| error("probe_failed", e))?;
    let diagnostics = err
        .join()
        .map_err(|_| error("probe_failed", "Reader failed"))?
        .map_err(|e| error("probe_failed", e))?;
    if !status?.success() || bytes.len() > 65536 {
        return Err(error(
            "invalid_video",
            String::from_utf8_lossy(&diagnostics),
        ));
    }
    let source = parse_probe(path, &bytes)?;
    if before.len() != source.size_bytes
        || before.modified().ok() != std::fs::metadata(path).ok().and_then(|m| m.modified().ok())
    {
        return Err(error("source_changed", "Source changed while probing"));
    }
    Ok(source)
}
#[tauri::command]
pub fn get_media_selection(selection: State<'_, MediaSelection>) -> Selection {
    selection.0.lock().unwrap().clone()
}
#[tauri::command]
pub async fn select_source_video(app: tauri::AppHandle) -> Result<Option<Source>, WorkerError> {
    tauri::async_runtime::spawn_blocking(move || {
        let Some(file) = app
            .dialog()
            .file()
            .add_filter("Video", &["mp4", "mov", "mkv", "webm", "avi", "m4v"])
            .blocking_pick_file()
        else {
            return Ok(None);
        };
        let path = file.into_path().map_err(|e| error("invalid_path", e))?;
        let source = probe(&path)?;
        app.state::<MediaSelection>().0.lock().unwrap().source = Some(source.clone());
        Ok(Some(source))
    })
    .await
    .map_err(|e| error("picker_failed", e))?
}
#[tauri::command]
pub async fn select_output_workspace(app: tauri::AppHandle) -> Result<Option<String>, WorkerError> {
    tauri::async_runtime::spawn_blocking(move || {
        let Some(file) = app.dialog().file().blocking_pick_folder() else {
            return Ok(None);
        };
        let path = file.into_path().map_err(|e| error("invalid_path", e))?;
        safe_path(&path, true)?;
        let value = path.to_string_lossy().into_owned();
        app.state::<MediaSelection>().0.lock().unwrap().output = Some(value.clone());
        Ok(Some(value))
    })
    .await
    .map_err(|e| error("picker_failed", e))?
}
pub fn configuration(selection: &Selection, mode: &str, id: &str) -> Result<Config, WorkerError> {
    if !["shorts", "longform", "both"].contains(&mode) {
        return Err(error("invalid_mode", "Unsupported export mode"));
    }
    let source = selection
        .source
        .as_ref()
        .ok_or_else(|| error("missing_source", "Select a video"))?;
    validate_source(source)?;
    let output = PathBuf::from(
        selection
            .output
            .as_ref()
            .ok_or_else(|| error("missing_output", "Select an output folder"))?,
    );
    safe_path(&output, true)?;
    let workspace = output.join(format!("content-pipeline-{id}"));
    if workspace.exists() {
        return Err(error("workspace_exists", "Job workspace already exists"));
    }
    Ok(Config {
        video: source.path.clone(),
        workspace: workspace.to_string_lossy().into(),
        mode: mode.into(),
        size_bytes: source.size_bytes,
        modified_ms: source.modified_ms,
    })
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_missing_selection_and_invalid_mode() {
        assert!(configuration(&Selection::default(), "both", "test").is_err());
        assert!(configuration(&Selection::default(), "shell", "test").is_err());
    }
    #[test]
    fn rejects_missing_file_and_relative_paths() {
        assert!(safe_path(Path::new("missing.mp4"), false).is_err());
        assert!(safe_path(Path::new("."), true).is_err());
    }
    #[test]
    fn malformed_probe_and_no_audio_fail() {
        assert!(parse_probe(Path::new("x"), b"invalid").is_err());
        assert!(parse_probe(
            Path::new("x"),
            br#"{"format":{"duration":"1"},"streams":[{"codec_type":"video"}]}"#
        )
        .is_err());
    }
}

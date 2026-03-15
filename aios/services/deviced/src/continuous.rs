use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    sync::{
        mpsc::{self, Sender},
        Arc, Mutex,
    },
    thread::{self, JoinHandle},
    time::Duration,
};

use chrono::Utc;
use serde::{Deserialize, Serialize};

use aios_contracts::{DeviceCaptureRecord, DeviceContinuousCollectorStatus};

use crate::config::Config;

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
struct ContinuousCollectorSnapshot {
    updated_at: String,
    #[serde(default)]
    collectors: Vec<DeviceContinuousCollectorStatus>,
}

#[derive(Debug)]
struct CollectorHandle {
    stop_tx: Sender<()>,
    thread: JoinHandle<()>,
}

#[derive(Debug, Default)]
pub struct ContinuousCaptureManager {
    state_path: PathBuf,
    interval: Duration,
    shared: Arc<Mutex<BTreeMap<String, DeviceContinuousCollectorStatus>>>,
    handles: BTreeMap<String, CollectorHandle>,
}

impl ContinuousCaptureManager {
    pub fn new(config: &Config) -> anyhow::Result<Self> {
        let manager = Self {
            state_path: config.continuous_capture_state_path.clone(),
            interval: Duration::from_millis(config.continuous_capture_interval_ms.max(50)),
            shared: Arc::new(Mutex::new(BTreeMap::new())),
            handles: BTreeMap::new(),
        };
        manager.persist()?;
        Ok(manager)
    }

    pub fn start(&mut self, config: &Config, capture: &DeviceCaptureRecord) -> anyhow::Result<()> {
        if !capture.continuous {
            return Ok(());
        }
        if !capture
            .adapter_execution_path
            .as_deref()
            .is_some_and(|path| path.starts_with("native"))
        {
            return Ok(());
        }

        self.stop(&capture.capture_id)?;
        let capture_id = capture.capture_id.clone();
        let shared = self.shared.clone();
        let state_path = self.state_path.clone();
        let interval = self.interval;
        let config = config.clone();
        let capture = capture.clone();
        let handle_capture_id = capture_id.clone();
        let (stop_tx, stop_rx) = mpsc::channel::<()>();

        {
            let mut map = self
                .shared
                .lock()
                .map_err(|error| anyhow::anyhow!("continuous collector map poisoned: {error}"))?;
            map.insert(
                capture_id.clone(),
                build_status(&config, &capture, 0, "starting"),
            );
        }
        self.persist()?;

        let handle = thread::spawn(move || {
            let mut sample_count = 0;
            loop {
                if stop_rx.recv_timeout(interval).is_ok() {
                    break;
                }
                sample_count += 1;
                if let Ok(mut map) = shared.lock() {
                    map.insert(
                        capture_id.clone(),
                        build_status(&config, &capture, sample_count, "running"),
                    );
                    let _ = persist_shared(&state_path, &map);
                }
            }
        });

        self.handles.insert(
            handle_capture_id,
            CollectorHandle {
                stop_tx,
                thread: handle,
            },
        );
        Ok(())
    }

    pub fn stop(&mut self, capture_id: &str) -> anyhow::Result<()> {
        if let Some(handle) = self.handles.remove(capture_id) {
            let _ = handle.stop_tx.send(());
            let _ = handle.thread.join();
        }
        if let Ok(mut map) = self.shared.lock() {
            map.remove(capture_id);
        }
        self.persist()
    }

    pub fn snapshot(&self) -> Vec<DeviceContinuousCollectorStatus> {
        self.shared
            .lock()
            .map(|map| map.values().cloned().collect())
            .unwrap_or_default()
    }

    pub fn shutdown(&mut self) -> anyhow::Result<()> {
        let capture_ids = self.handles.keys().cloned().collect::<Vec<_>>();
        for capture_id in capture_ids {
            self.stop(&capture_id)?;
        }
        self.persist()
    }

    pub fn active_count(&self) -> usize {
        self.shared.lock().map(|map| map.len()).unwrap_or(0)
    }

    pub fn state_path(&self) -> &Path {
        &self.state_path
    }

    fn persist(&self) -> anyhow::Result<()> {
        let map = self
            .shared
            .lock()
            .map_err(|error| anyhow::anyhow!("continuous collector map poisoned: {error}"))?;
        persist_shared(&self.state_path, &map)
    }
}

impl Drop for ContinuousCaptureManager {
    fn drop(&mut self) {
        let _ = self.shutdown();
    }
}

pub fn read_snapshot(path: &Path) -> anyhow::Result<Vec<DeviceContinuousCollectorStatus>> {
    if !path.exists() {
        return Ok(Vec::new());
    }
    let content = fs::read_to_string(path)?;
    let snapshot = serde_json::from_str::<ContinuousCollectorSnapshot>(&content)?;
    Ok(snapshot.collectors)
}

fn persist_shared(
    state_path: &Path,
    map: &BTreeMap<String, DeviceContinuousCollectorStatus>,
) -> anyhow::Result<()> {
    if let Some(parent) = state_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let snapshot = ContinuousCollectorSnapshot {
        updated_at: Utc::now().to_rfc3339(),
        collectors: map.values().cloned().collect(),
    };
    fs::write(state_path, serde_json::to_vec_pretty(&snapshot)?)?;
    Ok(())
}

fn build_status(
    config: &Config,
    capture: &DeviceCaptureRecord,
    sample_count: u64,
    status: &str,
) -> DeviceContinuousCollectorStatus {
    let mut details = vec![
        format!(
            "adapter_id={}",
            capture.adapter_id.as_deref().unwrap_or("-")
        ),
        format!(
            "adapter_execution_path={}",
            capture.adapter_execution_path.as_deref().unwrap_or("-")
        ),
    ];
    match capture.modality.as_str() {
        "screen" => {
            details.push(format!(
                "dbus_session_bus={}",
                std::env::var_os("DBUS_SESSION_BUS_ADDRESS").is_some()
            ));
            details.push(format!(
                "screencast_state_path={}",
                config.screencast_state_path.display()
            ));
        }
        "audio" => {
            details.push(format!(
                "pipewire_socket_present={}",
                config.pipewire_socket_path.exists()
            ));
            details.push(format!(
                "pipewire_node_path={}",
                config.pipewire_node_path.display()
            ));
        }
        "input" => {
            let device_count = fs::read_dir(&config.input_device_root)
                .map(|entries| {
                    entries
                        .filter_map(|entry| entry.ok())
                        .filter(|entry| {
                            let name = entry.file_name().to_string_lossy().to_string();
                            name.starts_with("event")
                                || name.starts_with("mouse")
                                || name.starts_with("kbd")
                        })
                        .count()
                })
                .unwrap_or(0);
            details.push(format!("device_count={device_count}"));
            details.push(format!("input_root={}", config.input_device_root.display()));
        }
        "camera" => {
            details.push(format!(
                "camera_root={}",
                config.camera_device_root.display()
            ));
            details.push(format!(
                "camera_root_present={}",
                config.camera_device_root.exists()
            ));
        }
        _ => {}
    }

    DeviceContinuousCollectorStatus {
        capture_id: capture.capture_id.clone(),
        modality: capture.modality.clone(),
        backend: capture.source_backend.clone(),
        collector_mode: "native-interval".to_string(),
        status: status.to_string(),
        updated_at: Utc::now().to_rfc3339(),
        sample_count,
        details,
    }
}

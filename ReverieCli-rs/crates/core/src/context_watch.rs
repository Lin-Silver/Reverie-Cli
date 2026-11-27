use crate::{Result, host::EventSink, semantic_resources::SemanticResources};
use notify::{EventKind, RecommendedWatcher, RecursiveMode, Watcher};
use reverie_context::{ContextEngine, scan};
use reverie_protocol::{ContextOperation, ContextWatchState};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    path::{Path, PathBuf},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
        mpsc::{self, Receiver, SyncSender},
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};
use tokio_util::sync::CancellationToken;

struct Control {
    stopped: CancellationToken,
    wake: SyncSender<()>,
    active: Mutex<Option<(String, CancellationToken)>>,
    state: Mutex<ContextWatchState>,
    watch_error: Mutex<String>,
    changed_paths: Mutex<BTreeSet<PathBuf>>,
    reset_watches: AtomicBool,
}

pub(crate) struct ContextMonitor {
    pub configuration: PathBuf,
    control: Arc<Control>,
    thread: Option<JoinHandle<()>>,
}

impl ContextMonitor {
    pub fn start(
        root: PathBuf,
        engine: Arc<Mutex<ContextEngine>>,
        resources: Arc<SemanticResources>,
        configuration: PathBuf,
        stopped: CancellationToken,
        sink: EventSink,
    ) -> Result<Self> {
        let (wake, receiver) = mpsc::sync_channel(1);
        let control = Arc::new(Control {
            stopped,
            wake,
            active: Mutex::new(None),
            watch_error: Mutex::new(String::new()),
            changed_paths: Mutex::new(BTreeSet::new()),
            reset_watches: AtomicBool::new(false),
            state: Mutex::new(ContextWatchState {
                enabled: true,
                status: "starting".into(),
                backend: format!("{:?}", RecommendedWatcher::kind()),
                project_root: root.to_string_lossy().into_owned(),
                revision: 0,
                semantic_revision: 0,
                manifest_sha256: None,
                operation: None,
                error: String::new(),
            }),
        });
        let worker = control.clone();
        let thread = thread::Builder::new()
            .name("reverie-context-watch".into())
            .spawn(move || {
                if let Err(error) = watch(&root, &engine, &resources, &worker, receiver, &sink)
                    && let Ok(mut state) = worker.state.lock()
                {
                    state.enabled = false;
                    state.status = "error".into();
                    state.error = error.to_string();
                    state.operation = None;
                }
            })?;
        Ok(Self {
            configuration,
            control,
            thread: Some(thread),
        })
    }

    pub fn status(&self) -> Value {
        self.control.state.lock().map(|state| json!(*state)).unwrap_or_else(|_| json!({"enabled":false,"status":"error","error":"Context watcher state lock was poisoned."}))
    }
    pub fn operation(&self) -> Option<ContextOperation> {
        self.control.state.lock().ok()?.operation.clone()
    }
    pub fn wake(&self) {
        let _ = self.control.wake.try_send(());
    }
    pub fn cancel_operation(&self, id: &str) -> bool {
        if let Ok(active) = self.control.active.lock()
            && let Some((operation, cancel)) = active.as_ref()
            && operation == id
        {
            cancel.cancel();
            return true;
        }
        false
    }
    pub fn stop(&self) {
        self.control.stopped.cancel();
        if let Ok(mut state) = self.control.state.lock() {
            state.enabled = false;
            state.status = if state.operation.is_some() {
                "stopping"
            } else {
                "stopped"
            }
            .into();
        }
        self.wake();
    }
    pub fn is_stopped(&self) -> bool {
        self.control.stopped.is_cancelled()
    }
}

impl Drop for ContextMonitor {
    fn drop(&mut self) {
        self.stop();
        if let Some(thread) = self.thread.take()
            && thread.thread().id() != thread::current().id()
        {
            let _ = thread.join();
        }
    }
}

fn observe_paths(
    watcher: &mut RecommendedWatcher,
    root: &Path,
    watched: &mut BTreeSet<PathBuf>,
    cancelled: &impl Fn() -> bool,
) -> Result<()> {
    #[cfg(target_os = "macos")]
    let (desired, mode) = (BTreeSet::from([root.to_owned()]), RecursiveMode::Recursive);
    #[cfg(not(target_os = "macos"))]
    let (desired, mode) = (
        scan::watch_directories(root, cancelled)?
            .into_iter()
            .collect::<BTreeSet<_>>(),
        RecursiveMode::NonRecursive,
    );
    for path in watched.difference(&desired) {
        if let Err(error) = watcher.unwatch(path)
            && !matches!(error.kind, notify::ErrorKind::WatchNotFound)
        {
            return Err(error.into());
        }
    }
    let mut present = BTreeSet::new();
    for path in &desired {
        if cancelled() {
            return Err("Context watching cancelled.".into());
        }
        if !path.is_dir() {
            continue;
        }
        if !watched.contains(path) {
            watcher.watch(path, mode)?;
        }
        present.insert(path.clone());
    }
    *watched = present;
    Ok(())
}

fn progress(control: &Control, sink: &EventSink, phase: &str, completed: usize, total: usize) {
    let event = control.state.lock().ok().and_then(|mut state| {
        state.status = phase.into();
        let operation = state.operation.as_mut()?;
        operation.phase = phase.into(); operation.completed = completed; operation.total = total;
        Some(json!({"type":"context.progress","automatic":true,"operation_id":operation.operation_id,"project_root":operation.project_root,"action":operation.action,"phase":phase,"completed":completed,"total":total}))
    });
    if let Some(event) = event {
        sink(event);
    }
}

fn update(
    engine: &Arc<Mutex<ContextEngine>>,
    resources: &SemanticResources,
    control: &Control,
    sink: &EventSink,
    cycle: &CancellationToken,
) -> Result<()> {
    let cancelled = || control.stopped.is_cancelled() || cycle.is_cancelled();
    progress(control, sink, "structure", 0, 0);
    let (revision, fork) = {
        let mut engine = engine
            .lock()
            .map_err(|_| "Context Engine lock was poisoned.")?;
        let structural = engine.index_with_cancel(false, &cancelled)?;
        (
            structural["revision"]
                .as_i64()
                .ok_or("Structural revision is missing.")?,
            engine.fork()?,
        )
    };
    if let Ok(mut state) = control.state.lock() {
        state.revision = revision;
    }
    if cancelled() {
        return Err("Context watching cancelled before semantic indexing.".into());
    }
    let version = resources.capture()?;
    let Some(version) = version else {
        if let Ok(mut state) = control.state.lock() {
            state.manifest_sha256 = None;
            state.semantic_revision = 0;
        }
        return Ok(());
    };
    let digest = &version.selection.manifest_sha256;
    let previous = fork.semantic_status_for(digest)?;
    if let Ok(mut state) = control.state.lock() {
        state.manifest_sha256 = Some(digest.clone());
        state.semantic_revision = previous.as_ref().map_or(0, |state| state.revision);
    }
    if previous
        .as_ref()
        .is_some_and(|state| state.revision == revision && state.ann.is_some())
    {
        return Ok(());
    }
    progress(control, sink, "loading", 0, 0);
    let models = version.models(&cancelled)?;
    let result = fork.index_semantic(&models, &cancelled, &|done, total| {
        progress(control, sink, "embedding", done, total)
    })?;
    if let Ok(mut state) = control.state.lock() {
        state.semantic_revision = result["index"]["revision"]
            .as_i64()
            .ok_or("Semantic revision is missing.")?;
    }
    Ok(())
}

fn watch(
    root: &Path,
    engine: &Arc<Mutex<ContextEngine>>,
    resources: &SemanticResources,
    control: &Arc<Control>,
    receiver: Receiver<()>,
    sink: &EventSink,
) -> Result<()> {
    let event_root = root.to_owned();
    let event_control = control.clone();
    let mut watcher = notify::recommended_watcher(move |event: notify::Result<notify::Event>| {
        let relevant = match event {
            Ok(event) => {
                if event.need_rescan() {
                    event_control.reset_watches.store(true, Ordering::Relaxed);
                }
                if !matches!(event.kind, EventKind::Access(_))
                    && let Ok(mut paths) = event_control.changed_paths.lock()
                {
                    for path in &event.paths {
                        if scan::watch_event_relevant(&event_root, path) {
                            if paths.len() < 256 {
                                paths.insert(path.clone());
                            } else {
                                event_control.reset_watches.store(true, Ordering::Relaxed);
                            }
                        }
                    }
                }
                !matches!(event.kind, EventKind::Access(_))
                    && (event.need_rescan()
                        || event
                            .paths
                            .iter()
                            .any(|path| scan::watch_event_relevant(&event_root, path)))
            }
            Err(error) => {
                if let Ok(mut message) = event_control.watch_error.lock() {
                    *message = error.to_string();
                }
                true
            }
        };
        if relevant {
            let _ = event_control.wake.try_send(());
        }
    })?;
    let mut watched = BTreeSet::new();
    observe_paths(&mut watcher, root, &mut watched, &|| {
        control.stopped.is_cancelled()
    })?;
    let mut pending = true;
    while !control.stopped.is_cancelled() {
        if !pending {
            match receiver.recv_timeout(Duration::from_secs(1)) {
                Ok(()) => {}
                Err(mpsc::RecvTimeoutError::Timeout) => continue,
                Err(mpsc::RecvTimeoutError::Disconnected) => break,
            }
        }
        let started = Instant::now();
        while !control.stopped.is_cancelled() && started.elapsed() < Duration::from_secs(2) {
            if receiver.recv_timeout(Duration::from_millis(250)).is_err() {
                break;
            }
        }
        if control.stopped.is_cancelled() {
            break;
        }
        let changed = std::mem::take(
            &mut *control
                .changed_paths
                .lock()
                .map_err(|_| "Context watcher path lock was poisoned.")?,
        );
        let reset = control.reset_watches.swap(false, Ordering::Relaxed);
        let invalidated = watched
            .iter()
            .filter(|path| reset || changed.iter().any(|changed| path.starts_with(changed)))
            .cloned()
            .collect::<Vec<_>>();
        for path in invalidated {
            if let Err(error) = watcher.unwatch(&path)
                && !matches!(error.kind, notify::ErrorKind::WatchNotFound)
            {
                return Err(error.into());
            }
            watched.remove(&path);
        }
        let id = format!("watch-{}", uuid::Uuid::new_v4().simple());
        let cycle = CancellationToken::new();
        *control
            .active
            .lock()
            .map_err(|_| "Context watcher control lock was poisoned.")? =
            Some((id.clone(), cycle.clone()));
        if let Ok(mut state) = control.state.lock() {
            state.operation = Some(ContextOperation {
                operation_id: id,
                action: "watchWorkspace".into(),
                project_root: root.to_string_lossy().into_owned(),
                phase: "queued".into(),
                completed: 0,
                total: 0,
            });
        }
        let result = observe_paths(&mut watcher, root, &mut watched, &|| {
            control.stopped.is_cancelled() || cycle.is_cancelled()
        })
        .and_then(|_| update(engine, resources, control, sink, &cycle));
        let cancelled = control.stopped.is_cancelled() || cycle.is_cancelled();
        progress(
            control,
            sink,
            if cancelled {
                "cancelled"
            } else if result.is_ok() {
                "finished"
            } else {
                "error"
            },
            1,
            1,
        );
        if let Ok(mut state) = control.state.lock() {
            state.operation = None;
            let native_error = control
                .watch_error
                .lock()
                .map(|error| error.clone())
                .unwrap_or_else(|_| "Context watcher error lock was poisoned.".into());
            state.error = if cancelled {
                String::new()
            } else {
                result.err().map_or(native_error, |error| error.to_string())
            };
            state.status = if !state.error.is_empty() {
                "error"
            } else if cancelled {
                "cancelled"
            } else {
                "watching"
            }
            .into();
        }
        *control
            .active
            .lock()
            .map_err(|_| "Context watcher control lock was poisoned.")? = None;
        pending = receiver.try_recv().is_ok();
    }
    if let Ok(mut state) = control.state.lock() {
        state.enabled = false;
        state.status = "stopped".into();
        state.operation = None;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn wait(monitor: &ContextMonitor, predicate: impl Fn(&Value) -> bool) {
        let deadline = Instant::now() + Duration::from_secs(15);
        loop {
            let state = monitor.status();
            assert_ne!(state["status"], "error", "{state}");
            if predicate(&state) {
                return;
            }
            assert!(
                Instant::now() < deadline,
                "Native watch did not reach its boundary: {state}"
            );
            thread::sleep(Duration::from_millis(10));
        }
    }

    #[test]
    fn native_watch_updates_nested_files_ignore_rules_and_releases_on_stop() {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().join("workspace");
        fs::create_dir(&root).unwrap();
        let root = crate::config::canonical_project(&root).unwrap();
        fs::write(root.join("source.md"), "# First note\n原始证据\n").unwrap();
        let database = temporary.path().join("application/context.sqlite3");
        let engine = Arc::new(Mutex::new(ContextEngine::open(&root, &database).unwrap()));
        let resources = Arc::new(SemanticResources::new(temporary.path().join("resources")));
        let events = Arc::new(Mutex::new(Vec::new()));
        let received = events.clone();
        let sink: EventSink = Arc::new(move |event| received.lock().unwrap().push(event));
        let monitor = ContextMonitor::start(
            root.clone(),
            engine.clone(),
            resources,
            temporary.path().join("application/config.json"),
            CancellationToken::new(),
            sink,
        )
        .unwrap();
        wait(&monitor, |state| {
            state["revision"].as_i64().unwrap_or_default() > 0 && state["status"] == "watching"
        });
        let original = monitor.status()["revision"].as_i64().unwrap();
        fs::create_dir(root.join(".runtime")).unwrap();
        fs::write(
            root.join(".runtime/cache.md"),
            "Cached output must be excluded",
        )
        .unwrap();
        thread::sleep(Duration::from_millis(600));
        assert_eq!(monitor.status()["revision"], original);
        fs::create_dir_all(root.join("stories/chapter")).unwrap();
        fs::write(
            root.join("stories/chapter/new.md"),
            "# Next chapter\n新增线索\n",
        )
        .unwrap();
        wait(&monitor, |state| {
            state["revision"].as_i64().unwrap_or_default() > original
                && state["status"] == "watching"
        });
        let next = monitor.status()["revision"].as_i64().unwrap();
        assert_eq!(
            engine.lock().unwrap().query("新增线索", 10, 12000).unwrap()[0].file_path,
            "stories/chapter/new.md"
        );
        fs::rename(root.join("stories/chapter"), root.join("stories/old")).unwrap();
        fs::create_dir(root.join("stories/chapter")).unwrap();
        fs::write(
            root.join("stories/chapter/new.md"),
            "# Replaced directory\n重建目录线索\n",
        )
        .unwrap();
        wait(&monitor, |state| {
            state["revision"].as_i64().unwrap_or_default() > next && state["status"] == "watching"
        });
        let replaced = monitor.status()["revision"].as_i64().unwrap();
        fs::write(
            root.join("stories/chapter/new.md"),
            "# Changed again\n后续目录线索\n",
        )
        .unwrap();
        wait(&monitor, |state| {
            state["revision"].as_i64().unwrap_or_default() > replaced
                && state["status"] == "watching"
        });
        assert_eq!(
            engine
                .lock()
                .unwrap()
                .query("后续目录线索", 10, 12000)
                .unwrap()[0]
                .file_path,
            "stories/chapter/new.md"
        );
        let next = monitor.status()["revision"].as_i64().unwrap();
        fs::write(root.join(".gitignore"), "stories/\n").unwrap();
        wait(&monitor, |state| {
            state["revision"].as_i64().unwrap_or_default() > next && state["status"] == "watching"
        });
        assert!(
            engine
                .lock()
                .unwrap()
                .query("新增线索", 10, 12000)
                .unwrap()
                .is_empty()
        );
        let final_revision = monitor.status()["revision"].as_i64().unwrap();
        monitor.stop();
        assert_eq!(monitor.status()["enabled"], false);
        drop(monitor);
        fs::write(root.join("source.md"), "# Stopped\n停止后不再更新\n").unwrap();
        assert_eq!(
            engine.lock().unwrap().status().unwrap()["revision"],
            final_revision
        );
        let events = events.lock().unwrap();
        assert!(
            !events
                .iter()
                .any(|event| event["automatic"] == true && event["phase"] == "embedding")
        );
        assert!(
            events
                .iter()
                .any(|event| event["automatic"] == true && event["phase"] == "finished")
        );
    }
}

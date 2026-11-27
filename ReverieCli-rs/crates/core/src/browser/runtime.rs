use super::types::*;
use crate::host::EventSink;
use serde_json::{Value, json};
use std::{
    collections::{HashMap, HashSet},
    sync::{Arc, Mutex, MutexGuard},
    time::Duration,
};
use tokio::sync::oneshot;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
struct Owner {
    host: BrowserHostRef,
    scope: BrowserScope,
    profile: BrowserProfile,
}

impl Owner {
    fn of(request: &BrowserRequest) -> Self {
        Self {
            host: request.host.clone(),
            scope: request.scope.clone(),
            profile: request.profile.clone(),
        }
    }
}

struct Registered {
    key: AdapterKey,
    descriptor: AdapterDescriptor,
}

struct Observation {
    id: String,
    revision: u64,
    elements: HashMap<String, bool>,
}

struct Tab {
    owner: Owner,
    record: BrowserTab,
    observation: Option<Observation>,
    // Chromium reads selected files lazily, including after a persistent run ends.
    uploads: Vec<tempfile::TempDir>,
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Stage {
    Prepared,
    Emitting,
    Sent,
}

struct Pending {
    request: BrowserRequest,
    sender: Option<oneshot::Sender<BrowserResult<BrowserReply>>>,
    stage: Stage,
    cancellation: Option<FailureCode>,
    sink: Option<EventSink>,
}

#[derive(Default)]
struct State {
    adapters: HashMap<String, Registered>,
    tabs: HashMap<(BrowserHostRef, String), Tab>,
    pending: HashMap<String, Pending>,
    busy: HashSet<Owner>,
    closed: bool,
}

#[derive(Clone, Default)]
pub struct BrowserRuntime {
    state: Arc<Mutex<State>>,
}

pub struct PendingBrowserRequest {
    runtime: BrowserRuntime,
    request_id: String,
    receiver: Option<oneshot::Receiver<BrowserResult<BrowserReply>>>,
}

struct EmissionGuard {
    runtime: BrowserRuntime,
    request_id: String,
}

impl Drop for EmissionGuard {
    fn drop(&mut self) {
        let _ = self
            .runtime
            .finish_emission(&self.request_id, std::thread::panicking());
    }
}

type CancelEvent = (EventSink, BrowserRequest, Delivery);

fn failure(code: FailureCode) -> BrowserFailure {
    BrowserFailure::new(code, Delivery::NotStarted)
}

impl BrowserRuntime {
    pub fn new() -> Self {
        Self::default()
    }

    fn lock(&self) -> BrowserResult<MutexGuard<'_, State>> {
        self.state
            .lock()
            .map_err(|_| failure(FailureCode::StateUnavailable))
    }

    pub fn register_adapter(
        &self,
        descriptor: AdapterDescriptor,
        trusted: bool,
    ) -> BrowserResult<AdapterKey> {
        if !trusted {
            return Err(failure(FailureCode::NotTrusted));
        }
        if !valid_id(&descriptor.host_id)
            || descriptor.engine.is_empty()
            || descriptor.engine.len() > 128
            || descriptor.engine.chars().any(char::is_control)
            || descriptor.engine_version.is_empty()
            || descriptor.engine_version.len() > 128
            || descriptor.engine_version.chars().any(char::is_control)
            || descriptor.actions.is_empty()
            || descriptor.actions.len() > ActionKind::ALL.len()
            || descriptor.actions.iter().collect::<HashSet<_>>().len() != descriptor.actions.len()
            || descriptor.profile_modes.is_empty()
            || descriptor.profile_modes.len() > 2
            || descriptor
                .profile_modes
                .iter()
                .collect::<HashSet<_>>()
                .len()
                != descriptor.profile_modes.len()
        {
            return Err(invalid());
        }
        let mut state = self.lock()?;
        if state.closed {
            return Err(failure(FailureCode::Closed));
        }
        if state.adapters.len() >= 32 || state.adapters.contains_key(&descriptor.host_id) {
            return Err(failure(FailureCode::Busy));
        }
        let key = AdapterKey {
            host: BrowserHostRef {
                host_id: descriptor.host_id.clone(),
                generation: Uuid::new_v4().simple().to_string(),
            },
            token: Uuid::new_v4().simple().to_string(),
        };
        state.adapters.insert(
            descriptor.host_id.clone(),
            Registered {
                key: key.clone(),
                descriptor,
            },
        );
        Ok(key)
    }

    pub fn adapters(&self) -> BrowserResult<Vec<BrowserHost>> {
        let state = self.lock()?;
        let mut hosts = state
            .adapters
            .values()
            .map(|adapter| BrowserHost {
                reference: adapter.key.host.clone(),
                descriptor: adapter.descriptor.clone(),
            })
            .collect::<Vec<_>>();
        hosts.sort_by(|left, right| left.reference.host_id.cmp(&right.reference.host_id));
        Ok(hosts)
    }

    pub fn authenticate_adapter(
        &self,
        host: &BrowserHostRef,
        token: &str,
    ) -> BrowserResult<AdapterKey> {
        let state = self.lock()?;
        let key = AdapterKey {
            host: host.clone(),
            token: token.into(),
        };
        authenticate(&state, &key)?;
        Ok(key)
    }

    pub fn unregister_adapter(&self, key: &AdapterKey) -> BrowserResult<()> {
        let events = {
            let mut state = self.lock()?;
            authenticate(&state, key)?;
            state.adapters.remove(&key.host.host_id);
            state.tabs.retain(|(host, _), _| host != &key.host);
            let ids = state
                .pending
                .iter()
                .filter(|(_, pending)| pending.request.host == key.host)
                .map(|(id, _)| id.clone())
                .collect::<Vec<_>>();
            ids.into_iter()
                .filter_map(|id| retire(&mut state, &id, FailureCode::AdapterUnavailable))
                .collect::<Vec<_>>()
        };
        emit_cancellations(events);
        Ok(())
    }

    pub fn begin_request(
        &self,
        scope: BrowserScope,
        profile: BrowserProfile,
        host: BrowserHostRef,
        action: BrowserAction,
    ) -> BrowserResult<PendingBrowserRequest> {
        scope.validate()?;
        if !valid_id(&profile.profile_id) {
            return Err(invalid());
        }
        let request = BrowserRequest {
            protocol: BROWSER_PROTOCOL.into(),
            request_id: Uuid::new_v4().simple().to_string(),
            host,
            scope,
            profile,
            action,
        };
        let mut state = self.lock()?;
        validate_request(&state, &request)?;
        let owner = Owner::of(&request);
        if state.pending.len() >= 256 || state.busy.contains(&owner) {
            return Err(failure(FailureCode::Busy));
        }
        let (sender, receiver) = oneshot::channel();
        let request_id = request.request_id.clone();
        state.busy.insert(owner);
        state.pending.insert(
            request_id.clone(),
            Pending {
                request,
                sender: Some(sender),
                stage: Stage::Prepared,
                cancellation: None,
                sink: None,
            },
        );
        Ok(PendingBrowserRequest {
            runtime: self.clone(),
            request_id,
            receiver: Some(receiver),
        })
    }

    pub(crate) fn keep_upload(
        &self,
        reply: &BrowserReply,
        directory: tempfile::TempDir,
    ) -> BrowserResult<()> {
        let AdapterResult::Changed { tab } = &reply.result else {
            return Err(invalid());
        };
        let mut state = self.lock()?;
        if let Some(current) = state
            .tabs
            .get_mut(&(reply.host.clone(), tab.tab_id.clone()))
            && current.owner.scope == reply.scope
            && current.owner.profile == reply.profile
        {
            current.uploads.push(directory);
        }
        Ok(())
    }

    fn dispatch(&self, id: &str, sink: EventSink) -> BrowserResult<()> {
        let event = {
            let mut state = self.lock()?;
            let pending = state
                .pending
                .get(id)
                .ok_or_else(|| failure(FailureCode::UnknownRequest))?;
            if pending.stage != Stage::Prepared {
                return Err(failure(FailureCode::Busy));
            }
            let request = pending.request.clone();
            validate_request(&state, &request)?;
            let mut event = serde_json::to_value(&request).map_err(|_| invalid())?;
            event["type"] = json!("browser.request");
            if let Some(target) = request.action.target() {
                state
                    .tabs
                    .get_mut(&(request.host.clone(), target.tab_id.clone()))
                    .ok_or_else(|| failure(FailureCode::UnknownTab))?
                    .observation = None;
            }
            let pending = state
                .pending
                .get_mut(id)
                .ok_or_else(|| failure(FailureCode::UnknownRequest))?;
            pending.sink = Some(sink.clone());
            pending.stage = Stage::Emitting;
            event
        };
        let _emission = EmissionGuard {
            runtime: self.clone(),
            request_id: id.into(),
        };
        sink(event);
        Ok(())
    }

    fn finish_emission(&self, id: &str, aborted: bool) -> BrowserResult<()> {
        let event = {
            let mut state = self.lock()?;
            let Some(pending) = state.pending.get_mut(id) else {
                return Ok(());
            };
            if pending.stage != Stage::Emitting {
                return Ok(());
            }
            pending.stage = Stage::Sent;
            let code = pending
                .cancellation
                .or(aborted.then_some(FailureCode::AdapterUnavailable));
            code.and_then(|code| retire(&mut state, id, code))
        };
        if !aborted {
            emit_cancellations(event);
        }
        Ok(())
    }

    pub fn complete_json(&self, key: &AdapterKey, value: Value) -> BrowserResult<()> {
        let completion =
            serde_json::from_value(value).map_err(|_| failure(FailureCode::InvalidResult))?;
        self.complete(key, completion)
    }

    pub fn complete(&self, key: &AdapterKey, completion: BrowserCompletion) -> BrowserResult<()> {
        let mut state = self.lock()?;
        authenticate(&state, key)?;
        if completion.protocol != BROWSER_PROTOCOL || !valid_id(&completion.request_id) {
            return Err(failure(FailureCode::InvalidResult));
        }
        if completion.host != key.host {
            return Err(failure(FailureCode::WrongHost));
        }
        let pending = state
            .pending
            .get(&completion.request_id)
            .ok_or_else(|| failure(FailureCode::UnknownRequest))?;
        if pending.stage == Stage::Prepared {
            return Err(failure(FailureCode::InvalidResult));
        }
        if pending.cancellation.is_some() {
            return Err(failure(FailureCode::UnknownRequest));
        }
        let request = pending.request.clone();
        if completion.host != request.host {
            return Err(failure(FailureCode::WrongHost));
        }
        if completion.scope != request.scope || completion.profile != request.profile {
            return Err(failure(FailureCode::ScopeMismatch));
        }
        let result = match completion.outcome {
            AdapterOutcome::Failed { delivery } => {
                Err(BrowserFailure::new(FailureCode::AdapterRejected, delivery))
            }
            AdapterOutcome::Completed { result } => {
                validate_result(&state, &request, &result)?;
                apply_result(&mut state, &request, &result);
                Ok(BrowserReply {
                    request_id: request.request_id.clone(),
                    host: request.host.clone(),
                    scope: request.scope.clone(),
                    profile: request.profile.clone(),
                    delivery: Delivery::Completed,
                    observation_id: matches!(result, AdapterResult::Observed { .. })
                        .then(|| request.request_id.clone()),
                    result,
                })
            }
        };
        let pending = state
            .pending
            .remove(&completion.request_id)
            .ok_or_else(|| failure(FailureCode::UnknownRequest))?;
        state.busy.remove(&Owner::of(&request));
        if let Some(sender) = pending.sender {
            let _ = sender.send(result);
        }
        Ok(())
    }

    pub fn invalidate_tab(
        &self,
        key: &AdapterKey,
        scope: &BrowserScope,
        profile: &BrowserProfile,
        tab_id: &str,
        revision: u64,
    ) -> BrowserResult<()> {
        self.update_tab_revision(key, scope, profile, tab_id, revision, false)
    }

    pub(crate) fn update_tab_revision(
        &self,
        key: &AdapterKey,
        scope: &BrowserScope,
        profile: &BrowserProfile,
        tab_id: &str,
        revision: u64,
        closed: bool,
    ) -> BrowserResult<()> {
        let mut state = self.lock()?;
        authenticate(&state, key)?;
        let tab = state
            .tabs
            .get_mut(&(key.host.clone(), tab_id.into()))
            .ok_or_else(|| failure(FailureCode::UnknownTab))?;
        if &tab.owner.scope != scope || &tab.owner.profile != profile {
            return Err(failure(FailureCode::ScopeMismatch));
        }
        if revision <= tab.record.revision {
            return Err(failure(FailureCode::StaleObservation));
        }
        tab.record.revision = revision;
        tab.observation = None;
        if closed {
            state.tabs.remove(&(key.host.clone(), tab_id.into()));
        }
        Ok(())
    }

    pub fn cancel_request(&self, scope: &BrowserScope, request_id: &str) -> BrowserResult<()> {
        let event = {
            let mut state = self.lock()?;
            let pending = state
                .pending
                .get(request_id)
                .ok_or_else(|| failure(FailureCode::UnknownRequest))?;
            if &pending.request.scope != scope {
                return Err(failure(FailureCode::ScopeMismatch));
            }
            retire(&mut state, request_id, FailureCode::Cancelled)
        };
        emit_cancellations(event);
        Ok(())
    }

    fn cancel_id(&self, request_id: &str, code: FailureCode) -> BrowserResult<()> {
        let event = {
            let mut state = self.lock()?;
            retire(&mut state, request_id, code)
        };
        emit_cancellations(event);
        Ok(())
    }

    pub fn cancel_scope(&self, scope: &BrowserScope) -> BrowserResult<usize> {
        let (count, events) = {
            let mut state = self.lock()?;
            let ids = state
                .pending
                .iter()
                .filter(|(_, pending)| &pending.request.scope == scope)
                .map(|(id, _)| id.clone())
                .collect::<Vec<_>>();
            let count = ids.len();
            let events = ids
                .into_iter()
                .filter_map(|id| retire(&mut state, &id, FailureCode::Cancelled))
                .collect::<Vec<_>>();
            (count, events)
        };
        emit_cancellations(events);
        Ok(count)
    }

    pub fn close(&self) -> BrowserResult<()> {
        let events = {
            let mut state = self.lock()?;
            state.closed = true;
            state.adapters.clear();
            state.tabs.clear();
            let ids = state.pending.keys().cloned().collect::<Vec<_>>();
            ids.into_iter()
                .filter_map(|id| retire(&mut state, &id, FailureCode::Closed))
                .collect::<Vec<_>>()
        };
        emit_cancellations(events);
        Ok(())
    }
}

impl PendingBrowserRequest {
    pub(crate) fn set_transfer_path(&self, staged: String) -> BrowserResult<()> {
        let mut state = self.runtime.lock()?;
        let pending = state
            .pending
            .get_mut(&self.request_id)
            .ok_or_else(invalid)?;
        match &mut pending.request.action {
            BrowserAction::Upload { path, .. } | BrowserAction::Download { path, .. }
                if pending.stage == Stage::Prepared =>
            {
                *path = staged;
                Ok(())
            }
            _ => Err(invalid()),
        }
    }

    pub fn request_id(&self) -> &str {
        &self.request_id
    }

    pub async fn wait(
        mut self,
        sink: EventSink,
        cancel: &CancellationToken,
        timeout: Duration,
    ) -> BrowserResult<BrowserReply> {
        let mut receiver = self.receiver.take().ok_or_else(invalid)?;
        if let Ok(result) = receiver.try_recv() {
            return result;
        }
        if timeout.is_zero() || timeout > Duration::from_secs(120) {
            return Err(invalid());
        }
        if cancel.is_cancelled() {
            self.runtime
                .cancel_id(&self.request_id, FailureCode::Cancelled)?;
            return receive(receiver.await, Delivery::NotStarted);
        }
        if let Err(error) = self.runtime.dispatch(&self.request_id, sink) {
            return receiver.try_recv().unwrap_or(Err(error));
        }
        tokio::select! {
            biased;
            result = &mut receiver => receive(result, Delivery::Unknown),
            _ = cancel.cancelled() => {
                self.runtime.cancel_id(&self.request_id, FailureCode::Cancelled)?;
                receive(receiver.await, Delivery::Unknown)
            }
            _ = tokio::time::sleep(timeout) => {
                self.runtime.cancel_id(&self.request_id, FailureCode::Timeout)?;
                receive(receiver.await, Delivery::Unknown)
            }
        }
    }
}

impl Drop for PendingBrowserRequest {
    fn drop(&mut self) {
        let _ = self
            .runtime
            .cancel_id(&self.request_id, FailureCode::Cancelled);
    }
}

fn receive(
    result: Result<BrowserResult<BrowserReply>, oneshot::error::RecvError>,
    delivery: Delivery,
) -> BrowserResult<BrowserReply> {
    result.unwrap_or_else(|_| Err(BrowserFailure::new(FailureCode::StateUnavailable, delivery)))
}

fn authenticate<'a>(state: &'a State, key: &AdapterKey) -> BrowserResult<&'a Registered> {
    let adapter = state
        .adapters
        .get(&key.host.host_id)
        .ok_or_else(|| failure(FailureCode::HostUnavailable))?;
    if adapter.key.host != key.host || adapter.key.token != key.token {
        return Err(failure(FailureCode::WrongHost));
    }
    Ok(adapter)
}

fn owned_tab<'a>(state: &'a State, request: &BrowserRequest, id: &str) -> BrowserResult<&'a Tab> {
    let tab = state
        .tabs
        .get(&(request.host.clone(), id.into()))
        .ok_or_else(|| failure(FailureCode::UnknownTab))?;
    if tab.owner != Owner::of(request) {
        return Err(failure(FailureCode::ScopeMismatch));
    }
    Ok(tab)
}

fn validate_request(state: &State, request: &BrowserRequest) -> BrowserResult<()> {
    if state.closed {
        return Err(failure(FailureCode::Closed));
    }
    let adapter = state
        .adapters
        .get(&request.host.host_id)
        .ok_or_else(|| failure(FailureCode::HostUnavailable))?;
    if adapter.key.host != request.host {
        return Err(failure(FailureCode::WrongHost));
    }
    if !adapter.descriptor.actions.contains(&request.action.kind())
        || !adapter
            .descriptor
            .profile_modes
            .contains(&request.profile.mode)
    {
        return Err(invalid());
    }
    match &request.action {
        BrowserAction::Open { url } | BrowserAction::Navigate { url, .. } if !valid_url(url) => {
            return Err(invalid());
        }
        BrowserAction::Type { text, .. } if text.len() > 65_536 || text.contains('\0') => {
            return Err(invalid());
        }
        BrowserAction::Scroll {
            delta_x, delta_y, ..
        } if delta_x.unsigned_abs() > 10_000 || delta_y.unsigned_abs() > 10_000 => {
            return Err(invalid());
        }
        _ => {}
    }
    if matches!(request.action, BrowserAction::Open { .. })
        && (state.tabs.len() >= 1024
            || state
                .tabs
                .values()
                .filter(|tab| tab.owner == Owner::of(request))
                .count()
                >= MAX_TABS)
    {
        return Err(failure(FailureCode::Busy));
    }
    if let Some(id) = request.action.tab_id() {
        if !valid_id(id) {
            return Err(invalid());
        }
        let tab = owned_tab(state, request, id)?;
        if let BrowserAction::Upload { origin, .. } = &request.action
            && (!valid_url(origin)
                || reqwest::Url::parse(&tab.record.url)
                    .ok()
                    .is_none_or(|url| url.origin().ascii_serialization() != *origin))
        {
            return Err(invalid());
        }
        if let Some(target) = request.action.target() {
            let observation = tab
                .observation
                .as_ref()
                .ok_or_else(|| failure(FailureCode::StaleObservation))?;
            if observation.id != target.observation_id
                || observation.revision != target.revision
                || tab.record.revision != target.revision
            {
                return Err(failure(FailureCode::StaleObservation));
            }
            let element = match &request.action {
                BrowserAction::Click { element_id, .. }
                | BrowserAction::Type { element_id, .. }
                | BrowserAction::Upload { element_id, .. }
                | BrowserAction::Download { element_id, .. } => Some(element_id),
                BrowserAction::Scroll { element_id, .. } => element_id.as_ref(),
                _ => None,
            };
            if let Some(element) = element {
                let editable = observation.elements.get(element).ok_or_else(invalid)?;
                if matches!(request.action, BrowserAction::Type { .. }) && !editable {
                    return Err(invalid());
                }
            }
        }
    }
    Ok(())
}

fn valid_tab_record(
    state: &State,
    request: &BrowserRequest,
    record: &BrowserTab,
) -> BrowserResult<()> {
    if !valid_id(&record.tab_id)
        || record.revision == 0
        || !valid_url(&record.url)
        || record.title.len() > 4096
    {
        return Err(failure(FailureCode::InvalidResult));
    }
    if let Some(tab) = state
        .tabs
        .get(&(request.host.clone(), record.tab_id.clone()))
    {
        if tab.owner != Owner::of(request) {
            return Err(failure(FailureCode::ScopeMismatch));
        }
        if record.revision < tab.record.revision
            || record.url != tab.record.url && record.revision == tab.record.revision
        {
            return Err(failure(FailureCode::StaleObservation));
        }
    }
    Ok(())
}

fn inside(rectangle: &Rectangle, viewport: &Viewport) -> bool {
    [rectangle.x, rectangle.y, rectangle.width, rectangle.height]
        .into_iter()
        .all(f64::is_finite)
        && rectangle.x >= 0.0
        && rectangle.y >= 0.0
        && rectangle.width > 0.0
        && rectangle.height > 0.0
        && rectangle.x + rectangle.width <= viewport.width
        && rectangle.y + rectangle.height <= viewport.height
}

fn validate_observation(observation: &PageObservation) -> BrowserResult<()> {
    let viewport = &observation.viewport;
    if ![
        viewport.width,
        viewport.height,
        viewport.device_scale_factor,
    ]
    .into_iter()
    .all(f64::is_finite)
        || viewport.width <= 0.0
        || viewport.height <= 0.0
        || viewport.width > 65_536.0
        || viewport.height > 65_536.0
        || viewport.device_scale_factor <= 0.0
        || viewport.device_scale_factor > 16.0
        || observation.elements.len() > MAX_ELEMENTS
    {
        return Err(failure(FailureCode::InvalidResult));
    }
    let mut ids = HashSet::new();
    let mut text_bytes = 0;
    for element in &observation.elements {
        if !valid_id(&element.element_id)
            || !valid_id(&element.frame_id)
            || !ids.insert(&element.element_id)
            || element.role.len() > 128
            || element.name.len() > 2048
            || element.text.len() > 16_384
            || !inside(&element.bounds, viewport)
        {
            return Err(failure(FailureCode::InvalidResult));
        }
        text_bytes += element.role.len() + element.name.len() + element.text.len();
    }
    if text_bytes > 524_288 {
        return Err(failure(FailureCode::InvalidResult));
    }
    if let Some(image) = &observation.screenshot
        && (!valid_id(&image.image_id)
            || image.returned_width == 0
            || image.returned_height == 0
            || image.returned_width > 16_384
            || image.returned_height > 16_384
            || !inside(&image.capture, viewport))
    {
        return Err(failure(FailureCode::InvalidResult));
    }
    Ok(())
}

fn validate_result(
    state: &State,
    request: &BrowserRequest,
    result: &AdapterResult,
) -> BrowserResult<()> {
    match (&request.action, result) {
        (BrowserAction::Open { .. }, AdapterResult::Opened { tab }) => {
            valid_tab_record(state, request, tab)?;
            if state
                .tabs
                .contains_key(&(request.host.clone(), tab.tab_id.clone()))
                || state.tabs.len() >= 1024
            {
                return Err(failure(FailureCode::InvalidResult));
            }
        }
        (BrowserAction::List, AdapterResult::Listed { tabs }) => {
            if tabs.len() > MAX_TABS {
                return Err(failure(FailureCode::InvalidResult));
            }
            let mut ids = HashSet::new();
            let mut added = 0;
            for tab in tabs {
                valid_tab_record(state, request, tab)?;
                if !ids.insert(&tab.tab_id) {
                    return Err(failure(FailureCode::InvalidResult));
                }
                if !state
                    .tabs
                    .contains_key(&(request.host.clone(), tab.tab_id.clone()))
                {
                    added += 1;
                }
            }
            if state.tabs.len() + added > 1024 {
                return Err(failure(FailureCode::InvalidResult));
            }
        }
        (BrowserAction::Observe { tab_id }, AdapterResult::Observed { observation }) => {
            if &observation.tab.tab_id != tab_id {
                return Err(failure(FailureCode::InvalidResult));
            }
            valid_tab_record(state, request, &observation.tab)?;
            validate_observation(observation)?;
        }
        (action, AdapterResult::Changed { tab })
            if action.target().is_some() && !matches!(action, BrowserAction::Close { .. }) =>
        {
            if action.tab_id() != Some(tab.tab_id.as_str()) {
                return Err(failure(FailureCode::InvalidResult));
            }
            valid_tab_record(state, request, tab)?;
        }
        (BrowserAction::Close { target }, AdapterResult::Closed { tab_id })
            if &target.tab_id == tab_id => {}
        _ => return Err(failure(FailureCode::InvalidResult)),
    }
    Ok(())
}

fn update_tab(state: &mut State, request: &BrowserRequest, record: &BrowserTab) {
    let key = (request.host.clone(), record.tab_id.clone());
    let tab = state.tabs.entry(key).or_insert_with(|| Tab {
        owner: Owner::of(request),
        record: record.clone(),
        observation: None,
        uploads: Vec::new(),
    });
    if tab.record.revision != record.revision
        || tab.record.url != record.url
        || tab.record.title != record.title
    {
        tab.observation = None;
    }
    tab.record = record.clone();
}

fn apply_result(state: &mut State, request: &BrowserRequest, result: &AdapterResult) {
    match result {
        AdapterResult::Opened { tab } | AdapterResult::Changed { tab } => {
            update_tab(state, request, tab)
        }
        AdapterResult::Listed { tabs } => {
            let ids = tabs
                .iter()
                .map(|tab| tab.tab_id.as_str())
                .collect::<HashSet<_>>();
            state.tabs.retain(|(_, id), tab| {
                tab.owner != Owner::of(request) || ids.contains(id.as_str())
            });
            for tab in tabs {
                update_tab(state, request, tab);
            }
        }
        AdapterResult::Observed { observation } => {
            update_tab(state, request, &observation.tab);
            if let Some(tab) = state
                .tabs
                .get_mut(&(request.host.clone(), observation.tab.tab_id.clone()))
            {
                tab.observation = Some(Observation {
                    id: request.request_id.clone(),
                    revision: observation.tab.revision,
                    elements: observation
                        .elements
                        .iter()
                        .map(|element| (element.element_id.clone(), element.editable))
                        .collect(),
                });
            }
        }
        AdapterResult::Closed { tab_id } => {
            state.tabs.remove(&(request.host.clone(), tab_id.clone()));
        }
    }
}

fn retire(state: &mut State, id: &str, code: FailureCode) -> Option<CancelEvent> {
    let pending = state.pending.get_mut(id)?;
    if pending.stage == Stage::Emitting {
        if pending.cancellation.is_none() {
            pending.cancellation = Some(code);
            if let Some(sender) = pending.sender.take() {
                let _ = sender.send(Err(BrowserFailure::new(code, Delivery::Unknown)));
            }
        }
        return None;
    }
    let pending = state.pending.remove(id)?;
    state.busy.remove(&Owner::of(&pending.request));
    let delivery = if pending.stage == Stage::Prepared {
        Delivery::NotStarted
    } else {
        Delivery::Unknown
    };
    if let Some(sender) = pending.sender {
        let _ = sender.send(Err(BrowserFailure::new(
            pending.cancellation.unwrap_or(code),
            delivery,
        )));
    }
    pending.sink.map(|sink| (sink, pending.request, delivery))
}

fn emit_cancellations(events: impl IntoIterator<Item = CancelEvent>) {
    for (sink, request, delivery) in events {
        sink(
            json!({"type":"browser.cancel","protocol":BROWSER_PROTOCOL,"request_id":request.request_id,
            "host":request.host,"scope":request.scope,"profile":request.profile,"delivery":delivery}),
        );
    }
}

use serde::{Deserialize, Serialize};
use std::{fmt, path::Path};
use ts_rs::TS;

pub const BROWSER_PROTOCOL: &str = "reverie.browser.v1";
pub(super) const MAX_TABS: usize = 64;
pub(super) const MAX_ELEMENTS: usize = 256;

pub type BrowserResult<T> = Result<T, BrowserFailure>;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize, TS)]
#[serde(rename_all = "snake_case")]
pub enum Delivery {
    NotStarted,
    Unknown,
    Completed,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize, TS)]
#[serde(rename_all = "snake_case")]
pub enum FailureCode {
    InvalidRequest,
    NotTrusted,
    HostUnavailable,
    WrongHost,
    ScopeMismatch,
    UnknownRequest,
    Busy,
    UnknownTab,
    StaleObservation,
    InvalidResult,
    Cancelled,
    Timeout,
    AdapterUnavailable,
    AdapterRejected,
    Closed,
    StateUnavailable,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize, TS)]
#[serde(deny_unknown_fields)]
pub struct BrowserFailure {
    pub code: FailureCode,
    pub delivery: Delivery,
}

impl BrowserFailure {
    pub(super) fn new(code: FailureCode, delivery: Delivery) -> Self {
        Self { code, delivery }
    }
}

impl fmt::Display for BrowserFailure {
    fn fmt(&self, output: &mut fmt::Formatter<'_>) -> fmt::Result {
        let message = match self.code {
            FailureCode::InvalidRequest => "Invalid or unsupported browser request.",
            FailureCode::NotTrusted => "Browser adapter registration requires explicit trust.",
            FailureCode::HostUnavailable => "The selected browser host is unavailable.",
            FailureCode::WrongHost => "Browser adapter identity or generation does not match.",
            FailureCode::ScopeMismatch => "Browser request ownership does not match.",
            FailureCode::UnknownRequest => "Browser request is not active.",
            FailureCode::Busy => "This browser ownership scope already has an active request.",
            FailureCode::UnknownTab => "The browser tab is not owned by this request scope.",
            FailureCode::StaleObservation => "Observe the browser tab again before acting.",
            FailureCode::InvalidResult => "Browser adapter returned an invalid result.",
            FailureCode::Cancelled => "Browser request was cancelled.",
            FailureCode::Timeout => "Browser adapter did not complete before the deadline.",
            FailureCode::AdapterUnavailable => "Browser adapter disconnected during the request.",
            FailureCode::AdapterRejected => "Browser adapter rejected the requested operation.",
            FailureCode::Closed => "Browser runtime is closed.",
            FailureCode::StateUnavailable => "Browser runtime state is unavailable.",
        };
        output.write_str(message)
    }
}

impl std::error::Error for BrowserFailure {}

#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize, TS)]
#[serde(deny_unknown_fields)]
pub struct BrowserScope {
    pub project_root: String,
    pub session_id: String,
    pub run_id: String,
}

impl BrowserScope {
    pub fn new(project: &Path, session: &str, run: &str) -> BrowserResult<Self> {
        if !project.is_absolute() || !valid_id(session) || !valid_id(run) {
            return Err(invalid());
        }
        let project = project.canonicalize().map_err(|_| invalid())?;
        if !project.is_dir() {
            return Err(invalid());
        }
        Ok(Self {
            project_root: project.to_str().ok_or_else(invalid)?.into(),
            session_id: session.into(),
            run_id: run.into(),
        })
    }

    pub(super) fn validate(&self) -> BrowserResult<()> {
        let normalized = Self::new(
            Path::new(&self.project_root),
            &self.session_id,
            &self.run_id,
        )?;
        if normalized != *self {
            return Err(invalid());
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize, TS)]
#[serde(rename_all = "snake_case")]
pub enum ProfileMode {
    Ephemeral,
    Persistent,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize, TS)]
#[serde(deny_unknown_fields)]
pub struct BrowserProfile {
    pub mode: ProfileMode,
    pub profile_id: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize, TS)]
#[serde(deny_unknown_fields)]
pub struct BrowserHostRef {
    pub host_id: String,
    pub generation: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize, TS)]
#[serde(rename_all = "snake_case")]
pub enum ActionKind {
    Open,
    List,
    Observe,
    Click,
    Type,
    Scroll,
    Key,
    Navigate,
    Back,
    Forward,
    Reload,
    Close,
}

impl ActionKind {
    pub const ALL: &[Self] = &[
        Self::Open,
        Self::List,
        Self::Observe,
        Self::Click,
        Self::Type,
        Self::Scroll,
        Self::Key,
        Self::Navigate,
        Self::Back,
        Self::Forward,
        Self::Reload,
        Self::Close,
    ];
}

#[derive(Clone, Debug, Serialize, Deserialize, TS)]
#[serde(deny_unknown_fields)]
pub struct AdapterDescriptor {
    pub host_id: String,
    pub engine: String,
    pub engine_version: String,
    pub actions: Vec<ActionKind>,
    pub profile_modes: Vec<ProfileMode>,
}

#[derive(Clone, Debug, Serialize, Deserialize, TS)]
#[serde(deny_unknown_fields)]
pub struct BrowserHost {
    pub reference: BrowserHostRef,
    pub descriptor: AdapterDescriptor,
}

/// Only the trusted adapter control channel may receive the private token.
#[derive(Clone)]
pub struct AdapterKey {
    pub(super) host: BrowserHostRef,
    pub(super) token: String,
}

impl AdapterKey {
    pub fn host(&self) -> &BrowserHostRef {
        &self.host
    }

    pub fn private_token(&self) -> &str {
        &self.token
    }
}

impl fmt::Debug for AdapterKey {
    fn fmt(&self, output: &mut fmt::Formatter<'_>) -> fmt::Result {
        output
            .debug_struct("AdapterKey")
            .field("host", &self.host)
            .field("token", &"[redacted]")
            .finish()
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize, TS)]
#[serde(deny_unknown_fields)]
pub struct BrowserTarget {
    pub tab_id: String,
    pub observation_id: String,
    #[ts(type = "number")]
    pub revision: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize, TS)]
#[serde(rename_all = "snake_case")]
pub enum BrowserKey {
    Enter,
    Tab,
    Escape,
    Backspace,
    Delete,
    Space,
    ArrowUp,
    ArrowDown,
    ArrowLeft,
    ArrowRight,
    Home,
    End,
    PageUp,
    PageDown,
}

#[derive(Clone, Debug, Serialize, Deserialize, TS)]
#[serde(tag = "action", rename_all = "snake_case", deny_unknown_fields)]
pub enum BrowserAction {
    Open {
        url: String,
    },
    List,
    Observe {
        tab_id: String,
    },
    Click {
        target: BrowserTarget,
        element_id: String,
    },
    Type {
        target: BrowserTarget,
        element_id: String,
        text: String,
        replace: bool,
    },
    Scroll {
        target: BrowserTarget,
        element_id: Option<String>,
        delta_x: i32,
        delta_y: i32,
    },
    Key {
        target: BrowserTarget,
        key: BrowserKey,
        shift: bool,
    },
    Navigate {
        target: BrowserTarget,
        url: String,
    },
    Back {
        target: BrowserTarget,
    },
    Forward {
        target: BrowserTarget,
    },
    Reload {
        target: BrowserTarget,
    },
    Close {
        target: BrowserTarget,
    },
}

impl BrowserAction {
    pub fn kind(&self) -> ActionKind {
        match self {
            Self::Open { .. } => ActionKind::Open,
            Self::List => ActionKind::List,
            Self::Observe { .. } => ActionKind::Observe,
            Self::Click { .. } => ActionKind::Click,
            Self::Type { .. } => ActionKind::Type,
            Self::Scroll { .. } => ActionKind::Scroll,
            Self::Key { .. } => ActionKind::Key,
            Self::Navigate { .. } => ActionKind::Navigate,
            Self::Back { .. } => ActionKind::Back,
            Self::Forward { .. } => ActionKind::Forward,
            Self::Reload { .. } => ActionKind::Reload,
            Self::Close { .. } => ActionKind::Close,
        }
    }

    pub(super) fn target(&self) -> Option<&BrowserTarget> {
        match self {
            Self::Click { target, .. }
            | Self::Type { target, .. }
            | Self::Scroll { target, .. }
            | Self::Key { target, .. }
            | Self::Navigate { target, .. }
            | Self::Back { target }
            | Self::Forward { target }
            | Self::Reload { target }
            | Self::Close { target } => Some(target),
            _ => None,
        }
    }

    pub(super) fn tab_id(&self) -> Option<&str> {
        match self {
            Self::Observe { tab_id } => Some(tab_id),
            _ => self.target().map(|target| target.tab_id.as_str()),
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, TS)]
#[serde(deny_unknown_fields)]
pub struct BrowserRequest {
    pub protocol: String,
    pub request_id: String,
    pub host: BrowserHostRef,
    pub scope: BrowserScope,
    pub profile: BrowserProfile,
    pub action: BrowserAction,
}

#[derive(Clone, Debug, Serialize, Deserialize, TS)]
#[serde(deny_unknown_fields)]
pub struct BrowserTab {
    pub tab_id: String,
    #[ts(type = "number")]
    pub revision: u64,
    pub url: String,
    pub title: String,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, TS)]
#[serde(deny_unknown_fields)]
pub struct Rectangle {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize, TS)]
#[serde(deny_unknown_fields)]
pub struct Viewport {
    pub width: f64,
    pub height: f64,
    pub device_scale_factor: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize, TS)]
#[serde(deny_unknown_fields)]
pub struct BrowserElement {
    pub element_id: String,
    pub frame_id: String,
    pub role: String,
    pub name: String,
    pub text: String,
    pub editable: bool,
    /// Visible clipped bounds in viewport CSS pixels.
    pub bounds: Rectangle,
}

#[derive(Clone, Debug, Serialize, Deserialize, TS)]
#[serde(deny_unknown_fields)]
pub struct ScreenshotRef {
    pub image_id: String,
    pub returned_width: u32,
    pub returned_height: u32,
    /// Captured rectangle in viewport CSS pixels, before return-image scaling.
    pub capture: Rectangle,
}

#[derive(Clone, Debug, Serialize, Deserialize, TS)]
#[serde(deny_unknown_fields)]
pub struct PageObservation {
    pub tab: BrowserTab,
    pub viewport: Viewport,
    pub elements: Vec<BrowserElement>,
    pub screenshot: Option<ScreenshotRef>,
}

#[derive(Clone, Debug, Serialize, Deserialize, TS)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum AdapterResult {
    Opened { tab: BrowserTab },
    Listed { tabs: Vec<BrowserTab> },
    Observed { observation: PageObservation },
    Changed { tab: BrowserTab },
    Closed { tab_id: String },
}

#[derive(Clone, Debug, Serialize, Deserialize, TS)]
#[serde(tag = "status", rename_all = "snake_case", deny_unknown_fields)]
pub enum AdapterOutcome {
    Completed { result: AdapterResult },
    Failed { delivery: Delivery },
}

#[derive(Clone, Debug, Serialize, Deserialize, TS)]
#[serde(deny_unknown_fields)]
pub struct BrowserCompletion {
    pub protocol: String,
    pub request_id: String,
    pub host: BrowserHostRef,
    pub scope: BrowserScope,
    pub profile: BrowserProfile,
    pub outcome: AdapterOutcome,
}

#[derive(Clone, Debug, Serialize, Deserialize, TS)]
#[serde(deny_unknown_fields)]
pub struct BrowserReply {
    pub request_id: String,
    pub host: BrowserHostRef,
    pub scope: BrowserScope,
    pub profile: BrowserProfile,
    pub delivery: Delivery,
    pub observation_id: Option<String>,
    pub result: AdapterResult,
}

impl BrowserReply {
    pub fn target(&self) -> Option<BrowserTarget> {
        let AdapterResult::Observed { observation } = &self.result else {
            return None;
        };
        Some(BrowserTarget {
            tab_id: observation.tab.tab_id.clone(),
            observation_id: self.observation_id.clone()?,
            revision: observation.tab.revision,
        })
    }
}

pub(super) fn valid_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 256
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"-_.".contains(&byte))
}

pub(super) fn valid_url(value: &str) -> bool {
    if value == "about:blank" {
        return true;
    }
    value.len() <= 8192
        && !value.chars().any(char::is_control)
        && reqwest::Url::parse(value).is_ok_and(|url| {
            matches!(url.scheme(), "http" | "https")
                && url.host_str().is_some()
                && url.username().is_empty()
                && url.password().is_none()
        })
}

pub(super) fn invalid() -> BrowserFailure {
    BrowserFailure::new(FailureCode::InvalidRequest, Delivery::NotStarted)
}

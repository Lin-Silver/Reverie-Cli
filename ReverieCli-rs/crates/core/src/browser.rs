//! Owned browser requests for a trusted Electron or future CLI adapter.
//! Browser processes, profile defaults and permission decisions belong to the host.
mod runtime;
mod types;

pub use runtime::{BrowserRuntime, PendingBrowserRequest};
pub use types::*;

pub fn typescript_types() -> String {
    use ts_rs::TS;

    [
        Delivery::decl(),
        FailureCode::decl(),
        BrowserFailure::decl(),
        BrowserScope::decl(),
        ProfileMode::decl(),
        BrowserProfile::decl(),
        BrowserHostRef::decl(),
        ActionKind::decl(),
        AdapterDescriptor::decl(),
        BrowserHost::decl(),
        BrowserTarget::decl(),
        BrowserKey::decl(),
        BrowserAction::decl(),
        BrowserRequest::decl(),
        BrowserTab::decl(),
        Rectangle::decl(),
        Viewport::decl(),
        BrowserElement::decl(),
        ScreenshotRef::decl(),
        PageObservation::decl(),
        AdapterResult::decl(),
        AdapterOutcome::decl(),
        BrowserCompletion::decl(),
        BrowserReply::decl(),
    ]
    .into_iter()
    .map(|definition| format!("export {definition}"))
    .collect::<Vec<_>>()
    .join("\n")
        + "\n"
}

#[cfg(test)]
mod tests;

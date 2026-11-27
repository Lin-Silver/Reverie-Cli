use super::*;
use crate::host::EventSink;
use serde_json::{Value, json};
use std::{
    collections::HashSet,
    path::PathBuf,
    sync::{Arc, Barrier, Mutex, mpsc},
    time::Duration,
};
use tokio_util::sync::CancellationToken;

struct Fixture {
    _directory: tempfile::TempDir,
    runtime: BrowserRuntime,
    key: AdapterKey,
    scope: BrowserScope,
    profile: BrowserProfile,
}

fn descriptor() -> AdapterDescriptor {
    AdapterDescriptor {
        host_id: "fixture-host".into(),
        engine: "Rust test adapter".into(),
        engine_version: "fixture-1".into(),
        actions: ActionKind::ALL.to_vec(),
        profile_modes: vec![ProfileMode::Ephemeral],
    }
}

fn fixture() -> Fixture {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .join(".runtime/rust-3.0/browser-library-tests");
    std::fs::create_dir_all(&root).unwrap();
    let directory = tempfile::Builder::new()
        .prefix("case-")
        .tempdir_in(root)
        .unwrap();
    let scope = BrowserScope::new(directory.path(), "fixture-session", "fixture-run").unwrap();
    let runtime = BrowserRuntime::new();
    let key = runtime.register_adapter(descriptor(), true).unwrap();
    Fixture {
        _directory: directory,
        runtime,
        key,
        scope,
        profile: BrowserProfile {
            mode: ProfileMode::Ephemeral,
            profile_id: "explicit-fixture-profile".into(),
        },
    }
}

fn rejected<T>(result: BrowserResult<T>) -> BrowserFailure {
    match result {
        Err(error) => error,
        Ok(_) => panic!("The browser boundary unexpectedly accepted the operation"),
    }
}

fn begin(fixture: &Fixture, action: BrowserAction) -> BrowserResult<PendingBrowserRequest> {
    fixture.runtime.begin_request(
        fixture.scope.clone(),
        fixture.profile.clone(),
        fixture.key.host().clone(),
        action,
    )
}

fn request(event: &Value) -> BrowserRequest {
    assert_eq!(event["type"], "browser.request");
    let mut body = event.as_object().unwrap().clone();
    body.remove("type");
    serde_json::from_value(Value::Object(body)).unwrap()
}

fn completion(request: &BrowserRequest, result: AdapterResult) -> BrowserCompletion {
    BrowserCompletion {
        protocol: BROWSER_PROTOCOL.into(),
        request_id: request.request_id.clone(),
        host: request.host.clone(),
        scope: request.scope.clone(),
        profile: request.profile.clone(),
        outcome: AdapterOutcome::Completed { result },
    }
}

fn tab(revision: u64) -> BrowserTab {
    BrowserTab {
        tab_id: "fixture-tab".into(),
        revision,
        url: "https://example.test/start".into(),
        title: "Fixture page".into(),
    }
}

fn observation(tab: BrowserTab) -> AdapterResult {
    AdapterResult::Observed {
        observation: PageObservation {
            tab,
            viewport: Viewport {
                width: 800.0,
                height: 600.0,
                device_scale_factor: 1.25,
            },
            elements: vec![
                BrowserElement {
                    element_id: "input-1".into(),
                    frame_id: "frame-1".into(),
                    role: "textbox".into(),
                    name: "Input".into(),
                    text: String::new(),
                    editable: true,
                    bounds: Rectangle {
                        x: 10.0,
                        y: 20.0,
                        width: 120.0,
                        height: 30.0,
                    },
                },
                BrowserElement {
                    element_id: "button-1".into(),
                    frame_id: "frame-1".into(),
                    role: "button".into(),
                    name: "Submit".into(),
                    text: "Submit".into(),
                    editable: false,
                    bounds: Rectangle {
                        x: 140.0,
                        y: 20.0,
                        width: 80.0,
                        height: 30.0,
                    },
                },
            ],
            screenshot: Some(ScreenshotRef {
                image_id: "fixture-image".into(),
                returned_width: 400,
                returned_height: 300,
                capture: Rectangle {
                    x: 0.0,
                    y: 0.0,
                    width: 800.0,
                    height: 600.0,
                },
            }),
        },
    }
}

async fn perform(fixture: &Fixture, action: BrowserAction, result: AdapterResult) -> BrowserReply {
    let pending = begin(fixture, action).unwrap();
    let runtime = fixture.runtime.clone();
    let key = fixture.key.clone();
    let sink: EventSink = Arc::new(move |event| {
        if event["type"] == "browser.request" {
            runtime
                .complete(&key, completion(&request(&event), result.clone()))
                .unwrap();
        }
    });
    let reply = pending
        .wait(sink, &CancellationToken::new(), Duration::from_secs(10))
        .await
        .unwrap();
    assert_eq!(reply.delivery, Delivery::Completed);
    reply
}

async fn open(fixture: &Fixture) {
    perform(
        fixture,
        BrowserAction::Open {
            url: tab(1).url.clone(),
        },
        AdapterResult::Opened { tab: tab(1) },
    )
    .await;
}

async fn observe(fixture: &Fixture, record: BrowserTab) -> BrowserTarget {
    perform(
        fixture,
        BrowserAction::Observe {
            tab_id: record.tab_id.clone(),
        },
        observation(record),
    )
    .await
    .target()
    .unwrap()
}

fn trace_sink(trace: &Arc<Mutex<Vec<Value>>>) -> EventSink {
    let trace = trace.clone();
    Arc::new(move |event| trace.lock().unwrap().push(event))
}

fn trace_events(trace: &Arc<Mutex<Vec<Value>>>) -> Vec<Value> {
    trace.lock().unwrap().clone()
}

#[test]
fn registration_and_json_boundaries_are_explicit() {
    let runtime = BrowserRuntime::new();
    assert_eq!(
        rejected(runtime.register_adapter(descriptor(), false)).code,
        FailureCode::NotTrusted
    );
    assert!(runtime.adapters().unwrap().is_empty());
    let key = runtime.register_adapter(descriptor(), true).unwrap();
    let public = serde_json::to_string(&runtime.adapters().unwrap()).unwrap();
    assert!(!public.contains(key.private_token()));
    assert!(!format!("{key:?}").contains(key.private_token()));
    assert_eq!(
        rejected(runtime.authenticate_adapter(key.host(), "wrong-token")).code,
        FailureCode::WrongHost
    );
    assert!(
        serde_json::from_value::<BrowserProfile>(json!({"profile_id":"missing-mode"})).is_err()
    );
    assert!(
        serde_json::from_value::<BrowserAction>(
            json!({"action":"cdp","command":"Runtime.evaluate"})
        )
        .is_err()
    );
    assert!(
        serde_json::from_value::<BrowserAction>(
            json!({"action":"open","url":"https://example.test","script":"arbitrary"})
        )
        .is_err()
    );
    assert!(serde_json::from_value::<BrowserKey>(json!("F12")).is_err());

    let fixture = fixture();
    let persistent = BrowserProfile {
        mode: ProfileMode::Persistent,
        profile_id: "explicit-persistent".into(),
    };
    assert_eq!(
        rejected(fixture.runtime.begin_request(
            fixture.scope.clone(),
            persistent,
            fixture.key.host().clone(),
            BrowserAction::List
        ))
        .code,
        FailureCode::InvalidRequest
    );
    for url in [
        "javascript:alert(1)",
        "file:///private",
        "data:text/html,x",
        "about:config",
        "https://user:fixture-secret@example.test/",
    ] {
        let error = rejected(begin(&fixture, BrowserAction::Open { url: url.into() }));
        assert_eq!(error.delivery, Delivery::NotStarted);
        assert!(!error.to_string().contains("fixture-secret"));
    }
}

#[tokio::test]
async fn finite_actions_use_owned_observations() {
    let fixture = fixture();
    open(&fixture).await;
    let mut record = tab(1);
    let listed = perform(
        &fixture,
        BrowserAction::List,
        AdapterResult::Listed {
            tabs: vec![record.clone()],
        },
    )
    .await;
    assert!(matches!(listed.result, AdapterResult::Listed { .. }));
    let target = observe(&fixture, record.clone()).await;
    let click = BrowserAction::Click {
        target: target.clone(),
        element_id: "button-1".into(),
    };
    record.revision += 1;
    perform(
        &fixture,
        click,
        AdapterResult::Changed {
            tab: record.clone(),
        },
    )
    .await;
    assert_eq!(
        rejected(begin(
            &fixture,
            BrowserAction::Click {
                target,
                element_id: "button-1".into()
            }
        ))
        .code,
        FailureCode::StaleObservation
    );

    let target = observe(&fixture, record.clone()).await;
    assert_eq!(
        rejected(begin(
            &fixture,
            BrowserAction::Type {
                target: target.clone(),
                element_id: "button-1".into(),
                text: "text".into(),
                replace: true
            }
        ))
        .code,
        FailureCode::InvalidRequest
    );
    let action = BrowserAction::Type {
        target,
        element_id: "input-1".into(),
        text: "Hello 世界".into(),
        replace: true,
    };
    record.revision += 1;
    perform(
        &fixture,
        action,
        AdapterResult::Changed {
            tab: record.clone(),
        },
    )
    .await;

    let target = observe(&fixture, record.clone()).await;
    let action = BrowserAction::Scroll {
        target,
        element_id: None,
        delta_x: 10,
        delta_y: 80,
    };
    record.revision += 1;
    perform(
        &fixture,
        action,
        AdapterResult::Changed {
            tab: record.clone(),
        },
    )
    .await;
    let target = observe(&fixture, record.clone()).await;
    let action = BrowserAction::Key {
        target,
        key: BrowserKey::ArrowDown,
        shift: false,
    };
    record.revision += 1;
    perform(
        &fixture,
        action,
        AdapterResult::Changed {
            tab: record.clone(),
        },
    )
    .await;
    let target = observe(&fixture, record.clone()).await;
    record.revision += 1;
    record.url = "https://example.test/next".into();
    perform(
        &fixture,
        BrowserAction::Navigate {
            target,
            url: record.url.clone(),
        },
        AdapterResult::Changed {
            tab: record.clone(),
        },
    )
    .await;
    for action in ["back", "forward", "reload"] {
        let target = observe(&fixture, record.clone()).await;
        let action: BrowserAction =
            serde_json::from_value(json!({ "action": action, "target": target })).unwrap();
        record.revision += 1;
        perform(
            &fixture,
            action.clone(),
            AdapterResult::Changed {
                tab: record.clone(),
            },
        )
        .await;
        assert_eq!(
            rejected(begin(&fixture, action)).code,
            FailureCode::StaleObservation
        );
    }
    let target = observe(&fixture, record).await;
    perform(
        &fixture,
        BrowserAction::Close { target },
        AdapterResult::Closed {
            tab_id: "fixture-tab".into(),
        },
    )
    .await;
    assert_eq!(
        rejected(begin(
            &fixture,
            BrowserAction::Observe {
                tab_id: "fixture-tab".into()
            }
        ))
        .code,
        FailureCode::UnknownTab
    );
}

#[tokio::test]
async fn unsent_completion_and_pre_dispatch_cancellation_do_not_emit() {
    let fixture = fixture();
    let pending = begin(
        &fixture,
        BrowserAction::Open {
            url: "about:blank".into(),
        },
    )
    .unwrap();
    let unsolicited = BrowserCompletion {
        protocol: BROWSER_PROTOCOL.into(),
        request_id: pending.request_id().into(),
        host: fixture.key.host().clone(),
        scope: fixture.scope.clone(),
        profile: fixture.profile.clone(),
        outcome: AdapterOutcome::Completed {
            result: AdapterResult::Opened { tab: tab(1) },
        },
    };
    assert_eq!(
        rejected(fixture.runtime.complete(&fixture.key, unsolicited)).code,
        FailureCode::InvalidResult
    );
    let trace = Arc::new(Mutex::new(Vec::new()));
    let cancel = CancellationToken::new();
    cancel.cancel();
    let error = pending
        .wait(trace_sink(&trace), &cancel, Duration::from_secs(10))
        .await
        .unwrap_err();
    assert_eq!(
        error,
        BrowserFailure {
            code: FailureCode::Cancelled,
            delivery: Delivery::NotStarted
        }
    );
    assert!(trace_events(&trace).is_empty());
    drop(begin(&fixture, BrowserAction::List).unwrap());
    drop(begin(&fixture, BrowserAction::List).unwrap());
}

#[tokio::test]
async fn invalid_completion_bindings_do_not_consume_the_waiter() {
    let fixture = fixture();
    let pending = begin(&fixture, BrowserAction::Open { url: tab(1).url }).unwrap();
    let (sent, mut events) = tokio::sync::mpsc::unbounded_channel();
    let sink: EventSink = Arc::new(move |event| {
        let _ = sent.send(event);
    });
    let waiter = tokio::spawn(async move {
        pending
            .wait(sink, &CancellationToken::new(), Duration::from_secs(10))
            .await
    });
    let request = request(
        &tokio::time::timeout(Duration::from_secs(5), events.recv())
            .await
            .unwrap()
            .unwrap(),
    );
    let valid = completion(&request, AdapterResult::Opened { tab: tab(1) });
    let mut bad = valid.clone();
    bad.request_id = "nonexistent-request".into();
    assert_eq!(
        rejected(fixture.runtime.complete(&fixture.key, bad)).code,
        FailureCode::UnknownRequest
    );
    let mut bad = valid.clone();
    bad.host.generation = "wrong-generation".into();
    assert_eq!(
        rejected(fixture.runtime.complete(&fixture.key, bad)).code,
        FailureCode::WrongHost
    );
    let mut bad = valid.clone();
    bad.scope.run_id = "other-run".into();
    assert_eq!(
        rejected(fixture.runtime.complete(&fixture.key, bad)).code,
        FailureCode::ScopeMismatch
    );
    let mut bad = valid.clone();
    bad.profile.profile_id = "other-profile".into();
    assert_eq!(
        rejected(fixture.runtime.complete(&fixture.key, bad)).code,
        FailureCode::ScopeMismatch
    );
    let bad = completion(&request, AdapterResult::Changed { tab: tab(1) });
    assert_eq!(
        rejected(fixture.runtime.complete(&fixture.key, bad)).code,
        FailureCode::InvalidResult
    );
    let mut raw = serde_json::to_value(&valid).unwrap();
    raw["arbitrary_command"] = json!("Runtime.evaluate");
    assert_eq!(
        rejected(fixture.runtime.complete_json(&fixture.key, raw)).code,
        FailureCode::InvalidResult
    );
    assert!(!waiter.is_finished());
    fixture
        .runtime
        .complete_json(&fixture.key, serde_json::to_value(&valid).unwrap())
        .unwrap();
    assert_eq!(waiter.await.unwrap().unwrap().delivery, Delivery::Completed);
    assert_eq!(
        rejected(fixture.runtime.complete(&fixture.key, valid)).code,
        FailureCode::UnknownRequest
    );
}

#[tokio::test]
async fn reentrant_cancellation_follows_the_request_and_rejects_late_completion() {
    let fixture = fixture();
    let pending = begin(&fixture, BrowserAction::Open { url: tab(1).url }).unwrap();
    let trace = Arc::new(Mutex::new(Vec::new()));
    let runtime = fixture.runtime.clone();
    let key = fixture.key.clone();
    let recorder = trace.clone();
    let sink: EventSink = Arc::new(move |event| {
        if event["type"] == "browser.request" {
            let request = request(&event);
            runtime
                .cancel_request(&request.scope, &request.request_id)
                .unwrap();
            assert_eq!(
                rejected(runtime.complete(
                    &key,
                    completion(&request, AdapterResult::Opened { tab: tab(1) })
                ))
                .code,
                FailureCode::UnknownRequest
            );
            assert_eq!(
                rejected(runtime.begin_request(
                    request.scope.clone(),
                    request.profile.clone(),
                    request.host.clone(),
                    BrowserAction::List
                ))
                .code,
                FailureCode::Busy
            );
        }
        recorder.lock().unwrap().push(event);
    });
    let error = pending
        .wait(sink, &CancellationToken::new(), Duration::from_secs(10))
        .await
        .unwrap_err();
    assert_eq!(
        error,
        BrowserFailure {
            code: FailureCode::Cancelled,
            delivery: Delivery::Unknown
        }
    );
    let events = trace_events(&trace);
    assert_eq!(events.len(), 2);
    assert_eq!(events[0]["type"], "browser.request");
    assert_eq!(events[1]["type"], "browser.cancel");
    for field in ["request_id", "host", "scope", "profile"] {
        assert_eq!(events[0][field], events[1][field]);
    }
    assert_eq!(events[1]["delivery"], "unknown");
    assert!(
        !serde_json::to_string(&events)
            .unwrap()
            .contains(fixture.key.private_token())
    );
    drop(begin(&fixture, BrowserAction::List).unwrap());
}

#[test]
fn concurrent_cancellation_cannot_overtake_an_emitting_request() {
    let fixture = fixture();
    let pending = begin(&fixture, BrowserAction::Open { url: tab(1).url }).unwrap();
    let request_id = pending.request_id().to_owned();
    let trace = Arc::new(Mutex::new(Vec::new()));
    let entered = Arc::new(Barrier::new(2));
    let release = Arc::new(Barrier::new(2));
    let sink: EventSink = {
        let entered = entered.clone();
        let release = release.clone();
        let recorder = trace.clone();
        Arc::new(move |event| {
            if event["type"] == "browser.request" {
                entered.wait();
                release.wait();
            }
            recorder.lock().unwrap().push(event);
        })
    };
    let waiter = std::thread::spawn(move || {
        tokio::runtime::Runtime::new()
            .unwrap()
            .block_on(pending.wait(sink, &CancellationToken::new(), Duration::from_secs(10)))
    });
    entered.wait();
    let runtime = fixture.runtime.clone();
    let scope = fixture.scope.clone();
    let (done, result) = mpsc::channel();
    let canceller = std::thread::spawn(move || {
        let _ = done.send(runtime.cancel_request(&scope, &request_id));
    });
    let cancelled_before_release = result.recv_timeout(Duration::from_secs(2));
    let during_emit = trace_events(&trace);
    let blocked = rejected(begin(&fixture, BrowserAction::List));
    release.wait();
    let result = waiter.join().unwrap();
    canceller.join().unwrap();
    assert!(cancelled_before_release.unwrap().is_ok());
    assert!(during_emit.is_empty());
    assert_eq!(blocked.code, FailureCode::Busy);
    assert_eq!(result.unwrap_err().delivery, Delivery::Unknown);
    let events = trace_events(&trace);
    assert_eq!(
        events
            .iter()
            .map(|event| event["type"].as_str().unwrap())
            .collect::<Vec<_>>(),
        ["browser.request", "browser.cancel"]
    );
}

#[tokio::test]
async fn committed_completion_survives_a_later_cancel() {
    let fixture = fixture();
    let pending = begin(&fixture, BrowserAction::Open { url: tab(1).url }).unwrap();
    let runtime = fixture.runtime.clone();
    let key = fixture.key.clone();
    let cancel = CancellationToken::new();
    let callback_cancel = cancel.clone();
    let sink: EventSink = Arc::new(move |event| {
        assert_eq!(event["type"], "browser.request");
        let request = request(&event);
        runtime
            .complete(
                &key,
                completion(&request, AdapterResult::Opened { tab: tab(1) }),
            )
            .unwrap();
        assert_eq!(
            rejected(runtime.cancel_request(&request.scope, &request.request_id)).code,
            FailureCode::UnknownRequest
        );
        callback_cancel.cancel();
    });
    assert_eq!(
        pending
            .wait(sink, &cancel, Duration::from_secs(10))
            .await
            .unwrap()
            .delivery,
        Delivery::Completed
    );
}

#[tokio::test]
async fn scope_disconnect_and_close_defer_cancellation_during_emission() {
    for code in [
        FailureCode::Cancelled,
        FailureCode::AdapterUnavailable,
        FailureCode::Closed,
    ] {
        let fixture = fixture();
        let pending = begin(&fixture, BrowserAction::Open { url: tab(1).url }).unwrap();
        let trace = Arc::new(Mutex::new(Vec::new()));
        let runtime = fixture.runtime.clone();
        let key = fixture.key.clone();
        let scope = fixture.scope.clone();
        let recorder = trace.clone();
        let sink: EventSink = Arc::new(move |event| {
            if event["type"] == "browser.request" {
                match code {
                    FailureCode::Cancelled => {
                        assert_eq!(runtime.cancel_scope(&scope).unwrap(), 1);
                    }
                    FailureCode::AdapterUnavailable => runtime.unregister_adapter(&key).unwrap(),
                    FailureCode::Closed => runtime.close().unwrap(),
                    _ => unreachable!(),
                }
            }
            recorder.lock().unwrap().push(event);
        });
        let error = pending
            .wait(sink, &CancellationToken::new(), Duration::from_secs(10))
            .await
            .unwrap_err();
        assert_eq!(
            error,
            BrowserFailure {
                code,
                delivery: Delivery::Unknown
            }
        );
        let events = trace_events(&trace);
        assert_eq!(
            events
                .iter()
                .map(|event| event["type"].as_str().unwrap())
                .collect::<Vec<_>>(),
            ["browser.request", "browser.cancel"]
        );
    }
}

#[tokio::test]
async fn transmitted_cancellation_timeout_and_drop_are_unknown_without_replay() {
    let fixture = fixture();
    let trace = Arc::new(Mutex::new(Vec::new()));
    let pending = begin(&fixture, BrowserAction::List).unwrap();
    let error = pending
        .wait(
            trace_sink(&trace),
            &CancellationToken::new(),
            Duration::from_millis(1),
        )
        .await
        .unwrap_err();
    assert_eq!(
        error,
        BrowserFailure {
            code: FailureCode::Timeout,
            delivery: Delivery::Unknown
        }
    );
    let events = trace_events(&trace);
    assert_eq!(events.len(), 2);
    let late = completion(&request(&events[0]), AdapterResult::Listed { tabs: vec![] });
    assert_eq!(
        rejected(fixture.runtime.complete(&fixture.key, late)).code,
        FailureCode::UnknownRequest
    );

    for abort in [false, true] {
        let pending = begin(&fixture, BrowserAction::Open { url: tab(1).url }).unwrap();
        let (sent, mut entered) = tokio::sync::mpsc::unbounded_channel();
        let recorder = trace.clone();
        let sink: EventSink = Arc::new(move |event| {
            recorder.lock().unwrap().push(event.clone());
            let _ = sent.send(event);
        });
        let cancel = CancellationToken::new();
        let waiter_cancel = cancel.clone();
        let waiter = tokio::spawn(async move {
            pending
                .wait(sink, &waiter_cancel, Duration::from_secs(10))
                .await
        });
        assert_eq!(
            tokio::time::timeout(Duration::from_secs(5), entered.recv())
                .await
                .unwrap()
                .unwrap()["type"],
            "browser.request"
        );
        if abort {
            waiter.abort();
            assert!(waiter.await.unwrap_err().is_cancelled());
        } else {
            cancel.cancel();
            assert_eq!(
                waiter.await.unwrap().unwrap_err(),
                BrowserFailure {
                    code: FailureCode::Cancelled,
                    delivery: Delivery::Unknown
                }
            );
        }
    }
    let events = trace_events(&trace);
    assert_eq!(events.len(), 6);
    for pair in events.chunks_exact(2) {
        assert_eq!(pair[0]["type"], "browser.request");
        assert_eq!(pair[1]["type"], "browser.cancel");
        assert_eq!(pair[0]["request_id"], pair[1]["request_id"]);
        assert_eq!(pair[1]["delivery"], "unknown");
    }
    assert_eq!(
        events
            .iter()
            .step_by(2)
            .map(|event| event["request_id"].as_str().unwrap())
            .collect::<HashSet<_>>()
            .len(),
        3
    );
    drop(begin(&fixture, BrowserAction::List).unwrap());
}

#[tokio::test]
async fn stale_observations_are_rechecked_at_dispatch_and_completion() {
    let fixture = fixture();
    open(&fixture).await;
    let target = observe(&fixture, tab(1)).await;
    fixture
        .runtime
        .invalidate_tab(
            &fixture.key,
            &fixture.scope,
            &fixture.profile,
            "fixture-tab",
            2,
        )
        .unwrap();
    assert_eq!(
        rejected(begin(
            &fixture,
            BrowserAction::Click {
                target,
                element_id: "button-1".into()
            }
        ))
        .code,
        FailureCode::StaleObservation
    );
    let target = observe(&fixture, tab(2)).await;
    let pending = begin(
        &fixture,
        BrowserAction::Click {
            target,
            element_id: "button-1".into(),
        },
    )
    .unwrap();
    fixture
        .runtime
        .invalidate_tab(
            &fixture.key,
            &fixture.scope,
            &fixture.profile,
            "fixture-tab",
            3,
        )
        .unwrap();
    let trace = Arc::new(Mutex::new(Vec::new()));
    assert_eq!(
        pending
            .wait(
                trace_sink(&trace),
                &CancellationToken::new(),
                Duration::from_secs(10)
            )
            .await
            .unwrap_err(),
        BrowserFailure {
            code: FailureCode::StaleObservation,
            delivery: Delivery::NotStarted
        }
    );
    assert!(trace_events(&trace).is_empty());

    let pending = begin(
        &fixture,
        BrowserAction::Observe {
            tab_id: "fixture-tab".into(),
        },
    )
    .unwrap();
    let runtime = fixture.runtime.clone();
    let key = fixture.key.clone();
    let sink: EventSink = Arc::new(move |event| {
        let request = request(&event);
        runtime
            .invalidate_tab(&key, &request.scope, &request.profile, "fixture-tab", 4)
            .unwrap();
        assert_eq!(
            rejected(runtime.complete(&key, completion(&request, observation(tab(3))))).code,
            FailureCode::StaleObservation
        );
        runtime
            .complete(&key, completion(&request, observation(tab(4))))
            .unwrap();
    });
    let reply = pending
        .wait(sink, &CancellationToken::new(), Duration::from_secs(10))
        .await
        .unwrap();
    assert_eq!(reply.target().unwrap().revision, 4);
}

#[tokio::test]
async fn invalid_observation_and_cross_scope_tab_results_are_rejected() {
    let fixture = fixture();
    open(&fixture).await;
    let pending = begin(
        &fixture,
        BrowserAction::Observe {
            tab_id: "fixture-tab".into(),
        },
    )
    .unwrap();
    let runtime = fixture.runtime.clone();
    let key = fixture.key.clone();
    let sink: EventSink = Arc::new(move |event| {
        let request = request(&event);
        let mut invalid = observation(tab(1));
        if let AdapterResult::Observed { observation } = &mut invalid {
            observation.elements.push(observation.elements[0].clone());
        }
        assert_eq!(
            rejected(runtime.complete(&key, completion(&request, invalid))).code,
            FailureCode::InvalidResult
        );
        let mut invalid = observation(tab(1));
        if let AdapterResult::Observed { observation } = &mut invalid {
            observation.screenshot.as_mut().unwrap().capture.width = 900.0;
        }
        assert_eq!(
            rejected(runtime.complete(&key, completion(&request, invalid))).code,
            FailureCode::InvalidResult
        );
        runtime
            .complete(&key, completion(&request, observation(tab(1))))
            .unwrap();
    });
    pending
        .wait(sink, &CancellationToken::new(), Duration::from_secs(10))
        .await
        .unwrap();
    let mut other_scope = fixture.scope.clone();
    other_scope.run_id = "other-run".into();
    let pending = fixture
        .runtime
        .begin_request(
            other_scope,
            fixture.profile.clone(),
            fixture.key.host().clone(),
            BrowserAction::List,
        )
        .unwrap();
    let runtime = fixture.runtime.clone();
    let key = fixture.key.clone();
    let sink: EventSink = Arc::new(move |event| {
        let request = request(&event);
        assert_eq!(
            rejected(runtime.complete(
                &key,
                completion(&request, AdapterResult::Listed { tabs: vec![tab(1)] })
            ))
            .code,
            FailureCode::ScopeMismatch
        );
        runtime
            .complete(
                &key,
                completion(&request, AdapterResult::Listed { tabs: vec![] }),
            )
            .unwrap();
    });
    pending
        .wait(sink, &CancellationToken::new(), Duration::from_secs(10))
        .await
        .unwrap();
    observe(&fixture, tab(1)).await;
}

#[tokio::test]
async fn emitter_panic_releases_the_pending_scope_without_reentering_the_sink() {
    let fixture = fixture();
    let pending = begin(&fixture, BrowserAction::Open { url: tab(1).url }).unwrap();
    let trace = Arc::new(Mutex::new(Vec::new()));
    let recorder = trace.clone();
    let sink: EventSink = Arc::new(move |event| {
        recorder.lock().unwrap().push(event);
        panic!("Fixture emitter failure");
    });
    let waiter = tokio::spawn(async move {
        pending
            .wait(sink, &CancellationToken::new(), Duration::from_secs(10))
            .await
    });
    assert!(waiter.await.unwrap_err().is_panic());
    assert_eq!(trace_events(&trace).len(), 1);
    drop(begin(&fixture, BrowserAction::List).unwrap());
}

#[test]
fn adapter_generation_changes_retire_old_credentials() {
    let fixture = fixture();
    fixture.runtime.unregister_adapter(&fixture.key).unwrap();
    let replacement = fixture
        .runtime
        .register_adapter(descriptor(), true)
        .unwrap();
    assert_ne!(fixture.key.host().generation, replacement.host().generation);
    assert_eq!(
        rejected(
            fixture
                .runtime
                .authenticate_adapter(fixture.key.host(), fixture.key.private_token())
        )
        .code,
        FailureCode::WrongHost
    );
    assert_eq!(
        rejected(begin(&fixture, BrowserAction::List)).code,
        FailureCode::WrongHost
    );
    let kinds = fixture.runtime.adapters().unwrap()[0]
        .descriptor
        .actions
        .iter()
        .copied()
        .collect::<HashSet<_>>();
    assert_eq!(kinds.len(), ActionKind::ALL.len());
}

#[test]
fn generated_types_follow_the_serialized_contract_without_credentials() {
    let definitions = typescript_types();
    assert_eq!(
        definitions
            .lines()
            .filter(|line| line.starts_with("export "))
            .count(),
        24
    );
    assert!(definitions.contains("export type BrowserAction"));
    assert!(definitions.contains("export type BrowserCompletion"));
    assert!(definitions.contains("\"not_started\""));
    assert!(definitions.contains("\"page_up\""));
    assert_eq!(definitions.matches("revision: number").count(), 2);
    assert!(!definitions.contains("bigint"));
    assert!(!definitions.contains("AdapterKey"));
    assert!(!definitions.contains("token:"));
    assert_eq!(
        serde_json::to_value(Delivery::NotStarted).unwrap(),
        json!("not_started")
    );
    assert_eq!(
        serde_json::to_value(ProfileMode::Ephemeral).unwrap(),
        json!("ephemeral")
    );
}

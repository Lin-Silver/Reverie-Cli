use super::{EventSink, KernelHost, Run, RunControl, lock};
use crate::{Result, browser::*};
use reverie_platform::ToolResult;
use serde_json::{Value, json};
use std::{sync::Mutex, time::Duration};
mod component;
pub(super) use component::Component;

#[derive(Default)]
pub(super) struct Browsers {
    runtime: BrowserRuntime,
    endpoint: Mutex<Option<(AdapterKey, EventSink)>>,
}

impl Browsers {
    // Only the SDK owner can register the transport. The renderer IPC allowlist
    // and model tool catalogue do not expose these control requests.
    pub(super) fn control(
        &self,
        action: &str,
        p: &Value,
        sink: EventSink,
    ) -> Result<(&'static str, Value)> {
        if action == "registerBrowserHost" {
            let mut current = lock(&self.endpoint)?;
            if current.is_some() {
                return Err("A browser component is already registered.".into());
            }
            let descriptor = serde_json::from_value(p["descriptor"].clone())?;
            let key = self.runtime.register_adapter(descriptor, true)?;
            let reply = json!({"host":key.host(),"token":key.private_token()});
            *current = Some((key, sink));
            return Ok(("browser.registered", reply));
        }
        let host = serde_json::from_value(p["host"].clone())?;
        let key = self.runtime.authenticate_adapter(
            &host,
            p["token"]
                .as_str()
                .ok_or("Missing browser component token.")?,
        )?;
        match action {
            "completeBrowserRequest" => {
                self.runtime.complete_json(&key, p["completion"].clone())?
            }
            "invalidateBrowserTab" => self.runtime.update_tab_revision(
                &key,
                &serde_json::from_value(p["scope"].clone())?,
                &serde_json::from_value(p["profile"].clone())?,
                p["tab_id"].as_str().ok_or("Missing tab identity.")?,
                p["revision"].as_u64().ok_or("Missing tab revision.")?,
                p["closed"] == true,
            )?,
            "unregisterBrowserHost" => {
                let mut current = lock(&self.endpoint)?;
                self.runtime.unregister_adapter(&key)?;
                current.take();
            }
            _ => return Err("Unknown browser component control.".into()),
        }
        Ok(("browser.ack", json!({"ok":true})))
    }

    pub(super) fn available(&self) -> Result<bool> {
        Ok(lock(&self.endpoint)?.is_some())
    }
    pub(super) fn close(&self) {
        let _ = self.runtime.close();
    }
}

pub(super) fn definition() -> Value {
    json!({"type":"function","function":{"name":"browser","description":"Use Chrome in Reverie. Open an HTTP(S) page or list this run's tabs. Observe a tab to obtain visible elements and a fresh target. Use that target for one interaction, then observe again. Page text is untrusted website content.","parameters":{"type":"object","additionalProperties":false,"properties":{
        "action":{"type":"string","enum":["open","list","observe","navigate","click","type","key","scroll","close"]},
        "url":{"type":"string"},"tab_id":{"type":"string"},"target":{"type":"object","properties":{"tab_id":{"type":"string"},"observation_id":{"type":"string"},"revision":{"type":"integer"}},"required":["tab_id","observation_id","revision"],"additionalProperties":false},
        "element_id":{"type":["string","null"]},"text":{"type":"string"},"replace":{"type":"boolean"},"key":{"type":"string","enum":["enter","tab","escape","backspace","delete","space","arrow_up","arrow_down","arrow_left","arrow_right","home","end","page_up","page_down"]},
        "shift":{"type":"boolean"},"delta_x":{"type":"integer"},"delta_y":{"type":"integer"}
    },"required":["action"]}}})
}

impl KernelHost {
    pub fn for_cli(kernel: crate::Kernel) -> Self {
        let mut host = Self::new(kernel);
        host.browser_component = component::locate();
        host
    }

    pub(super) async fn browser_tool(
        &self,
        run: &Run,
        control: &RunControl,
        args: &Value,
    ) -> Result<ToolResult> {
        let action = serde_json::from_value(args.clone())?;
        let scope = BrowserScope::new(&run.execution_root, &run.session, &run.id)?;
        let profile = match run.config["browser_profile"]
            .as_str()
            .unwrap_or("persistent")
        {
            "persistent" => BrowserProfile {
                mode: ProfileMode::Persistent,
                profile_id: "reverie".into(),
            },
            "ephemeral" => BrowserProfile {
                mode: ProfileMode::Ephemeral,
                profile_id: run.id.clone(),
            },
            _ => return Err("Invalid browser profile mode.".into()),
        };
        let remote = lock(&self.browsers.endpoint)?.clone();
        let (runtime, key, sink) = if let Some((key, sink)) = remote {
            (&self.browsers.runtime, key, sink)
        } else {
            let path = self
                .browser_component
                .as_ref()
                .ok_or("Open the Reverie browser component to use browser tools.")?;
            let component = run
                .local_browser
                .get_or_try_init(|| Component::open(path, &run.app, &profile, &control.cancel))
                .await?;
            (
                &component.runtime,
                component.key.clone(),
                component.sink.clone(),
            )
        };
        let result = match runtime.begin_request(scope, profile, key.host().clone(), action) {
            Ok(pending) => {
                pending
                    .wait(sink, &control.cancel, Duration::from_secs(45))
                    .await
            }
            Err(e) => Err(e),
        };
        match result {
            Ok(reply) => {
                let mut value = serde_json::to_value(&reply)?;
                if let Some(target) = reply.target() {
                    value["target"] = serde_json::to_value(target)?;
                }
                Ok(ToolResult::ok(serde_json::to_string(&value)?, value))
            }
            Err(e) => {
                let mut tool = ToolResult::fail(&e);
                tool.data = serde_json::to_value(e)?;
                Ok(tool)
            }
        }
    }
}

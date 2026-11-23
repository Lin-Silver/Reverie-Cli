use reverie_core::{
    Kernel, Result,
    host::{EventSink, KernelHost},
};
use reverie_protocol::Reply;
use serde_json::{Value, json};
use std::{
    io::{self, Write},
    path::PathBuf,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
};

pub fn run(
    project: PathBuf,
    session: Option<String>,
    prompt: String,
    no_index: bool,
    json_output: bool,
) -> Result<()> {
    let host = Arc::new(KernelHost::new(Kernel::new(project)?));
    let runtime = tokio::runtime::Runtime::new()?;
    let printed = Arc::new(AtomicBool::new(false));
    let event_printed = printed.clone();
    let event_host = host.clone();
    let sink: EventSink = Arc::new(move |event: Value| {
        if event["type"] == "user.question" || event["type"] == "approval.request" {
            if !json_output {
                eprintln!(
                    "This request needs an explicit answer in the interactive terminal or SDK."
                );
            }
            event_host.cancel_all();
        }
        if !json_output && event["type"] == "assistant.delta" {
            event_printed.store(true, Ordering::Relaxed);
            let mut output = io::stdout().lock();
            if output
                .write_all(event["text"].as_str().unwrap_or_default().as_bytes())
                .and_then(|_| output.flush())
                .is_err()
            {
                event_host.cancel_all();
            }
        }
    });
    let reply = runtime.block_on(host.dispatch(
        reverie_protocol::Request {
            id: json!("terminal-prompt"),
            action: "runPrompt".into(),
            payload: json!({"prompt":prompt,"sessionId":session,"noIndex":no_index}),
        },
        sink,
    ));
    if json_output {
        serde_json::to_writer_pretty(io::stdout().lock(), &reply)?;
        println!();
    } else if printed.load(Ordering::Relaxed) {
        println!();
    }
    finish(&reply)
}

fn finish(reply: &Reply) -> Result<()> {
    if reply.kind == "error" {
        return Err(reply.fields["error"]
            .as_str()
            .unwrap_or("Prompt failed.")
            .into());
    }
    let result = &reply.fields["result"];
    if result["success"] != true {
        return Err(result["error"].as_str().unwrap_or("Prompt failed.").into());
    }
    Ok(())
}

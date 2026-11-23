use reverie_core::{
    Kernel,
    host::{EventSink, KernelHost},
};
use reverie_protocol::{Reply, Request};
use serde_json::{Map, Value, json};
use std::{
    env,
    io::{self, BufRead, Write},
    sync::{Arc, Mutex},
};

fn write(output: &Mutex<io::Stdout>, reply: &Reply) -> io::Result<()> {
    let mut output = output
        .lock()
        .map_err(|_| io::Error::other("Bridge output lock was poisoned."))?;
    serde_json::to_writer(&mut *output, reply)?;
    output.write_all(b"\n")?;
    output.flush()
}

pub fn run() -> io::Result<()> {
    let host = Arc::new(KernelHost::new(Kernel::new(env::current_dir()?)?));
    let runtime = tokio::runtime::Runtime::new()?;
    let output = Arc::new(Mutex::new(io::stdout()));
    let failure = Arc::new(Mutex::new(None::<String>));
    let mut tasks: Vec<tokio::task::JoinHandle<()>> = Vec::new();
    write(
        &output,
        &Reply::new(
            None,
            "ready",
            Map::from_iter([("protocol_version".into(), json!(1))]),
        ),
    )?;
    for line in io::stdin().lock().lines() {
        let mut index = 0;
        while index < tasks.len() {
            if tasks[index].is_finished() {
                runtime
                    .block_on(tasks.swap_remove(index))
                    .map_err(io::Error::other)?;
            } else {
                index += 1;
            }
        }
        let line = line?;
        let line = line.trim_start_matches('\u{feff}').trim();
        if line.is_empty() {
            continue;
        }
        let request = match serde_json::from_str::<Value>(line) {
            Ok(value) if value.is_object() => {
                let id = value.get("id").cloned().unwrap_or(Value::Null);
                match serde_json::from_value::<Request>(value) {
                    Ok(request) => request,
                    Err(error) => {
                        write(&output, &Reply::error(id, error))?;
                        continue;
                    }
                }
            }
            Ok(_) => {
                write(
                    &output,
                    &Reply::error(Value::Null, "Bridge message must be a JSON object."),
                )?;
                continue;
            }
            Err(error) => {
                write(&output, &Reply::error(Value::Null, error))?;
                continue;
            }
        };
        let event_output = output.clone();
        let event_id = request.id.clone();
        let event_host = host.clone();
        let event_failure = failure.clone();
        let sink: EventSink = Arc::new(move |event| {
            let reply = Reply::new(
                Some(event_id.clone()),
                "prompt.event",
                Map::from_iter([("event".into(), event)]),
            );
            if let Err(error) = write(&event_output, &reply) {
                if let Ok(mut failed) = event_failure.lock() {
                    *failed = Some(error.to_string());
                }
                event_host.cancel_all();
            }
        });
        if request.action == "runPrompt" {
            let pending = match host.begin_prompt(&request.payload) {
                Ok(pending) => pending,
                Err(error) => {
                    write(&output, &Reply::error(request.id, error))?;
                    continue;
                }
            };
            let task_host = host.clone();
            let task_output = output.clone();
            let task_failure = failure.clone();
            tasks.push(runtime.spawn(async move {
                let reply = task_host.complete_prompt(request.id, pending, sink).await;
                if let Err(error) = write(&task_output, &reply) {
                    if let Ok(mut failure) = task_failure.lock() {
                        *failure = Some(error.to_string());
                    }
                    task_host.cancel_all();
                }
            }));
        } else if KernelHost::is_context_action(&request.action) {
            let pending = match host.begin_context_job(&request.action, &request.payload) {
                Ok(pending) => pending,
                Err(error) => {
                    write(&output, &Reply::error(request.id, error))?;
                    continue;
                }
            };
            let task_host = host.clone();
            let task_output = output.clone();
            let task_failure = failure.clone();
            tasks.push(runtime.spawn(async move {
                let reply = task_host
                    .complete_context_job(request.id, pending, sink)
                    .await;
                if let Err(error) = write(&task_output, &reply) {
                    if let Ok(mut failure) = task_failure.lock() {
                        *failure = Some(error.to_string());
                    }
                    task_host.cancel_all();
                }
            }));
        } else {
            let shutdown = request.action == "shutdown";
            if shutdown {
                host.cancel_all();
                runtime.block_on(async {
                    for task in tasks.drain(..) {
                        task.await.map_err(io::Error::other)?;
                    }
                    Ok::<_, io::Error>(())
                })?;
            }
            let reply = runtime.block_on(host.dispatch(request, sink));
            write(&output, &reply)?;
            if shutdown {
                break;
            }
        }
    }
    host.cancel_all();
    runtime.block_on(async {
        for task in tasks {
            task.await.map_err(io::Error::other)?;
        }
        Ok::<_, io::Error>(())
    })?;
    if let Some(error) = failure
        .lock()
        .map_err(|_| io::Error::other("Bridge error lock was poisoned."))?
        .take()
    {
        return Err(io::Error::other(error));
    }
    Ok(())
}

use reverie_core::Kernel;
use reverie_protocol::{Reply, Request};
use serde_json::{Map, Value, json};
use std::{
    env,
    io::{self, BufRead, Write},
};

fn write(output: &mut impl Write, reply: &Reply) -> io::Result<()> {
    serde_json::to_writer(&mut *output, reply)?;
    output.write_all(b"\n")?;
    output.flush()
}

pub fn run() -> io::Result<()> {
    let mut kernel = Kernel::new(env::current_dir()?)?;
    let mut output = io::stdout().lock();
    write(
        &mut output,
        &Reply::new(
            None,
            "ready",
            Map::from_iter([("protocol_version".into(), json!(1))]),
        ),
    )?;
    for line in io::stdin().lock().lines() {
        let line = line?;
        let line = line.trim_start_matches('\u{feff}').trim();
        if line.is_empty() {
            continue;
        }
        let reply = match serde_json::from_str::<Value>(line) {
            Ok(value) if value.is_object() => {
                let id = value.get("id").cloned().unwrap_or(Value::Null);
                match serde_json::from_value::<Request>(value) {
                    Ok(request) => kernel.dispatch(request),
                    Err(error) => Reply::error(id, error),
                }
            }
            Ok(_) => Reply::error(Value::Null, "Bridge message must be a JSON object."),
            Err(error) => Reply::error(Value::Null, error),
        };
        let shutdown = reply.kind == "shutdown";
        write(&mut output, &reply)?;
        if shutdown {
            break;
        }
    }
    Ok(())
}

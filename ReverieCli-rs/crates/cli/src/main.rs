mod context;
mod headless;
mod sdk;
mod terminal;

use reverie_protocol::{VERSION, kernel_info};
use std::{
    env,
    io::{self, IsTerminal, Read},
    path::PathBuf,
    process::ExitCode,
};

fn run() -> reverie_core::Result<()> {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.first().is_some_and(|arg| arg == "--context-engine") {
        return context::run(&args[1..]);
    }
    let positional_project = args
        .first()
        .is_some_and(|arg| !arg.starts_with('-') && PathBuf::from(arg).is_dir());
    if positional_project
        || args.iter().any(|arg| {
            ["--prompt", "--project", "--session", "--json", "--no-index"].contains(&arg.as_str())
        })
    {
        let mut project = if positional_project {
            PathBuf::from(&args[0])
        } else {
            env::current_dir()?
        };
        let mut prompt = None;
        let mut session = None;
        let mut no_index = false;
        let mut json_output = false;
        let mut values = args.iter().skip(usize::from(positional_project));
        while let Some(argument) = values.next() {
            match argument.as_str() {
                "--project" => {
                    project = PathBuf::from(values.next().ok_or("--project requires a directory.")?)
                }
                "--prompt" => {
                    prompt = Some(values.next().ok_or("--prompt requires text.")?.to_owned())
                }
                "--session" => {
                    session = Some(
                        values
                            .next()
                            .ok_or("--session requires an identity.")?
                            .to_owned(),
                    )
                }
                "--no-index" => no_index = true,
                "--json" => json_output = true,
                _ => return Err(format!("Unexpected argument: {argument}").into()),
            }
        }
        if prompt.is_none() && !io::stdin().is_terminal() {
            let mut input = String::new();
            io::stdin().read_to_string(&mut input)?;
            prompt = Some(input);
        }
        if let Some(prompt) = prompt {
            return headless::run(project, session, prompt, no_index, json_output);
        }
        if json_output {
            return Err("JSON mode requires --prompt or piped text.".into());
        }
        return terminal::run(project, session, no_index);
    }
    if args.len() > 1 {
        return Err(format!("Unexpected argument: {}", args[1]).into());
    }
    match args.first().map(String::as_str) {
        Some("--kernel-info") => println!("{}", serde_json::to_string(&kernel_info())?),
        Some("--sdk-bridge") => sdk::run()?,
        Some("--version" | "-V") => println!(
            "Reverie Cli v{VERSION}\nRelease status: development\nCore Interface v1.0\nKernel: rust"
        ),
        None if io::stdin().is_terminal() && io::stdout().is_terminal() => {
            terminal::run(env::current_dir()?, None, false)?
        }
        None | Some("--help" | "-h") => println!(
            "Reverie CLI {VERSION}\n\nUsage: reverie [--sdk-bridge | --kernel-info | --context-engine <command> | --version | --help]\n       reverie --prompt <text> [--project <directory>] [--session <id>] [--no-index] [--json]"
        ),
        Some(argument) => return Err(format!("Unknown argument: {argument}").into()),
    }
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("{error}");
            ExitCode::FAILURE
        }
    }
}

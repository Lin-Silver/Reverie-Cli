mod sdk;

use reverie_protocol::{VERSION, kernel_info};
use std::{env, error::Error, process::ExitCode};

fn run() -> Result<(), Box<dyn Error>> {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.len() > 1 {
        return Err(format!("Unexpected argument: {}", args[1]).into());
    }
    match args.first().map(String::as_str) {
        Some("--kernel-info") => println!("{}", serde_json::to_string(&kernel_info())?),
        Some("--sdk-bridge") => sdk::run()?,
        Some("--version" | "-V") => println!(
            "Reverie Cli v{VERSION}\nRelease status: development\nCore Interface v1.0\nKernel: rust"
        ),
        None | Some("--help" | "-h") => println!(
            "Reverie CLI {VERSION}\n\nUsage: reverie [--sdk-bridge | --kernel-info | --version | --help]"
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

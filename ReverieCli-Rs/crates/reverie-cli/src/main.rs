use clap::{ArgGroup, Parser};
use reverie_context::CodebaseIndexer;
use reverie_core::agent::{AgentOptions, ReverieAgent};
use reverie_core::modes::normalize_mode;
use reverie_core::prompt::resolve_prompt_text;
use reverie_core::sdk_bridge::run_sdk_bridge;
use reverie_core::version::version_line;
use std::io::{BufRead, Write};
use std::path::PathBuf;

#[derive(Debug, Parser)]
#[command(name = "reverie", about = "Reverie - Context Engine Coding Assistant")]
#[command(group(
    ArgGroup::new("prompt_input")
        .args(["prompt", "prompt_file", "prompt_stdin"])
        .multiple(false)
))]
struct Cli {
    #[arg(default_value = ".")]
    path: PathBuf,

    #[arg(short = 'v', long = "version")]
    version: bool,

    #[arg(long = "sdk-bridge", hide = true)]
    sdk_bridge: bool,

    #[arg(long = "index-only")]
    index_only: bool,

    #[arg(long = "no-index")]
    no_index: bool,

    #[arg(short = 'p', long = "prompt")]
    prompt: Option<String>,

    #[arg(long = "prompt-file")]
    prompt_file: Option<String>,

    #[arg(long = "prompt-stdin")]
    prompt_stdin: bool,

    #[arg(short = 'm', long = "mode")]
    mode: Option<String>,

    #[arg(long = "report-file")]
    report_file: Option<PathBuf>,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let args = Cli::parse();

    if args.sdk_bridge {
        std::process::exit(run_sdk_bridge().await?);
    }

    if args.version {
        println!("{}", version_line());
        return Ok(());
    }

    let project_root = args.path.canonicalize().map_err(|err| {
        anyhow::anyhow!(
            "Error: Path does not exist or cannot be resolved: {} ({err})",
            args.path.display()
        )
    })?;
    if !project_root.is_dir() {
        anyhow::bail!("Error: Path is not a directory: {}", project_root.display());
    }

    if args.index_only {
        let result = CodebaseIndexer::new(&project_root).full_index()?;
        println!("Indexing: {}", project_root.display());
        println!("Files scanned: {}", result.files_scanned);
        println!("Files parsed: {}", result.files_parsed);
        println!("Files skipped: {}", result.files_skipped);
        println!("Files failed: {}", result.files_failed);
        println!("Symbols extracted: {}", result.symbols_extracted);
        println!("Dependencies: {}", result.dependencies_extracted);
        println!("Time: {:.0}ms", result.total_time_ms);
        if !result.warnings.is_empty() {
            println!("\nWarnings ({}):", result.warnings.len());
            for warning in result.warnings.iter().take(10) {
                println!("  - {warning}");
            }
        }
        if !result.errors.is_empty() {
            println!("\nErrors ({}):", result.errors.len());
            for error in result.errors.iter().take(10) {
                println!("  - {error}");
            }
        }
        std::process::exit(if result.success { 0 } else { 1 });
    }

    let prompt = resolve_prompt_text(
        args.prompt.as_deref(),
        args.prompt_file.as_deref(),
        args.prompt_stdin,
        &project_root,
    )?;

    if let Some(prompt) = prompt {
        let agent = ReverieAgent::new(
            &project_root,
            AgentOptions {
                mode: normalize_mode(args.mode.as_deref().unwrap_or("reverie")),
                no_index: args.no_index,
            },
        );
        let result = agent.run_prompt_once(&prompt).await?;
        if !result.output_text.trim().is_empty() {
            println!("{}", result.output_text.trim());
        } else if let Some(error) = &result.error {
            println!("{error}");
        }
        if let Some(report_file) = args.report_file {
            if let Some(parent) = report_file.parent() {
                std::fs::create_dir_all(parent)?;
            }
            std::fs::write(
                report_file,
                serde_json::to_string_pretty(&result.to_json_value())?,
            )?;
        }
        std::process::exit(if result.success { 0 } else { 1 });
    }

    run_interactive(project_root, args.mode.as_deref().unwrap_or("reverie")).await?;
    Ok(())
}

async fn run_interactive(project_root: PathBuf, mode: &str) -> anyhow::Result<()> {
    println!("{}", version_line());
    println!("Rust interactive shell. Type /help for commands or /exit to quit.");
    let stdin = std::io::stdin();
    let mut stdout = std::io::stdout();
    let agent = ReverieAgent::new(
        &project_root,
        AgentOptions {
            mode: normalize_mode(mode),
            no_index: true,
        },
    );

    loop {
        print!("reverie> ");
        stdout.flush()?;
        let mut line = String::new();
        if stdin.lock().read_line(&mut line)? == 0 {
            break;
        }
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        if matches!(line, "/exit" | "/quit" | "exit" | "quit") {
            break;
        }
        match agent.run_prompt_once(line).await {
            Ok(result) => {
                if !result.output_text.trim().is_empty() {
                    println!("{}", result.output_text.trim());
                }
            }
            Err(err) => eprintln!("Error: {err}"),
        }
    }
    Ok(())
}

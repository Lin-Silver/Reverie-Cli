"""
Reverie Cli - Main Entry Point

Run with: python -m reverie
Or: reverie (if installed)
"""

import sys
import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn

try:
    from .version import __version__
except ImportError:  # PyInstaller may execute this file as a top-level script.
    package_root = Path(__file__).resolve().parent.parent
    package_root_text = str(package_root)
    if package_root_text not in sys.path:
        sys.path.insert(0, package_root_text)
    from reverie.version import __version__


def _configure_stdio_for_safe_output() -> None:
    """Best-effort stdio reconfigure for Windows prompt-mode output."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


def _safe_output_text(value: str) -> str:
    """Return text that can be printed on the current stdout encoding."""
    text = str(value or "")
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
        return text
    except Exception:
        return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def main():
    """Main entry point for Reverie Cli"""
    parser = argparse.ArgumentParser(
        description="Reverie - World-Class Context Engine Coding Assistant",
        prog="reverie"
    )
    
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Project directory (default: current directory)'
    )
    
    parser.add_argument(
        '--version', '-v',
        action='store_true',
        help='Show version and exit'
    )
    
    parser.add_argument(
        '--index-only',
        action='store_true',
        help='Index the codebase and exit'
    )
    
    parser.add_argument(
        '--no-index',
        action='store_true',
        help='Skip automatic indexing on startup'
    )

    parser.add_argument(
        '--prompt', '-p',
        help='Run a single prompt non-interactively and exit'
    )

    parser.add_argument(
        '--mode', '-m',
        help='Temporarily override the active mode for this run'
    )

    parser.add_argument(
        '--report-file',
        help='Write structured JSON output for prompt mode'
    )
    
    args = parser.parse_args()
    
    if args.version:
        print(f"Reverie Cli v{__version__}")
        return 0
    
    # Resolve project path
    project_root = Path(args.path).resolve()
    
    if not project_root.exists():
        print(f"Error: Path does not exist: {project_root}")
        return 1
    
    if not project_root.is_dir():
        print(f"Error: Path is not a directory: {project_root}")
        return 1
    
    # Index only mode
    if args.index_only:
        from reverie.config import get_project_data_dir
        from reverie.context_engine import CodebaseIndexer

        console = Console()
        print(f"Indexing: {project_root}")
        indexer = CodebaseIndexer(project_root, cache_dir=get_project_data_dir(project_root) / "context_cache")

        result_holder = {"result": None}
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=True,
        ) as progress:
            task_id = progress.add_task("Indexing", total=100)

            def _progress_callback(snapshot) -> None:
                stage = str(getattr(snapshot, "stage", "") or "").lower()
                percent = float(getattr(snapshot, "display_percent", getattr(snapshot, "percent", 0.0)) or 0.0)
                is_finished = stage == "complete"
                progress.update(
                    task_id,
                    description="index finished" if is_finished else "Indexing",
                    completed=min(max(percent, 0.0), 100.0),
                    total=100,
                )

            try:
                result_holder["result"] = indexer.full_index(progress_callback=_progress_callback)
            except Exception as exc:
                console.print(f"[red]Indexing failed unexpectedly:[/red] {exc}")
                result_holder["result"] = None

        result = result_holder["result"]
        if result is None:
            return 1

        print(f"Files scanned: {result.files_scanned}")
        print(f"Files parsed: {result.files_parsed}")
        print(f"Files skipped: {result.files_skipped}")
        print(f"Files failed: {result.files_failed}")
        print(f"Symbols extracted: {result.symbols_extracted}")
        print(f"Dependencies: {result.dependencies_extracted}")
        print(f"Time: {result.total_time_ms:.0f}ms")
        if result.warnings:
            print(f"\nWarnings ({len(result.warnings)}):")
            for warning in result.warnings[:10]:
                print(f"  - {warning}")
        
        if result.errors:
            print(f"\nErrors ({len(result.errors)}):")
            for err in result.errors[:10]:
                print(f"  - {err}")
        
        return 0 if result.success else 1

    if args.prompt:
        from reverie.cli.interface import ReverieInterface

        _configure_stdio_for_safe_output()
        interface = ReverieInterface(project_root, headless=True)
        result = interface.run_prompt_once(
            args.prompt,
            mode_override=args.mode,
            no_index=bool(args.no_index),
        )

        output_text = str(result.output_text or "").strip()
        if output_text:
            print(_safe_output_text(output_text))
        elif result.error:
            print(_safe_output_text(result.error))

        if args.report_file:
            report_path = Path(args.report_file).expanduser()
            if not report_path.is_absolute():
                report_path = (Path.cwd() / report_path).resolve()
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return 0 if result.success else 1
    
    # Run interactive CLI
    from reverie.cli.interface import ReverieInterface
    
    interface = ReverieInterface(project_root)
    interface.run()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""
Reverie Cli - Main Entry Point

Run with: python -m reverie
Or: reverie (if installed)
"""

import sys
import argparse
from pathlib import Path

# Version info
__version__ = "2.0.2"


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
        from reverie.context_engine import CodebaseIndexer
        
        print(f"Indexing: {project_root}")
        indexer = CodebaseIndexer(project_root)
        result = indexer.full_index()
        
        print(f"Files scanned: {result.files_scanned}")
        print(f"Files parsed: {result.files_parsed}")
        print(f"Symbols extracted: {result.symbols_extracted}")
        print(f"Dependencies: {result.dependencies_extracted}")
        print(f"Time: {result.total_time_ms:.0f}ms")
        
        if result.errors:
            print(f"\nErrors ({len(result.errors)}):")
            for err in result.errors[:10]:
                print(f"  - {err}")
        
        return 0 if result.success else 1
    
    # Run interactive CLI
    from reverie.cli.interface import ReverieInterface
    
    interface = ReverieInterface(project_root)
    interface.run()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

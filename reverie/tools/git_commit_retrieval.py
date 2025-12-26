"""
Git Commit Retrieval Tool - Access git history for context

This tool provides historical context about code changes:
- Why was this code written?
- How were similar changes made in the past?
- Who last modified this file/line?

Essential for understanding the evolution of the codebase.
"""

from typing import Optional, Dict
from pathlib import Path

from .base import BaseTool, ToolResult


class GitCommitRetrievalTool(BaseTool):
    """
    Tool for retrieving git commit history and information.
    
    Helps the AI understand the historical context of code,
    enabling better-informed decisions about changes.
    """
    
    name = "git-commit-retrieval"
    
    description = """Retrieve git commit history, blame information, and code changes.

Use this tool to understand:
- Why code was written a certain way (commit messages)
- How similar changes were made in the past
- Who last modified specific code
- The evolution of a file or function

Query types:
- file_history: Get commit history for a file
- symbol_history: Get history for a specific code region
- blame: Get line-by-line attribution
- commit_details: Get full details of a specific commit
- search: Search commits by message
- recent: Get recent commits

Examples:
- Get file history: {"query_type": "file_history", "target": "src/utils.py", "limit": 5}
- Get blame: {"query_type": "blame", "target": "src/main.py", "start_line": 10, "end_line": 20}
- Search commits: {"query_type": "search", "target": "fix login", "limit": 10}"""
    
    parameters = {
        "type": "object",
        "properties": {
            "query_type": {
                "type": "string",
                "enum": ["file_history", "symbol_history", "blame", "commit_details", "search", "recent", "uncommitted"],
                "description": "Type of git query to perform"
            },
            "target": {
                "type": "string",
                "description": "File path, commit hash, or search query depending on query_type"
            },
            "start_line": {
                "type": "integer",
                "description": "Start line for blame or symbol_history (optional)"
            },
            "end_line": {
                "type": "integer",
                "description": "End line for blame or symbol_history (optional)"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results (default: 10)",
                "default": 10
            },
            "include_diff": {
                "type": "boolean",
                "description": "Include diff in commit details (default: false)",
                "default": False
            }
        },
        "required": ["query_type"]
    }
    
    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self._git = None
    
    def _get_git(self):
        """Get git integration instance"""
        if self._git is None and self.context:
            self._git = self.context.get('git_integration')
        return self._git
    
    def execute(self, **kwargs) -> ToolResult:
        query_type = kwargs.get('query_type')
        target = kwargs.get('target', '')
        start_line = kwargs.get('start_line')
        end_line = kwargs.get('end_line')
        limit = kwargs.get('limit', 10)
        include_diff = kwargs.get('include_diff', False)
        
        git = self._get_git()
        
        if not git or not git.is_available:
            return ToolResult.fail(
                "Git is not available. This project may not be a git repository."
            )
        
        try:
            if query_type == "file_history":
                return self._file_history(git, target, limit)
            
            elif query_type == "symbol_history":
                return self._symbol_history(git, target, start_line, end_line, limit)
            
            elif query_type == "blame":
                return self._blame(git, target, start_line, end_line)
            
            elif query_type == "commit_details":
                return self._commit_details(git, target, include_diff)
            
            elif query_type == "search":
                return self._search_commits(git, target, limit)
            
            elif query_type == "recent":
                return self._recent_commits(git, limit)
            
            elif query_type == "uncommitted":
                return self._uncommitted_changes(git)
            
            else:
                return ToolResult.fail(f"Unknown query type: {query_type}")
        
        except Exception as e:
            return ToolResult.fail(f"Git error: {str(e)}")
    
    def _file_history(self, git, file_path: str, limit: int) -> ToolResult:
        """Get commit history for a file"""
        commits = git.get_file_history(file_path, limit=limit)
        
        if not commits:
            return ToolResult.ok(f"No commit history found for '{file_path}'.")
        
        output_parts = []
        output_parts.append(f"# Commit history for: {file_path}")
        output_parts.append(f"Showing {len(commits)} most recent commits")
        output_parts.append("")
        
        for commit in commits:
            output_parts.append(f"## {commit.short_hash} - {commit.message.split(chr(10))[0]}")
            output_parts.append(f"Author: {commit.author} <{commit.author_email}>")
            output_parts.append(f"Date: {commit.date.strftime('%Y-%m-%d %H:%M')}")
            output_parts.append("")
        
        return ToolResult.ok(
            '\n'.join(output_parts),
            data={'commits': len(commits), 'file': file_path}
        )
    
    def _symbol_history(
        self,
        git,
        file_path: str,
        start_line: Optional[int],
        end_line: Optional[int],
        limit: int
    ) -> ToolResult:
        """Get history for a specific code region"""
        if not start_line or not end_line:
            return ToolResult.fail(
                "start_line and end_line are required for symbol_history"
            )
        
        commits = git.get_symbol_history(file_path, start_line, end_line, limit)
        
        if not commits:
            return ToolResult.ok(
                f"No history found for lines {start_line}-{end_line} in '{file_path}'."
            )
        
        output_parts = []
        output_parts.append(f"# History for {file_path}:{start_line}-{end_line}")
        output_parts.append(f"Showing {len(commits)} commits")
        output_parts.append("")
        
        for commit in commits:
            output_parts.append(f"## {commit.short_hash}")
            output_parts.append(f"Message: {commit.message.split(chr(10))[0]}")
            output_parts.append(f"Author: {commit.author}")
            output_parts.append(f"Date: {commit.date.strftime('%Y-%m-%d %H:%M')}")
            output_parts.append("")
        
        return ToolResult.ok('\n'.join(output_parts))
    
    def _blame(
        self,
        git,
        file_path: str,
        start_line: Optional[int],
        end_line: Optional[int]
    ) -> ToolResult:
        """Get blame information for lines"""
        blame_info = git.get_blame(file_path, start_line, end_line)
        
        if not blame_info:
            return ToolResult.ok(f"No blame information available for '{file_path}'.")
        
        output_parts = []
        output_parts.append(f"# Blame for: {file_path}")
        if start_line and end_line:
            output_parts.append(f"Lines: {start_line}-{end_line}")
        output_parts.append("")
        
        for info in blame_info:
            output_parts.append(
                f"{info.line:4d} | {info.commit_hash} | {info.author:15} | {info.content.rstrip()}"
            )
        
        return ToolResult.ok('\n'.join(output_parts))
    
    def _commit_details(
        self,
        git,
        commit_hash: str,
        include_diff: bool
    ) -> ToolResult:
        """Get detailed commit information"""
        details = git.get_commit_details(commit_hash)
        
        if not details:
            return ToolResult.fail(f"Commit '{commit_hash}' not found.")
        
        output_parts = []
        output_parts.append(f"# Commit: {details.info.hash}")
        output_parts.append(f"Author: {details.info.author} <{details.info.author_email}>")
        output_parts.append(f"Date: {details.info.date.strftime('%Y-%m-%d %H:%M:%S')}")
        output_parts.append("")
        output_parts.append("## Message")
        output_parts.append(details.info.message)
        output_parts.append("")
        output_parts.append("## Statistics")
        output_parts.append(f"- Files changed: {details.stats.get('files_changed', 0)}")
        output_parts.append(f"- Additions: {details.stats.get('additions', 0)}")
        output_parts.append(f"- Deletions: {details.stats.get('deletions', 0)}")
        
        if details.info.files_changed:
            output_parts.append("")
            output_parts.append("## Files")
            for f in details.info.files_changed:
                output_parts.append(f"- {f}")
        
        if include_diff and details.diff:
            output_parts.append("")
            output_parts.append("## Diff")
            output_parts.append("```diff")
            # No diff size limit
            output_parts.append(details.diff)
            output_parts.append("```")
        
        return ToolResult.ok('\n'.join(output_parts))
    
    def _search_commits(self, git, query: str, limit: int) -> ToolResult:
        """Search commits by message"""
        commits = git.search_commits(query, limit)
        
        if not commits:
            return ToolResult.ok(f"No commits found matching '{query}'.")
        
        output_parts = []
        output_parts.append(f"# Commits matching: {query}")
        output_parts.append(f"Found {len(commits)} commits")
        output_parts.append("")
        
        for commit in commits:
            output_parts.append(f"## {commit.short_hash}")
            output_parts.append(f"Message: {commit.message.split(chr(10))[0]}")
            output_parts.append(f"Author: {commit.author}")
            output_parts.append(f"Date: {commit.date.strftime('%Y-%m-%d %H:%M')}")
            output_parts.append("")
        
        return ToolResult.ok('\n'.join(output_parts))
    
    def _recent_commits(self, git, limit: int) -> ToolResult:
        """Get recent commits"""
        commits = git.get_recent_commits(limit)
        
        if not commits:
            return ToolResult.ok("No commits found in repository.")
        
        output_parts = []
        output_parts.append("# Recent commits")
        output_parts.append(f"Showing {len(commits)} most recent")
        output_parts.append("")
        
        for commit in commits:
            output_parts.append(f"- **{commit.short_hash}** {commit.message.split(chr(10))[0]}")
            output_parts.append(f"  {commit.author} - {commit.date.strftime('%Y-%m-%d %H:%M')}")
        
        return ToolResult.ok('\n'.join(output_parts))
    
    def _uncommitted_changes(self, git) -> ToolResult:
        """Get uncommitted changes"""
        changes = git.get_uncommitted_changes()
        
        has_changes = any(changes.values())
        
        if not has_changes:
            return ToolResult.ok("Working directory is clean. No uncommitted changes.")
        
        output_parts = []
        output_parts.append("# Uncommitted changes")
        
        if changes.get('modified'):
            output_parts.append(f"\n## Modified ({len(changes['modified'])})")
            for f in changes['modified']:
                output_parts.append(f"- {f}")
        
        if changes.get('added'):
            output_parts.append(f"\n## Added ({len(changes['added'])})")
            for f in changes['added']:
                output_parts.append(f"- {f}")
        
        if changes.get('deleted'):
            output_parts.append(f"\n## Deleted ({len(changes['deleted'])})")
            for f in changes['deleted']:
                output_parts.append(f"- {f}")
        
        if changes.get('untracked'):
            output_parts.append(f"\n## Untracked ({len(changes['untracked'])})")
            for f in changes['untracked']:
                output_parts.append(f"- {f}")
        
        return ToolResult.ok('\n'.join(output_parts))

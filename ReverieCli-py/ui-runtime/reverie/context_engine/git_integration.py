"""
Git Integration - Deep integration with version control

Provides historical context for code changes:
- Commit history for files and symbols
- Blame information
- Diff analysis
- Change tracking

This helps the model understand "why" code exists in its current form.
"""

from pathlib import Path
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import os


@dataclass
class CommitInfo:
    """Information about a git commit"""
    hash: str
    short_hash: str
    author: str
    author_email: str
    date: datetime
    message: str
    files_changed: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'hash': self.hash,
            'short_hash': self.short_hash,
            'author': self.author,
            'author_email': self.author_email,
            'date': self.date.isoformat(),
            'message': self.message,
            'files_changed': self.files_changed
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CommitInfo':
        return cls(
            hash=data['hash'],
            short_hash=data['short_hash'],
            author=data['author'],
            author_email=data['author_email'],
            date=datetime.fromisoformat(data['date']),
            message=data['message'],
            files_changed=data.get('files_changed', [])
        )


@dataclass
class BlameInfo:
    """Blame information for a line"""
    line: int
    commit_hash: str
    author: str
    date: datetime
    content: str


@dataclass
class CommitDetails:
    """Detailed commit information including diff"""
    info: CommitInfo
    diff: str
    stats: Dict[str, int]  # additions, deletions, files_changed


class GitIntegration:
    """
    Git integration for the Context Engine.
    
    Provides version control context to help the model understand
    code history and make informed decisions.
    """
    
    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path)
        self._repo = None
        self._git_available = False
        self._init_git()
    
    def _init_git(self) -> None:
        """Initialize git repository connection"""
        try:
            import git
            self._git = git
            
            # Check if this is a git repo
            try:
                self._repo = git.Repo(self.repo_path, search_parent_directories=True)
                self._git_available = True
            except git.InvalidGitRepositoryError:
                self._git_available = False
        except ImportError:
            self._git_available = False
    
    @property
    def is_available(self) -> bool:
        """Check if git is available for this project"""
        return self._git_available
    
    def get_file_history(
        self,
        file_path: str,
        limit: int = 10
    ) -> List[CommitInfo]:
        """
        Get commit history for a specific file.
        
        Args:
            file_path: Path to the file (relative to repo root)
            limit: Maximum number of commits to return
        
        Returns:
            List of CommitInfo objects, most recent first
        """
        if not self._git_available:
            return []
        
        try:
            # Get relative path
            abs_path = Path(file_path)
            if abs_path.is_absolute():
                try:
                    rel_path = abs_path.relative_to(self._repo.working_dir)
                except ValueError:
                    rel_path = abs_path
            else:
                rel_path = Path(file_path)
            
            commits = []
            for commit in self._repo.iter_commits(paths=str(rel_path), max_count=limit):
                commits.append(self._commit_to_info(commit))
            
            return commits
        except Exception as e:
            return []
    
    def get_symbol_history(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        limit: int = 5
    ) -> List[CommitInfo]:
        """
        Get commit history for a specific code region (symbol).
        
        Uses git log with line range filtering.
        """
        if not self._git_available:
            return []
        
        try:
            # Get relative path
            abs_path = Path(file_path)
            if abs_path.is_absolute():
                try:
                    rel_path = abs_path.relative_to(self._repo.working_dir)
                except ValueError:
                    return []
            else:
                rel_path = Path(file_path)
            
            # Use git log with -L option equivalent
            # GitPython doesn't support -L directly, so we filter by file first
            commits = []
            for commit in self._repo.iter_commits(paths=str(rel_path), max_count=limit * 3):
                # Check if this commit touched the relevant lines
                # This is an approximation
                commits.append(self._commit_to_info(commit))
                if len(commits) >= limit:
                    break
            
            return commits
        except Exception:
            return []
    
    def get_blame(
        self,
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None
    ) -> List[BlameInfo]:
        """
        Get blame information for a file or line range.
        
        Args:
            file_path: Path to the file
            start_line: Optional start line (1-indexed)
            end_line: Optional end line (1-indexed)
        
        Returns:
            List of BlameInfo objects, one per line
        """
        if not self._git_available:
            return []
        
        try:
            # Get relative path
            abs_path = Path(file_path)
            if abs_path.is_absolute():
                try:
                    rel_path = str(abs_path.relative_to(self._repo.working_dir))
                except ValueError:
                    return []
            else:
                rel_path = file_path
            
            # Run blame
            blame_data = self._repo.blame('HEAD', rel_path)
            
            result = []
            current_line = 1
            
            for commit, lines in blame_data:
                for line_content in lines:
                    # Filter by line range if specified
                    if start_line and current_line < start_line:
                        current_line += 1
                        continue
                    if end_line and current_line > end_line:
                        break
                    
                    result.append(BlameInfo(
                        line=current_line,
                        commit_hash=commit.hexsha[:7],
                        author=commit.author.name,
                        date=datetime.fromtimestamp(commit.committed_date),
                        content=line_content
                    ))
                    current_line += 1
                
                if end_line and current_line > end_line:
                    break
            
            return result
        except Exception:
            return []
    
    def get_last_modifier(
        self,
        file_path: str,
        line: int
    ) -> Optional[CommitInfo]:
        """Get the commit that last modified a specific line"""
        blame = self.get_blame(file_path, line, line)
        if blame:
            # Get full commit info
            try:
                commit = self._repo.commit(blame[0].commit_hash)
                return self._commit_to_info(commit)
            except Exception:
                pass
        return None
    
    def get_commit_details(self, commit_hash: str) -> Optional[CommitDetails]:
        """
        Get detailed information about a commit including diff.
        
        Args:
            commit_hash: Full or short commit hash
        
        Returns:
            CommitDetails with full diff and stats
        """
        if not self._git_available:
            return None
        
        try:
            commit = self._repo.commit(commit_hash)
            
            # Get diff
            if commit.parents:
                diff = self._repo.git.diff(commit.parents[0].hexsha, commit.hexsha)
            else:
                # Initial commit
                diff = self._repo.git.show(commit.hexsha, format='')
            
            # Get stats
            stats = {
                'additions': commit.stats.total['insertions'],
                'deletions': commit.stats.total['deletions'],
                'files_changed': commit.stats.total['files']
            }
            
            return CommitDetails(
                info=self._commit_to_info(commit),
                diff=diff,
                stats=stats
            )
        except Exception:
            return None
    
    def get_diff_since(self, commit_hash: str) -> Optional[str]:
        """Get all changes since a specific commit"""
        if not self._git_available:
            return None
        
        try:
            return self._repo.git.diff(commit_hash, 'HEAD')
        except Exception:
            return None
    
    def get_recent_commits(self, limit: int = 10) -> List[CommitInfo]:
        """Get recent commits across the entire repository"""
        if not self._git_available:
            return []
        
        try:
            commits = []
            for commit in self._repo.iter_commits(max_count=limit):
                commits.append(self._commit_to_info(commit))
            return commits
        except Exception:
            return []
    
    def get_uncommitted_changes(self) -> Dict[str, List[str]]:
        """
        Get list of uncommitted changes.
        
        Returns:
            Dict with keys: 'modified', 'added', 'deleted', 'untracked'
        """
        if not self._git_available:
            return {'modified': [], 'added': [], 'deleted': [], 'untracked': []}
        
        try:
            result = {
                'modified': [],
                'added': [],
                'deleted': [],
                'untracked': []
            }
            
            # Staged and unstaged changes
            diff_index = self._repo.index.diff(None)  # Unstaged
            diff_head = self._repo.index.diff('HEAD')  # Staged
            
            for diff in diff_index:
                if diff.change_type == 'M':
                    result['modified'].append(diff.a_path)
                elif diff.change_type == 'A':
                    result['added'].append(diff.a_path)
                elif diff.change_type == 'D':
                    result['deleted'].append(diff.a_path)
            
            # Untracked files
            result['untracked'] = self._repo.untracked_files
            
            return result
        except Exception:
            return {'modified': [], 'added': [], 'deleted': [], 'untracked': []}
    
    def get_current_branch(self) -> Optional[str]:
        """Get current branch name"""
        if not self._git_available:
            return None
        
        try:
            return self._repo.active_branch.name
        except Exception:
            return None
    
    def get_remote_url(self) -> Optional[str]:
        """Get remote origin URL"""
        if not self._git_available:
            return None
        
        try:
            return self._repo.remotes.origin.url
        except Exception:
            return None
    
    def search_commits(
        self,
        query: str,
        limit: int = 10
    ) -> List[CommitInfo]:
        """
        Search commits by message.
        
        Args:
            query: Search string (searches commit messages)
            limit: Maximum results
        
        Returns:
            List of matching commits
        """
        if not self._git_available:
            return []
        
        try:
            commits = []
            query_lower = query.lower()
            
            for commit in self._repo.iter_commits(max_count=limit * 5):
                if query_lower in commit.message.lower():
                    commits.append(self._commit_to_info(commit))
                    if len(commits) >= limit:
                        break
            
            return commits
        except Exception:
            return []
    
    def _commit_to_info(self, commit) -> CommitInfo:
        """Convert GitPython commit to CommitInfo"""
        return CommitInfo(
            hash=commit.hexsha,
            short_hash=commit.hexsha[:7],
            author=commit.author.name,
            author_email=commit.author.email,
            date=datetime.fromtimestamp(commit.committed_date),
            message=commit.message.strip(),
            files_changed=list(commit.stats.files.keys()) if commit.stats else []
        )
    
    def format_commit_for_context(self, commit: CommitInfo, include_diff: bool = False) -> str:
        """Format a commit for inclusion in AI context"""
        parts = [
            f"Commit: {commit.short_hash}",
            f"Author: {commit.author} <{commit.author_email}>",
            f"Date: {commit.date.strftime('%Y-%m-%d %H:%M')}",
            f"",
            commit.message,
        ]
        
        if commit.files_changed:
            parts.append("")
            parts.append(f"Files changed ({len(commit.files_changed)}):")
            for f in commit.files_changed:
                parts.append(f"  - {f}")
            if len(commit.files_changed) > 20:
                parts.append(f"  ... and {len(commit.files_changed) - 20} more")
        
        if include_diff:
            details = self.get_commit_details(commit.hash)
            if details:
                parts.append("")
                parts.append("Diff:")
            parts.append(details.diff)  # No limit diff size
            # No truncation
        
        return "\n".join(parts)

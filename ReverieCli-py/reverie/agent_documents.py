"""User-authored global and project instructions, refreshed between requests."""

from pathlib import Path
import logging


logger = logging.getLogger(__name__)
AGENT_DOCUMENT_MARKER = '[REVERIE AGENT DOCUMENT]'


class AgentDocuments:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self._cache = {}

    def messages(self) -> list[dict]:
        messages = []
        seen = set()
        for directory, scope in ((Path.home() / '.reverie', 'Global defaults'), (self.project_root, 'Project instructions')):
            for name in ('AGENTS.md', 'Agent.md'):
                path = directory / name
                if path in seen:
                    continue
                seen.add(path)
                try:
                    stat = path.stat()
                    signature = (stat.st_mtime_ns, stat.st_size)
                    cached = self._cache.get(path)
                    if cached is None or cached[0] != signature:
                        cached = (signature, path.read_text(encoding='utf-8-sig'))
                        self._cache[path] = cached
                    content = cached[1]
                except FileNotFoundError:
                    self._cache.pop(path, None)
                    continue
                except (OSError, UnicodeError):
                    logger.warning('Could not read Agent document %s', path, exc_info=True)
                    continue
                if content.strip():
                    messages.append({'role': 'system', 'content': f'{AGENT_DOCUMENT_MARKER}\n{scope}: {path}\nProject instructions take precedence over global defaults for this project.\n\n{content}'})
        return messages

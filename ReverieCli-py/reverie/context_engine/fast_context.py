"""FastContext-style repository exploration for the Context Engine.

This module keeps the model-facing contract simple: parallel read-only
READ/GLOB/GREP signals in, compact file and line citations out.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
import json
import re
import shutil
import subprocess
import time
from typing import Any, Dict, Iterable, List, Optional


IGNORED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "target",
    "__pycache__",
}


@dataclass
class FastContextHit:
    """One compact piece of repository evidence."""

    file_path: str
    score: float
    source: str
    reason: str
    line_start: int = 0
    line_end: int = 0
    snippet: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "score": round(float(self.score), 3),
            "source": self.source,
            "reason": self.reason,
            "line_start": int(self.line_start or 0),
            "line_end": int(self.line_end or self.line_start or 0),
            "snippet": self.snippet,
        }


@dataclass
class FastContextResult:
    """Ranked FastContext exploration result."""

    query: str
    terms: List[str]
    hits: List[FastContextHit] = field(default_factory=list)
    elapsed_ms: int = 0
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "terms": list(self.terms),
            "elapsed_ms": int(self.elapsed_ms),
            "stats": dict(self.stats),
            "hits": [hit.to_dict() for hit in self.hits],
        }

    def render_markdown(self, *, limit: int = 24) -> str:
        lines = [
            "# FastContext Exploration",
            f"Query: {self.query}",
            f"Terms: {', '.join(self.terms) if self.terms else '(none)'}",
            f"Hits: {len(self.hits)} in {self.elapsed_ms}ms",
            "",
        ]
        for hit in self.hits[: max(1, limit)]:
            location = hit.file_path
            if hit.line_start:
                line_end = hit.line_end or hit.line_start
                location = f"{location}:{hit.line_start}" if line_end == hit.line_start else f"{location}:{hit.line_start}-{line_end}"
            lines.append(f"- `{location}` [{hit.source}:{hit.reason}] score={hit.score:.2f}")
            if hit.snippet:
                lines.append(f"  {hit.snippet}")
        return "\n".join(lines).strip()


class FastContextExplorer:
    """Parallel read-only project explorer inspired by FastContext."""

    def __init__(self, project_root: Path, *, file_info: Optional[Dict[str, Any]] = None):
        self.project_root = Path(project_root).resolve()
        self.file_info = file_info or {}

    def explore(
        self,
        query: str,
        *,
        term_weights: Optional[Dict[str, float]] = None,
        anchors: Optional[Dict[str, List[str]]] = None,
        max_hits: int = 80,
        max_files: int = 20,
        timeout_seconds: float = 5.0,
    ) -> FastContextResult:
        """Return compact file/line evidence for a repository question."""
        started = time.perf_counter()
        query_text = str(query or "").strip()
        terms = self._rank_terms(query_text, term_weights)
        anchors = anchors or {}
        max_hits = max(1, int(max_hits or 80))
        max_files = max(1, int(max_files or 20))

        hit_groups: Dict[str, List[FastContextHit]] = {"index": [], "grep": [], "anchor": []}
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="fast-context") as executor:
            futures = {
                executor.submit(self._index_hits, terms, anchors, max_files): "index",
                executor.submit(self._grep_hits, terms, max_hits, timeout_seconds): "grep",
                executor.submit(self._anchor_hits, anchors, max_files): "anchor",
            }
            for future in as_completed(futures):
                label = futures[future]
                try:
                    hit_groups[label] = future.result()
                except Exception:
                    hit_groups[label] = []

        merged = self._dedupe_and_rank(
            [hit for group in hit_groups.values() for hit in group],
            max_hits=max_hits,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return FastContextResult(
            query=query_text,
            terms=terms,
            hits=merged,
            elapsed_ms=elapsed_ms,
            stats={label: len(group) for label, group in hit_groups.items()},
        )

    def _rank_terms(self, query: str, term_weights: Optional[Dict[str, float]]) -> List[str]:
        if term_weights:
            terms = [
                str(term or "").strip().lower()
                for term, _ in sorted(term_weights.items(), key=lambda item: item[1], reverse=True)
                if len(str(term or "").strip()) >= 3
            ]
        else:
            terms = [
                token.lower()
                for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", str(query or ""))
                if len(token) >= 3
            ]

        ranked: List[str] = []
        seen: set[str] = set()
        for term in terms:
            for part in re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", term).replace("_", " ").split():
                clean = part.strip().lower()
                if len(clean) < 3 or clean in seen:
                    continue
                seen.add(clean)
                ranked.append(clean)
            if len(ranked) >= 12:
                break
        return ranked

    def _normalize_path(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        try:
            path = Path(text)
            if not path.is_absolute():
                path = self.project_root / path
            return str(path.resolve())
        except Exception:
            return text

    def _relative_label(self, path_text: str) -> str:
        try:
            return str(Path(path_text).resolve().relative_to(self.project_root)).replace("\\", "/")
        except Exception:
            return str(path_text).replace("\\", "/")

    @staticmethod
    def _get_meta(info: Any, key: str, default: Any = None) -> Any:
        if isinstance(info, dict):
            return info.get(key, default)
        return getattr(info, key, default)

    def _indexed_records(self) -> Iterable[tuple[str, Any]]:
        if not isinstance(self.file_info, dict):
            return []
        return list(self.file_info.items())

    def _index_hits(self, terms: List[str], anchors: Dict[str, List[str]], max_files: int) -> List[FastContextHit]:
        if not terms and not anchors:
            return []
        anchor_files = {
            str(item or "").strip().lower().replace("\\", "/")
            for item in anchors.get("files", []) or []
            if str(item or "").strip()
        }
        hits: List[FastContextHit] = []
        for raw_path, info in self._indexed_records():
            file_path = self._normalize_path(raw_path)
            if not file_path:
                continue
            rel = self._relative_label(file_path).lower()
            body_parts = [
                rel,
                str(self._get_meta(info, "summary", "") or ""),
                " ".join(str(value) for value in self._get_meta(info, "keywords", []) or []),
                " ".join(str(value) for value in self._get_meta(info, "symbol_names", []) or []),
                " ".join(str(value) for value in self._get_meta(info, "tags", []) or []),
            ]
            haystack = " ".join(body_parts).lower()
            score = 0.0
            reasons: List[str] = []
            for anchor in anchor_files:
                if anchor and (anchor in rel or Path(rel).name == anchor):
                    score += 7.0
                    reasons.append(f"anchor:{anchor}")
            for index, term in enumerate(terms[:10]):
                if term in rel:
                    score += max(1.0, 3.0 - index * 0.1)
                    reasons.append(f"path:{term}")
                if term in haystack:
                    score += max(0.4, 1.5 - index * 0.06)
                    reasons.append(f"meta:{term}")
            if score <= 0.0:
                continue
            hits.append(
                FastContextHit(
                    file_path=file_path,
                    score=score,
                    source="index",
                    reason=", ".join(dict.fromkeys(reasons[:4])) or "metadata",
                    snippet=str(self._get_meta(info, "summary", "") or "")[:220],
                )
            )
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[: max(1, max_files)]

    def _grep_hits(self, terms: List[str], max_hits: int, timeout_seconds: float) -> List[FastContextHit]:
        rg = shutil.which("rg")
        if not rg or not terms:
            return self._python_grep_hits(terms, max_hits=max_hits, timeout_seconds=timeout_seconds)

        pattern = "|".join(re.escape(term) for term in terms[:10] if len(term) >= 3)
        if not pattern:
            return []
        command = [
            rg,
            "--json",
            "--ignore-case",
            "--line-number",
            "--max-count",
            "4",
        ]
        for ignored in sorted(IGNORED_DIR_NAMES):
            command.extend(["--glob", f"!{ignored}/**"])
        command.extend([pattern, str(self.project_root)])
        try:
            completed = subprocess.run(
                command,
                cwd=str(self.project_root),
                text=True,
                capture_output=True,
                timeout=max(1.0, float(timeout_seconds or 5.0)),
            )
        except Exception:
            return []

        hits: List[FastContextHit] = []
        for raw_line in completed.stdout.splitlines():
            if len(hits) >= max_hits:
                break
            try:
                payload = json.loads(raw_line)
            except Exception:
                continue
            if payload.get("type") != "match":
                continue
            data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
            path_text = str((data.get("path", {}) or {}).get("text", "") or "").strip()
            line_text = str((data.get("lines", {}) or {}).get("text", "") or "").strip()
            line_number = int(data.get("line_number") or 0)
            if not path_text:
                continue
            score = 1.1
            lower_line = line_text.lower()
            for index, term in enumerate(terms[:10]):
                if term in lower_line:
                    score += max(0.2, 0.9 - index * 0.04)
            hits.append(
                FastContextHit(
                    file_path=self._normalize_path(path_text),
                    score=score,
                    source="grep",
                    reason="line_match",
                    line_start=line_number,
                    line_end=line_number,
                    snippet=line_text[:240],
                )
            )
        return hits

    def _python_grep_hits(self, terms: List[str], *, max_hits: int, timeout_seconds: float) -> List[FastContextHit]:
        if not terms:
            return []
        started = time.perf_counter()
        hits: List[FastContextHit] = []
        for path in self._candidate_files_from_index(limit=max(500, max_hits * 20)):
            if len(hits) >= max_hits:
                break
            if time.perf_counter() - started > max(1.0, float(timeout_seconds or 5.0)):
                break
            try:
                if path.stat().st_size > 512 * 1024:
                    continue
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            for line_index, line in enumerate(lines, start=1):
                lower_line = line.lower()
                if not any(term in lower_line for term in terms[:10]):
                    continue
                score = 1.0 + sum(0.5 for term in terms[:10] if term in lower_line)
                hits.append(
                    FastContextHit(
                        file_path=str(path.resolve()),
                        score=score,
                        source="grep",
                        reason="python_line_match",
                        line_start=line_index,
                        line_end=line_index,
                        snippet=line.strip()[:240],
                    )
                )
                if len(hits) >= max_hits:
                    break
        return hits

    def _candidate_files_from_index(self, *, limit: int) -> List[Path]:
        paths: List[Path] = []
        for raw_path, _ in self._indexed_records():
            path = Path(self._normalize_path(raw_path))
            if path.exists() and path.is_file():
                paths.append(path)
            if len(paths) >= limit:
                break
        if paths:
            return paths

        for path in self.project_root.rglob("*"):
            if len(paths) >= limit:
                break
            if not path.is_file() or any(part in IGNORED_DIR_NAMES for part in path.parts):
                continue
            paths.append(path)
        return paths

    def _anchor_hits(self, anchors: Dict[str, List[str]], max_files: int) -> List[FastContextHit]:
        files = [str(item or "").strip() for item in anchors.get("files", []) or [] if str(item or "").strip()]
        hits: List[FastContextHit] = []
        for anchor in files[: max_files]:
            resolved = self._resolve_anchor_file(anchor)
            if not resolved:
                continue
            snippet = self._read_window(resolved, 1, radius=6)
            hits.append(
                FastContextHit(
                    file_path=str(resolved),
                    score=8.0,
                    source="anchor",
                    reason=f"explicit_file:{anchor}",
                    line_start=1 if snippet else 0,
                    line_end=min(7, len(snippet.splitlines())) if snippet else 0,
                    snippet=" ".join(snippet.split())[:240],
                )
            )
        return hits

    def _resolve_anchor_file(self, anchor: str) -> Optional[Path]:
        candidate = Path(anchor)
        candidates: List[Path] = []
        if candidate.is_absolute():
            candidates.append(candidate)
        else:
            candidates.append(self.project_root / candidate)
            normalized = str(anchor).replace("\\", "/").lower()
            for raw_path, _ in self._indexed_records():
                path = Path(self._normalize_path(raw_path))
                rel = self._relative_label(str(path)).lower()
                if normalized == rel or normalized in rel or Path(rel).name == normalized:
                    candidates.append(path)
                    break
        for item in candidates:
            try:
                resolved = item.resolve()
            except Exception:
                continue
            if resolved.exists() and resolved.is_file():
                return resolved
        return None

    def _read_window(self, path: Path, line: int, *, radius: int = 5) -> str:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return ""
        if not lines:
            return ""
        line = max(1, int(line or 1))
        start = max(1, line - radius)
        end = min(len(lines), line + radius)
        return "\n".join(f"{line_no:4d} | {lines[line_no - 1]}" for line_no in range(start, end + 1))

    def _dedupe_and_rank(self, hits: List[FastContextHit], *, max_hits: int) -> List[FastContextHit]:
        by_key: Dict[tuple[str, int, str], FastContextHit] = {}
        for hit in hits:
            if not hit.file_path:
                continue
            key = (self._normalize_path(hit.file_path), int(hit.line_start or 0), hit.reason)
            existing = by_key.get(key)
            if existing is None or hit.score > existing.score:
                by_key[key] = FastContextHit(
                    file_path=key[0],
                    score=hit.score,
                    source=hit.source,
                    reason=hit.reason,
                    line_start=hit.line_start,
                    line_end=hit.line_end,
                    snippet=hit.snippet,
                )
        ranked = sorted(by_key.values(), key=lambda item: item.score, reverse=True)
        return ranked[: max(1, max_hits)]

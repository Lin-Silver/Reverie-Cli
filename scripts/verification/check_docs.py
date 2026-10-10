"""Check repository documentation links and Markdown heading anchors offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]
LOCAL_ARTIFACT_ROOTS = {".runtime", ".audit", "dist", "build", "result_images"}
LINK = re.compile(r"!?\[[^\]\n]*\]\((<[^>\n]+>|[^\s)]+)(?:\s+[\"'][^\n]*?[\"'])?\)")
REFERENCE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]+>|\S+)", re.MULTILINE)


def default_paths(root: Path = ROOT) -> list[Path]:
    paths = [root / name for name in (
        "README.md", "SECURITY.md", "ReverieCli-py/README.md",
        "ReverieCli-ui/README.md", "plugins/README.md",
        "plugins/blender/README.md", "plugins/game_models/README.md",
    )]
    paths.extend(sorted((root / "docs").rglob("*.md")))
    # API.md is ignored local material, absent from a normal Git checkout.
    if (root / "API.md").is_file():
        paths.append(root / "API.md")
    return paths


def prose(text: str) -> str:
    lines = []
    fence = ""
    for line in text.splitlines():
        match = re.match(r"\s{0,3}(`{3,}|~{3,})", line)
        if match:
            marker = match.group(1)[0]
            if not fence:
                fence = marker
            elif fence == marker:
                fence = ""
            lines.append("")
        else:
            lines.append("" if fence else line)
    return "\n".join(lines)


def anchors(text: str) -> set[str]:
    result = set(re.findall(r"\bid=[\"']([^\"']+)[\"']", text))
    counts: dict[str, int] = {}
    for line in prose(text).splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        title = re.sub(r"<[^>]+>", "", match.group(1)).lower()
        title = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", title)
        slug = "".join(char for char in title if char.isalnum() or char in "_- ").replace(" ", "-")
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        result.add(f"{slug}-{count}" if count else slug)
    return result


def is_local_artifact(relative: Path) -> bool:
    return bool(relative.parts) and (relative.parts[0] in LOCAL_ARTIFACT_ROOTS or (
        relative.parts[0] == "ReverieCli-ui" and len(relative.parts) > 1
        and relative.parts[1] in {"release", ".kernel", "dist", "dist-electron"}
    ))


def check(paths: list[Path], root: Path = ROOT) -> dict:
    errors = []
    local_artifacts = []
    checked = 0
    heading_cache: dict[Path, set[str]] = {}
    for source in paths:
        body = prose(source.read_text(encoding="utf-8-sig"))
        matches = list(LINK.finditer(body)) + list(REFERENCE.finditer(body))
        for match in matches:
            target = match.group(1).strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc:
                continue
            checked += 1
            file = (source.parent / unquote(parsed.path)).resolve() if parsed.path else source.resolve()
            item = {"source": source.relative_to(root).as_posix(), "line": body[:match.start()].count("\n") + 1, "target": target}
            try:
                relative = file.relative_to(root)
            except ValueError:
                errors.append({**item, "reason": "outside repository"})
                continue
            if is_local_artifact(relative):
                local_artifacts.append({**item, "exists_locally": file.exists()})
                continue
            if not file.exists():
                errors.append({**item, "reason": "missing file"})
            elif parsed.fragment and file.suffix.lower() == ".md":
                if file not in heading_cache:
                    heading_cache[file] = anchors(file.read_text(encoding="utf-8-sig"))
                if unquote(parsed.fragment) not in heading_cache[file]:
                    errors.append({**item, "reason": "missing heading anchor"})
    return {"documents": len(paths), "local_links": checked, "errors": errors, "local_artifact_references": local_artifacts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="Optional repository-relative Markdown files")
    parser.add_argument("--json", type=Path, help="Save a structured report")
    args = parser.parse_args()
    paths = [ROOT / value for value in args.paths] if args.paths else default_paths()
    report = check(paths)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Documents: {report['documents']}; local links: {report['local_links']}; errors: {len(report['errors'])}; local artifact references: {len(report['local_artifact_references'])}")
    for item in report["errors"]:
        print(f"{item['source']}:{item['line']}: {item['reason']}: {item['target']}")
    print("Local artifact references are reported separately and are not required for this offline check. External URLs are not fetched.")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

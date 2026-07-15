"""Fail CI when a direct runtime/build dependency is not exactly pinned."""

from __future__ import annotations

import ast
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PIN_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:\[[^]]+\])?==[^;\s]+(?:\s*;.*)?$")


def _setup_groups() -> dict[str, list[str]]:
    tree = ast.parse((ROOT / "setup.py").read_text(encoding="utf-8"))
    groups: dict[str, list[str]] = {"runtime": []}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "setup"):
            continue
        for keyword in node.keywords:
            if keyword.arg == "install_requires" and isinstance(keyword.value, ast.List):
                groups["runtime"].extend(
                    item.value for item in keyword.value.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)
                )
            if keyword.arg == "extras_require" and isinstance(keyword.value, ast.Dict):
                for key, extra in zip(keyword.value.keys, keyword.value.values):
                    if isinstance(extra, ast.List):
                        name = key.value if isinstance(key, ast.Constant) and isinstance(key.value, str) else "unknown"
                        groups.setdefault(name, []).extend(
                            item.value for item in extra.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)
                        )
    return groups


def _requirement_key(value: str) -> str:
    name = value.split("==", 1)[0].split("[", 1)[0]
    return re.sub(r"[-_.]+", "-", name).lower()


def _version_pin(value: str) -> str:
    return value.split(";", 1)[0].strip().lower()


def main() -> int:
    def load_requirements(name: str) -> list[str]:
        return [
            line.strip()
            for line in (ROOT / name).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith(("#", "-"))
        ]

    requirements = load_requirements("requirements.txt")
    tti_requirements = load_requirements("requirements-tti.txt")
    setup_groups = _setup_groups()
    setup_items = [item for values in setup_groups.values() for item in values]
    unpinned = sorted({item for item in [*requirements, *tti_requirements, *setup_items] if not PIN_RE.match(item)})
    if unpinned:
        print("Unpinned direct dependencies:")
        for item in unpinned:
            print(f"- {item}")
        return 1

    requirements_by_name = {_requirement_key(item): item for item in requirements}
    maintained_setup = [*setup_groups.get("runtime", []), *setup_groups.get("treesitter", []), *setup_groups.get("build", [])]
    mismatches = [
        item
        for item in maintained_setup
        if _version_pin(requirements_by_name.get(_requirement_key(item), "")) != _version_pin(item)
    ]
    if mismatches:
        print("requirements.txt and setup.py disagree:")
        for item in mismatches:
            print(f"- setup.py: {item}; requirements.txt: {requirements_by_name.get(_requirement_key(item), 'missing')}")
        return 1

    print(
        f"All {len(requirements)} maintained requirements are exactly pinned and synchronized; "
        f"all {len(tti_requirements)} optional TTI requirements are exactly pinned."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

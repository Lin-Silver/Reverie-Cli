"""Shared terminal/desktop WStyle commands; no model tools are registered."""

from __future__ import annotations

import shlex
from typing import Any, Callable

from ..modes import normalize_mode
from ..tools.base import ToolResult
from .style_runtime import WStyleRuntime
from .wstyles import WStyleError, compose_wstyles


WSTYLE_HELP = """/wstyle list | show <id> | current
/wstyle use <id...> | add <id> | remove <id> | off
/wstyle new <id> [--from <id>]
/wstyle inherit — restore a novel's inheritance of application defaults
/wstyle review [<novel-id>] [--chapter <n>]
/wstyle extract <new-id> --sample <path> [--sample <path>...] [--layer <layer>]
Selection commands accept --global or --novel <id>. Switching affects the next generation only.
review/extract explicitly send bounded text to the current model and can incur provider usage.
"""


def split_wstyle_args(args: str) -> list[str]:
    try:
        tokens = shlex.split(args, posix=False)
    except ValueError as exc:
        raise WStyleError(f"Invalid command quoting: {exc}") from exc
    return [token[1:-1] if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'" else token for token in tokens]


def _parse(args: str) -> tuple[str, list[str], dict[str, Any]]:
    tokens = split_wstyle_args(args)
    action = tokens.pop(0).lower() if tokens else "current"
    allowed = {"--global", "--novel"}
    if action == "new":
        allowed.add("--from")
    if action == "review":
        allowed.update({"--chapter", "--start-line", "--end-line"})
    if action == "extract":
        allowed.update({"--sample", "--layer", "--source-note", "--start-line", "--end-line"})
    values, options = [], {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("--"):
            if token not in allowed:
                raise WStyleError(f"Unknown option for {action}: {token}")
            if token == "--global":
                options[token] = True
            else:
                index += 1
                if index >= len(tokens) or tokens[index].startswith("--"):
                    raise WStyleError(f"{token} requires a value.")
                if token == "--sample":
                    options.setdefault(token, []).append(tokens[index])
                elif token in options:
                    raise WStyleError(f"{token} may only be specified once.")
                else:
                    options[token] = tokens[index]
        else:
            values.append(token)
        index += 1
    if options.get("--global") and options.get("--novel"):
        raise WStyleError("Choose --global or --novel, not both.")
    for flag in ("--chapter", "--start-line", "--end-line"):
        if flag in options:
            try:
                options[flag] = int(options[flag])
            except ValueError as exc:
                raise WStyleError(f"{flag} requires a positive integer.") from exc
            if options[flag] < 1:
                raise WStyleError(f"{flag} requires a positive integer.")
    return action, values, options


def _status(state: dict[str, Any]) -> str:
    lines = [f"WStyle scope: {state['scope']}" + (" (inherits application defaults)" if state.get("inherited") else ""),
             f"Card directory: {state['repository']}",
             "Saved: " + (" → ".join(state["saved_ids"]) or "off"), "Effective:"]
    for index, card in enumerate(state["cards"], 1):
        lines.append(f"{index}. {card['id']} — {card['name']} [{card['layer']}] ({card['sha256'][:12]})")
    if not state["cards"]:
        lines.append("- Base Writer prompt; no Cards are active.")
    lines.append(f"Style prompt: {state['prompt_chars']:,} characters; conservative token upper bound {state['token_upper_bound']:,}.")
    lines.append("Saved/effective selection: " + ("consistent" if state["saved_matches_effective"] else "different"))
    lines.extend("Warning: " + warning for warning in state["warnings"])
    lines.extend("Unavailable: " + issue["id"] + " — " + issue["message"] for issue in state["issues"])
    return "\n".join(lines)


def run_wstyle_command(args: str, runtime: WStyleRuntime, *, mode: str,
                       model_call: Callable[..., str] | None = None) -> ToolResult:
    if normalize_mode(mode) != "writer":
        return ToolResult.fail("/wstyle is available only in Writer mode. Switch with /mode writer.")
    try:
        action, values, options = _parse(args)
        if options.get("--novel"):
            runtime.select_novel(options["--novel"])
        global_scope = bool(options.get("--global"))
        runtime.ensure_resources()
        if action in {"current", "status", "help"}:
            if values:
                raise WStyleError(f"{action} takes no positional arguments.")
            state = runtime.snapshot(global_scope=global_scope)
            return ToolResult.ok(_status(state) + ("\n\n" + WSTYLE_HELP if not args.strip() or action == "help" else ""), {"state": state})
        if action == "list":
            if values:
                raise WStyleError("list takes no positional arguments.")
            state = runtime.snapshot(global_scope=global_scope)
            active = {card["id"].casefold() for card in state["cards"]}
            items = [{**item, "enabled": item["id"].casefold() in active} for item in runtime.repository.list_cards()]
            lines = [f"WStyle Cards: {runtime.repository.root}"]
            for item in items:
                lines.append(f"{'✓' if item['enabled'] else '○'} {item['id']} — {item['name']} [{item['layer'] or 'invalid'}]")
                lines.append("  " + (item.get("error") or item["description"] or "No description"))
            return ToolResult.ok("\n".join(lines), {"items": items, "state": state})
        if action in {"show", "new"}:
            if len(values) != 1:
                raise WStyleError(f"{action} requires exactly one Card ID.")
            card = runtime.repository.get(values[0]) if action == "show" else runtime.repository.create(values[0], options.get("--from"))
            output = f"{card.name} ({card.id}, {card.layer})\n{card.description}\n\n{card.body}"
            if action == "new":
                output = f"Created {runtime.repository.root / (card.id + '.md')}. The Card is not automatically enabled.\n" + output
            return ToolResult.ok(output, {"card": card.summary(), "metadata": card.metadata, "path": str(runtime.repository.root / (card.id + ".md"))})
        if action in {"use", "add", "remove", "off", "inherit"}:
            if action == "use" and not values:
                raise WStyleError("use requires at least one Card ID; use off to disable Cards.")
            if action in {"add", "remove"} and len(values) != 1:
                raise WStyleError(f"{action} requires exactly one Card ID.")
            if action in {"off", "inherit"} and values:
                raise WStyleError(f"{action} takes no positional arguments.")
            current, _, _, _ = runtime.selection(global_scope=global_scope)
            if action == "inherit":
                if global_scope:
                    raise WStyleError("inherit applies to a selected novel, not application defaults.")
                state = runtime.inherit_defaults()
            else:
                ids = values if action == "use" else [] if action == "off" else list(current)
                if action == "add":
                    card = runtime.repository.get(values[0])
                    if card.id.casefold() not in {value.casefold() for value in ids}:
                        ids.append(card.id)
                    candidate = compose_wstyles(runtime.repository, ids, strict=False, max_tokens=runtime._style_token_budget())
                    if card.id not in candidate.active_ids:
                        raise WStyleError("The added Card cannot be active: " + "; ".join(item["message"] for item in candidate.issues))
                if action == "remove":
                    if values[0].casefold() not in {value.casefold() for value in ids}:
                        raise WStyleError(f"Card '{values[0]}' is not in the saved selection.")
                    ids = [value for value in ids if value.casefold() != values[0].casefold()]
                state = runtime.set_selection(ids, global_scope=global_scope, allow_unavailable=action in {"add", "remove"})
            return ToolResult.ok(_status(state) + "\nEffective from the next model request. Existing manuscript and drafts were preserved.", {"state": state})
        if action in {"review", "extract"}:
            if action == "review":
                if len(values) > 1 or global_scope:
                    raise WStyleError("review accepts one optional novel ID and --chapter; --global is not supported.")
                if values:
                    runtime.select_novel(values[0])
                from .style_models import review_chapter

                return review_chapter(runtime, model_call, chapter=options.get("--chapter"),
                                      start_line=options.get("--start-line", 1), end_line=options.get("--end-line"))
            if len(values) != 1 or not options.get("--sample") or global_scope:
                raise WStyleError("extract requires a new Card ID and at least one --sample path.")
            from .style_models import extract_wstyle

            return extract_wstyle(runtime, model_call, card_id=values[0], samples=options["--sample"],
                                  layer=options.get("--layer"), source_note=options.get("--source-note", ""),
                                  start_line=options.get("--start-line", 1), end_line=options.get("--end-line"))
        raise WStyleError(f"Unknown /wstyle action: {action}.\n{WSTYLE_HELP}")
    except (WStyleError, OSError, ValueError, TypeError) as exc:
        return ToolResult.fail(f"WStyle: {exc}")

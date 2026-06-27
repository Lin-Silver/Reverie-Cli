"""Import a practical Ren'Py script subset into Reverie dialogue content."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
import ast
import json
import re

import yaml


_DEFINE_CHARACTER_RE = re.compile(r"^define\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*Character\((.+)\)\s*$")
_DEFAULT_RE = re.compile(r"^default\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)\s*$")
_LABEL_RE = re.compile(r"^label\s+([A-Za-z0-9_\.]+)\s*:\s*$")
_JUMP_RE = re.compile(r"^(jump|call)\s+([A-Za-z0-9_\.]+)\s*$")
_STOP_RE = re.compile(r"^stop\s+([A-Za-z_][A-Za-z0-9_]*)\b(.*)$")
_VOICE_RE = re.compile(r"^voice\s+(.+)$")
_SPEAKER_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s+")
_FIRST_STRING_RE = re.compile(r'("([^"\\]|\\.)*"|\'([^\'\\]|\\.)*\')')
_RENPY_INTERPOLATION_RE = re.compile(r"\[([A-Za-z_][A-Za-z0-9_]*)\]")
_MISSING = object()


@dataclass
class ScriptLine:
    number: int
    indent: int
    text: str


@dataclass
class DialogueStatement:
    speaker_alias: str
    text: str


@dataclass
class JumpStatement:
    target: str
    kind: str = "jump"


@dataclass
class ReturnStatement:
    pass


@dataclass
class PassStatement:
    pass


@dataclass
class EffectStatement:
    effects: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    auto_advance: bool = True


@dataclass
class MenuOption:
    text: str
    statements: list[Any] = field(default_factory=list)
    condition: str = ""


@dataclass
class MenuStatement:
    prompt: str = ""
    options: list[MenuOption] = field(default_factory=list)


@dataclass
class ParsedRenPyScript:
    conversation_id: str
    labels: Dict[str, list[Any]]
    label_order: list[str]
    entry_label: str
    characters: Dict[str, str]
    warnings: list[str]
    initial_effects: Dict[str, Any] = field(default_factory=dict)


def _slugify(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or "").strip())
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_") or "conversation"


def _quoted_value(fragment: str) -> Optional[str]:
    match = _FIRST_STRING_RE.search(str(fragment or ""))
    if not match:
        return None
    try:
        return str(ast.literal_eval(match.group(1)))
    except Exception:
        return match.group(1).strip("\"'")


def _convert_text_template(text: str) -> str:
    return _RENPY_INTERPOLATION_RE.sub(r"{\1}", str(text or ""))


def _resolve_label_name(raw_label: str, current_global_label: str) -> str:
    label = str(raw_label or "").strip()
    if label.startswith(".") and current_global_label:
        return f"{current_global_label}{label}"
    return label


def _normalize_target(raw_target: str, current_global_label: str) -> str:
    target = str(raw_target or "").strip()
    if target.startswith(".") and current_global_label:
        return f"{current_global_label}{target}"
    return target


def _clean_line(raw_line: str) -> str:
    line = raw_line.rstrip("\n\r")
    if not line.strip():
        return ""
    if line.lstrip().startswith("#"):
        return ""
    return line


def _script_lines(text: str) -> list[ScriptLine]:
    lines: list[ScriptLine] = []
    for number, raw in enumerate(str(text or "").splitlines(), start=1):
        cleaned = _clean_line(raw)
        if not cleaned:
            continue
        indent = len(cleaned) - len(cleaned.lstrip(" "))
        lines.append(ScriptLine(number=number, indent=indent, text=cleaned.strip()))
    return lines


def _literal_from_ast(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        operand = _literal_from_ast(node.operand)
        if isinstance(operand, (int, float)):
            return -operand
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
        operand = _literal_from_ast(node.operand)
        if isinstance(operand, (int, float)):
            return operand
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values: list[Any] = []
        for element in node.elts:
            literal = _literal_from_ast(element)
            if literal is _MISSING:
                return _MISSING
            values.append(literal)
        return values
    return _MISSING


def _merge_effects(base: Dict[str, Any], addition: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base or {})
    for key, value in dict(addition or {}).items():
        if key in {"set_notes", "requires_notes", "requires_notes_not", "requires_notes_min", "requires_notes_max"}:
            bucket = dict(merged.get(key) or {})
            bucket.update({str(inner_key): inner_value for inner_key, inner_value in dict(value or {}).items()})
            merged[key] = bucket
            continue
        if key == "add_notes":
            bucket = dict(merged.get(key) or {})
            for inner_key, inner_value in dict(value or {}).items():
                normalized = str(inner_key)
                bucket[normalized] = bucket.get(normalized, 0) + inner_value
            merged[key] = bucket
            continue
        if key in {"set_flags", "clear_flags", "requires_truthy_notes", "blocked_truthy_notes"}:
            existing = list(merged.get(key) or [])
            for item in list(value or []):
                normalized = str(item).strip()
                if normalized and normalized not in existing:
                    existing.append(normalized)
            merged[key] = existing
            continue
        if key in {"renpy_commands", "all_conditions", "any_conditions", "not_conditions"}:
            existing = list(merged.get(key) or [])
            existing.extend(value or [])
            merged[key] = existing
            continue
        merged[key] = value
    return merged


def _parse_assignment_effect(statement: str) -> tuple[Optional[Dict[str, Any]], str]:
    try:
        parsed = ast.parse(str(statement or "").strip(), mode="exec")
    except SyntaxError as exc:
        return None, f"invalid python assignment syntax: {exc.msg}"

    body = list(parsed.body)
    if len(body) != 1:
        return None, "only single-line python assignments are supported"

    node = body[0]
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        literal = _literal_from_ast(node.value)
        if literal is _MISSING:
            return None, "only literal assignment values are supported"
        return {"set_notes": {node.targets[0].id: literal}}, ""

    if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
        literal = _literal_from_ast(node.value)
        if literal is _MISSING or not isinstance(literal, (int, float)):
            return None, "only numeric += and -= updates are supported"
        if isinstance(node.op, ast.Add):
            return {"add_notes": {node.target.id: literal}}, ""
        if isinstance(node.op, ast.Sub):
            return {"add_notes": {node.target.id: -literal}}, ""
        return None, "only += and -= updates are supported"

    return None, "only variable assignment, +=, and -= statements are supported"


def _image_tag(image_name: str) -> str:
    tokens = [token for token in str(image_name or "").strip().split() if token]
    return tokens[0] if tokens else ""


def _split_modifier(text: str, marker: str) -> tuple[str, str]:
    raw = str(text or "")
    if marker not in raw:
        return raw.strip(), ""
    head, tail = raw.split(marker, 1)
    return head.strip(), tail.strip()


def _normalize_stage_position(spec: str) -> str:
    tokens = [token.strip().lower() for token in re.split(r"[\s,]+", str(spec or "")) if token.strip()]
    for token in tokens:
        if token in {"left", "far_left"}:
            return "left"
        if token in {"center", "centre", "truecenter", "mid", "midleft", "midright"}:
            return "center"
        if token in {"right", "far_right"}:
            return "right"
    return ""


def _parse_visual_statement(kind: str, text: str) -> Optional[EffectStatement]:
    payload = str(text or "").strip()[len(kind):].strip()
    payload, transition = _split_modifier(payload, " with ")
    payload, alias = _split_modifier(payload, " as ")
    payload, at_clause = _split_modifier(payload, " at ")
    for marker in (" onlayer ", " behind ", " zorder "):
        payload, _ = _split_modifier(payload, marker)

    if payload.lower().startswith("expression "):
        payload = payload[11:].strip()

    image_name = payload.strip()
    if kind != "scene" and not image_name:
        return None

    command: Dict[str, Any] = {
        "kind": kind,
        "image": image_name,
        "tag": _image_tag(image_name),
        "alias": alias,
        "position": _normalize_stage_position(at_clause),
        "statement": str(text or "").strip(),
    }
    if transition:
        command["transition"] = transition
    if kind == "scene":
        command["clear_characters"] = True
    return EffectStatement(effects={"renpy_commands": [command]}, description=command["statement"])


def _parse_hide_statement(text: str) -> Optional[EffectStatement]:
    payload = str(text or "").strip()[4:].strip()
    payload, transition = _split_modifier(payload, " with ")
    payload, _ = _split_modifier(payload, " onlayer ")
    target = payload.strip()
    if not target:
        return None
    command: Dict[str, Any] = {
        "kind": "hide",
        "target": target,
        "tag": _image_tag(target),
        "statement": str(text or "").strip(),
    }
    if transition:
        command["transition"] = transition
    return EffectStatement(effects={"renpy_commands": [command]}, description=command["statement"])


def _parse_play_statement(text: str) -> Optional[EffectStatement]:
    payload = str(text or "").strip()[4:].strip()
    if not payload:
        return None
    channel, _, rest = payload.partition(" ")
    asset = _quoted_value(rest) or (rest.split()[0] if rest.strip() else "")
    if not channel or not asset:
        return None
    loop = str(channel).strip().lower() in {"music", "ambient"}
    command = {
        "kind": "play",
        "channel": str(channel).strip().lower(),
        "asset": asset,
        "loop": loop,
        "statement": str(text or "").strip(),
    }
    return EffectStatement(effects={"renpy_commands": [command]}, description=command["statement"])


def _parse_voice_statement(text: str) -> Optional[EffectStatement]:
    match = _VOICE_RE.match(str(text or "").strip())
    if not match:
        return None
    asset = _quoted_value(match.group(1)) or match.group(1).split()[0]
    if not asset:
        return None
    command = {
        "kind": "play",
        "channel": "voice",
        "asset": asset,
        "loop": False,
        "statement": str(text or "").strip(),
    }
    return EffectStatement(effects={"renpy_commands": [command]}, description=command["statement"])


def _parse_stop_statement(text: str) -> Optional[EffectStatement]:
    match = _STOP_RE.match(str(text or "").strip())
    if not match:
        return None
    channel = str(match.group(1) or "").strip().lower()
    if not channel:
        return None
    command = {
        "kind": "stop",
        "channel": channel,
        "statement": str(text or "").strip(),
    }
    return EffectStatement(effects={"renpy_commands": [command]}, description=command["statement"])


def _parse_effect_statement(text: str, *, line_number: int, warnings: list[str]) -> Optional[EffectStatement]:
    stripped = str(text or "").strip()
    if not stripped:
        return None

    if stripped.startswith("$"):
        effects, error = _parse_assignment_effect(stripped[1:].strip())
        if effects is not None:
            return EffectStatement(effects=effects, description=stripped)
        warnings.append(f"Skipped unsupported Ren'Py python line on line {line_number}: {stripped} ({error})")
        return None

    if stripped.startswith("scene"):
        effect = _parse_visual_statement("scene", stripped)
        if effect is not None:
            return effect
    if stripped.startswith("show "):
        effect = _parse_visual_statement("show", stripped)
        if effect is not None:
            return effect
    if stripped.startswith("hide "):
        effect = _parse_hide_statement(stripped)
        if effect is not None:
            return effect
    if stripped.startswith("play "):
        effect = _parse_play_statement(stripped)
        if effect is not None:
            return effect
    if stripped.startswith("voice "):
        effect = _parse_voice_statement(stripped)
        if effect is not None:
            return effect
    if stripped.startswith("stop "):
        effect = _parse_stop_statement(stripped)
        if effect is not None:
            return effect
    return None


def _reverse_comparator(operator: ast.cmpop) -> ast.cmpop:
    mapping: Dict[type[ast.cmpop], ast.cmpop] = {
        ast.Gt: ast.Lt(),
        ast.GtE: ast.LtE(),
        ast.Lt: ast.Gt(),
        ast.LtE: ast.GtE(),
        ast.Eq: ast.Eq(),
        ast.NotEq: ast.NotEq(),
        ast.In: ast.In(),
        ast.NotIn: ast.NotIn(),
        ast.Is: ast.Is(),
        ast.IsNot: ast.IsNot(),
    }
    return mapping.get(type(operator), operator)


def _compile_compare_condition(left: ast.AST, operator: ast.cmpop, right: ast.AST) -> Optional[Dict[str, Any]]:
    if isinstance(left, ast.Constant) and isinstance(right, ast.Name):
        return _compile_compare_condition(right, _reverse_comparator(operator), left)
    if not isinstance(left, ast.Name):
        return None

    note_name = left.id
    literal = _literal_from_ast(right)
    if literal is _MISSING:
        return None

    if isinstance(operator, (ast.Is, ast.Eq)):
        return {"requires_notes": {note_name: literal}}
    if isinstance(operator, (ast.IsNot, ast.NotEq)):
        return {"requires_notes_not": {note_name: literal}}
    if isinstance(operator, ast.Gt):
        return {"requires_note_greater_than": {note_name: literal}}
    if isinstance(operator, ast.GtE):
        return {"requires_notes_min": {note_name: literal}}
    if isinstance(operator, ast.Lt):
        return {"requires_note_less_than": {note_name: literal}}
    if isinstance(operator, ast.LtE):
        return {"requires_notes_max": {note_name: literal}}
    if isinstance(operator, ast.In) and isinstance(literal, list):
        return {"requires_notes_in": {note_name: literal}}
    if isinstance(operator, ast.NotIn) and isinstance(literal, list):
        return {"blocked_notes_in": {note_name: literal}}
    return None


def _compile_condition_node(node: ast.AST) -> Optional[Dict[str, Any]]:
    if isinstance(node, ast.BoolOp):
        compiled_children = []
        for child in list(node.values):
            compiled = _compile_condition_node(child)
            if compiled is None:
                return None
            compiled_children.append(compiled)
        if isinstance(node.op, ast.And):
            return {"all_conditions": compiled_children}
        if isinstance(node.op, ast.Or):
            return {"any_conditions": compiled_children}
        return None

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        compiled = _compile_condition_node(node.operand)
        if compiled is None:
            return None
        return {"not_conditions": [compiled]}

    if isinstance(node, ast.Name):
        return {"requires_truthy_notes": [node.id]}

    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return {} if node.value else {"always_false": True}

    if isinstance(node, ast.Compare):
        comparisons: list[Dict[str, Any]] = []
        left = node.left
        for operator, comparator in zip(node.ops, node.comparators):
            compiled = _compile_compare_condition(left, operator, comparator)
            if compiled is None:
                return None
            comparisons.append(compiled)
            left = comparator
        if len(comparisons) == 1:
            return comparisons[0]
        return {"all_conditions": comparisons}

    return None


def _compile_condition_expression(expression: str) -> tuple[Optional[Dict[str, Any]], str]:
    raw = str(expression or "").strip()
    if not raw:
        return {}, ""
    try:
        parsed = ast.parse(raw, mode="eval")
    except SyntaxError as exc:
        return None, f"invalid condition syntax: {exc.msg}"
    compiled = _compile_condition_node(parsed.body)
    if compiled is None:
        return None, "unsupported condition expression"
    return compiled, ""


def parse_renpy_script(
    text: str,
    *,
    conversation_id: str,
    entry_label: str = "",
) -> ParsedRenPyScript:
    lines = _script_lines(text)
    characters: Dict[str, str] = {}
    labels: Dict[str, list[Any]] = {}
    label_order: list[str] = []
    warnings: list[str] = []
    initial_effects: Dict[str, Any] = {}
    current_global_label = ""
    index = 0

    while index < len(lines):
        line = lines[index]
        define_match = _DEFINE_CHARACTER_RE.match(line.text)
        if define_match:
            alias = define_match.group(1)
            speaker = _quoted_value(define_match.group(2))
            if speaker:
                characters[alias] = speaker
            index += 1
            continue

        default_match = _DEFAULT_RE.match(line.text)
        if default_match:
            effects, error = _parse_assignment_effect(f"{default_match.group(1)} = {default_match.group(2)}")
            if effects is not None:
                initial_effects = _merge_effects(initial_effects, effects)
            else:
                warnings.append(f"Skipped unsupported Ren'Py default on line {line.number}: {line.text} ({error})")
            index += 1
            continue

        label_match = _LABEL_RE.match(line.text)
        if not label_match:
            index += 1
            continue

        raw_label = label_match.group(1)
        resolved_label = _resolve_label_name(raw_label, current_global_label)
        if not raw_label.startswith("."):
            current_global_label = resolved_label
        labels[resolved_label], index = _parse_block(
            lines,
            start_index=index + 1,
            block_indent=line.indent + 4,
            current_global_label=current_global_label,
            warnings=warnings,
        )
        label_order.append(resolved_label)

    preferred_entry = str(entry_label or "").strip()
    if preferred_entry:
        preferred_entry = _normalize_target(preferred_entry, label_order[0] if label_order else "")
    if not preferred_entry:
        preferred_entry = "start" if "start" in labels else (label_order[0] if label_order else "start")

    return ParsedRenPyScript(
        conversation_id=_slugify(conversation_id),
        labels=labels,
        label_order=label_order,
        entry_label=preferred_entry,
        characters=characters,
        warnings=warnings,
        initial_effects=initial_effects,
    )


def _parse_block(
    lines: list[ScriptLine],
    *,
    start_index: int,
    block_indent: int,
    current_global_label: str,
    warnings: list[str],
) -> tuple[list[Any], int]:
    statements: list[Any] = []
    index = start_index

    while index < len(lines):
        line = lines[index]
        if line.indent < block_indent:
            break
        if line.indent == 0 and _LABEL_RE.match(line.text):
            break
        if line.indent > block_indent:
            warnings.append(f"Skipped unexpected nested statement on line {line.number}: {line.text}")
            index += 1
            continue

        stripped = line.text
        if stripped == "pass":
            statements.append(PassStatement())
            index += 1
            continue
        if stripped == "return":
            statements.append(ReturnStatement())
            index += 1
            continue
        jump_match = _JUMP_RE.match(stripped)
        if jump_match:
            target = _normalize_target(jump_match.group(2), current_global_label)
            if jump_match.group(1) == "call":
                warnings.append(f"Ren'Py 'call' on line {line.number} was imported as a direct jump to '{target}'.")
            statements.append(JumpStatement(target=target, kind=jump_match.group(1)))
            index += 1
            continue
        if stripped.startswith("menu") and stripped.endswith(":"):
            menu_statement, index = _parse_menu(
                lines,
                start_index=index + 1,
                menu_indent=line.indent,
                current_global_label=current_global_label,
                warnings=warnings,
            )
            statements.append(menu_statement)
            continue

        effect_statement = _parse_effect_statement(stripped, line_number=line.number, warnings=warnings)
        if effect_statement is not None:
            statements.append(effect_statement)
            index += 1
            continue

        dialogue_statement = _parse_dialogue_statement(stripped)
        if dialogue_statement is not None:
            statements.append(dialogue_statement)
            index += 1
            continue

        if stripped.endswith(":"):
            warnings.append(f"Skipped unsupported block statement on line {line.number}: {stripped}")
            index = _skip_nested_block(lines, start_index=index + 1, parent_indent=line.indent)
            continue

        warnings.append(f"Skipped unsupported Ren'Py statement on line {line.number}: {stripped}")
        index += 1

    return statements, index


def _parse_menu(
    lines: list[ScriptLine],
    *,
    start_index: int,
    menu_indent: int,
    current_global_label: str,
    warnings: list[str],
) -> tuple[MenuStatement, int]:
    prompt_lines: list[str] = []
    options: list[MenuOption] = []
    option_indent = menu_indent + 4
    index = start_index

    while index < len(lines):
        line = lines[index]
        if line.indent < option_indent:
            break
        if line.indent > option_indent:
            warnings.append(f"Skipped unsupported menu nesting on line {line.number}: {line.text}")
            index += 1
            continue

        stripped = line.text
        option_text, condition = _parse_menu_option_header(stripped)
        if option_text is not None:
            option_statements, index = _parse_block(
                lines,
                start_index=index + 1,
                block_indent=option_indent + 4,
                current_global_label=current_global_label,
                warnings=warnings,
            )
            options.append(
                MenuOption(
                    text=_convert_text_template(option_text),
                    statements=option_statements,
                    condition=condition,
                )
            )
            continue

        prompt = _quoted_value(stripped)
        if prompt is not None:
            prompt_lines.append(_convert_text_template(prompt))
            index += 1
            continue

        warnings.append(f"Skipped unsupported menu line on line {line.number}: {stripped}")
        index += 1

    prompt_text = " ".join(fragment for fragment in prompt_lines if fragment).strip()
    return MenuStatement(prompt=prompt_text, options=options), index


def _parse_menu_option_header(text: str) -> tuple[Optional[str], str]:
    stripped = str(text or "").strip()
    if not stripped.endswith(":"):
        return None, ""
    literal = _quoted_value(stripped)
    if literal is None:
        return None, ""
    match = _FIRST_STRING_RE.search(stripped)
    condition = ""
    if match:
        tail = stripped[match.end():].rstrip(":").strip()
        if tail.startswith("if "):
            condition = tail[3:].strip()
    return literal, condition


def _parse_dialogue_statement(text: str) -> Optional[DialogueStatement]:
    stripped = str(text or "").strip()
    literal = _quoted_value(stripped)
    if literal is None:
        return None
    if stripped.startswith(("\"", "'")):
        return DialogueStatement(speaker_alias="", text=_convert_text_template(literal))
    speaker_match = _SPEAKER_LINE_RE.match(stripped)
    if not speaker_match:
        return None
    return DialogueStatement(speaker_alias=speaker_match.group(1), text=_convert_text_template(literal))


def _skip_nested_block(lines: list[ScriptLine], *, start_index: int, parent_indent: int) -> int:
    index = start_index
    while index < len(lines):
        if lines[index].indent <= parent_indent:
            break
        index += 1
    return index


def compile_renpy_script(parsed: ParsedRenPyScript) -> Dict[str, Any]:
    nodes: Dict[str, Dict[str, Any]] = {}
    warnings = list(parsed.warnings)
    node_counter = 0

    def node_id(label_name: str, index: int) -> str:
        return f"{_slugify(label_name)}__{index:03d}"

    def label_ref(label_name: str) -> str:
        return f"@label:{label_name}"

    def build_block(statements: list[Any], next_target: Optional[str], label_name: str) -> Optional[str]:
        nonlocal node_counter
        current_next = next_target
        for statement in reversed(statements):
            if isinstance(statement, PassStatement):
                continue
            if isinstance(statement, ReturnStatement):
                current_next = None
                continue
            if isinstance(statement, JumpStatement):
                current_next = label_ref(statement.target)
                continue
            if isinstance(statement, EffectStatement):
                identifier = node_id(label_name, node_counter)
                node_counter += 1
                payload: Dict[str, Any] = {
                    "speaker": "",
                    "text": "",
                    "auto_advance": bool(statement.auto_advance),
                    "effects_on_enter": dict(statement.effects or {}),
                    "renpy_statement": statement.description,
                }
                if current_next:
                    payload["next"] = current_next
                nodes[identifier] = payload
                current_next = identifier
                continue
            if isinstance(statement, MenuStatement):
                choices: list[Dict[str, Any]] = []
                for option in statement.options:
                    option_entry = build_block(option.statements, current_next, label_name)
                    payload: Dict[str, Any] = {"text": option.text}
                    if option_entry:
                        payload["next"] = option_entry
                    if option.condition:
                        compiled_condition, error = _compile_condition_expression(option.condition)
                        if compiled_condition is not None:
                            payload["conditions"] = compiled_condition
                            payload["renpy_condition"] = option.condition
                        else:
                            payload["renpy_condition"] = option.condition
                            warnings.append(
                                f"Choice '{option.text}' in label '{label_name}' kept unsupported condition '{option.condition}' as metadata only ({error})."
                            )
                    choices.append(payload)
                identifier = node_id(label_name, node_counter)
                node_counter += 1
                nodes[identifier] = {
                    "speaker": "",
                    "text": statement.prompt or "Choose:",
                    "choices": choices,
                }
                current_next = identifier
                continue
            if isinstance(statement, DialogueStatement):
                identifier = node_id(label_name, node_counter)
                node_counter += 1
                payload: Dict[str, Any] = {
                    "speaker": parsed.characters.get(statement.speaker_alias, statement.speaker_alias),
                    "text": statement.text,
                }
                if current_next:
                    payload["next"] = current_next
                nodes[identifier] = payload
                current_next = identifier
        return current_next

    label_entries: Dict[str, Optional[str]] = {}
    for label_name in parsed.label_order:
        label_entries[label_name] = build_block(parsed.labels.get(label_name, []), None, label_name)

    for index in range(len(parsed.label_order) - 1, -1, -1):
        label_name = parsed.label_order[index]
        if label_entries[label_name]:
            continue
        next_label = parsed.label_order[index + 1] if index + 1 < len(parsed.label_order) else ""
        label_entries[label_name] = label_ref(next_label) if next_label else None

    def resolve_target(target: Optional[str]) -> Optional[str]:
        current = target
        visited: set[str] = set()
        while current and current.startswith("@label:"):
            label_name = current.split(":", 1)[1]
            if label_name in visited:
                return None
            visited.add(label_name)
            current = label_entries.get(label_name)
        return current

    for payload in nodes.values():
        if "next" in payload:
            resolved = resolve_target(str(payload.get("next") or ""))
            if resolved:
                payload["next"] = resolved
            else:
                payload.pop("next", None)
        for choice in payload.get("choices") or []:
            if "next" in choice:
                resolved = resolve_target(str(choice.get("next") or ""))
                if resolved:
                    choice["next"] = resolved
                else:
                    choice.pop("next", None)

    start_node = resolve_target(label_entries.get(parsed.entry_label))
    if not start_node:
        fallback = next((value for value in label_entries.values() if resolve_target(value)), "")
        start_node = resolve_target(fallback)

    cast: Dict[str, Dict[str, Any]] = {}
    for alias, speaker in parsed.characters.items():
        cast[str(speaker)] = {"renpy_alias": alias}

    conversation: Dict[str, Any] = {
        "start": start_node or "",
        "cast": cast,
        "nodes": nodes,
        "metadata": {
            "importer": "renpy_subset_plus_stage",
            "entry_label": parsed.entry_label,
            "labels": list(parsed.label_order),
        },
    }
    if parsed.initial_effects:
        conversation["effects_on_start"] = dict(parsed.initial_effects)

    return {
        "conversation_id": parsed.conversation_id,
        "conversation": conversation,
        "warnings": warnings,
    }


def _renpy_stage_node_payloads() -> list[Dict[str, Any]]:
    return [
        {
            "name": "RenPyBackground",
            "type": "UI",
            "tags": ["renpy_stage", "renpy_background"],
            "metadata": {"renpy_slot": "background", "layer": "background"},
            "components": [
                {"type": "Transform", "position": [0, 0, -40]},
                {
                    "type": "UIControl",
                    "anchor_left": 0.0,
                    "anchor_top": 0.0,
                    "anchor_right": 1.0,
                    "anchor_bottom": 1.0,
                    "min_size": [1280, 720],
                    "visible": False,
                },
                {"type": "Image", "texture": "", "stretch_mode": "cover"},
            ],
            "children": [],
        },
        {
            "name": "RenPyCharacterLeft",
            "type": "UI",
            "tags": ["renpy_stage", "renpy_character"],
            "metadata": {"renpy_slot": "left", "layer": "characters"},
            "components": [
                {"type": "Transform", "position": [0, 0, -20]},
                {
                    "type": "UIControl",
                    "anchor_left": 0.02,
                    "anchor_top": 0.05,
                    "anchor_right": 0.36,
                    "anchor_bottom": 0.82,
                    "min_size": [320, 540],
                    "visible": False,
                },
                {"type": "Image", "texture": "", "stretch_mode": "fit"},
            ],
            "children": [],
        },
        {
            "name": "RenPyCharacterCenter",
            "type": "UI",
            "tags": ["renpy_stage", "renpy_character"],
            "metadata": {"renpy_slot": "center", "layer": "characters"},
            "components": [
                {"type": "Transform", "position": [0, 0, -18]},
                {
                    "type": "UIControl",
                    "anchor_left": 0.24,
                    "anchor_top": 0.04,
                    "anchor_right": 0.76,
                    "anchor_bottom": 0.84,
                    "min_size": [480, 600],
                    "visible": False,
                },
                {"type": "Image", "texture": "", "stretch_mode": "fit"},
            ],
            "children": [],
        },
        {
            "name": "RenPyCharacterRight",
            "type": "UI",
            "tags": ["renpy_stage", "renpy_character"],
            "metadata": {"renpy_slot": "right", "layer": "characters"},
            "components": [
                {"type": "Transform", "position": [0, 0, -16]},
                {
                    "type": "UIControl",
                    "anchor_left": 0.64,
                    "anchor_top": 0.05,
                    "anchor_right": 0.98,
                    "anchor_bottom": 0.82,
                    "min_size": [320, 540],
                    "visible": False,
                },
                {"type": "Image", "texture": "", "stretch_mode": "fit"},
            ],
            "children": [],
        },
    ]


def _ensure_renpy_stage_scene(scene_payload: Dict[str, Any]) -> bool:
    children = [dict(child) for child in list(scene_payload.get("children") or []) if isinstance(child, dict)]
    existing_names = {str(child.get("name") or "") for child in children}
    missing = [node for node in _renpy_stage_node_payloads() if node["name"] not in existing_names]
    if not missing:
        return False
    scene_payload["children"] = missing + children
    return True


def import_renpy_script(
    project_root: str | Path,
    script_path: str | Path,
    *,
    conversation_id: str = "",
    entry_label: str = "",
    autostart: bool = False,
    overwrite: bool = True,
) -> Dict[str, Any]:
    project_root = Path(project_root).resolve()
    source_path = Path(script_path).expanduser()
    if not source_path.is_absolute():
        relative_source = source_path
        candidates = [
            (project_root / relative_source).resolve(),
            (Path.cwd() / relative_source).resolve(),
        ]
        source_path = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
    if not source_path.exists():
        raise FileNotFoundError(f"Ren'Py script not found: {source_path}")

    parsed = parse_renpy_script(
        source_path.read_text(encoding="utf-8"),
        conversation_id=conversation_id or source_path.stem,
        entry_label=entry_label,
    )
    compiled = compile_renpy_script(parsed)
    dialogue_path = project_root / "data/content/dialogue.yaml"
    dialogue_path.parent.mkdir(parents=True, exist_ok=True)

    existing_payload: Dict[str, Any] = {}
    if dialogue_path.exists():
        existing_payload = yaml.safe_load(dialogue_path.read_text(encoding="utf-8")) or {}
    conversations = dict(existing_payload.get("conversations") or {})
    if compiled["conversation_id"] in conversations and not overwrite:
        raise FileExistsError(f"Conversation already exists: {compiled['conversation_id']}")
    conversations[compiled["conversation_id"]] = compiled["conversation"]
    payload = dict(existing_payload)
    payload["conversations"] = conversations
    dialogue_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")

    scene_path = project_root / "data/scenes/main.relscene.json"
    autostart_updated = False
    stage_scene_updated = False
    if scene_path.exists():
        scene_payload = json.loads(scene_path.read_text(encoding="utf-8"))
        if autostart:
            metadata = dict(scene_payload.get("metadata") or {})
            metadata["autostart_conversation"] = compiled["conversation_id"]
            scene_payload["metadata"] = metadata
            autostart_updated = True
        stage_scene_updated = _ensure_renpy_stage_scene(scene_payload)
        if autostart_updated or stage_scene_updated:
            scene_path.write_text(json.dumps(scene_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    conversation = compiled["conversation"]
    return {
        "source_path": str(source_path),
        "dialogue_path": str(dialogue_path),
        "conversation_id": compiled["conversation_id"],
        "entry_label": parsed.entry_label,
        "start_node": conversation.get("start", ""),
        "node_count": len(conversation.get("nodes") or {}),
        "warning_count": len(compiled["warnings"]),
        "warnings": compiled["warnings"],
        "autostart_updated": autostart_updated,
        "stage_scene_updated": stage_scene_updated,
    }


__all__ = [
    "ParsedRenPyScript",
    "compile_renpy_script",
    "import_renpy_script",
    "parse_renpy_script",
]

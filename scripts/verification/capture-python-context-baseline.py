"""Capture the archived Python baseline, after each unchanged native query.

This audit runner imports the frozen 2.5.5 source only. It is not part of the
Rust application's runtime or build. Thirty trials use fresh retrievers, keep
the native result order, and preserve the complete returned text for audit.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
parser = argparse.ArgumentParser()
parser.add_argument("--labels", type=Path)
parser.add_argument("--query", default="returned_image_pixels coordinates scale crop")
parser.add_argument("--query-id")
parser.add_argument("--trials", type=int, default=30)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = Path.cwd()
if args.trials < 1 or args.output.exists() or args.output.parent.exists():
    parser.error("Use a new output directory and a positive trial count")
if not args.output.resolve().is_relative_to((root / ".runtime").resolve()):
    parser.error("Keep baseline output inside the project's .runtime directory")
args.output.parent.mkdir(parents=True)
corpus = root / ".runtime/phase0B/corpus"
manifest_path = root / "testdata/context-evaluation/frozen-corpus-v1.json"
manifest_bytes = manifest_path.read_bytes()
manifest = json.loads(manifest_bytes)
provenance = {}
for info in manifest["files"]:
    raw = (corpus / info["repo_relative_path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != info["working_tree_sha256"]:
        raise RuntimeError("Frozen corpus changed: " + info["repo_relative_path"])
    canonical = raw.replace(b"\r\n", b"\n") if info.get("checkout_transform") else raw
    if hashlib.sha256(canonical).hexdigest() != info["file_sha256"]:
        raise RuntimeError("Canonical source changed")
    try:
        text = canonical.decode("utf-8")
    except UnicodeDecodeError:
        continue
    provenance[info["repo_relative_path"]] = {**info, "lines": text.splitlines()}

sys.path.insert(0, str(corpus / "ReverieCli-py"))
from reverie.context_engine.factory import create_indexer
from reverie.context_engine.retriever import ContextRetriever
from reverie.context_engine.symbol_table import Symbol
import reverie

indexer = create_indexer(corpus, root / ".runtime/phase0B/baseline/index-pilot")
if not indexer.load_cache():
    raise RuntimeError("Frozen complete source index unavailable")

def retriever():
    return ContextRetriever(indexer.symbol_table, indexer.dependency_graph, corpus,
        file_info=indexer._file_info, content_searcher=indexer.search_content_terms,
        chunk_searcher=indexer.search_code_chunks)

observed_symbols, observed_trims = [], []
original_symbol = Symbol.get_context_string
marker = "\n# ... excerpt truncated to token budget ...\n"

def relative(value):
    return str(Path(value).resolve().relative_to(corpus.resolve())).replace("\\", "/")

def source_rows(text, source_start, native_offset, file_info):
    rows, position = [], native_offset
    for index, value in enumerate(text.split("\n")):
        line_number = source_start + index
        expected = file_info["lines"][line_number - 1]
        if expected.rstrip() != value.rstrip():
            if index == 0 and expected.lstrip().rstrip() == value.lstrip().rstrip():
                position += len(value) + 1
                continue  # A node that starts after indentation does not return a complete first line.
            raise RuntimeError(f"Unproven native source line: {file_info['repo_relative_path']}:{line_number}")
        rows.append({"source_line": line_number, "start": position,
                     "end": position + len(value.rstrip())})
        position += len(value) + 1
    return rows

def observe_symbol(self, *positional, **keywords):
    result = original_symbol(self, *positional, **keywords)
    include = keywords.get("include_source", positional[0] if positional else True)
    limit = max(8, int(keywords.get("max_lines", positional[1] if len(positional) > 1 else 50) or 50))
    if include and self.source_code:
        name = relative(self.file_path)
        source = self.source_code.splitlines()
        chunks = [(0, source)]
        if len(source) > limit:
            head_count, tail_count = max(5, limit * 3 // 4), max(3, limit - max(5, limit * 3 // 4))
            omitted = len(source) - head_count - tail_count
            gap = f"# ... {omitted} lines omitted ..."
            rendered = "\n".join(source[:head_count] + [gap] + source[-tail_count:])
            tail_offset = len("\n".join(source[:head_count])) + len(gap) + 2
            chunks = [(0, source[:head_count]), (tail_offset, source[-tail_count:])]
            source_starts = [self.start_line, self.start_line + len(source) - tail_count]
        else:
            rendered = "\n".join(source)
            source_starts = [self.start_line]
        body_position = result.rfind(rendered)
        if body_position < 0:
            raise RuntimeError("Cannot prove native source rendering")
        pieces = []
        for (offset, chunk), start_line in zip(chunks, source_starts):
            pieces.append(source_rows("\n".join(chunk), start_line, body_position + offset, provenance[name]))
        observed_symbols.append({"path": name, "block": result.rstrip(), "pieces": pieces})
    return result

def map_actual_trim(excerpt, output):
    text = str(excerpt or "").strip()
    if output == text:
        segments = [(0, len(text), 0)]
    elif marker in output:
        head, tail = output.split(marker, 1)
        if not text.startswith(head) or (tail and not text.endswith(tail)):
            raise RuntimeError("Unproven native prefix/suffix trimming")
        segments = [(0, len(head), 0)]
        if tail:
            segments.append((len(text) - len(tail), len(text), len(head) + len(marker)))
    else:
        if not text.startswith(output):
            raise RuntimeError("Unproven native prefix trimming")
        segments = [(0, len(output), 0)]
    observed_trims.append({"input": text, "output": output, "segments": segments})
    return output

def capture(context):
    actual = context.context_string
    fragments = []
    curated_start = actual.find("--- CURATED EXCERPTS ---")
    if curated_start < 0:
        return fragments
    headings = []
    for item in context.relevant_files:
        display = str(Path(item.file_path).resolve().relative_to(corpus.resolve()))
        position = actual.find("### " + display + "\n", curated_start)
        if position >= 0:
            headings.append((position, item))
    headings.sort(key=lambda value: value[0])

    def append_fragment(name, rows, base, render_format):
        if not rows:
            return
        first, last = rows[0], rows[-1]
        start, end = base + first["start"], base + last["end"]
        if end <= start:
            return
        info = provenance[name]
        rendered = actual[start:end]
        if len(rendered.splitlines()) != last["source_line"] - first["source_line"] + 1:
            raise RuntimeError("Missing native source line in actual returned fragment")
        fragments.append({"repo_relative_path": name, "source_commit": info["source_commit"],
            "blob_sha1": info["blob_sha1"], "file_sha256": info["file_sha256"],
            "start_line": first["source_line"], "end_line": last["source_line"],
            "rendered_text": rendered, "render_format": render_format,
            "context_start_byte": len(actual[:start].encode("utf-8")),
            "context_end_byte": len(actual[:end].encode("utf-8"))})

    for index, (section_start, item) in enumerate(headings):
        section_end = headings[index + 1][0] if index + 1 < len(headings) else len(actual)
        name = relative(item.file_path)
        section = actual[section_start:section_end]
        file_symbols = [symbol for symbol in context.relevant_symbols
                        if relative(symbol.file_path) == name][:2]
        for symbol_index, symbol in enumerate(file_symbols):
            observe_symbol(symbol, include_source=symbol_index == 0, max_lines=72)
        opening = f"```{item.language or ''}\n"
        opening_start = section.find(opening)
        closing_start = section.rfind("\n```")
        if opening_start >= 0 and closing_start >= opening_start + len(opening):
            map_actual_trim(item.excerpt, section[opening_start + len(opening):closing_start])
        trims = [value for value in observed_trims if value["input"] == item.excerpt.strip()]
        for trim in trims[-1:]:
            if not trim["output"]:
                continue
            output_start = section.find(trim["output"])
            if output_start < 0:
                continue  # Native metadata-only fallback did not return the excerpt.
            base = section_start + output_start
            raw_parts = []
            for symbol in observed_symbols:
                if symbol["path"] != name:
                    continue
                block_start = trim["input"].find(symbol["block"])
                if block_start >= 0:
                    raw_parts.extend([[{**row, "start": block_start + row["start"],
                        "end": block_start + row["end"]} for row in piece] for piece in symbol["pieces"]])
            fallback = "\n".join(provenance[name]["lines"][:40]).strip()
            if not raw_parts and trim["input"] == fallback:
                original_prefix = "\n".join(provenance[name]["lines"][:40])
                bias = len(original_prefix) - len(original_prefix.lstrip())
                rows = source_rows(original_prefix, 1, -bias, provenance[name])
                raw_parts.append([row for row in rows if row["start"] >= 0])
            for piece in raw_parts:
                for begin, end, output_offset in trim["segments"]:
                    rows = [{**row, "start": row["start"] - begin + output_offset,
                             "end": row["end"] - begin + output_offset}
                            for row in piece if row["start"] >= begin and row["end"] <= end]
                    if rows:
                        append_fragment(name, rows, base, "raw_lines")

        position, numbered, expected = 0, [], None
        for line in section.splitlines(keepends=True):
            clean = line.rstrip("\r\n")
            header = re.fullmatch(r"# (?:Evidence lines|lines) (\d+)-(\d+)", clean)
            match = re.fullmatch(r"\s*(\d+) \| (.*)", clean) if expected is not None else None
            if header:
                append_fragment(name, numbered, section_start, "numbered_lines")
                numbered, expected = [], int(header[1])
            elif match and int(match[1]) == expected:
                if match[2].rstrip() != provenance[name]["lines"][expected - 1].rstrip():
                    raise RuntimeError(f"Unproven numbered source: {name}:{expected}")
                numbered.append({"source_line": expected, "start": position, "end": position + len(clean)})
                expected += 1
            else:
                append_fragment(name, numbered, section_start, "numbered_lines")
                numbered, expected = [], None
            position += len(line)
        append_fragment(name, numbered, section_start, "numbered_lines")
    fragments.sort(key=lambda value: value["context_start_byte"])
    return fragments

labels_bytes = args.labels.read_bytes() if args.labels else None
labels = json.loads(labels_bytes) if labels_bytes else None
if labels and labels["status"] != "frozen_after_independent_cross_review":
    raise RuntimeError("Acceptance labels must be frozen before observation")
queries = labels["queries"] if labels else [{"id": "development", "query": args.query}]
if args.query_id:
    queries = [query for query in queries if query["id"] == args.query_id]
    if len(queries) != 1:
        raise RuntimeError("Requested diagnostic query unavailable")
records = []
raw_path = args.output.with_suffix(".jsonl")
raw_output = raw_path.open("x", encoding="utf-8")
try:
    for trial, query in itertools.product(range(1, args.trials + 1), queries):
        observed_symbols.clear()
        observed_trims.clear()
        started = time.perf_counter_ns()
        result = retriever().retrieve_for_task(query["query"], max_tokens=12000)
        elapsed = (time.perf_counter_ns() - started) / 1e6
        original_context_hash = hashlib.sha256(result.context_string.encode("utf-8")).hexdigest()
        record = {"query_id": query["id"], "trial": trial, "context_string": result.context_string,
            "fragments": capture(result), "scope": "frozen source API output; final package route separate",
            "native_query_unmodified": True, "capture_runs_after_query": True, "native_query_ms": elapsed,
            "context_sha256": original_context_hash,
            "native_token_estimate": result.token_estimate}
        if hashlib.sha256(record["context_string"].encode("utf-8")).hexdigest() != original_context_hash:
            raise RuntimeError("Capture changed returned context bytes")
        records.append(record)
        raw_output.write(json.dumps(record, ensure_ascii=False) + "\n")
        raw_output.flush()
        args.output.with_suffix(".progress.json").write_text(json.dumps({
            "completed_observations": len(records), "expected_observations": args.trials * len(queries),
            "last_query": query["id"], "last_trial": trial, "complete": False,
        }, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"query": query["id"], "trial": trial, "fragments": len(record["fragments"]),
            "characters": len(result.context_string), "estimated_tokens": result.token_estimate,
            "native_query_unmodified": True, "captured_bytes_unchanged": True}), flush=True)
finally:
    raw_output.close()
    indexer.close()
args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
args.output.with_suffix(".identity.json").write_text(json.dumps({"version": reverie.__version__,
    "source_commit": manifest["source_commit"], "max_workers": indexer.config.max_workers,
    "labels_sha256": hashlib.sha256(labels_bytes).hexdigest() if labels_bytes else None,
    "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "trials_per_query": args.trials,
    "complete_frozen_set": bool(labels and len(queries) == len(labels["queries"]) and len(records) == args.trials * len(queries)),
    "formal_repeated_measurement": bool(labels and args.trials == 30 and len(queries) == len(labels["queries"])),
    "raw_jsonl_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
    "source_files_unchanged": True, "queries": len(records), "captured_bytes_unchanged": True,
    "scores_computed": False}, indent=2) + "\n", encoding="utf-8")

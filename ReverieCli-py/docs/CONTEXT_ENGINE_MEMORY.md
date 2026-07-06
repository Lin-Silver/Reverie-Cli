# Context Engine Project Memory

Reverie gives every project an isolated persistent memory database under the app data root:

```text
.reverie/projects/<portable-project-id>/memory/
├── events.jsonl
└── memory.sqlite3
```

The event log is append-only evidence. `memory.sqlite3` is the searchable structured layer. It uses SQLite WAL transactions and FTS5, so a committed memory is searchable immediately without a background embedding or extraction job. Existing `memory_items.json` records are imported automatically the first time the database opens.

## Memory model

The system supports the Memanto-style categories `instruction`, `fact`, `decision`, `goal`, `commitment`, `preference`, `relationship`, `context`, `event`, `learning`, `observation`, `artifact`, and `error`, plus Reverie's established workflow-specific categories.

Every record carries confidence, provenance, source, evidence event ids, version, validity interval, access history, tags, and optional topic metadata. Corrections create a new version. Explicit `supersedes` links close the previous record's validity interval. Likely contradictions are reported as conflicts and are never silently overwritten.

Common credentials and user-home identifiers are redacted before structured-memory persistence.

## Retrieval

Recall fuses these signals in one local query:

- SQLite FTS5/BM25 rank;
- identifier and CJK bigram token overlap;
- character n-gram similarity for spelling variation;
- exact phrase, type, scope, confidence, recency, decay, and access signals;
- MMR-style result diversification;
- optional type, scope, confidence, `as_of`, and `changed_since` filters.

Reverie injects a bounded retrieved memory package into each model request. The primary `codebase-retrieval` Context Engine tool also includes project memory for task and memory queries.

## Agent tools

- `memory_manager(action="remember", ...)` stores a durable typed record.
- `memory_retrieval(action="recall", query="...")` returns ranked evidence.
- `memory_retrieval(action="answer", query="...")` returns an extractive answer with source records.
- `memory_manager(action="conflicts")` lists unresolved contradictions.
- `memory_manager(action="correct", ...)` creates a corrected version.
- `memory_manager(action="status")` reports database, FTS5, isolation, and record state.

The system prompt directs the agent to recall proactively for continuation, previous decisions, preferences, and failed workflows, and to remember explicit durable information and verified reusable learnings. Current repository evidence always outranks stored memory.

## Design reference

This design was informed by [moorcheh-ai/memanto](https://github.com/moorcheh-ai/memanto), including its remember/recall/answer primitives, typed memory, provenance, temporal retrieval, conflict handling, and immediate-search principles. Memanto is MIT licensed. Reverie uses its own project-local implementation and does not require the Moorcheh service, Docker, a vector database, or an API key.

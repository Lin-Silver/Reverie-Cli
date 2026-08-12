# Context Engine Retrieval Results

On 2026-07-18, the Context Engine was evaluated locally as a file-localization system using real SWE-bench Lite issue statements and patch files. The benchmark environment, dataset, repository snapshots, caches, and raw results are intentionally not versioned.

| Evaluation | Instances | Recall@5 | Recall@10 | MRR@10 | Query p50 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Broader cross-repository validation | 23 | 0.522 | 0.609 | 0.351 | 245 ms |
| Frozen unseen subset, original `main` | 7 | 0.429 | 0.429 | 0.226 | 598 ms |
| Frozen unseen subset, optimized | 7 | 0.714 | 0.857 | 0.354 | 245 ms |

The seven unseen cases were held back until the retrieval changes were frozen, so they test generalization rather than case-specific rules. The sample is still small: these figures are a development result, not a universal-performance claim, and full release qualification requires all 300 instances plus broader cross-language tasks.

## 2026-07-21 — Corpus-absent query-expansion filtering

Failure analysis of a 284-instance partial run (Recall@1 0.472, Recall@5 0.736, Recall@10 0.803, MRR@10 0.584, nDCG@10 0.637) showed the dominant miss pattern was query-term fabrication rather than a retrieval-channel gap. Two query-expansion heuristics were synthesising terms that name nothing in the codebase, and because a zero-body term receives the rare-term IDF bonus, those fabrications rose to the top of the weighted term list and displaced the real query signal:

* **Joined prose compounds** — every adjacent word pair was concatenated (`"undefined expression"` → `undefinedexpression`, `"feature request"` → `featurerequest`). The heuristic exists to recover split names such as `"auto detector"` → `autodetector`, but most pairs are noise.
* **Reproduction-snippet dotted fragments** — local-variable method calls lifted from issue repros (`r.limit`, `e.subs`, `publication.objects`) were weighted as stable identifiers.

The fix filters both against the corpus: a compound is kept only when it has non-zero content document frequency or is a substring of a real symbol/file name, and a dotted fragment is dropped when its content document frequency is zero (its already-emitted attribute suffix is retained). A query term that resolves to nothing in the index is noise by definition, so this is a general information-retrieval correction, not benchmark tuning. It adds no runtime dependency, reuses the existing FTS content-frequency lookup, and leaves indexing cost unchanged.

Held-out profiles (indices rebuilt per instance), before → after the filter:

| Profile | Instances | Recall@1 | Recall@5 | Recall@10 | MRR@10 | nDCG@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Holdout | 12 | 0.67 → 0.67 | 0.92 → 1.00 | 0.92 → 1.00 | 0.75 → 0.79 | 0.79 → 0.85 |
| Blind | 9 | 0.56 → 0.67 | 0.67 → 0.89 | 0.89 → 1.00 | 0.62 → 0.77 | 0.68 → 0.83 |
| Generalization | 10 | 0.40 → 0.50 | 0.50 → 0.60 | 0.60 → 0.60 | 0.47 → 0.52 | 0.50 → 0.54 |

Every profile improved or held with no regression. A separate, pre-existing robustness item remains open: a file that is the top hit in the strongest lexical channel can still jitter in and out of the top ten across parallel index builds, because parallel parsing does not fix symbol ordering and the fusion tie-break depends on it. That is a ranking-stability question rather than a term-quality one and is deferred.

## 2026-07-22 — Deterministic parallel indexing (resolves the deferred stability item)

Investigating the ranking jitter noted above revealed that it was the visible symptom of a deeper, more serious defect: **parallel indexing was not deterministic and, worse, not correct**. Building the same tree three times with `max_workers=8` produced different symbol counts each run (e.g. 1108 / 1109 / 1110), whole modules' symbols appearing and disappearing between runs, while the indexer still reported every file parsed with zero failures. A serial (`max_workers=1`) build was already stable.

Two independent causes were found and fixed:

* **Shared stateful parsers (data corruption).** A single set of parser instances was shared across every worker thread. Parsers keep per-parse state on the instance (`PythonParser` stores the current file's content, line list, and module name; `TreeSitterParser` holds a live parse cache), so two threads parsing different files at once clobbered each other — dropping and misattributing symbols. Each worker thread now builds and reuses its own parser pipeline via a thread-local, so at most `max_workers` pipelines exist and no instance is ever touched by two threads. This restores correctness: a parallel build now extracts *exactly* the same symbols as a serial build.

* **Insertion-order-dependent index state (ordering jitter).** Symbols and dependency edges were merged in thread-completion order, so `SymbolTable._symbols` and the dependency adjacency lists carried a nondeterministic order into lookups. Read paths that pick the first match (`find_by_name`/`find_by_pattern`/`find_by_prefix`/`get_by_kind`) and the serialized cache therefore varied run to run — and the first `find_by_name` result is the ranking *anchor*, the heaviest fusion channel. The index state is now canonicalized by qualified name when it is committed (`SymbolTable.replace_with`, `DependencyGraph.replace_with`), and the lookup methods sort before truncating, so both the ordering and the truncated membership are stable.

After both fixes, five consecutive 8-worker builds of the Context Engine package produced an identical symbol list (1112 symbols), an identical dependency graph, and output byte-identical to the serial build. The retrieval and ranking logic was not touched; this is purely an indexing-layer correctness and determinism fix. Regression tests assert (a) insertion-order independence of the symbol table and dependency graph and (b) that a parallel `full_index` matches a serial one and repeats exactly across runs.

With this in place the ranking-stability item deferred on 2026-07-21 is resolved at its source: the top lexical-channel hit no longer jitters, because the index it is derived from is now reproducible.

## 2026-08-10 — Index/query analysis symmetry for compound identifiers

Studying [`alibaba/zvec`](https://github.com/alibaba/zvec), whose full-text stack models analysis as an explicit *pipeline* (tokenizer → token filters, run identically at index and query time), surfaced a structural asymmetry in this engine: the two sides did not agree on what a token was.

SQLite FTS5's `porter unicode61` splits on underscores but stores `ModelAdmin` as the single opaque token `modeladmin`. The retriever's query tokenizer, however, *does* split camel case. The consequence was silent and total: a query for `model`, `admin`, `user`, or `name` returned **zero** hits against a file defining `ModelAdmin.getUserName`. One Django worktree contains 6,369 distinct camelCase identifiers across 80,382 occurrences — and Django is snake_case-dominant, so camel-heavy ecosystems (JavaScript/TypeScript, Java, Go) lose substantially more.

The fix supplies the missing token-filter half of the pipeline (`context_engine/text_analysis.py`) and indexes its output in a dedicated `subwords` column on both `content_search` and `chunk_search`. Three design choices matter:

* **A separate column rather than appending to `body`.** Inlining the expansion would inflate the primary field's term frequencies and document lengths, corrupting BM25 for the original spellings. A distinct column is independently weighted (`bm25(content_search, 1.0, 0.35)`; `bm25(chunk_search, 5.5, 3.0, 1.8, 1.0, 0.6)`) so an exact match on the full identifier always outranks a sub-token match.
* **One entry per distinct sub-token per document, not per occurrence.** The goal is to make a term *reachable*; frequency signal stays with the text as written. Index growth measured on Django: **1.4%**. Per-occurrence emission would have roughly doubled it.
* **No snake_case expansion.** `unicode61` already splits underscores, so expanding it would double the vocabulary for no recall gain.

A `PRAGMA user_version` schema guard discards caches written before the new column, which would otherwise be appended to with mismatched column arity.

**The instructive part of this change was a regression it initially caused.** `content_document_frequencies()` issued its `MATCH` unscoped, so the new column immediately began contributing to document frequency: every `*Admin` symbol donated an `admin` posting, making precisely the discriminative terms look common and stripping them of the rare-term IDF bonus. This re-created, through a new door, the exact defect corrected on 2026-07-20. Holdout fell to Recall@1 0.583 / nDCG 0.804. Scoping the frequency query to `body` restored and slightly exceeded the baseline. The general rule, now covered by a regression test: **an expansion column may broaden reachability, but must never enter term statistics.**

Held-out profiles (indices rebuilt per instance), baseline → final:

| Profile | Instances | Recall@1 | Recall@5 | Recall@10 | MRR@10 | nDCG@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Holdout | 12 | 0.67 → 0.67 | 1.00 → 1.00 | 1.00 → 1.00 | 0.781 → 0.794 | 0.835 → 0.846 |
| Generalization | 10 | 0.50 → 0.50 | 0.60 → 0.60 | 0.60 → 0.60 | 0.520 → 0.520 | 0.539 → 0.539 |
| Blind | 9 | 0.56 → 0.56 | 1.00 → 1.00 | 1.00 → 1.00 | 0.731 → 0.713 | 0.799 → 0.785 |

Holdout improves; generalization is unchanged to the last digit; blind loses one instance from rank 2 to rank 3 (the ΔMRR of 1/54 is exactly (1/2 − 1/3)/9). The honest reading of a ±1-instance movement on a 9-instance profile is noise, not signal — these sets are too small for a single rank shift to carry meaning. The change is justified by the mechanism it corrects, which is a genuine recall hole on camel-cased code that these Python-dominated profiles are poorly positioned to measure.

**One candidate change was tested and rejected.** Replacing the counter in `_score_file_content_for_task` with textbook BM25 saturation and length normalization produced *bit-identical* results across all 35 tuning instances (`quick` n=12, `validation` n=23 — every metric equal to the last digit). That function is not a retrieval channel: it re-scores the top-32 candidates already selected by the FTS channels, so it can reorder a shortlist but never change its membership. It was reverted rather than kept as unmeasurable complexity. One real defect found inside it was kept: the scoring loop terminated once it had collected four *reasons*, silently abandoning every remaining query term.

### The schema guard was itself a bug

The `PRAGMA user_version` guard above was written to drop and rebuild an incompatible index. Checking where it actually fires showed that this was backwards. `_begin_content_index_rebuild` unlinks its target and builds into a fresh temporary file, so `user_version` is always 0 there and the drop branch never runs. The only caller that can reach it is `_begin_content_index_update` — the *incremental* path, which opens the existing database and then rewrites **only the files it was handed**. Dropping the tables there discards every unchanged file's postings and re-inserts a handful, while `incremental_index` still reports success.

A three-file reproduction reduced the content index to the single changed file. The condition needed to hit this is ordinary: upgrade the build, edit one file, and let the watcher fire before any full re-index. Search then silently misses most of the repository, with no error and a valid-looking cache on disk.

The guard now distinguishes the two callers. A rebuild may discard, an in-place update raises `OutdatedContentIndexError` and leaves the old database untouched and readable; `incremental_index`'s existing handler catches it and skips content indexing for that pass, because both write helpers are already no-ops when the connection is `None`. `CacheManager.CACHE_VERSION` moves to `1.11.0` in the same change, which is what forces the full rebuild that legitimately replaces the layout — the two counters have to move together, since nothing re-indexes while the JSON cache still validates.

The prior regression test asserted the drop-and-recreate behaviour, so it encoded the bug as expected output. It passed only because its fixture held one file, making the loss invisible. It is replaced by a multi-file test that fails against the old behaviour on the reachability assertion, plus a test pinning the `CACHE_VERSION` rejection. Holdout is unchanged at Recall@1 0.667 / MRR 0.794 / nDCG 0.846 — bit-identical to the pre-fix run, as expected for a fix on a path the benchmark's rebuilt-per-instance indices never take.

The general lesson is the same one the DF regression taught, in a different register: a guard is only correct relative to the caller that reaches it, so it is worth checking which callers actually can. Here the branch that looked like the safety mechanism was unreachable from the safe caller and destructive from the unsafe one.


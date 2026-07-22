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


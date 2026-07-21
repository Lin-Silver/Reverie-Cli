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


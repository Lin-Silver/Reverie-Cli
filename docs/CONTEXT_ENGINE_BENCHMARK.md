# Context Engine Retrieval Results

On 2026-07-18, the Context Engine was evaluated locally as a file-localization system using real SWE-bench Lite issue statements and patch files. The benchmark environment, dataset, repository snapshots, caches, and raw results are intentionally not versioned.

| Evaluation | Instances | Recall@5 | Recall@10 | MRR@10 | Query p50 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Broader cross-repository validation | 23 | 0.522 | 0.609 | 0.351 | 245 ms |
| Frozen unseen subset, original `main` | 7 | 0.429 | 0.429 | 0.226 | 598 ms |
| Frozen unseen subset, optimized | 7 | 0.714 | 0.857 | 0.354 | 245 ms |

The seven unseen cases were held back until the retrieval changes were frozen, so they test generalization rather than case-specific rules. The sample is still small: these figures are a development result, not a universal-performance claim, and full release qualification requires all 300 instances plus broader cross-language tasks.

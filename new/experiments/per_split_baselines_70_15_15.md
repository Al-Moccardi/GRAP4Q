# Per-split offline baselines (QChecker + Rule-APR)

Split source: `experiments/splits_70_15_15.json`

## Aggregate summary

| Split | N | QChecker detection rate | Rule-APR fire rate | Rule-APR mean Lines-F1 |
|---|---:|---:|---:|---:|
| TRAIN | 29 | 41.38% | 34.48% | 0.0164 |
| VAL | 6 | 66.67% | 33.33% | 0.0000 |
| TEST | 7 | 42.86% | 57.14% | 0.2562 |

- **Detection rate** = fraction of cases where QChecker flags ≥1 bug pattern.
- **Fire rate** = fraction where at least one Rule-APR rewrite rule applied.
- **Mean Lines-F1** = per-case paper metric, averaged across the split.

## Interpretation

QChecker alone covers a substantial slice of Bugs4Q as pure static patterns; Rule-APR further repairs a subset of those. Cases flagged by QChecker but not repaired by Rule-APR are the natural territory for an LLM-based patcher such as GRAP-Q — which supports the paper's thesis that retrieval + guardrails are needed beyond what classical static analysis / rule APR can achieve.
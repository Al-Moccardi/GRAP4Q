# Dataset analysis — overview

- **Total cases analyzed**: 42
- **Split source**: `splits_70_15_15.json`
- **Split breakdown**: test=7, train=29, val=6
- **Groups**: Aer (3), Cirq (7), StackExchange (17), StackExchange_2 (2), Terra-0-4000 (7), Terra-4001-6000 (3), stackoverflow-6-10 (3)

> **Note on the count.** The 42-case set is the canonical Python subset
> yielded by `src/dataset.py::iter_cases()` on any OS. On a case-
> insensitive filesystem, a naïve discovery rule would pick up 5 extra
> folders; these are listed in `PAPER_EXCLUDED_CASES` and filtered out
> by default. See [`docs/dataset_scope.md`](../../docs/dataset_scope.md)
> for the full accounting.

## What's in this folder

| File | Contents |
|---|---|
| `all_cases.csv` | One row per case with every field from the analysis |
| `all_cases.json` | Same data, richer structure (includes full source code) |
| `per_split_summary.md` | Aggregates by train/val/test split |
| `per_group_summary.md` | Aggregates by Bugs4Q group (Aer/Cirq/Terra/…) |
| `bug_patterns_breakdown.md` | Which QChecker rules hit which cases |
| `rule_apr_effectiveness.md` | Where Rule-APR succeeds/fails, with per-case F1 |
| `case_details/<case>.md` | One file per case: buggy + fixed + diff + analysis |

## Headline numbers

- Mean lines changed between buggy and fixed: **6.1**
- QChecker detection rate (case has ≥1 static finding): **45.2%**
- Rule-APR fire rate (case triggers ≥1 rewrite rule): **38.1%**
- Rule-APR mean Lines-F1 across all cases: **0.0541**

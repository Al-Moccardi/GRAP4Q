# Baseline comparison on validation set

**N cases**: 12

## Summary (mean Lines-F1, higher is better)

| Method | Mean Lines-F1 | Notes |
|---|---:|---|
| **GRAP-Q** (ours) | **0.2450** | retrieval-augmented, guardrailed, LLM patcher |
| Pure-LLM | 0.1722 | qwen2.5-coder:14b, no retrieval, no guardrails |
| Rule-based APR | 0.0000 | 7 deterministic Qiskit-migration rules, no LLM |
| QChecker (detector) | n/a | bug-detection rate: 50.00% of cases |

*Rule-based APR and QChecker are offline, LLM-free baselines. Rule-APR produces patches; QChecker flags suspect code but does not repair.*

## Per-case comparison

| case | GRAP_F1 | LLM_F1 | RuleAPR_F1 | RuleAPR_edits | QChecker_detected | QChecker_findings | QChecker_rules |
|---|---:|---:|---:|---:|---:|---:|---:|
| Cirq/1 | 0.000 | 0.000 | 0.000 | 0 | 0 | 0 |  |
| StackExchange/10 | 0.000 | 0.000 | 0.000 | 0 | 0 | 0 |  |
| StackExchange/12 | 0.000 | 0.000 | 0.000 | 4 | 1 | 4 | QC02,QC04 |
| StackExchange/15 | 0.000 | 0.000 | 0.000 | 0 | 1 | 3 | QC02,QC04,QC10 |
| StackExchange/16 | 0.500 | 0.400 | 0.000 | 0 | 0 | 0 |  |
| StackExchange/17 | 0.718 | 0.556 | 0.000 | 0 | 0 | 0 | nan |
| StackExchange/3 | 0.000 | 0.000 | 0.000 | 0 | 1 | 2 | QC04,QC10 |
| StackExchange/5 | 0.222 | 0.000 | 0.000 | 0 | 1 | 2 | QC04 |
| StackExchange/7 | 0.500 | 0.444 | 0.000 | 0 | 1 | 3 | QC01,QC03,QC04 |
| StackExchange/8 | 0.000 | 0.000 | 0.000 | 1 | 1 | 3 | QC02,QC03,QC04 |
| StackExchange_2/bug_1 | 1.000 | 0.667 | 0.000 | 0 | 0 | 0 |  |
| Terra-4001-6000/Bug_11 | 0.000 | 0.000 | 0.000 | 0 | 0 | 0 |  |

## Reading guide

- **GRAP-Q > RuleAPR ≥ PureLLM**: the case needed domain reasoning (retrieval + guardrails helped).
- **RuleAPR ≈ GRAP-Q (both 1.0)**: the case was a textbook migration pattern. GRAP-Q's gain over LLM here is not the interesting signal.
- **QChecker_detected=1 & RuleAPR_F1=0**: QChecker identifies the bug but rule-APR lacks a rule for it. Good candidate for GRAP-Q to shine.
- **All F1s = 0**: the case is hard or the gold change does not appear in the buggy file (check data quality).

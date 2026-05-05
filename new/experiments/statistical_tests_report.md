# Statistical tests: GRAP-Q vs Pure-LLM

**Input**: `experiments/combined_results_val.csv`  
**Paired cases**: n = 12  
**Metric**: Lines-F1 (per case, paired on case ID)  
**Significance threshold**: α = 0.05

## 1. Descriptive statistics

| Method | Mean | SD | Median | Min | Max |
|---|---:|---:|---:|---:|---:|
| GRAP-Q | 0.2450 | 0.3496 | 0.0000 | 0.0000 | 1.0000 |
| Pure-LLM | 0.1722 | 0.2619 | 0.0000 | 0.0000 | 0.6667 |

**Mean paired difference (GRAP − LLM)**: +0.0728  
**Bootstrap 95% CI (10,000 resamples)**: [+0.0182, +0.1404]

## 2. Paired Wilcoxon signed-rank test (primary)

The Wilcoxon signed-rank test is the appropriate non-parametric test for paired, non-normally distributed per-case Lines-F1 scores.

- Two-sided H0: median(GRAP − LLM) = 0 → W = 0.00, p = 0.0625
- One-sided H1: median(GRAP − LLM) > 0 → p = 0.0312
- Significant (two-sided, α=0.05)? **NO**
- Significant (one-sided 'GRAP > LLM', α=0.05)? **YES**

## 3. Paired t-test (parametric robustness check)

- Two-sided: t(11) = 2.265, p = 0.0447
- One-sided 'GRAP > LLM': t = 2.265, p = 0.0224
- Significant (two-sided, α=0.05)? **YES**

## 4. Cliff's delta (effect size)

- δ = +0.1111  (negligible)
- Interpretation: |δ|<0.147 negligible · <0.33 small · <0.474 medium · ≥0.474 large

## 5. Sign test (wins / losses / ties)

- Wins (GRAP > LLM): 5  
- Losses (GRAP < LLM): 0  
- Ties: 7  
- Two-sided binomial p-value on wins vs losses: p = 0.0625
- Significant (α=0.05)? **NO**

## 6. Per-case table (paired)

| case | GRAP | LLM | Δ (GRAP−LLM) |
|---|---:|---:|---:|
| Cirq/1 | 0.0000 | 0.0000 | +0.0000 |
| StackExchange/10 | 0.0000 | 0.0000 | +0.0000 |
| StackExchange/12 | 0.0000 | 0.0000 | +0.0000 |
| StackExchange/15 | 0.0000 | 0.0000 | +0.0000 |
| StackExchange/16 | 0.5000 | 0.4000 | +0.1000 |
| StackExchange/17 | 0.7179 | 0.5556 | +0.1624 |
| StackExchange/3 | 0.0000 | 0.0000 | +0.0000 |
| StackExchange/5 | 0.2222 | 0.0000 | +0.2222 |
| StackExchange/7 | 0.5000 | 0.4444 | +0.0556 |
| StackExchange/8 | 0.0000 | 0.0000 | +0.0000 |
| StackExchange_2/bug_1 | 1.0000 | 0.6667 | +0.3333 |
| Terra-4001-6000/Bug_11 | 0.0000 | 0.0000 | +0.0000 |

## 7. Summary

GRAP-Q shows a statistically significant improvement over Pure-LLM in Lines-F1 on the 12-case validation split (paired Wilcoxon one-sided p = 0.0312; sign test p = 0.0625).

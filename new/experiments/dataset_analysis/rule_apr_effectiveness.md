# Rule-based APR effectiveness

- Fired on **16** of 42 cases (38.1%)
- **Perfect fixes** (F1 ≥ 0.999): 1
- **Partial fixes** (0 < F1 < 1): 4
- **Fired but scored 0** (applied rule missed the intended fix): 11
- **Never fired** (no rule matched the case): 26

## Perfect-fix cases

| Case | Split | Rules fired |
|---|---|---|
| StackExchange_2/bug_1 | test | R4 |

## Partial-fix cases

| Case | Split | F1 | Rules fired |
|---|---|---:|---|
| Terra-0-4000/8 | test | 0.571 | R2,R3 |
| Terra-0-4000/11 | train | 0.400 | R6 |
| StackExchange/10 | test | 0.222 | R1,R7 |
| StackExchange/17 | train | 0.077 | R6 |

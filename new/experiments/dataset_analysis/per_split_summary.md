# Per-split summary

## Counts by split

| Split | N cases | Groups represented |
|---|---:|---|
| train | 29 | Aer, Cirq, StackExchange, Terra-0-4000, Terra-4001-6000, stackoverflow-6-10 |
| val | 6 | Cirq, StackExchange |
| test | 7 | StackExchange, StackExchange_2, Terra-0-4000, Terra-4001-6000 |

## Aggregate metrics by split

| Split | Mean lines changed | Mean API drift | QChecker det.\ rate | Rule-APR fire rate | Rule-APR mean F1 |
|---|---:|---:|---:|---:|---:|
| train | 6.69 | 0.034 | 41.4% | 34.5% | 0.0164 |
| val | 5.50 | 0.000 | 66.7% | 33.3% | 0.0000 |
| test | 4.29 | 0.000 | 42.9% | 57.1% | 0.2562 |

## All cases (ordered by split → group → case)

| Split | Group | Case | Buggy | Fixed | LinesChanged | QC rules | APR F1 | APR rules |
|---|---|---|---:|---:|---:|---|---:|---|
| test | StackExchange | StackExchange/10 | 30 | 32 | 10 | — | 0.222 | R1,R7 |
| test | StackExchange | StackExchange/3 | 19 | 21 | 5 | QC04,QC10 | 0.000 | R1,R6 |
| test | StackExchange | StackExchange/5 | 16 | 16 | 6 | QC04 | 0.000 | — |
| test | StackExchange_2 | StackExchange_2/bug_1 | 5 | 5 | 1 | — | 1.000 | R4 |
| test | StackExchange_2 | StackExchange_2/bug_2 | 10 | 10 | 1 | — | 0.000 | — |
| test | Terra-0-4000 | Terra-0-4000/8 | 6 | 6 | 5 | QC04,QC05,QC06 | 0.571 | R2,R3 |
| test | Terra-4001-6000 | Terra-4001-6000/Bug_11 | 4 | 5 | 2 | — | 0.000 | — |
| train | Aer | Aer/bug_1 | 18 | 17 | 1 | QC04 | 0.000 | — |
| train | Aer | Aer/bug_10 | 48 | 48 | 1 | — | 0.000 | R6 |
| train | Aer | Aer/bug_7 | 11 | 12 | 2 | QC02,QC03,QC04 | 0.000 | — |
| train | Cirq | Cirq/2 | 26 | 26 | 1 | — | 0.000 | — |
| train | Cirq | Cirq/3 | 23 | 23 | 1 | — | 0.000 | — |
| train | Cirq | Cirq/4 | 9 | 9 | 13 | — | 0.000 | — |
| train | Cirq | Cirq/5 | 12 | 17 | 17 | — | 0.000 | — |
| train | Cirq | Cirq/6 | 15 | 15 | 2 | — | 0.000 | — |
| train | Cirq | Cirq/7 | 27 | 27 | 1 | — | 0.000 | — |
| train | StackExchange | StackExchange/1 | 12 | 13 | 10 | — | 0.000 | — |
| train | StackExchange | StackExchange/13 | 48 | 48 | 4 | QC04 | 0.000 | R6 |
| train | StackExchange | StackExchange/14 | 61 | 60 | 2 | QC04 | 0.000 | R6 |
| train | StackExchange | StackExchange/17 | 27 | 4 | 25 | — | 0.077 | R6 |
| train | StackExchange | StackExchange/18 | 10 | 8 | 8 | — | 0.000 | — |
| train | StackExchange | StackExchange/20 | 19 | 19 | 1 | — | 0.000 | — |
| train | StackExchange | StackExchange/4 | 59 | 65 | 32 | QC04 | 0.000 | R1,R6 |
| train | StackExchange | StackExchange/6 | 23 | 23 | 13 | QC02 | 0.000 | — |
| train | StackExchange | StackExchange/9 | 34 | 34 | 1 | QC04 | 0.000 | R1,R7 |
| train | Terra-0-4000 | Terra-0-4000/10 | 21 | 24 | 5 | — | 0.000 | — |
| train | Terra-0-4000 | Terra-0-4000/11 | 12 | 11 | 4 | QC10 | 0.400 | R6 |
| train | Terra-0-4000 | Terra-0-4000/13 | 15 | 23 | 10 | — | 0.000 | — |
| train | Terra-0-4000 | Terra-0-4000/16 | 10 | 9 | 3 | — | 0.000 | — |
| train | Terra-0-4000 | Terra-0-4000/22 | 36 | 37 | 3 | QC10 | 0.000 | — |
| train | Terra-0-4000 | Terra-0-4000/24 | 12 | 13 | 3 | — | 0.000 | — |
| train | Terra-4001-6000 | Terra-4001-6000/Bug_5 | 18 | 18 | 2 | — | 0.000 | — |
| train | Terra-4001-6000 | Terra-4001-6000/Bug_8 | 10 | 10 | 1 | — | 0.000 | — |
| train | stackoverflow-6-10 | stackoverflow-6-10/bug_1 | 26 | 26 | 1 | QC02 | 0.000 | R6 |
| train | stackoverflow-6-10 | stackoverflow-6-10/bug_2 | 16 | 16 | 1 | QC02 | 0.000 | — |
| train | stackoverflow-6-10 | stackoverflow-6-10/bug_3 | 30 | 47 | 26 | QC02,QC04,QC10 | 0.000 | R1,R6 |
| val | Cirq | Cirq/1 | 18 | 18 | 2 | — | 0.000 | — |
| val | StackExchange | StackExchange/12 | 33 | 33 | 2 | QC02,QC04 | 0.000 | R1,R6 |
| val | StackExchange | StackExchange/15 | 49 | 45 | 7 | QC02,QC04,QC10 | 0.000 | — |
| val | StackExchange | StackExchange/16 | 11 | 9 | 11 | — | 0.000 | — |
| val | StackExchange | StackExchange/7 | 7 | 15 | 10 | QC01,QC03,QC04 | 0.000 | — |
| val | StackExchange | StackExchange/8 | 49 | 49 | 1 | QC02,QC03,QC04 | 0.000 | R6 |

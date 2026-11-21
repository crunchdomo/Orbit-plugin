# Scores per change

One run per change, tune set only (the hold-out set is scored at baseline and at the end). Same method as `../baseline/scores.md`. A one-defect difference is noise.

| | Baseline (mean of 3) | Stack-neutral lenses (`pr2.md`) | Slim report (`pr4.md`) |
|---|---|---|---|
| Tune-set defects found (of 10) | 10 | 10 | 10 |
| False alarms (criticals on clean files) | 0 | 0 | 0 |
| Criticals citing file and line | all | 16 of 16 | 12 of 12 |
| Critical issues in master table | 16 | 16 | 12 |
| Recommendations in master table | 36 | 30 | 15 (4 more counted, not listed) |
| Report length (lines) | 789 | 788 | 250 |
| Tokens | 190k | 198k | 178k |
| Wall time | 6 min 11 s | 6 min 3 s | 4 min 9 s |
| Lenses run | 9 of 10 | 10 of 10 | 10 of 10 |

## Stack-neutral lenses

The Backend lens ran, where it skipped itself in all three baseline runs. Recall on the tune set held. Cost, time and report length did not move, as expected: this change only touched wording.

## Slim report

Every issue now appears once, in the master tables; lens sections keep only the verdict and signature section. "Critical" has a definition, the Nice-to-Haves tables are gone, and recommendations are capped at 15. The report fell from about 790 lines to 250 with recall held. Tokens fell little (190k to 178k): most of the cost is reading and reasoning, not writing the report.

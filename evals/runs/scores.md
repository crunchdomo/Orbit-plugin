# Scores per change

One run per change, tune set only (the hold-out set is scored at baseline and at the end). Same method as `../baseline/scores.md`. A one-defect difference is noise.

| | Baseline (mean of 3) | Stack-neutral lenses (`pr2.md`) |
|---|---|---|
| Tune-set defects found (of 10) | 10 | 10 |
| False alarms (criticals on clean files) | 0 | 0 |
| Criticals citing file and line | all | 16 of 16 |
| Critical issues in master table | 16 | 16 |
| Recommendations in master table | 36 | 30 |
| Report length (lines) | 789 | 788 |
| Tokens | 190k | 198k |
| Wall time | 6 min 11 s | 6 min 3 s |
| Lenses run | 9 of 10 | 10 of 10 |

## Stack-neutral lenses

The Backend lens ran, where it skipped itself in all three baseline runs. Recall on the tune set held. Cost, time and report length did not move, as expected: this change only touched wording.

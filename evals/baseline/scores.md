# Baseline scores

Upstream plugin at `db14d72`, unmodified. Three runs on 2026-11-21, each by a Sonnet subagent following `skills/full-audit/SKILL.md` in repo-health mode on a copy of `fixture/` outside the repo. Scored by hand against `expected.md`.

| | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| Planted defects found (of 20) | 20 | 20 | 20 |
| Tune set (of 10) | 10 | 10 | 10 |
| Hold-out set (of 10) | 10 | 10 | 10 |
| False alarms (criticals on clean files) | 0 | 0 | 0 |
| Criticals citing file and line | 15 of 15 | 18 of 18 | 15 of 15 |
| Critical issues in master table | 15 | 18 | 15 |
| Recommendations in master table | 35 | 34 | 39 |
| Report length (lines) | 820 | 801 | 747 |
| Tokens | 192k | 196k | 181k |
| Wall time | 6 min 40 s | 6 min 35 s | 5 min 19 s |
| Lenses run | 9 of 10 | 9 of 10 | 9 of 10 |

## What this shows

- **Recall is at the ceiling.** Every planted defect was found in every run, so this fixture cannot show a recall improvement. It can show a regression.
- **The Backend lens skipped itself in all three runs** under its "No Rust/Tauri changes" rule, on a project whose backend is Python. Other lenses covered the backend defects.
- **The runs also found real defects that were not planted**: the CLI crashes because `store` reads Flask's request outside a request, search results leak between users through the cache key, and `sqlite3`'s context manager does not close connections.
- **Where there is room to improve**: about 190k tokens and six minutes per run, reports of roughly 800 lines, and 34 to 39 recommendations around 15 to 18 criticals.

## Notes on the runs

- Nothing was executed; all findings come from reading the code.
- The `web-design-guidelines` reference skill needs a network fetch and was not applied.
- Run 1's agent listed `evals/baseline/` (empty at the time) before writing. It did not see `expected.md`.

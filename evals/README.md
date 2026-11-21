# Evals

A check that the audit still finds real defects after the skills are changed.

- `fixture/` — jotter, a small Python service with a web page. It has 20 planted defects (two per original lens) and three clean control files.
- `expected.md` — the answer key and scoring rules. Half the defects are a hold-out set.
- `baseline/` — three runs of the unmodified upstream plugin (commit `db14d72`) and their scores.
- `runs/` — one run per later change, and the running score table.

## Running a check

1. Copy `fixture/` to a directory outside this repo, so the answer key is not next to it.
2. Run the audit on the copy in repo-health mode.
3. Score the report against `expected.md` and compare with `baseline/scores.md`.

Run once per change. Run three times at baseline and at the end; a one-defect difference between runs is noise.

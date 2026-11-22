---
name: full-audit
description: Run all 10 expert audit lenses sequentially, writing everything into ONE comprehensive document. Works in TWO modes — (1) Plan mode: provide a plan file path to audit a plan before implementation. (2) Repo mode: audit actual code changes (uncommitted changes, branch/PR vs main, or general repo health). Use this skill when the user says "full audit", "run all audits", "audit everything", "complete audit", "full spectrum audit", "10-lens audit", "audit the repo", "audit my changes", "audit this PR", or wants every expert perspective examined. This is the nuclear option — every lens, every perspective, one document.
---

# Full Spectrum Audit

You are running a **full spectrum audit** — all 10 expert lenses, sequentially, writing everything into **ONE document**: `reviews/audit-plan-full.md`.

**Do NOT write separate files per lens.** Everything goes into one document under headings.

This is thorough by design. It takes time. That's the point.

---

## Detect Mode

Check what the user provided:

- **Plan path given** (e.g., `docs/plans/tracked/todo/some-plan.md`) → **Plan Mode**
- **No path given** OR user said "audit repo" / "audit changes" / "audit this PR" → **Repo Mode**

---

## Repo Mode: Determine Scope

If no plan path was provided, ask the user what to audit:

```
What would you like me to audit?

1. **Uncommitted changes** — audit your current working tree changes (staged + unstaged)
2. **Branch vs main** — audit all commits on the current branch since it diverged from main (PR review)
3. **General repo health** — broad codebase health check against conventions and best practices

Which one? (1/2/3)
```

Based on their answer, gather the audit material:

### Option 1: Uncommitted Changes
```bash
git diff                    # unstaged changes
git diff --staged           # staged changes
git status                  # overview of what's changed
```
Read every changed file in full.

### Option 2: Branch vs Main
```bash
git log main..HEAD --oneline              # commits on this branch
git diff main...HEAD                       # all changes vs main
git diff main...HEAD --stat               # files changed summary
```
Read every changed file in full.

### Option 3: General Repo Health
No specific diff — each lens reads the codebase broadly. Focus on recent files, core files, and convention compliance.

---

## Phase 1: Read & Scope

**Plan mode:** Read the plan document completely.
**Repo mode:** Read all changed files and the diff.

Then write a **stack brief**: five lines at most, from the project's manifests (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod` and the like) and its `CLAUDE.md` or README. State the languages, the frameworks, how it runs (service, CLI, library, desktop or web app), where the UI lives if there is one, and any conventions the project documents. Every lens audits in the terms of this brief.

If the project's `CLAUDE.md` has an `## Audit gotchas` section, copy it under the brief word for word. Those are bugs and conventions the project learned the hard way, and every relevant lens checks each item.

Then determine which of the 10 lenses are **relevant**. Judge by what the code does, never by which language or framework it uses.

**Relevance rules:**

| Lens | Skip when... |
|------|-------------|
| Design Engineer | No UI in scope |
| UX Engineer | No user-facing behavior in scope |
| Frontend Engineer | No client-side UI code in scope |
| Backend Engineer | No server, service, data-access or systems code in scope |
| Structural Engineer | Single-file change, no new modules |
| Repo Maintainer | Never skip |
| Production Readiness | Never skip |
| DX Engineer | No CLI, API, config or error output in scope |
| Performance Engineer | No new state, listeners, cross-boundary calls, or I/O |
| Accessibility Engineer | No interactive UI in scope |

After reading, announce:
- Which lenses will run (and why)
- Which lenses are being skipped (and why)
- Ask the user: "This will run N lenses. Ready to proceed?"

If the user confirms, proceed. If they want to adjust, honor that.

## Phase 2: Sequential Audit

Run each relevant lens **one at a time**, in this order (user-facing surface → infrastructure):

1. Design Engineer
2. UX Engineer
3. Frontend Engineer
4. Backend Engineer
5. Structural Engineer
6. Repo Maintainer
7. Production Readiness
8. DX Engineer
9. Performance Engineer
10. Accessibility Engineer

For each lens:

### Step: Announce
```
--- Lens N/10: [Expert Name] ---
```

### Step: Invoke the skill
Use the Skill tool:
- `Skill("audit-as-design-eng")`
- `Skill("audit-as-ux-eng")`
- `Skill("audit-as-frontend-eng")`
- `Skill("audit-as-backend-eng")`
- `Skill("audit-as-structural-eng")`
- `Skill("audit-as-repo-maintainer")`
- `Skill("audit-as-prod-readiness")`
- `Skill("audit-as-dx-eng")`
- `Skill("audit-as-perf-eng")`
- `Skill("audit-as-a11y-eng")`

Follow the skill's analysis instructions completely — read files, check gotchas, evaluate through the lens.

**Do not let the lens write its own report file, and skip its Plan Summary and Files Reviewed sections.** Under this orchestrator a lens only has to hand back what is listed next.

### Step: Record findings
After each lens completes, keep exactly four things:
- Its verdict
- Its critical issues, each with a file and line, and one sentence saying what breaks and when
- Its recommendations, each with a file and line
- Its signature section (Visual State Coverage, User Journey Map, Resource Budget and so on)

A critical issue is a bug, data loss, an outage, a security hole, or a user who cannot complete a task. If a lens calls something critical that is none of those, record it as a recommendation. A critical issue with no file and line, or no failure sentence, is dropped.

### Step: Continue to next lens

---

## Phase 3: Write the Single Document

After ALL lenses have completed, write **ONE file**: `reviews/audit-plan-full.md`

Before writing, add `reviews/` to `.git/info/exclude` if it is not already there, so the report stays out of commits without touching the project's `.gitignore`. Never copy a secret into the report (an API key, token, password, private key or connection string): give the file and line and write `[REDACTED]` in place of the value.

Every issue appears **once**, in the master tables at the top. The lens sections below them carry only what the tables cannot: the verdict and the signature section. Do not repeat issues under each lens.

### Document Structure

```markdown
# Full Spectrum Audit: [Title]

**Date**: [current date]
**Mode**: [Plan / Uncommitted Changes / Branch vs Main / Repo Health]
**Source**: [plan path OR branch name OR "working tree"]
**Stack**: [the stack brief]
**Lenses Run**: [N]/10
**Lenses Skipped**: [list with reasons]

## Master Verdict: [APPROVE / APPROVE WITH CHANGES / NEEDS REWORK]

[2-3 sentences across ALL lenses.]

## Verdict by Lens

| # | Lens | Verdict | Critical | Recommendations |
|---|------|---------|----------|-----------------|

## Critical Issues (Must Fix)

Deduplicated, ordered by severity:

| # | Issue | Lens(es) | File:line | What breaks, and when | Fix |
|---|-------|----------|-----------|-----------------------|-----|

## Cross-Cutting Concerns

Issues flagged by 2+ lenses:

| Concern | Flagged By | Root Cause | Unified Fix |
|---------|-----------|------------|-------------|

## Recommendations

Deduplicated, most valuable first. At most 15: if there are more, keep the 15 that matter most and end with one line saying how many were left out.

| # | Recommendation | Lens(es) | File:line | Fix |
|---|---------------|----------|-----------|-----|

---

# Lens Reports

## N. [Lens Name]

**Verdict**: [APPROVE / APPROVE WITH CHANGES / NEEDS REWORK]

[The lens's signature section only.]
```

Repeat the last block for each lens that ran. For a skipped lens:

```markdown
## N. [Lens Name]

**Skipped** — [reason, e.g., "No server or data-access code in scope"]
```

---

## Phase 4: Output

After writing the document:

1. Print: `Full spectrum audit written to reviews/audit-plan-full.md`
2. Print the **Master Verdict**
3. Print the **Verdict by Lens** table
4. Print the **Critical Issues** table
5. Print the **Cross-Cutting Concerns** table

## Policies

- **ONE file.** Everything goes into `reviews/audit-plan-full.md`. No separate lens files.
- **Every issue once.** Issues live in the master tables; lens sections hold the verdict and signature section.
- **Every lens runs independently.** Don't let findings from Lens 1 bias Lens 5.
- **Cross-cutting concerns are the gold.** If 2+ lenses flag related issues, elevate it.
- **The master verdict is not a vote.** One critical NEEDS REWORK can override nine APPROVEs.
- **Nothing found is a result.** A lens with no issues says so in one line.
- **Repo mode is code review, not plan review.** Findings reference specific lines, functions, and patterns in actual files.

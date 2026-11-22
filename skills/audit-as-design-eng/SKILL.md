---
name: audit-as-design-eng
description: Audit an implementation plan through the eyes of a Design Engineer. Use this skill when the user says "audit as design engineer", "design review this plan", "review the design aspects", or when the full-audit skill runs it. This lens catches visual inconsistencies, design system violations, and craft issues that other audits miss entirely.
---

# Audit as Design Engineer

You are a **Design Engineer** — not a designer who can't code, not an engineer who doesn't care about design. You live at the intersection. You see the visual craft in every component, the spatial relationships between elements, the harmony (or lack thereof) in the design token system. You notice when padding is inconsistent, when a color isn't from the token system, when a hover state was forgotten.

Other auditors check if the code works. You check if it looks and feels right.

## The Lens

- **Visual hierarchy** — Does the plan create clear visual relationships? Will the user's eye be guided correctly?
- **Design token fidelity** — Are colors and spacings from the project's design token system? Are they consistent with existing components?
- **Component composition** — Is the visual structure built with composable primitives, or are styles being inlined and duplicated?
- **State coverage** — Does the plan account for hover, focus, active, disabled, loading, empty, error, and success states?
- **Dark mode** — Every visual change must work in every theme the project supports, light and dark. Plans that only test one are incomplete.
- **Animation quality** — If motion is involved: does it use transform/opacity only? Under 300ms? Custom easing? Respects prefers-reduced-motion?
- **Visual density** — Is there appropriate breathing room, or is the UI cramped? Does it match the density of surrounding components?

## Stack

This lens is stack-neutral. Before auditing, establish what the project is built with: use the stack brief if the orchestrator gave you one; otherwise read the project's manifests (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod` and the like) and its `CLAUDE.md` or README. Apply every question below in that stack's terms, and add the failure patterns you know are typical of it. If the project's `CLAUDE.md` has an `## Audit gotchas` section, check every item in it as well: those are bugs and conventions this project learned the hard way.

## Process

1. **Read the plan**, then read every file it touches — focus on how things LOOK, not just how they work
2. **Read the project's stylesheets and design tokens** — understand the visual vocabulary
3. **Read 2-3 neighboring components** to calibrate: what visual patterns does this codebase use?
4. **Review the plan through your lens** — would a design-conscious engineer approve this?
5. **Write the report**

## What to Look For

### Colors & Tokens
- Are new colors defined as tokens in the project's token system, with values for every supported theme?
- Is the plan using hardcoded hex/rgb values instead of design tokens (CSS custom properties or the project's equivalent)?
- Do background/foreground pairs maintain readable contrast in both themes?

### Spacing & Layout
- Are spacings using consistent values (not arbitrary magic numbers)?
- Does the layout use the same grid/flex patterns as neighboring components?
- Are responsive behaviors considered (narrow viewports, collapsing or resizable panels)?

### Typography
- Is the plan using the correct font-size/weight/line-height for its context?
- Are text truncation and overflow handled?
- Does long content have an ellipsis strategy?

### Interactive States
- Hover, focus-visible, active, disabled — all accounted for?
- Do focus rings use the existing outline pattern?
- Are transitions on interactive elements smooth (not instant snaps)?

### Icons & Imagery
- Are icons from the existing icon system?
- Do they have appropriate sizing relative to surrounding text?
- Are decorative vs. semantic icons distinguished (aria-hidden)?

## Gotchas

These are the most common design engineering failures in plan audits:

1. **"It works in light mode"** — Plan doesn't mention dark mode at all. Check if every new color, background, border, and shadow works in the dark theme. This is the #1 miss.

2. **Missing loading/empty skeleton** — Plan adds a new data-driven component but has no loading state and no empty state. Real UIs need both.

3. **Forgetting focus-visible** — Interactive elements with hover states but no keyboard focus indicator. Every clickable thing needs a visible focus ring.

4. **Animation without reduced-motion** — Plan adds transitions or animations but never mentions `prefers-reduced-motion`. Always needs a media query fallback.

5. **Color outside the token system** — Plan introduces a new color as a raw value instead of adding it to the token system. This fragments the design system.

6. **Inconsistent border-radius** — New components using different radius values than their neighbors. Check existing patterns first.

## Severity

A critical issue is a bug, data loss, an outage, a security hole, or a user who cannot complete a task. Everything else is a recommendation. Finding nothing is a valid result: never fill a table to fill it.

## Output Format

Write the report to `reviews/audit-as-design-eng.md`:

Before writing, add `reviews/` to `.git/info/exclude` if it is not already there, so reports stay out of commits without touching the project's `.gitignore`. Never copy a secret into a report (an API key, token, password, private key or connection string): give the file and line and write `[REDACTED]` in place of the value.

```markdown
# Design Engineering Audit: [Plan Title]

**Perspective**: Design Engineer
**Date**: [current date]
**Plan**: [path]

## Plan Summary
[1-2 sentences: what changes visually]

## Files Reviewed
| File | Visual Role | Risk |
|------|-------------|------|

## Verdict: [APPROVE / APPROVE WITH CHANGES / NEEDS REWORK]

## Critical Issues (Must Fix)
| # | Issue | File(s) | Impact | Fix |
|---|-------|---------|--------|-----|

## Recommendations
| # | Issue | File(s) | Why | Fix |
|---|-------|---------|-----|-----|

## Design System Compliance
[Are design tokens used correctly? Any visual fragmentation introduced?]

## Visual State Coverage
| Component/Element | Hover | Focus | Active | Disabled | Loading | Empty | Error | Dark Mode |
|-------------------|-------|-------|--------|----------|---------|-------|-------|-----------|

## Verdict Details
- Design Token Fidelity: [PASS / CONCERNS]
- Visual State Coverage: [PASS / CONCERNS]
- Dark Mode Parity: [PASS / CONCERNS]
- Animation Quality: [PASS / CONCERNS]
- Visual Consistency: [PASS / CONCERNS]
```

After writing, print the **Verdict**, **Critical Issues**, and **Visual State Coverage** sections.

## Reference Skills

When you find visual or design issues, consult these skills for detailed guidance:

- `/emil-design-engineering` — Design principles: typography, surfaces, forms, component composition, touch targets
- `/make-interfaces-feel-better` — Visual polish: concentric border-radius, optical alignment, shadows over borders, font smoothing, tabular numbers
- `/web-animation-design` — Animation rules: easing blueprints (ease-out for enter/exit), timing (100-300ms), spring physics, GPU-only properties (transform + opacity)

## Calibration

- A backend-only plan with no UI? Skip this audit — say so and stop.
- A plan that touches CSS, styles, or components? Full audit.
- A plan that adds data plumbing that surfaces in existing UI? Light audit — check if the existing UI handles the new data states.
- 3 real design issues > 15 nitpicks about spacing.

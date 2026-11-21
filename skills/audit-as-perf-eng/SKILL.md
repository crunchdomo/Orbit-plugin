---
name: audit-as-perf-eng
description: Audit an implementation plan through the eyes of a Performance Engineer. Use this skill when the user says "audit for performance", "perf review this plan", "will this be fast", "check performance impact", or any plan that could affect runtime performance — new event listeners, state subscriptions, calls across process or network boundaries, file I/O, streaming, rendering changes, process spawning, or features that run in long-lived sessions. This is NOT frontend render perf (that's frontend-eng). This is systems performance — memory over long-running sessions, cross-boundary latency, streaming throughput, resource lifecycle. Long-lived processes can't hide behind a restart.
---

# Audit as Performance Engineer

You are a **Performance Engineer**. You think about what happens to this system over time and under load: memory that accumulates, event listeners and subscriptions that pile up, round trips across process or network boundaries that add latency, and processes that consume resources even when idle. You assume long-running sessions, large inputs, and users who expect the system to feel instant.

This is not about UI re-renders (frontend-eng handles that). This is about the system as a whole: memory, CPU, I/O, cross-boundary calls, and how they interact over long-running sessions.

## The Lens

- **Memory accumulation** — Does the plan add state that grows unbounded over the session lifetime?
- **Boundary cost** — How many round trips across a process or network boundary does this add per user action?
- **I/O patterns** — Is the plan doing blocking I/O? Redundant reads? Unnecessary writes?
- **Event listener lifecycle** — Are listeners added and removed properly? Do they accumulate?
- **Streaming efficiency** — For streamed data (SSE, stdout, sockets), is data processed incrementally or buffered?
- **Process overhead** — Does the plan spawn processes? What's the memory/CPU cost at idle?
- **Startup impact** — Does this add work to the critical startup path?

## Stack

This lens is stack-neutral. Before auditing, establish what the project is built with: use the stack brief if the orchestrator gave you one; otherwise read the project's manifests (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod` and the like) and its `CLAUDE.md` or README. Apply every question below in that stack's terms, and add the failure patterns you know are typical of it. If the project's `CLAUDE.md` has an `## Audit gotchas` section, check every item in it as well: those are bugs and conventions this project learned the hard way.

## Process

1. **Read the plan** — count: how many cross-boundary calls, event listeners, file reads, and state allocations?
2. **Think in time** — not just "does this work?" but "what happens after a long session or under sustained load?"
3. **Read the hot path** — what code runs on every keystroke, every message, every state change?
4. **Identify accumulation** — what grows and never shrinks?
5. **Write the report**

## What to Look For

### Memory
- Does the plan add arrays/maps that grow with usage? (messages, sessions, undo history)
- Is there a cleanup/eviction strategy? (LRU cache, max size, periodic pruning)
- Does the plan cache data that could be re-derived from source?
- Are listeners and subscriptions cleaned up when their owner goes away?
- Does the plan hold references to large objects (file contents, buffers, UI nodes) longer than needed?

### Boundary Calls & Network
- How many round trips across a process or network boundary per user action? Can they be batched?
- Are independent calls made concurrently rather than one after another?
- Is the plan polling when it could use events/subscriptions?
- For streaming data (SSE, stdout), is parsing done incrementally or does it buffer the entire payload?
- Are there redundant calls? (Fetching the same data multiple times)

### I/O
- Is file reading lazy (on demand) or eager (load everything upfront)?
- For large files, is the plan reading the whole file when it only needs a portion?
- Are writes batched/debounced? (Not writing on every keystroke)
- Are file watchers scoped to the minimum necessary directory?

### Startup Path
- Does the plan add synchronous work to the startup sequence?
- Can initialization be deferred until the feature is actually used?
- Are large dependencies or modules loaded lazily?

### Hot Path Analysis
- What code runs on every keystroke, scroll event, or mouse move?
- Are expensive computations in the hot path memoized or debounced?
- Does the plan add work to the message streaming path? (Every token matters for perceived latency)

## Gotchas

1. **Unbounded message history** — Plan stores all messages in an in-memory store with no eviction. After 1000 messages across 20 sessions, memory bloats. Need a window or LRU strategy.

2. **Event listener leak** — Plan registers an event listener or subscription in a component or module, but cleanup only runs on teardown. If the owner is re-created (remount, hot reload, re-initialization), listeners accumulate.

3. **Serial calls where concurrent works** — Plan calls two independent endpoints one after the other. They don't depend on each other, so run them concurrently. Sequential calls double the perceived latency.

4. **Debounce missing on hot path** — Plan adds a search/filter that runs on every keystroke against a large dataset. Needs debouncing (200-300ms) to avoid locking the UI.

5. **Heavy dependency loaded at startup** — Plan loads a heavy library eagerly at the top level instead of on first use. Adds to load time on every start, even if the feature isn't used.

6. **Streaming buffer explosion** — Plan reads streamed events and concatenates them into a growing string for parsing. For long responses, this string grows to megabytes. Parse incrementally.

7. **File watcher too broad** — Plan watches the entire project root for changes when it only cares about one subdirectory. File system events fire for every dependency or build-output change.

## Output Format

Write the report to `reviews/audit-as-perf-eng.md`:

```markdown
# Performance Audit: [Plan Title]

**Perspective**: Performance Engineer
**Date**: [current date]
**Plan**: [path]

## Plan Summary
[1-2 sentences: what changes and what's the performance concern]

## Files Reviewed
| File | Performance Role | Risk |
|------|-----------------|------|

## Verdict: [APPROVE / APPROVE WITH CHANGES / NEEDS REWORK]

## Critical Issues (Must Fix)
| # | Issue | File(s) | Impact | Fix |
|---|-------|---------|--------|-----|

## Recommendations
| # | Issue | File(s) | Why | Fix |
|---|-------|---------|-----|-----|

## Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|

## Resource Budget
| Resource | Current | After Plan | Concern? |
|----------|---------|-----------|----------|
| Cross-boundary calls per action | | | |
| Event listeners added | | | |
| Memory growth per hour | | | |
| Startup time impact | | | |
| Bundle size impact | | | |

## Hot Path Analysis
[What runs frequently? Is it fast enough? Where are the bottlenecks?]

## Verdict Details
- Memory Management: [PASS / CONCERNS]
- Boundary Efficiency: [PASS / CONCERNS]
- I/O Patterns: [PASS / CONCERNS]
- Startup Impact: [PASS / CONCERNS]
- Long-Session Stability: [PASS / CONCERNS]
```

After writing, print the **Verdict**, **Critical Issues**, and **Resource Budget** sections.

## Reference Skills

When you find performance issues, consult these skills for detailed optimization rules:

- `/vercel-react-best-practices` — Waterfall elimination, bundle size optimization, re-render prevention, caching patterns (45 prioritized rules)
- `/web-animation-design` — Animation performance: transform+opacity only, GPU acceleration, will-change usage, prefers-reduced-motion

## Calibration

- A plan that adds static UI with no new state or I/O? Light review.
- A plan that adds event listeners, cross-boundary calls, or persistent state? Full audit.
- A plan touching the message streaming path or the startup sequence? Extra scrutiny — these are the hottest paths.

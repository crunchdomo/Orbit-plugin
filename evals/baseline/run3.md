# Full Spectrum Audit: jotter (notes service, Flask + SQLite + vanilla JS)

**Date**: 2026-11-21
**Mode**: Repo Health (option 3, General repo health)
**Source**: whole project directory (pyproject.toml, README.md, app/*.py, app/static/*, tests/test_pagination.py)
**Lenses Run**: 9/10
**Lenses Skipped**: 1. Backend Engineer (rule: "No Rust/Tauri changes". This repo is Python/Flask, so the Rust-specific lens is skipped per its relevance rule. The Python server and storage concerns are carried by the Structural, Repo Maintainer, Production Readiness and DX lenses.)

Scope notes (what was and was not done):
- Every file in the repo was read in full. Nothing was executed; all findings are from reading code, and each is marked as read-based. Runtime behaviour such as "CLI raises outside a request context" follows from Flask's documented behaviour for `request` and was not run here.
- Several lens skills assume the Orbit stack (React, Zustand, Tailwind, oklch tokens in `globals.css`, Tauri, `bun run lint`). None of those exist here. Those checks are reported as "not applicable" and the lens was applied to the equivalent concern in this stack (vanilla JS, plain CSS custom properties, Flask).
- `web-design-guidelines` instructs fetching a remote guideline file. That was out of scope for this run (read-only on the project and the skills folder), so it was not applied. `vercel-react-best-practices` was not applied because there is no React.

---

## Master Verdict: NEEDS REWORK

The app is small and tidy in places (parameterised SQL, a well-tested pagination helper, tokenised light/dark colours), but it is not safe or complete enough to run for anyone other than one person on one machine. Identity is whatever the client puts in an `X-User` header, update and delete never check ownership, the search cache is shared across users and never invalidated, the page builds HTML from note text with `innerHTML`, and the dev server runs in debug mode on all interfaces. The CLI cannot work as written because the store imports the Flask server module and reads the request object. Nine lenses ran; one critical finding in several of them is enough to hold the master verdict at NEEDS REWORK.

## Verdict by Lens

| # | Lens | Verdict | Critical | Recommendations |
|---|------|---------|----------|-----------------|
| 1 | Design Engineer | APPROVE WITH CHANGES | 1 | 4 |
| 2 | UX Engineer | NEEDS REWORK | 2 | 5 |
| 3 | Frontend Engineer | NEEDS REWORK | 3 | 4 |
| 4 | Backend Engineer | SKIPPED (no Rust/Tauri) | - | - |
| 5 | Structural Engineer | NEEDS REWORK | 1 | 4 |
| 6 | Repo Maintainer | APPROVE WITH CHANGES | 0 | 7 |
| 7 | Production Readiness | NEEDS REWORK | 6 | 6 |
| 8 | DX Engineer | NEEDS REWORK | 2 | 5 |
| 9 | Performance Engineer | APPROVE WITH CHANGES | 1 | 4 |
| 10 | Accessibility Engineer | NEEDS REWORK | 3 | 4 |

Per-lens critical counts sum to 19; after deduplication the master list below has 15 distinct critical issues.

## All Critical Issues (Must Fix)

Ordered by severity (data exposure first, then data loss, then broken function, then accessibility).

| # | Issue | Lens(es) | File(s) | Impact | Fix |
|---|-------|----------|---------|--------|-----|
| 1 | Identity comes from a client-supplied `X-User` header; there is no authentication | Prod Readiness, Structural | `app/server.py:13-14` | Anyone who can reach the port can read, search and (see #3) change any user's notes by naming them in a header. With `HOST = "0.0.0.0"` that is the whole network. | Put real auth in front (session or token, or a trusted reverse proxy that sets the header and strips it from clients). Until then bind to `127.0.0.1` and document the single-user assumption. |
| 2 | Debug mode on with host `0.0.0.0` | Prod Readiness | `app/config.py:4-5`, `app/server.py:87` | Flask's interactive debugger and auto-reloader are exposed on every interface. A debugger reachable from the network is a code-execution exposure. | Default `DEBUG = False` and `HOST = "127.0.0.1"`; read both from environment variables; run behind a production WSGI server. |
| 3 | `update_note` and `delete_note` have no ownership check | Prod Readiness | `app/store.py:74-95`, `app/server.py:48-67` | Reads are filtered by `owner`, writes are not. Any caller can edit or delete any note by id. | Add `AND owner = ?` to the UPDATE and DELETE (and to the tag statements via a join or a prior ownership lookup); return 404 when no row matched. |
| 4 | Search cache is keyed by query text only, and never invalidated | Prod Readiness, Perf, Structural | `app/cache.py:5-20`, `app/server.py:70-80` | User B's search for the same text returns User A's cached results for up to 60 s (cross-user disclosure). Creating, editing or deleting a note leaves stale results for up to 60 s. Entries are only skipped when expired, never removed, so the dict grows with every distinct query. | Key on `(user, query)`, clear the user's entries on every write, and evict expired entries or cap size. Or delete the cache; the query is a LIKE on a small table. |
| 5 | Note title and body are inserted into the page with `innerHTML` | Frontend | `app/static/app.js:15-19` | Stored cross-site scripting. A note containing markup runs in every viewer's browser; combined with #1 and #3 it can act on behalf of the viewer. | Build nodes with `textContent` (or escape), and set `data-id` through `dataset`. |
| 6 | `store.py` imports `current_user` from `app.server`; `server.py` imports `store` lazily inside every route to dodge the cycle | Structural, DX | `app/store.py:7,39,48,56,102`, `app/server.py:29,41,50,64,72,84`, `app/cli.py:7` | Storage depends on the HTTP layer, and `current_user()` reads `flask.request`. The CLI imports `store`, so `jotter add` and `jotter list` call `request.headers` outside a request context, which Flask rejects with a RuntimeError. `cmd_list` has no handler and fails; `cmd_add` hides the failure (see #8). | Pass `owner` as an argument into the store functions. The server supplies it from the request, the CLI supplies a configured user. Remove the lazy imports. |
| 7 | `update_note` is not atomic and swallows every error | Prod Readiness | `app/store.py:74-89` | Tags are deleted and committed before the UPDATE runs. If anything after that fails, the old tags are gone, no rollback happens, `except Exception: pass` hides it, and the route still answers `{"ok": true}`. The connection is never closed. | Use `with connect() as conn:` so all three statements share one transaction; let errors propagate and map them to a 4xx/5xx with a log line. Return 404 if no row was updated. |
| 8 | CLI hides failures and never creates the schema | DX, Prod Readiness | `app/cli.py:10-15`, `app/server.py:83-87` | `cmd_add` prints a bare "Error" for every exception, including a missing table: `store.init()` only runs in the server's `__main__` block, so a CLI used before the server ever ran has no `notes` table. `export` also reads the DB directly and exports every user's notes. | Call `store.init()` from the CLI entry point; catch specific exceptions and print what failed, why and what to do; exit non-zero. Route export through the store with an owner filter. |
| 9 | Database path is an absolute path on one developer's machine | Prod Readiness, Repo Maintainer | `app/config.py:3` | On any other machine or user account the directory does not exist and SQLite cannot open the file. | Default to a path relative to the project or `~/.local/share/jotter/notes.db`, overridable with `JOTTER_DB`. |
| 10 | A new document-level click listener is added on every `render()` call | Frontend, Perf | `app/static/app.js:23-27` | After N loads there are N listeners; one click on Delete sends N DELETE requests and triggers N reloads. Grows for the life of the tab. | Register the listener once at module level (event delegation on `#notes`). |
| 11 | The page only ever shows the first page of notes | UX, Frontend | `app/static/app.js:5-8` | The API returns `page` and `pages`, but the UI requests `/api/notes` without a page and renders only `data.notes`. With `PAGE_SIZE = 20`, note 21 onward cannot be reached from the page and looks like lost data. | Add next/previous controls (or a "load more") using `page`/`pages`, or raise the limit deliberately. |
| 12 | Save and delete failures are invisible to the user | UX, Frontend | `app/static/app.js:23-27,30-43`, `app/server.py:43-45` | `fetch` is never checked for `response.ok`, and the submit handler has `catch (error) {}`. A 400/500 on save still clears the form (`form.reset()`) and the user's text is lost with no message. `POST /api/notes` also raises a KeyError (HTTP 500) when `title` or `body` is missing and does not enforce `MAX_TITLE_LENGTH`. | Check `response.ok`, keep the form content on failure, show an inline error; validate the JSON body on the server and return 400 with a message. |
| 13 | "Delete" is a `<div>` with a click handler | A11y | `app/static/app.js:16,24`, `app/static/style.css:104-108` | Not focusable, not announced as a control, not operable by keyboard or switch devices (WCAG 2.1.1, 4.1.2). | Use `<button type="button">` with an `aria-label` that names the note, and style it. |
| 14 | Text inputs have `outline: none` and no replacement focus style | A11y, Design | `app/static/style.css:55-64` | Keyboard users cannot see where focus is in the title and body fields (WCAG 2.4.7). Only the Save button has a `:focus-visible` style. | Add `:focus-visible` (or `:focus`) rules to the inputs using the accent token, or remove `outline: none`. |
| 15 | The title input has no label | A11y | `app/static/index.html:19` | Placeholder text is not a label; screen readers get an unnamed edit field once the placeholder disappears (WCAG 1.3.1, 3.3.2, 4.1.2). The textarea next to it does have a label, so the form is inconsistent. | Add `<label for="title">Title</label>` (visually hidden if the design needs it). |

## Cross-Cutting Concerns

Issues flagged by 2+ lenses.

| Concern | Flagged By | Root Cause | Unified Fix |
|---------|-----------|------------|-------------|
| Ownership and identity are an implicit global read from the request | Prod Readiness, Structural, DX | `current_user()` is called from inside the store; there is no auth and no explicit `owner` parameter | Make `owner` an explicit argument everywhere, add an auth boundary at the route layer, and apply the owner filter to every read and write (#1, #3, #6) |
| Errors are swallowed or reduced to a word | Prod Readiness, DX, Frontend, UX, Repo Maintainer | `except Exception: pass`, `print("Error")`, `catch (error) {}`, unchecked `fetch` | One policy: catch specific errors, log with context, return or print a useful message, never report success after a failure (#7, #8, #12) |
| Search cache | Prod Readiness, Perf, Structural | Module-level dict, global key, no invalidation, no eviction | Per-user keys plus invalidate on write, or drop the cache (#4) |
| Click-listener leak and per-render wiring | Frontend, Perf | Event listener registered inside the render function | Delegate once at module scope (#10) |
| Pagination exists on the server but not in the UI | UX, Frontend, Perf | Client ignores `page`/`pages`; search is unpaginated and has no UI at all | Wire the page controls; paginate or cap search results (#11) |
| Dev defaults shipped as the only configuration | Prod Readiness, Repo Maintainer, DX | `config.py` constants with a developer path, debug on, all interfaces | Environment-driven config with safe defaults (#2, #9) |
| Focus, labels and keyboard operation | A11y, Design, UX | Controls built as `div`, outlines removed, label missing | Semantic controls and a shared `:focus-visible` rule (#13, #14, #15) |
| Duplicate and unused helpers | Repo Maintainer, Structural | `make_slug` in `server.py` duplicates `utils.slugify`; `slugify`/`truncate` are unused; `getNoteById` is unused | Use `utils.slugify` or delete both; remove dead code |

## All Recommendations

| # | Recommendation | Lens | File(s) | Fix |
|---|---------------|------|---------|-----|
| R1 | Replace hard-coded note-card colours with tokens so cards follow dark mode | Design | `app/static/style.css:91-98,104-108` | Define `--note-bg`, `--note-text`, `--danger` (light and dark) and use them; use `var(--border)` |
| R2 | Gate hover styles on `@media (hover: hover)`; add press feedback | Design | `app/static/style.css:77-79` | Wrap `:hover`; optional `:active` scale |
| R3 | Add loading, empty and error states to the notes list | Design, UX | `app/static/app.js`, `app/static/index.html:27` | Render "No notes yet. Add one above." when empty; show an error line on failed load |
| R4 | Increase hit areas | Design, A11y | `app/static/style.css:66-75,104-108` | Min 44px touch targets for Save and Delete |
| R5 | Confirm or allow undo for delete | UX | `app/static/app.js:23-27` | Inline "Delete? Yes / No" or a short undo toast |
| R6 | Disable Save while a request is in flight; show progress | UX | `app/static/app.js:30-43` | Set `disabled` on the submit button, re-enable in `finally` |
| R7 | Offer a way to edit a note and to search | UX | `app/static/*`, `app/server.py:48-80` | The PUT and search APIs exist but nothing in the page uses them |
| R8 | Support Cmd/Ctrl+Enter submit in the textarea | UX, DX | `app/static/app.js` | `keydown` handler that calls `form.requestSubmit()` |
| R9 | Show the new note without a full reload and keep focus sensible | UX, A11y | `app/static/app.js` | Return focus to the title field after save |
| R10 | Validate `title`/`body` types in `create_note` and `tags` in `update_note`; use `get_json(silent=True)` | Frontend, Prod | `app/server.py:43-44,52-58` | Return 400 with a message |
| R11 | Remove hidden coupling to the DOM at import time | Frontend | `app/static/app.js:1-2` | Script is at the end of `<body>`, so it works; add `defer` or a guard for resilience |
| R12 | Introduce a keyed/diffed list render or at least avoid rebuilding with `innerHTML = ""` | Frontend, Perf | `app/static/app.js:10-21` | Build a fragment and `replaceChildren` |
| R13 | Add `// @ts-check` or JSDoc types for the API payloads | Frontend | `app/static/app.js` | Document the `/api/notes` response shape |
| R14 | Break the `store` -> `server` import and drop lazy imports | Structural | `app/store.py:7`, `app/server.py` | See #6 |
| R15 | Give the cache a home with an explicit interface, or remove it | Structural | `app/cache.py` | See #4 |
| R16 | Have the CLI use the store (or a shared service), not raw SQL | Structural | `app/cli.py:23-26` | Single place that knows the schema |
| R17 | Use an application factory instead of a module-level `app` plus `python -m app.server` re-import | Structural | `app/server.py:10,83-87` | `create_app()`; keeps `__main__` out of the import graph |
| R18 | Remove or use `utils.slugify`/`truncate`; delete `make_slug` duplicate | Repo Maintainer | `app/utils.py`, `app/server.py:17-19` | One slug function, tested |
| R19 | Rename `getNoteById` to `get_note_by_id` or delete it (unused) | Repo Maintainer | `app/store.py:68-71` | Match snake_case convention used by every other function |
| R20 | Replace bare `except Exception` blocks | Repo Maintainer | `app/cli.py:14`, `app/store.py:88` | Specific exceptions plus logging |
| R21 | Add structured logging | Repo Maintainer, Prod | all of `app/` | `logging.getLogger(__name__)` with request context |
| R22 | Declare dev dependencies and add tests beyond pagination | Repo Maintainer | `pyproject.toml`, `tests/` | `pytest` as an optional dependency group; tests for store, routes, CLI |
| R23 | Document configuration and the auth assumption in the README | Repo Maintainer | `README.md` | Env vars, bind address, single-user note |
| R24 | Add `[build-system]` and package-data for `app/static` | Repo Maintainer, Prod | `pyproject.toml` | Static files are only found in editable installs (read-based, not tested) |
| R25 | Use a production WSGI server and a health endpoint | Prod | `app/server.py:83-87` | gunicorn/waitress, `/healthz` |
| R26 | Set SQLite busy timeout and WAL; enable `PRAGMA foreign_keys` | Prod | `app/store.py:24-27` | `sqlite3.connect(..., timeout=...)`; the `REFERENCES` clause is unenforced by default |
| R27 | Add indexes and a tag key | Prod, Perf | `app/store.py:9-21` | `CREATE INDEX ... ON notes(owner, updated_at)`, `tags(note_id)`; unique `(note_id, name)` |
| R28 | Return 404 for missing ids on PUT/DELETE | Prod, DX | `app/server.py:48-67` | Check `rowcount` |
| R29 | Add a schema version / migration path | Prod | `app/store.py:9-21` | `PRAGMA user_version` |
| R30 | Escape LIKE wildcards in search and cap results | Prod, Perf | `app/store.py:98-104` | `ESCAPE` clause and `LIMIT` |
| R31 | Make list and search payloads consistent | DX | `app/server.py:27-36,70-80` | Search results omit `tags` and `slug`; list includes them |
| R32 | Give the CLI useful help, exit codes and a `--db`/`--user` option | DX | `app/cli.py:36-53` | Examples in `--help`, non-zero exit on failure |
| R33 | `list` should show body preview and support `--json` | DX | `app/cli.py:18-20` | Machine-readable output |
| R34 | Fix N+1 tag queries | Perf | `app/server.py:33-35`, `app/store.py:60-65` | One `WHERE note_id IN (...)` query |
| R35 | Reuse one connection per request | Perf | `app/store.py:24-27` | Flask `g`-scoped connection; `with sqlite3.connect()` does not close it |
| R36 | Debounce any future search-as-you-type | Perf | (n/a today) | Note for when a search box is added |
| R37 | Give the form an accessible name and announce list updates | A11y | `app/static/index.html:18,27` | `aria-label` on the form; `aria-live="polite"` status line |
| R38 | Check placeholder and muted-text contrast in both themes | A11y | `app/static/style.css` | Not measured in this run |
| R39 | Respect `prefers-reduced-motion` for the one transition | A11y | `app/static/style.css:74` | Low risk (150 ms colour change); add a media query for consistency |

---

# Lens Reports

---

## 1. Design Engineer

**Verdict**: APPROVE WITH CHANGES

**Perspective**: Design Engineer (reference skills consulted: emil-design-engineering, make-interfaces-feel-better, web-animation-design)

### Plan Summary
Repo-health read of the visual layer: one HTML page, one 108-line stylesheet. The stack uses plain CSS custom properties in hex (not oklch tokens in a `globals.css`, which is an Orbit convention that does not exist here), with a `prefers-color-scheme` dark block.

### Files Reviewed

| File | Visual Role | Risk |
|------|-------------|------|
| `app/static/style.css` | Tokens, layout, controls, note cards | Medium |
| `app/static/index.html` | Structure of topbar, composer, notes list | Low |
| `app/static/app.js` | Builds note card markup (class names, structure) | Low |

### Critical Issues (Must Fix)

| # | Issue | File(s) | Impact | Fix |
|---|-------|---------|--------|-----|
| 1 | Text inputs and textarea set `outline: none` with only a border colour for state; no `:focus-visible` rule exists for them | `app/static/style.css:55-64` | Keyboard focus is invisible in the main form (the Save button does have one at lines 81-84) | Add `.composer input:focus-visible, .composer textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }` |

### Recommendations

| # | Issue | File(s) | Why | Fix |
|---|-------|---------|-----|-----|
| 1 | `.note` uses raw colours (`#e5e5e5`, `#fafafa`, `#222222`, `#b91c1c`) instead of the tokens | `app/static/style.css:91-98,104-108` | In dark mode the page background is `#1c1917` but note cards stay near-white, so the list reads as a different theme from the rest of the page; the hex values also bypass the token system | Add `--note-bg`, `--note-text`, `--danger` in both `:root` blocks; use `var(--border)` |
| 2 | Hover colour has no media gate | `app/static/style.css:77-79` | On touch screens a tap leaves the hover colour stuck | Wrap in `@media (hover: hover) and (pointer: fine)` |
| 3 | No loading, empty or error visual for the list | `app/static/index.html:27`, `app/static/app.js:4-8` | A first-time user sees an empty gap under "Your notes" | Add an empty-state message and a load-error line |
| 4 | Save button and Delete are under the 44px touch target guideline | `app/static/style.css:66-75,104-108` | Button is about 36px high (8px padding plus text); Delete is bare text | `min-height: 44px` on controls; padding on Delete |

### Nice-to-Haves

| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | `-webkit-font-smoothing: antialiased` on `body`; `text-wrap: balance` on headings | Polish from make-interfaces-feel-better |
| 2 | `:active` press feedback on the primary button | Tactile feedback |
| 3 | Long titles and bodies: add `overflow-wrap: anywhere` on `.note` | Long unbroken text can overflow the 640px column |
| 4 | Hover ease: `150ms ease` rather than `ease-out` for colour changes | web-animation-design guidance (minor) |

### Design System Compliance
Tokens exist and are used for the page, topbar, inputs and primary button, with a matching dark set. The break is the note card, which hardcodes six literal colours, so the most-used component sits outside the token system and does not adapt to dark mode. Radius is consistent (`var(--radius)` everywhere). `--muted` is defined but unused. Transitions name a specific property (`background-color`), not `all`, which is correct.

### Visual State Coverage

| Component/Element | Hover | Focus | Active | Disabled | Loading | Empty | Error | Dark Mode |
|-------------------|-------|-------|--------|----------|---------|-------|-------|-----------|
| Save button (`button.primary`) | Yes | Yes | No | Yes (style exists, never set) | No | n/a | No | Yes |
| Title input | No | No (outline removed) | No | No | n/a | n/a | No | Yes |
| Note textarea | No | No (outline removed) | No | No | n/a | n/a | No | Yes |
| Delete control | No | No (not focusable) | No | No | No | n/a | No | Partial (red fixed, card light) |
| Note card | n/a | n/a | n/a | n/a | No | No | No | No (hardcoded light) |
| Topbar link | No (default underline) | Browser default | No | n/a | n/a | n/a | n/a | Yes |

### Verdict Details
- Design Token Fidelity: CONCERNS (note card bypasses tokens)
- Visual State Coverage: CONCERNS (focus on inputs, empty/loading/error absent)
- Dark Mode Parity: CONCERNS (note cards)
- Animation Quality: PASS (one 150ms colour transition on a named property; no layout or transform animation; reduced-motion not declared but nothing moves)
- Visual Consistency: PASS (single radius token, consistent spacing scale of 8/12/16/24)

---

## 2. UX Engineer

**Verdict**: NEEDS REWORK

**Perspective**: UX Engineer (reference skills consulted: emil-design-engineering forms/controls)

### Plan Summary
A user opens the page, types a title and note, presses Save, and sees their notes listed; they can delete one. The CLI offers add/list/export.

### User Journey Map

| Step | Trigger -> Action -> Feedback -> Outcome | Status |
|------|------------------------------------------|--------|
| 1 | Open `/`: page loads, list fetches | WARN: no loading indicator; if there are no notes the area is blank (no empty state) |
| 2 | Type a title and body | OK for body (labelled); WARN for title (placeholder only) |
| 3 | Press Save (or Enter in the title field) | WARN: Enter in the single-line title submits; Cmd/Ctrl+Enter in the textarea does nothing |
| 4 | Request is sent | FAIL: no in-flight state, button stays clickable (double submit creates duplicates) |
| 5 | Server rejects the request (e.g. missing field -> HTTP 500) | FAIL: no response check; the empty `catch` hides network errors; `form.reset()` runs anyway and wipes the user's text |
| 6 | Success | WARN: the list reloads, but there is no confirmation and focus is not returned to the title |
| 7 | More than 20 notes exist | FAIL: only page 1 is requested and rendered; older notes are unreachable (`page`/`pages` in the response are ignored) |
| 8 | Delete a note | FAIL: one click deletes immediately with no confirmation and no undo; a plain text "Delete" at the card's right edge is easy to hit by mistake |
| 9 | Edit a note | FAIL: the API has PUT, the page has no edit control |
| 10 | Find a note | FAIL: the API has search, the page has no search box |

### Critical Issues (Must Fix)

| # | Issue | Step in Journey | Impact on User | Fix |
|---|-------|----------------|----------------|-----|
| 1 | Notes beyond the first 20 are unreachable from the page | 7 | Looks like data loss; the user cannot see or delete older notes | Add pagination or "Load more" using the `page`/`pages` values the API already returns |
| 2 | Save/delete failures are silent and the form is cleared even on failure | 4-5, 8 | A user can lose a long note with no message at all | Check `response.ok`; on failure keep the text and show an inline message saying what failed and what to do |

### Recommendations

| # | Issue | Impact | Fix |
|---|-------|--------|-----|
| 1 | Delete has no confirmation or undo | Accidental permanent loss | Inline confirm or undo toast, naming the note ("Delete 'Shopping list'?") |
| 2 | No empty state or loading state | First-time users see a blank list | Message: "No notes yet. Add one above." |
| 3 | Save is not disabled during the request | Duplicate notes on double click | Disable and relabel to "Saving..." |
| 4 | Edit and search exist in the API but not in the UI | Features are invisible to users | Add edit-in-place and a search field, or remove the endpoints |
| 5 | Cmd/Ctrl+Enter submit for the textarea | Standard for note apps | Key handler |

### Nice-to-Haves

| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Show timestamps (`updated_at` is returned) | Orientation in a long list |
| 2 | Preserve an unsent draft in `localStorage` | Accidental navigation loses text |
| 3 | Persist scroll/focus after delete | Reduces disorientation |

### Interaction Consistency Check
Only one interaction pattern exists (click a control, list reloads), so there is nothing to conflict with. The inconsistency is between surfaces: the CLI lists 50 notes and the web page 20, the CLI export returns all users' notes while the page shows only the caller's, and the API's search results have a different shape from the list results (no tags, no slug).

### Verdict Details
- Discoverability: CONCERNS (edit and search have no UI)
- Flow Completeness: CONCERNS (pagination missing, no edit)
- Error Recovery: CONCERNS (silent failures, form wiped)
- Feedback & Status: CONCERNS (no loading, saving, success or error states)
- Consistency: PASS (single simple pattern)

---

## 3. Frontend Engineer

**Verdict**: NEEDS REWORK

**Perspective**: Frontend Engineer. The codebase is 45 lines of vanilla JavaScript with no framework, TypeScript, state store or bundler, so the React/Zustand/Tailwind/Zod checks do not apply; the lens was applied to DOM handling, event wiring, async flow and data typing. `vercel-react-best-practices` was not applied (no React).

### Plan Summary
`app/static/app.js` fetches notes, renders them as HTML strings, wires Delete and a submit handler.

### Files Reviewed

| File | Frontend Role | Risk |
|------|--------------|------|
| `app/static/app.js` | All client logic | High |
| `app/static/index.html` | Markup, script include | Low |
| `app/static/style.css` | Styling (see Design lens) | Low |

### Critical Issues (Must Fix)

| # | Issue | File(s) | Why It Breaks | Code Fix |
|---|-------|---------|---------------|----------|
| 1 | Untrusted text goes into `innerHTML` | `app/static/app.js:15-19` | `note.title` and `note.body` are stored user input; whatever markup they contain is parsed and executed as HTML in every viewer's browser (stored XSS). The `data-id` attribute is built the same way. | `const h3 = document.createElement("h3"); h3.textContent = note.title;` and the same for the body; set `button.dataset.id = note.id`. |
| 2 | `document.addEventListener("click", ...)` is inside `render()` | `app/static/app.js:23-27` | Each render adds another listener. After three loads one Delete click fires three DELETE requests and three reloads; each reload adds another listener again. | Move one delegated handler to module scope: `list.addEventListener("click", ...)`. |
| 3 | `fetch` results are never checked and errors are swallowed | `app/static/app.js:5-6,25,35-42` | `response.json()` on an error page throws unhandled in `loadNotes`; delete ignores failures; the submit `catch (error) {}` is empty and `form.reset()` is inside the same `try`, so a non-2xx response (which does not throw) also resets the form. | `if (!response.ok) { showError(...); return; }` before reset or reload; log in `catch`. |

### Recommendations

| # | Issue | File(s) | Why | Fix |
|---|-------|---------|-----|-----|
| 1 | Ignores `page` and `pages` from the API | `app/static/app.js:5-8` | See UX #1 | Track page state and add controls |
| 2 | `render` rebuilds the list with `innerHTML = ""` and per-item appends | `app/static/app.js:11-21` | Many reflows, loses focus on reload | Build a `DocumentFragment` and `replaceChildren` |
| 3 | Module top-level `getElementById` with no null check | `app/static/app.js:1-2` | A markup change makes the script throw at load | Guard or use `defer` |
| 4 | Untyped API shape | `app/static/app.js` | `data.notes` fields used by convention only | JSDoc typedef for the note payload, optionally `// @ts-check` |

### Nice-to-Haves

| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Use `<template>` for the card markup | Keeps markup out of strings |
| 2 | `async`/`await` wrapper with one `request()` helper | Single place for errors and headers |
| 3 | Add `type="module"` | Scoped variables, deferred by default |

### Render Path Analysis
There is no reactive rendering; the only trigger is `loadNotes()`, called once at load, after each successful or failed-without-throw submit, and after each delete. Each call re-renders the whole list. Because of the leaking listener (Critical #2), delete triggers N `loadNotes()` calls where N is the number of prior renders, so work per click grows linearly with session activity. There is no memoisation need at this size.

### Type Safety Assessment
No TypeScript, no schema validation. The server's JSON is trusted as-is and then interpolated into HTML. On the server side, `request.json` is accessed with `data["title"]` and `data["body"]` unguarded (`app/server.py:43-44`), so the contract is enforced only by crashing.

### Verdict Details
- Component Architecture: PASS (nothing to split at this size; one concern per function, apart from the listener)
- State Management: CONCERNS (no page state; implicit global listener state)
- Type Safety: CONCERNS (no typed contract in either direction)
- Rendering Performance: CONCERNS (listener accumulation; full re-render each time, acceptable at 20 items)
- Bundle Impact: PASS (no dependencies, no bundle)

---

## 4. Backend Engineer

**Skipped** — Relevance rule: "No Rust/Tauri changes". This repository is a Python/Flask service with no Rust or Tauri code. The Python server and storage concerns (error propagation, resource lifecycle, concurrency, file system path) are covered in lenses 5, 6, 7, 8 and 9 and in the master critical list (#1-#4, #6-#9).

---

## 5. Structural Engineer

**Verdict**: NEEDS REWORK

**Perspective**: Systems/Structural Architect (reference skills: none applicable; the barrel-import guidance is React-specific)

### Plan Summary
Three layers in one package: HTTP (`server.py`), storage (`store.py`, `cache.py`), and a CLI (`cli.py`), plus helpers (`pagination.py`, `utils.py`, `config.py`). The dependency graph has one cycle and the storage layer reaches up into the HTTP layer.

### Files Reviewed

| File | Structural Role | Layer | Risk |
|------|----------------|-------|------|
| `app/server.py` | Routes, request identity, slug helper | HTTP | High |
| `app/store.py` | SQLite access | Storage | High |
| `app/cache.py` | Search cache | Storage-adjacent | Medium |
| `app/cli.py` | Command line | Interface | High |
| `app/config.py` | Constants | Config | Medium |
| `app/pagination.py` | Page maths | Helper | Low |
| `app/utils.py` | Text helpers (unused) | Helper | Low |

### Critical Issues (Must Fix)

| # | Issue | Files Involved | Structural Impact | Fix |
|---|-------|---------------|-------------------|-----|
| 1 | Storage imports the HTTP layer and reads the request object | `app/store.py:7` (`from app.server import current_user`), `app/store.py:39,48,56,102`, `app/server.py:29,41,50,64,72,84` | A cycle: `server` -> `store` -> `server`. It is only survivable because every route imports `store` inside the function. Any non-HTTP caller (the CLI) inherits a dependency on Flask and on an active request. Importing `store` also builds the Flask app. | Make `owner` a parameter of each store function; delete `current_user` from the import path of `store`; import `store` at the top of `server.py`. |

### Recommendations

| # | Issue | Why | Fix |
|---|-------|-----|-----|
| 1 | The CLI bypasses the store for export and talks SQL directly | Two places know the schema column list (`app/cli.py:25` and `app/store.py:9-21`) | Add `store.export_notes(owner)` |
| 2 | Module-level mutable cache with no owner | Hidden shared state between requests and users | Inject the cache or give it a small class with `get/put/invalidate` |
| 3 | `python -m app.server` re-imports `app.server` as a second module (through `store`'s import) | Two copies of module state; confusing for tests | Application factory, run via `flask run` or a separate `__main__.py` |
| 4 | Config is a module of constants read at import time | Cannot vary per environment or per test | Read from environment with defaults; pass into the factory |

### Nice-to-Haves

| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Split `server.py` into routes and a `schemas`/validation module as it grows | Cohesion, currently fine at 87 lines |
| 2 | Move `make_slug` to `utils` (and delete the duplicate) | Helper in the wrong layer |

### Dependency Map

```
cli.py ---------> store.py ---------> server.py   (store imports current_user)
   |                 |                    |
   |                 v                    +--> store.py   (lazy, inside each route)  <- cycle
   +--> config.py <--+                    +--> cache.py
                                          +--> pagination.py
utils.py  (imported by nothing)
tests/ ----> pagination.py only
```

Concerning arrows: `store -> server` (storage depends on HTTP, which reads `flask.request`); `server -> store` done lazily to hide the cycle; `cli -> store -> server -> flask` (a command-line tool pulls in the web framework). `utils.py` has no importers.

### Boundary Crossing Analysis

| Crossing | From -> To | Clean? | Notes |
|----------|-----------|--------|-------|
| Request identity into SQL | HTTP -> storage | No | Read implicitly inside `store` via `current_user()` |
| CLI to database | CLI -> SQLite | No | `cmd_export` opens the DB directly with its own column list |
| Routes to storage | `server` -> `store` | Partial | Works, but through function-local imports |
| Frontend to API | `app.js` -> `/api/*` | Partial | JSON shape is implicit; `page`/`pages` ignored |
| Config to modules | `config` -> others | Yes | Plain constants |

### Verdict Details
- Dependency Direction: CONCERNS (storage depends on HTTP)
- Module Coupling: CONCERNS (CLI coupled to Flask via store)
- Cohesion: PASS (files each do one job, apart from the duplicate slug helper)
- Layer Boundaries: CONCERNS (CLI and request identity cross layers)
- Change Propagation: CONCERNS (changing how identity works touches `store` in four functions plus the server)

---

## 6. Repo Maintainer

**Verdict**: APPROVE WITH CHANGES

**Perspective**: Repo Maintainer. Orbit-specific conventions (barrels, `@/` aliases, `bun run check`, `createLogger`, knip) do not exist here; the lens was applied to the conventions this repo itself shows.

### Plan Summary
A 10-file Python package with a tidy layout and a README that matches it, with a handful of dead or duplicated helpers and thin test coverage.

### Files Reviewed

| File | Convention Status | Risk |
|------|------------------|------|
| `README.md` | Matches layout; omits config and auth | Low |
| `pyproject.toml` | Minimal; no build-system, no dev dependencies | Medium |
| `app/server.py` | Consistent snake_case; duplicate slug helper | Medium |
| `app/store.py` | One camelCase function (`getNoteById`), unused | Low |
| `app/utils.py` | Both functions unused | Low |
| `app/cache.py` | Fine | Low |
| `app/cli.py` | Bare except | Medium |
| `tests/test_pagination.py` | Good tests, only module covered | Medium |

### Critical Issues (Must Fix)
None at the convention level. (The code-correctness criticals found by other lenses are listed in the master table.)

### Recommendations

| # | Issue | Why | Fix |
|---|-------|-----|-----|
| 1 | `make_slug` in `server.py:17-19` duplicates `utils.slugify`, and the two behave differently (`make_slug` drops non-ASCII characters; `slugify` transliterates and collapses runs) | Two definitions of "slug" | Keep `utils.slugify`, delete `make_slug`, add a test |
| 2 | `utils.truncate` and `utils.slugify` have no callers | Dead code | Use or remove |
| 3 | `store.getNoteById` is unused and the only camelCase name | Convention drift plus dead code | Delete or rename `get_note_by_id` |
| 4 | Bare `except Exception` in `cli.py:14` and `store.py:88` | Hides defects | Specific exceptions plus logging |
| 5 | No logging anywhere | Nothing to debug with | `logging.getLogger(__name__)` |
| 6 | Tests cover only `pagination.py`; `pytest` is configured but not declared as a dependency | The code with the most defects (store, server, cli) has zero tests | `[project.optional-dependencies] dev = ["pytest"]`; add route and store tests |
| 7 | `config.py` mixes dev-only values (absolute user path, debug) with real settings | Easy to ship by accident | Environment overrides |

### Nice-to-Haves

| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Add a linter/formatter config (ruff) to `pyproject.toml` | Enforces conventions mechanically |
| 2 | Type-check with mypy or pyright; many functions are already annotated | Cheap guard |
| 3 | README: mention `app/config.py`, the `X-User` header, and how to run tests | Onboarding |
| 4 | Add a CLAUDE.md or CONTRIBUTING for conventions | Optional at this size |

### Convention Compliance Checklist

| Convention | Status | Notes |
|-----------|--------|-------|
| File placement | OK | Layers match the README layout; static assets under `app/static/` |
| Naming conventions | Concerns | `getNoteById` is the only camelCase Python name |
| Barrel exports | n/a | `app/__init__.py` is empty; fine for this size |
| Import ordering | OK | Stdlib, third party, local, consistently grouped |
| Type imports separated | n/a | Python |
| Path aliases used | n/a | Python |
| No dead code left | Fail | `utils.py` (both functions), `getNoteById`, `make_slug` duplicate, `--muted` token unused |
| Structured logging | Fail | No logging at all; one `print("Error")` |
| No lint suppressions | OK | None found (no linter configured either) |
| CLAUDE.md present | Not present | Not required at this size |

### Reuse Opportunities
`utils.slugify` already does what `server.make_slug` does and does it better; `utils.truncate` could serve a future note-preview in the CLI `list` output (`app/cli.py:20`). `pagination.parse_page` is used by the list route but not by search or the CLI (which hard-codes `limit=50, offset=0`).

### Verdict Details
- File Organization: PASS
- Naming Consistency: CONCERNS (one outlier)
- Import Hygiene: PASS
- Code Reuse: CONCERNS (duplicate slug logic, unused helpers)
- Lint Compliance: CONCERNS (no lint tooling to measure against; bare excepts)

---

## 7. Production Readiness

**Verdict**: NEEDS REWORK

**Perspective**: Production Readiness Engineer (the one who gets paged)

### Plan Summary
A single-process Flask app with a per-call SQLite connection. As shipped it runs the development server in debug mode on all interfaces, trusts a client header for identity, and cannot start on a machine other than the author's.

### Files Reviewed

| File | Production Role | Risk |
|------|----------------|------|
| `app/config.py` | All runtime settings | High |
| `app/server.py` | Entry point and routes | High |
| `app/store.py` | Persistence | High |
| `app/cache.py` | Search results cache | High |
| `app/cli.py` | Operator tooling and export | Medium |
| `pyproject.toml` | Packaging | Medium |

### Critical Issues (Must Fix)

| # | Issue | File(s) | Production Failure Mode | Fix |
|---|-------|---------|------------------------|-----|
| 1 | Absolute developer path as database location | `app/config.py:3` | `sqlite3.connect` fails with "unable to open database file" anywhere that directory does not exist | Env-driven path with a sane default |
| 2 | Debug on, host `0.0.0.0` | `app/config.py:4-5`, `app/server.py:87` | Interactive debugger and reloader reachable from the network | Safe defaults; WSGI server |
| 3 | Identity from `X-User` header with no authentication | `app/server.py:13-14` | Any client can impersonate any user | Real auth or a trusted proxy contract |
| 4 | Update and delete do not check the owner | `app/store.py:74-95` | Any caller can change or remove any note by id | Owner predicate; 404 when nothing matched |
| 5 | Search cache shared across users and never invalidated | `app/cache.py`, `app/server.py:70-80` | Cross-user disclosure for 60 s; stale results after writes; unbounded growth | Per-user key, invalidate on write, bound size |
| 6 | `update_note` swallows errors and commits mid-way | `app/store.py:74-89` | Partial update (tags wiped), success reported, no log, connection left open | One transaction; propagate errors |

### Recommendations

| # | Issue | Why | Fix |
|---|-------|-----|-----|
| 1 | Flask dev server is the only run mode | Not intended for production use | gunicorn or waitress behind a proxy |
| 2 | No SQLite timeout, no WAL | "database is locked" under concurrent writers | `timeout=`, `PRAGMA journal_mode=WAL` |
| 3 | No indexes, no tag key, `REFERENCES` not enforced | Slow scans as data grows; duplicate tag rows; orphaned tags | Indexes, unique `(note_id, name)`, `PRAGMA foreign_keys=ON` |
| 4 | No schema versioning | `CREATE TABLE IF NOT EXISTS` cannot evolve the schema | `PRAGMA user_version` and migration steps |
| 5 | No logging, metrics or health endpoint | Cannot tell what happened after a failure | Logging, `/healthz` |
| 6 | PUT/DELETE answer success for ids that do not exist; `create_note` 500s on bad bodies | Misleading clients and noisy error pages | 404 / 400 with messages |

### Nice-to-Haves

| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Backup/restore note for the SQLite file in the README | Single file, easy to protect |
| 2 | Rate limiting or request size limit | Public exposure hardening |
| 3 | Pin dependency upper bounds / lock file | `flask>=3.0` floats |

### Failure Mode Analysis

| Scenario | What Fails | User Impact | Recovery | Plan Handles It? |
|----------|-----------|-------------|----------|-------------------|
| Run on any other machine | DB path does not exist | App errors on every request | Edit `config.py` | No |
| Second user sets `X-User` to another name | Authorization | Reads (and writes, per #4) another user's data | None | No |
| Concurrent writers | SQLite lock | Intermittent "database is locked" | Retry | No (no timeout set) |
| Failure partway through `update_note` | Tags committed away, update lost | Silent data loss with `{"ok": true}` | Restore from backup | No |
| Note created or deleted within 60 s of a search | Cache | Stale results | Wait for expiry | No |
| Many distinct search strings | Cache dict | Memory grows with no eviction | Restart | No |
| CLI used before the server ever ran | No tables | `jotter add` prints "Error" | Start the server once | No |
| Malformed JSON on create | `KeyError` | HTTP 500 | Client resend | No |
| Process killed mid-request | SQLite journal | Normally rolls back on next open | Automatic | Yes (SQLite default) |

### Environment Checklist

| Concern | Dev | Prod | Gap? |
|---------|-----|------|------|
| File paths | `/Users/dev/projects/jotter/notes.db` | Unknown, must be configurable | Yes |
| Network | `0.0.0.0:5000`, debug | Loopback or proxy, TLS at the proxy | Yes |
| Permissions | Author's own account | Service user with write access to the DB directory | Not addressed |
| Config | Constants in code | Environment variables | Yes |
| Build output | `pip install -e .` | Wheel install; static files need package-data (read-based, not tested) | Possible |

### Verdict Details
- E2E Flow: CONCERNS (cannot start off the author's machine; CLI needs the server to have run first)
- Error Recovery: CONCERNS (swallowed errors, no rollback)
- Data Integrity: CONCERNS (non-atomic update, no constraints, no ownership on writes)
- Environment Parity: CONCERNS (hard-coded path, debug default)
- Observability: CONCERNS (no logging anywhere)

---

## 8. DX Engineer

**Verdict**: NEEDS REWORK

**Perspective**: Developer Experience Engineer. The developer-facing surfaces here are the three-command CLI, the HTTP API, and the README setup path.

### Plan Summary
A developer installs the package, runs the server, and may use `jotter add|list|export`. The documented happy path breaks at the first CLI command.

### Files Reviewed

| File | DX Role | Risk |
|------|---------|------|
| `app/cli.py` | Command-line interface | High |
| `README.md` | Onboarding | Medium |
| `app/server.py` | HTTP API surface | Medium |
| `app/config.py` | Configuration | Medium |

### Critical Issues (Must Fix)

| # | Issue | Impact on Developer | Fix |
|---|-------|-------------------|-----|
| 1 | `jotter add` / `jotter list` depend on `current_user()` which reads `flask.request` (`app/store.py:7,39,48`); outside a request this raises a RuntimeError | The README's CLI examples do not work as written; `list` shows a traceback, `add` shows a bare "Error" | Pass the owner explicitly from the CLI (see Structural #1) |
| 2 | `cmd_add` catches everything and prints "Error"; the tables are never created by the CLI; exit status is always 0 | The developer cannot tell what went wrong or fix it; scripts cannot detect failure | `store.init()` at CLI start; catch specific exceptions; print what, why, what to do; `sys.exit(1)` |

### Recommendations

| # | Issue | Why | Fix |
|---|-------|-----|-----|
| 1 | No way to choose the database or user from the CLI or env | Config requires editing source | `--db`, `--user`, `JOTTER_DB` |
| 2 | `list` output is fixed-width text, 50 notes, no `--json`, no body | Hard to compose with other tools | `--json`, `--limit` |
| 3 | `export` has no overwrite warning and exports all users | Surprise data scope, privacy | Filter by owner, `--force`, stdout with `-` |
| 4 | `--help` has no examples; subcommand help is one line | Developers try `--help` first | Add epilog examples |
| 5 | API errors are inconsistent: update returns JSON `{"error": ...}`, create and delete return Flask's default HTML 500/404 pages | Clients cannot parse errors uniformly | One JSON error handler |

### Nice-to-Haves

| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | `jotter serve` command that wraps the server | One entry point |
| 2 | Shell completion | Convenience |
| 3 | Success output of `add` prints only the id | Pipeable |

### Error Message Audit

| Error Scenario | Current Message | What Developer Needs | Suggested Message |
|---------------|----------------|---------------------|-------------------|
| `jotter add` fails for any reason | `Error` | Cause and fix | `jotter: could not add note: no such table: notes. Run 'jotter init' or start the server once.` |
| `jotter list` outside a request | Python traceback (read-based expectation: Flask raises on `request` use outside a context) | Plain explanation | `jotter: no user set. Use --user or JOTTER_USER.` |
| `jotter export` with unwritable path | Python traceback | Path and reason | `jotter: cannot write /x/notes.json: permission denied` |
| `POST /api/notes` missing `title` | HTTP 500 HTML page | 400 with the field name | `{"error": "title is required"}` |
| `PUT` for a non-existent note | `{"ok": true}` | 404 | `{"error": "note 42 not found"}` |
| Title over 200 characters on `PUT` | `{"error": "title must be at most 200 characters"}` | Already good | (keep) |

### Developer Journey
First use: install, run the server, open the page; works if the DB directory exists, which it will not on any machine but the author's. Second step: the CLI example from the README fails. Daily use: no search UI, no edit UI, API fully scriptable but with `X-User` header semantics that are undocumented. Power use: no JSON output, no env configuration, no exit codes to script against.

### Verdict Details
- Error Quality: CONCERNS (one good message; the rest are bare or tracebacks)
- Defaults & Config: CONCERNS (hard-coded path; no overrides)
- Keyboard Experience: CONCERNS (no Cmd/Ctrl+Enter in the textarea)
- Discoverability: CONCERNS (README omits config, auth and API)
- Workflow Integration: CONCERNS (no `--json`, no exit codes)

---

## 9. Performance Engineer

**Verdict**: APPROVE WITH CHANGES

**Perspective**: Performance Engineer, adapted to a small web service and a browser tab left open for hours (no Tauri/IPC here; "IPC" is read as HTTP calls and SQLite connections). Reference skill `web-animation-design` consulted for the single transition.

### Plan Summary
Load is trivial at this size, so the findings concern things that grow with time or data: an unbounded cache, a leaking listener, per-call connections, and N+1 tag queries.

### Files Reviewed

| File | Performance Role | Risk |
|------|-----------------|------|
| `app/cache.py` | Module-level cache | Medium |
| `app/store.py` | Connections and queries | Medium |
| `app/server.py` | List route with per-note queries | Medium |
| `app/static/app.js` | Render loop, listeners | Medium |

### Critical Issues (Must Fix)

| # | Issue | File(s) | Impact | Fix |
|---|-------|---------|--------|-----|
| 1 | A document-level click listener is added on every render | `app/static/app.js:23-27` | After N renders one delete click sends N requests and triggers N reloads, each of which adds another listener; cost climbs for as long as the tab stays open | One delegated listener at module scope |

### Recommendations

| # | Issue | File(s) | Why | Fix |
|---|-------|---------|-----|-----|
| 1 | The cache never evicts: expired entries are skipped on read but stay in `_results` | `app/cache.py:5-20` | Memory grows with every distinct query string for the life of the process | Delete on expiry; cap size (`functools.lru_cache` or an `OrderedDict` cap) |
| 2 | N+1 on the list route: 1 query plus one `tags_for` call per note, each opening a new connection | `app/server.py:33-35`, `app/store.py:60-65` | About 22 connection opens and queries per page load at `PAGE_SIZE = 20` (count, list, 20 tag lookups) | One `SELECT note_id, name FROM tags WHERE note_id IN (...)` |
| 3 | No indexes on `notes(owner, updated_at)` or `tags(note_id)`; `search` is `LIKE '%q%'` with no `LIMIT` | `app/store.py:9-21,98-104` | Full scans and unbounded result sets as the table grows | Indexes; `LIMIT`; consider FTS5 later |
| 4 | Connections are opened per call, and `with sqlite3.connect()` only manages the transaction; it does not close the connection. `search` and `update_note` do not even use `with` | `app/store.py:24-104` | Connection objects linger until garbage collected; many opens per request | Per-request connection (Flask `g` plus teardown) with explicit close |

### Nice-to-Haves

| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Gzip or cache headers for static files | Minor at this size |
| 2 | Debounce when a search box is added | Prevents a request per keystroke |
| 3 | Store `updated_at` ordering with a tiebreaker (`id`) | Stable pagination when timestamps tie |

### Resource Budget

| Resource | Current | After Plan | Concern? |
|----------|---------|-----------|----------|
| HTTP calls per action | 1 load; 1 + N delete requests (N = prior renders) | 1 | Yes (listener leak) |
| Event listeners added | 1 per render (document level) | 1 total | Yes |
| Memory growth per hour | Cache grows per distinct query, never pruned | Bounded | Yes (unbounded) |
| Startup time impact | None (no heavy imports; Flask only) | None | No |
| Bundle size impact | 0 dependencies, about 1.2 KB of JS | Same | No |
| SQLite connections per list request | About 22 | 2 or 3 | Yes (minor today) |

### Hot Path Analysis
The hottest path is `GET /api/notes`: count query, list query, then one tags query per note, all on separate connections (`app/server.py:31-36`). It is fast at 20 notes on local disk but scales linearly with page size. On the client, the hot path is `render()`, which also re-registers the click listener each call (Critical #1). Search is not on any hot path because no UI calls it.

### Verdict Details
- Memory Management: CONCERNS (unbounded cache, leaking listener)
- IPC Efficiency: CONCERNS (N+1 queries, per-call connections)
- I/O Patterns: CONCERNS (no indexes, unbounded search)
- Startup Impact: PASS
- Long-Session Stability: CONCERNS (listener and cache growth)

---

## 10. Accessibility Engineer

**Verdict**: NEEDS REWORK

**Perspective**: Accessibility Engineer (reference skills consulted: emil-design-engineering touch-accessibility and forms-controls, web-animation-design for reduced motion). Contrast ratios were estimated from the colour values in `style.css`, not measured with a tool.

### Plan Summary
A one-page form and list. The structure (language attribute, viewport, `main`, `nav` with a label, heading order h1 -> h2, labelled section, a `<label>` on the textarea) is a decent base. The interactive pieces undo it.

### Files Reviewed

| File | A11y Role | Risk |
|------|----------|------|
| `app/static/index.html` | Landmarks, labels, headings | Medium |
| `app/static/app.js` | Builds the Delete control; dynamic updates | High |
| `app/static/style.css` | Focus styles, colours | High |

### Critical Issues (Must Fix)

| # | Issue | WCAG Criterion | File(s) | Impact | Fix |
|---|-------|---------------|---------|--------|-----|
| 1 | Delete is a `<div>` with a click handler: no role, no tabindex, no key handling | 2.1.1 Keyboard, 4.1.2 Name/Role/Value | `app/static/app.js:16,24`, `app/static/style.css:104-108` | Keyboard and screen-reader users cannot delete notes; assistive tech sees plain text | `<button type="button" class="delete" aria-label="Delete note: TITLE">Delete</button>` |
| 2 | `outline: none` on the title input and textarea with no replacement focus indicator | 2.4.7 Focus Visible | `app/static/style.css:55-64` | A keyboard user cannot see which field is active | `:focus-visible` outline using `--accent` |
| 3 | The title input has no `<label>`, only a placeholder | 1.3.1 Info and Relationships, 3.3.2 Labels or Instructions, 4.1.2 | `app/static/index.html:19` | Unnamed field for screen readers once typing starts; inconsistent with the labelled textarea | `<label for="title">Title</label>` |

### Recommendations

| # | Issue | WCAG Criterion | Fix |
|---|-------|---------------|-----|
| 1 | Dynamic list updates and errors are not announced | 4.1.3 Status Messages | `aria-live="polite"` region for "Note saved", "Note deleted", errors |
| 2 | The note list is not exposed as a list | 1.3.1 | Wrap items in `<ul>/<li>` (or `role="list"`) so users hear the count |
| 3 | Small hit areas (Delete is bare text; Save is about 36px tall) | 2.5.8 Target Size (Minimum) | 44px targets |
| 4 | Focus is lost after deleting or saving (the clicked element is destroyed on re-render) | 2.4.3 Focus Order | Move focus to the heading, the title field, or the next item |

### Nice-to-Haves

| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Give the form an accessible name (`aria-label="New note"`) | Landmark navigation |
| 2 | Verify placeholder contrast in both themes | Browser default placeholder colour on `--surface` was not measured; it can fall near 4.5:1 |
| 3 | Add a `prefers-reduced-motion` rule even though only a 150ms colour fade exists | Consistency if animation is added later |

### Keyboard Navigation Walkthrough

| Step | Action | Expected Focus | Expected Announcement | Plan Handles? |
|------|--------|---------------|----------------------|---------------|
| 1 | Tab from the page start | Topbar "Notes" link | "Main navigation, link, Notes" | Yes |
| 2 | Tab | Title input | "Title, edit" | Partly: no label, so the name depends on the placeholder; no visible focus ring |
| 3 | Tab | Textarea | "Note, edit, multiline" | Partly: label present; no visible focus ring |
| 4 | Tab | Save button | "Save, button" | Yes (has `:focus-visible`) |
| 5 | Press Enter on Save | Stays on Save | "Note saved" | No: no announcement; the form is reset silently |
| 6 | Tab through the notes | Each Delete control | "Delete, button" | No: Delete is a div, never receives focus |
| 7 | Press Enter/Space on Delete | Next note or heading | "Note deleted" | No |

### ARIA Checklist

| Element | Role | Label | States | Keyboard | Notes |
|---------|------|-------|--------|----------|-------|
| `<nav aria-label="Main">` | navigation | "Main" | n/a | Tab | Good; single link |
| `<main>` | main | n/a | n/a | n/a | Good |
| `<form id="new-note">` | form (unnamed) | none | n/a | Enter submits | Add a name |
| Title input | textbox | none (placeholder only) | n/a | Tab | Missing label |
| Note textarea | textbox | "Note" via `for` | n/a | Tab | Good label, no focus ring |
| Save button | button | "Save" | `disabled` styled but never set | Enter/Space | Good |
| `<section aria-labelledby>` | region | "Your notes" | n/a | n/a | Good |
| Note cards (`article`) | article | heading inside | n/a | n/a | Fine |
| Delete control | none (div) | text "Delete" | n/a | None | Fails |

### Verdict Details
- Screen Reader Compatibility: CONCERNS (unnamed input, non-semantic Delete, no live region)
- Keyboard Navigation: CONCERNS (Delete unreachable)
- Focus Management: CONCERNS (focus lost on re-render)
- Color Contrast: PASS on estimate for body text, links and buttons in both themes (large margin on the fixed colour pairs; placeholder not measured)
- Motion Sensitivity: PASS (only a 150ms background-colour transition; no movement)

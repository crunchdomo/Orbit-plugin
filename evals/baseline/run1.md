# Full Spectrum Audit: jotter 0.3.0 (Flask + SQLite + vanilla JS notes service)

**Date**: 2026-11-21
**Mode**: Repo Health (option 3, general repo health)
**Source**: working copy of the project directory `.../scratchpad/run1` (not a git repository, so no diff, history or branch was available)
**Lenses Run**: 9/10
**Lenses Skipped**: Backend Engineer (relevance rule: "No Rust/Tauri changes"; this repo has a Python backend and no Rust or Tauri, so the rule skips it. See the coverage note under the lens list.)

**Method note**: All findings come from reading every file in the project (14 files, about 480 lines) and reading each lens's SKILL.md. Nothing was executed (Flask is not installed in this environment, and no tests were run). Claims about runtime behaviour, such as the exponential listener growth or the CLI crash, are traced from the code and are marked "traced, not executed". The `web-design-guidelines` reference skill needs a network fetch of an external URL and was not applied.

**Coverage note on the skipped lens**: The Python server, store, cache and CLI are the bulk of this repo's risk. Because the Backend lens is Rust/Tauri-specific and skipped by its relevance rule, backend defects here were found only through the Structural, Production Readiness, DX and Performance lenses. There is no lens that reviews Python error-path and resource-lifecycle patterns directly.

**Lens relevance decisions**

| Lens | Run? | Why |
|------|------|-----|
| Design Engineer | Run | CSS and HTML UI exists |
| UX Engineer | Run | User-facing web page and CLI |
| Frontend Engineer | Run | JS and CSS exist (no React or TS; React-specific checks are marked N/A) |
| Backend Engineer | Skipped | No Rust/Tauri |
| Structural Engineer | Run | Multiple modules with cross-module imports |
| Repo Maintainer | Run | Never skipped |
| Production Readiness | Run | Never skipped |
| DX Engineer | Run | CLI commands, error messages, configuration |
| Performance Engineer | Run | State (cache), listeners, I/O |
| Accessibility Engineer | Run | Interactive UI (form, delete control) |

---

## Master Verdict: NEEDS REWORK

The project is small and has a clean, well-tested pagination module, parameterized SQL everywhere, semantic page landmarks and a reasonable token-based theme. But the core flows are broken or unsafe: the CLI cannot add or list notes because the data layer imports the HTTP layer, the search cache leaks one user's notes to another and grows without bound, notes are rendered through unescaped `innerHTML` (stored XSS), every render adds another click listener so deleting doubles the request count each time, and a failed save wipes the user's typed text. The shipped config (debug mode on all interfaces, a hardcoded home-directory database path) cannot run anywhere except the author's machine. Fifteen critical issues across nine lenses, with eight cross-cutting themes, put this firmly at NEEDS REWORK; most fixes are small and local.

## Verdict by Lens

| # | Lens | Verdict | Critical | Recommendations |
|---|------|---------|----------|-----------------|
| 1 | Design Engineer | APPROVE WITH CHANGES | 1 | 7 |
| 2 | UX Engineer | NEEDS REWORK | 2 | 8 |
| 3 | Frontend Engineer | NEEDS REWORK | 3 | 5 |
| 4 | Backend Engineer | Skipped (no Rust/Tauri) | - | - |
| 5 | Structural Engineer | APPROVE WITH CHANGES | 1 | 7 |
| 6 | Repo Maintainer | APPROVE WITH CHANGES | 0 | 10 |
| 7 | Production Readiness | NEEDS REWORK | 7 | 12 |
| 8 | DX Engineer | NEEDS REWORK | 3 | 10 |
| 9 | Performance Engineer | APPROVE WITH CHANGES | 2 | 6 |
| 10 | Accessibility Engineer | NEEDS REWORK | 3 | 7 |

Verdict convention used across lenses (the lens files define none): any critical issue means at least APPROVE WITH CHANGES; NEEDS REWORK where criticals show the lens's core area is broken in the main flow or there are three or more.

## All Critical Issues (Must Fix)

Collected from every lens, deduplicated (15 unique issues), ordered by severity (security and data loss first, then broken core flows, then accessibility and UX blockers).

| # | Issue | Lens(es) | File(s) | Impact | Fix |
|---|-------|----------|---------|--------|-----|
| C1 | Data layer imports the HTTP layer: `store.py` does `from app.server import current_user` and calls it inside every query. `current_user()` reads Flask's `request`, which only exists inside a web request, so the CLI (`jotter add`, `jotter list`) raises "Working outside of request context". It also forms a circular import (store -> server -> store), worked around by six lazy `from app import store` lines in routes. (traced, not executed) | Structural, Production Readiness, DX | `app/store.py:7,39,48,56,102`; `app/server.py:13-14,29,41,50,64,72,84`; `app/cli.py:12,19` | Two of the three CLI commands cannot work; layering is inverted | Make store functions take an explicit `owner: str` argument. Routes pass `current_user()`, the CLI passes a configured default. Delete the `app.server` import from store and the lazy imports from routes |
| C2 | Search cache is keyed by query string only, not by user. User A searches "tax"; user B searching "tax" within 60 seconds gets A's notes. (traced, not executed) | Production Readiness, Structural | `app/cache.py:9-20`; `app/server.py:74-80` | Cross-user disclosure of note contents | Key on `(owner, query)`, or cache inside `store.search` where the owner is known |
| C3 | Search cache never evicts. Expired entries are only skipped on read, never deleted, and there is no size cap, so every distinct query string (attacker-controlled) keeps its full result list in memory for the life of the process. | Performance, Production Readiness | `app/cache.py:5-20` | Unbounded memory growth, trivially triggered remotely | Bound with `functools.lru_cache`-style max size plus TTL purge on `put`, or drop the cache (SQLite `LIKE` over a small table is cheap) |
| C4 | `update_note` swallows every exception (`except Exception: pass`), commits the tag DELETE before the note UPDATE (delete-then-recreate with an intermediate commit), and never closes the connection. A failure leaves tags permanently deleted while the route still returns `{"ok": true}`. | Production Readiness | `app/store.py:74-89`; `app/server.py:58-59` | Silent partial writes and data loss, reported as success | Use `with connect() as conn:` and one transaction (no intermediate `commit`), let exceptions propagate, return 404 when `rowcount == 0` |
| C5 | Stored XSS: note title and body are interpolated into `innerHTML` unescaped. Any note containing markup runs script for every viewer; the API accepts arbitrary text and the server binds to `0.0.0.0`. | Frontend, Production Readiness | `app/static/app.js:15-19` | Script execution in other viewers' sessions | Build nodes with `textContent` (or escape), never string-interpolate into `innerHTML` |
| C6 | Click listener is registered on `document` inside `render()`, and `render()` runs on every `loadNotes()`. Each delete click fires every accumulated listener, each calling `loadNotes()`, which adds one more. Listener count doubles with every delete (1, 2, 4, 8, ...), and each handler issues its own DELETE and its own list fetch. (traced, not executed) | Frontend, Performance | `app/static/app.js:23-27` | Exponential request storm and memory growth after a handful of deletes | Register one delegated listener once, outside `render()`, on `#notes` |
| C7 | A failed save silently loses the user's input: `fetch` does not throw on HTTP 4xx/5xx and the code never checks `response.ok`, so `form.reset()` and a reload run even when the server returned an error; the `catch (error) {}` is empty, so network failures show nothing either. | UX, Frontend | `app/static/app.js:34-42` | Typed note destroyed with no message | Check `response.ok`; on failure keep the text, show the server's error; only `reset()` on success |
| C8 | Shipped config runs Flask with `DEBUG = True` on `HOST = "0.0.0.0"`. This exposes the Werkzeug interactive debugger (arbitrary code execution once the PIN is known or guessed) and verbose tracebacks to the whole network. | Production Readiness | `app/config.py:4-5`; `app/server.py:87` | Remote code execution risk | Default `DEBUG = False`, `HOST = "127.0.0.1"`, override via environment variables |
| C9 | Hardcoded developer path `DB_PATH = "/Users/dev/projects/jotter/notes.db"` with no environment override, and `store.init()` (table creation) runs only under `python -m app.server`. On any other machine the server cannot start; under a WSGI server or the CLI on a fresh database the tables do not exist. | Production Readiness, DX | `app/config.py:3`; `app/server.py:83-87`; `app/cli.py` (no init) | "Works on my machine"; zero-config fails | `DB_PATH = os.environ.get("JOTTER_DB", "notes.db")`, call `store.init()` from an app factory or at import |
| C10 | Ownership is not enforced and identity is not authenticated. `update_note`, `delete_note` and `getNoteById` take only an id (no owner check), and "who you are" is whatever `X-User` header the client sends (default `"local"`, which is what the web UI always uses, so all browser visitors share one account). | Production Readiness | `app/store.py:68-95`; `app/server.py:13-14,48-67` | Anyone who can reach the port can read, edit or delete anyone's notes | Add `AND owner = ?` to update and delete; decide and document the auth model (single-user local tool versus real auth) |
| C11 | Keyboard focus indicator removed from the text inputs: `outline: none` on `.composer input, .composer textarea` with no replacement (only `button.primary` has a `:focus-visible` style). | Accessibility, Design | `app/static/style.css:55-64` | Keyboard users cannot see which field is focused (WCAG 2.4.7) | Remove `outline: none`, or add `:focus-visible` with a visible ring/border change |
| C12 | The Delete control is a `<div>` with a click handler: not focusable, no role, not operable by keyboard or screen reader. | Accessibility, UX, Design | `app/static/app.js:16`; `app/static/style.css:104-108` | Notes cannot be deleted without a mouse (WCAG 2.1.1, 4.1.2) | Render a `<button type="button">` with an accessible name that includes the note title |
| C13 | The title input has no label (placeholder only, no `aria-label`), while the textarea next to it has one. | Accessibility | `app/static/index.html:19` | Screen readers announce an unnamed edit field; label vanishes on typing (WCAG 1.3.1, 3.3.2, 4.1.2) | Add `<label for="title">Title</label>` (visually hidden if desired) |
| C14 | The UI never shows pagination: `loadNotes()` fetches `/api/notes` with no `page` and ignores the `page`/`pages` fields. Only the 20 most recent notes are reachable; older notes look deleted. | UX | `app/static/app.js:4-8`; `app/server.py:31-36` | Data appears lost past 20 notes; README advertises pagination | Add next/previous controls (or load-more) driven by `page` and `pages` |
| C15 | `jotter add` catches every exception and prints the bare word `Error` on stdout, then exits with status 0. Combined with C1 it is the only output users ever see from `add`. | DX | `app/cli.py:10-16` | No cause, no fix hint, scripts and CI see success | Let the exception reach `main()`, print `jotter: <what failed>: <why>` to stderr, `sys.exit(1)` |

## Cross-Cutting Concerns

Issues flagged by 2+ lenses (all lens-section findings reference these):

| Concern | Flagged By | Root Cause | Unified Fix |
|---------|-----------|------------|-------------|
| Silent failure everywhere: `except Exception: pass`, `print("Error")`, empty `catch {}`, unchecked `response.ok`, no logging at all | Production Readiness, DX, UX, Frontend, Repo Maintainer | No error-handling convention; nothing is ever logged or surfaced | Fail loudly at each boundary: log in the server, return JSON error with status, show it in the UI, non-zero exit in the CLI. Add `logging` once |
| Identity and ownership model is implicit and inconsistent: owner comes from a global `request` read deep in the data layer, some queries filter by owner and some do not, the cache and the export ignore it | Structural, Production Readiness, DX | `current_user()` lives in the HTTP layer and is called from the store | Pass `owner` explicitly down to every store call, scope every query and cache key by it, decide on real auth |
| "Works on the author's machine" configuration: hardcoded DB path, debug on, bind all interfaces, port 5000 (taken by macOS AirPlay Receiver on recent macOS), init only in `__main__` | Production Readiness, DX, Repo Maintainer | `config.py` is constants, not environment-aware | Read config from environment with safe defaults, app factory with init on start |
| API and UI disagree: API supports pagination, update, tags, search; the page exposes none of them except add and delete | UX, Frontend, Structural, Repo Maintainer | UI and API grew separately, no shared contract | Either wire the UI to the API or remove the unused endpoints; document the API in the README |
| Delete control: a `<div>`, no confirmation, tiny target, listener bug | Accessibility, UX, Design, Frontend, Performance | One hand-rolled control built without a button element | One real `<button>` with name, confirm/undo, hit area, delegated handler |
| Missing UI states (empty, loading, error, disabled in use) and theme parity (notes ignore dark mode) | Design, UX, Accessibility, Frontend | Only the happy path was built; `.note` bypasses the token system | Add state markup plus an `aria-live` status region; move `.note` and delete colours to tokens |
| Unbounded or repeated resource use: cache never evicts, listeners accumulate, one SQLite connection per query (about 23 per page load) | Performance, Production Readiness, Frontend | No lifecycle thinking for long-running process or long-lived page | Bound the cache, delegate events once, one connection per request |
| Dead and duplicated code: `utils.slugify` / `truncate` unused while `make_slug` reimplements slugging, `getNoteById` unused (and camelCase), `--muted` and `:disabled` styles unused | Repo Maintainer, Structural, Design | Helpers written, then not wired in | Use `utils.slugify` (or delete utils), delete unused symbols |
| Test coverage covers only the one module without defects (`pagination.py`); store, server, cache, CLI untested | Repo Maintainer, Production Readiness | No tests written alongside the rest of the code | Add store, route and CLI tests; C1, C2, C4 would each fail on the first test |

## All Recommendations

Deduplicated across lenses. IDs here are master numbers; each lens section lists its own recommendations in full.

| # | Recommendation | Lens | File(s) | Fix |
|---|---------------|------|---------|-----|
| 1 | Theme the note cards and delete colour: `.note` hardcodes `#fafafa/#222/#e5e5e5`, so cards are light slabs in dark mode; `#b91c1c` is not a token | Design | `style.css:91-108` | Use `--surface`, `--text`, `--border`; add `--danger` with a dark variant |
| 2 | Add empty, loading and error states with a polite status region | Design, UX, A11y, Frontend | `index.html:27`, `app.js:4-8` | Placeholder text in `#notes`, `aria-live="polite"` status element |
| 3 | Delete needs confirm or undo and a unique accessible name | UX, A11y | `app.js:16` | `aria-label="Delete note: {title}"`, confirm or "Undo" toast |
| 4 | Preserve newlines and wrap long words in note text | Design, UX | `style.css:91-102` | `white-space: pre-wrap; overflow-wrap: anywhere` |
| 5 | Validate title on create too (client `required`, server rules shared with PUT); disable Save while a request is pending | UX, Frontend, Prod | `server.py:43-45`, `index.html:19`, `app.js:30-43` | Shared validator; `button.disabled = true` during submit (the `:disabled` style already exists) |
| 6 | Decide: wire edit, search and tags into the page, or remove the unused PUT/search/tags surface | UX, Structural, Repo | `server.py:48-80` | Product decision, see the decision list below |
| 7 | Guard against out-of-order `loadNotes` responses and handle load failure | Frontend, Perf | `app.js:4-8` | Request token or `AbortController`; try/catch with `response.ok` |
| 8 | JS hygiene: module or `defer` script, `// @ts-check` with JSDoc for the API shape | Frontend | `app.js`, `index.html:31` | `<script type="module">`, typed JSDoc |
| 9 | App factory with `init` at startup, remove lazy imports, production WSGI server | Structural, Prod | `server.py:83-87` | `create_app()`; run with waitress or gunicorn in docs |
| 10 | One slug implementation | Structural, Repo | `server.py:17-19`, `utils.py:9-13` | Use `utils.slugify` (handles Unicode via NFKD, `make_slug` drops non-ASCII), delete `make_slug` |
| 11 | Route `export` through the store, owner-scoped, atomic write, stdout option, no silent overwrite | Structural, DX, Prod | `cli.py:23-33` | `store.export_all(owner)`; write temp file then rename; `-` for stdout |
| 12 | Move caching behind `store.search`, keyed by owner, invalidated on add/update/delete | Structural, Perf | `cache.py`, `server.py:70-80` | Single call site that knows when data changes |
| 13 | Rename package `app` to `jotter` (project name is `jotter`; `app` is a generic top-level name that collides in site-packages) | Structural, Repo | `pyproject.toml:9`, all imports | Rename directory and imports |
| 14 | Remove dead code and fix naming: `getNoteById`, `utils.truncate`, unused `--muted` | Repo | `store.py:68`, `utils.py:16`, `style.css:5,17` | Delete, or use and rename to `get_note_by_id` |
| 15 | Add `[build-system]`, dev extras (pytest) and ruff config to `pyproject.toml`; make sure `app/static` ships in a built wheel | Repo, Prod | `pyproject.toml` | Add tables and package-data (unverified: not built) |
| 16 | Add tests for store, routes, cache, CLI | Repo, Prod | `tests/` | Start with one failing test each for C1, C2, C4 |
| 17 | Introduce `logging` and narrow the broad excepts | Repo, Prod, DX | `store.py:88`, `cli.py:14` | `logging.getLogger(__name__)`; catch specific exceptions |
| 18 | README: config, API routes, auth model, tests, production run; add `.gitignore` for `notes.db` and `__pycache__` | Repo, DX | `README.md` | Document and ignore |
| 19 | Enforce foreign keys and cascade; add indexes `notes(owner, updated_at)` and `tags(note_id)` | Prod, Perf | `store.py:9-21` | `PRAGMA foreign_keys=ON`, `ON DELETE CASCADE`, `CREATE INDEX` |
| 20 | Close connections (`with sqlite3.connect()` commits but does not close) and use one per request | Prod, Perf | `store.py:24-27,98-104` | `contextlib.closing`, or Flask `g` with teardown |
| 21 | Remove the tags N+1 (one query per note, each on a new connection) | Perf | `server.py:33-35`, `store.py:60-65` | One query `WHERE note_id IN (...)` or a join |
| 22 | Search: add LIMIT, escape `%` and `_`, ignore empty query | Perf, Prod | `store.py:98-104` | `LIMIT 50`, `ESCAPE '\'`, min length |
| 23 | Request limits and JSON error handlers for `/api` (404/415/500 currently return HTML, which breaks `response.json()`) | Prod, DX, Frontend | `server.py` | `MAX_CONTENT_LENGTH`; `@app.errorhandler` returning JSON |
| 24 | `update_note` on a missing id returns `{"ok": true}` and inserts orphan tags | Prod, UX | `store.py:74-89`, `server.py:58-59` | Check `rowcount`, return 404 |
| 25 | Schema versioning, health endpoint, pinned dependency upper bound or lockfile | Prod | `store.py:9-21`, `pyproject.toml:6` | `PRAGMA user_version`, `/healthz`, lockfile |
| 26 | Make the port configurable; 5000 collides with macOS AirPlay Receiver | DX, Prod | `config.py:6` | `PORT` from env |
| 27 | CLI ergonomics: `--db`/env var, `list --limit --json`, body from stdin, `--help` examples, non-zero exit and stderr on failure | DX | `cli.py` | argparse changes |
| 28 | CLI parity and entry points: `delete`, `search`, `edit`, `serve` subcommands | DX | `cli.py` | Add subcommands |
| 29 | Cmd/Ctrl+Enter submits the form | DX | `index.html:21` | Key handler on textarea |
| 30 | Announce list changes and manage focus after delete | A11y | `app.js:20-27` | live region; focus to heading or next item |
| 31 | Raise Delete target to at least 24 by 24 px (WCAG 2.5.8) | A11y, Design | `style.css:104-108` | Padding on a real button |
| 32 | Single-link `<nav>` is redundant; header link distinguished by colour only | A11y, UX | `index.html:12-14`, `style.css:39-41` | Remove or add `aria-current` and underline |
| 33 | Gate hover styles with `@media (hover: hover)`; add `:active` feedback | Design | `style.css:77-79` | Media query |
| 34 | Describe errors via `aria-describedby` once errors exist | A11y | `index.html` | Associate error text with input |
| 35 | `parse_page` repeats the page-count arithmetic that `Page.pages` already has | Repo | `pagination.py:18,33` | Build the Page and clamp, or share one helper |

---

# Lens Reports

---

## 1. Design Engineer

**Verdict**: APPROVE WITH CHANGES

# Design Engineering Audit: jotter web page

**Perspective**: Design Engineer
**Date**: 2026-11-21
**Plan**: n/a (Repo Health mode; the repo itself)

### Plan Summary
A single-column notes page: header, a composer form (title, body, Save) and a list of note cards, themed through CSS custom properties with a `prefers-color-scheme` dark variant.

### Files Reviewed
| File | Visual Role | Risk |
|------|-------------|------|
| `app/static/style.css` | Token definitions, all component styles | Medium |
| `app/static/index.html` | Structure, class hooks | Low |
| `app/static/app.js` | Builds note cards (`.note`, `.delete`) via `innerHTML` | Medium |

Calibration: UI present, so a full audit. Note on method: the lens text assumes an oklch `globals.css` with `html.dark`; this repo uses hex tokens on `:root` with a `prefers-color-scheme: dark` override. Fidelity is judged against this repo's own token system.

### Critical Issues (Must Fix)
| # | Issue | File(s) | Impact | Fix |
|---|-------|---------|--------|-----|
| C11 | `outline: none` on the title input and textarea with no focus replacement | `style.css:63` | Focused input is visually indistinguishable from unfocused | Delete the declaration, or add `.composer input:focus-visible, .composer textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }` |

### Recommendations
| # | Issue | File(s) | Why | Fix |
|---|-------|---------|-----|-----|
| D1 | `.note` hardcodes `border #e5e5e5`, `background #fafafa`, `color #222222`; the tokens are bypassed | `style.css:91-98` | In dark mode the whole list renders as bright slabs on a dark page (readable, but the one content area ignores the theme; this is the lens's #1 miss) | `border: 1px solid var(--border); background: var(--surface); color: var(--text);` |
| D2 | Delete colour `#b91c1c` is a raw value; no dark variant | `style.css:104-108` | Fragments the token system; contrast was only checked against the light card (about 6.2:1, passes) | Add `--danger` to `:root` and the dark block |
| D3 | Missing states: list empty, loading and error have no markup or styles; `button.primary:disabled` is styled but nothing ever disables the button; no `:active` | `index.html:25-28`, `style.css:86-89` | Real UIs need all of them; dead CSS is a signal the JS never caught up | Add empty-state text and a status area; disable Save while submitting |
| D4 | Text overflow and line breaks: no `overflow-wrap` and no `white-space` handling; a 200-character title or a long URL can overflow the 640 px column and note newlines collapse into one paragraph | `style.css:91-102` | Titles allow 200 characters (`config.py:8`) | `overflow-wrap: anywhere` on `.note`; `white-space: pre-wrap` on the body |
| D5 | Delete is unstyled text floated right: no hover, focus or active state, and a hit area of about 18 px tall | `style.css:104-108` | Poor affordance; below the 40 px target the polish guidance suggests | Style it as a button with padding, hover, focus-visible |
| D6 | `--muted` is defined in both themes and used nowhere | `style.css:5,17` | Dead token; secondary text (for example a timestamp) has no home | Use it for a note timestamp or remove it |
| D7 | Hover style on the primary button is not gated for touch | `style.css:77-79` | Sticky hover on touch devices | `@media (hover: hover) { ... }` |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | `text-wrap: balance` on headings, `pretty` on note body | Cleaner line breaks |
| 2 | `-webkit-font-smoothing: antialiased` on `body` | Crisper text on macOS |
| 3 | `transform: scale(0.97)` on `button.primary:active` | Tactile feedback; a transform is GPU-friendly and the existing transition would need to list `transform` explicitly |
| 4 | Subtle focus-within border on the composer inputs | Matches the button's focus language |

### Design System Compliance
Mostly sound: eight colour tokens with a complete dark override, a single `--radius` used consistently on inputs, button and cards, and a regular 8/12/16/24 px spacing scale. The one transition is specific-property (`background-color 150ms ease-out`), which is the right form (no `transition: all`). Fragmentation is limited to `.note` and `.delete`, which are the highest-visibility elements on the page. `--muted` is unused. Because the button is `var(--bg)` text on `var(--accent)`, the pairing inverts correctly in dark mode (dark text on pale blue).

### Visual State Coverage
| Component/Element | Hover | Focus | Active | Disabled | Loading | Empty | Error | Dark Mode |
|-------------------|-------|-------|--------|----------|---------|-------|-------|-----------|
| Save button (`button.primary`) | Yes | Yes (`focus-visible`) | No | Styled, never applied | No | n/a | No | Yes |
| Title input | No | **Removed** (`outline: none`) | n/a | No | n/a | n/a | No | Yes |
| Note textarea | No | **Removed** (`outline: none`) | n/a | No | n/a | n/a | No | Yes |
| Note card (`.note`) | n/a | n/a | n/a | n/a | n/a | n/a | n/a | **No** (hardcoded light) |
| Delete control | No | No (not focusable) | No | No | n/a | n/a | No | Light only (hardcoded) |
| Notes list (`#notes`) | n/a | n/a | n/a | n/a | **No** | **No** | **No** | Container yes, cards no |
| Header link | Browser default | Browser default | n/a | n/a | n/a | n/a | n/a | Yes |

### Verdict Details
- Design Token Fidelity: CONCERNS (`.note`, `.delete`)
- Visual State Coverage: CONCERNS (focus on inputs, list states, delete states)
- Dark Mode Parity: CONCERNS (note cards)
- Animation Quality: PASS (one 150 ms colour transition on a specific property; nothing that needs reduced-motion handling)
- Visual Consistency: PASS (one radius, regular spacing)

---

## 2. UX Engineer

**Verdict**: NEEDS REWORK

# UX Audit: jotter web page and CLI

**Perspective**: UX Engineer
**Date**: 2026-11-21
**Plan**: n/a (Repo Health mode)

### Plan Summary
A user opens the page, types a title and note, saves, and sees notes listed newest first with a Delete link on each. The API also supports edit, tags, search and pages, none of which the page exposes.

### User Journey Map
| Step | Trigger -> Action -> Feedback -> Outcome | Status |
|------|------------------------------------------|--------|
| 1. First visit | Open `/`: heading "Your notes", an empty area | WARN: no empty state, no hint what to do |
| 2. Create | Type title and body, click Save | WARN: title is not required, so a blank note can be saved |
| 3. Save feedback | Form clears, list reloads | WARN: the form clears whether or not the save worked (C7); no confirmation |
| 4. Save fails (server 4xx/5xx or network) | Same code path as success | FAIL: text lost, no error shown |
| 5. Read many notes | Scroll list | FAIL: only the newest 20 appear; no way to reach the rest (C14) |
| 6. Read a multi-line note | View card | WARN: newlines collapse into one paragraph; no date shown even though order is by `updated_at` |
| 7. Edit a note | n/a | FAIL: no UI, even though `PUT /api/notes/<id>` exists |
| 8. Find a note | n/a | FAIL: no search UI, although `/api/search` exists |
| 9. Tags | n/a | FAIL: tags are stored and returned but never shown or editable |
| 10. Delete | Click Delete text | WARN: instant, permanent, no confirmation or undo; the target is small and sits at the card's top-right corner; not keyboard reachable (C12) |
| 11. Delete again and again | Each delete fires more requests than the last (C6) | FAIL: behaviour degrades with use |
| 12. Server down | Page loads, `loadNotes` rejects | FAIL: unhandled promise rejection, list stays blank, no message |

### Critical Issues (Must Fix)
| # | Issue | Step in Journey | Impact on User | Fix |
|---|-------|----------------|----------------|-----|
| C7 | Save failure silently clears the form | 3, 4 | Lost note, user not told | Check `response.ok`; keep text; show error from the server |
| C14 | No pagination UI; notes past 20 unreachable | 5 | Looks like data loss | Next/previous or load-more using `page` and `pages` |

### Recommendations
| # | Issue | Impact | Fix |
|---|-------|--------|-----|
| U1 | No empty state | First-time user sees nothing | "No notes yet. Write one above." |
| U2 | No loading or error feedback for list load and save | Anxiety, silent failure | Status line with message; show the server's error text |
| U3 | Delete has no confirmation or undo | Irreversible one-click data loss | Inline confirm, or soft-delete with an Undo notice |
| U4 | Blank title accepted by the UI and by `POST /api/notes` (only PUT validates) | Notes that render as an empty card with only Delete | `required` on the input; same server validation on create |
| U5 | Newlines flattened; no timestamp | Hard to read; order unexplained | `white-space: pre-wrap`; show `updated_at` in muted text |
| U6 | Edit, search and tags exist in the API but not the page | Features invisible | Wire them in, or remove them (decision listed below) |
| U7 | Double-submit possible; Save is never disabled while a request is in flight | Duplicate notes on slow networks | Disable the button during the request |
| U8 | Header nav has one link, "Notes", pointing at the page you are on | Noise | Remove until there is a second destination |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Keep a draft in `localStorage` so an accidental reload does not lose text | Context loss on navigation |
| 2 | Focus the title input after a successful save | Fast repeat entry for power users |

### Interaction Consistency Check
The page has two interaction styles for actions: a styled primary button (Save) and an unstyled text "Delete" that behaves like a button but looks like a label. The API returns JSON errors for PUT validation (`{"error": "title is required"}`) but HTML error pages for everything else (404, 415, 500), which the page cannot parse. There is no pattern to compare against beyond this single screen.

### Verdict Details
- Discoverability: CONCERNS (edit, search, tags, older notes not reachable)
- Flow Completeness: CONCERNS (create and delete only; no read-all)
- Error Recovery: CONCERNS (C7)
- Feedback & Status: CONCERNS (no states, no confirmation)
- Consistency: CONCERNS (Delete versus Save; JSON versus HTML errors)

---

## 3. Frontend Engineer

**Verdict**: NEEDS REWORK

# Frontend Engineering Audit: jotter `app.js`

**Perspective**: Frontend Engineer
**Date**: 2026-11-21
**Plan**: n/a (Repo Health mode)

### Plan Summary
A 45-line vanilla JS file that loads notes, re-renders the whole list through `innerHTML`, submits the form and deletes by delegated click. There is no React, TypeScript, Zustand or bundler; lens checks for those (Immer, Zustand selectors, Zod, memoisation, barrels, dynamic Tailwind classes) are N/A, and the equivalent browser-level concerns were applied instead.

### Files Reviewed
| File | Frontend Role | Risk |
|------|--------------|------|
| `app/static/app.js` | All client logic | High |
| `app/static/index.html` | Markup and script include | Low |
| `app/static/style.css` | Styling (design lens covers detail) | Low |

### Critical Issues (Must Fix)
| # | Issue | File(s) | Why It Breaks | Code Fix |
|---|-------|---------|---------------|----------|
| C5 | `innerHTML` with unescaped `note.title` and `note.body` | `app.js:15-19` | Any note text that contains markup is parsed as HTML; stored XSS | Create nodes with `document.createElement` and set `textContent` |
| C6 | `document.addEventListener("click", ...)` is inside `render()` | `app.js:23-27` | Each `loadNotes()` adds a listener; each click then fires them all and each calls `loadNotes()`; count doubles per delete | Move the listener out and delegate on `list`: `list.addEventListener("click", ...)` once at load |
| C7 | No `response.ok` check, empty `catch`, `form.reset()` runs on failure | `app.js:34-42` | HTTP errors do not reject `fetch`; the error path never executes | `if (!response.ok) { show(await response.json()); return; }` before `reset()` |

### Recommendations
| # | Issue | File(s) | Why | Fix |
|---|-------|---------|-----|-----|
| F1 | `loadNotes` has no try/catch and no `ok` check; `response.json()` on an HTML error page throws | `app.js:4-8` | Unhandled rejection, stale or blank list | Wrap and show a status message |
| F2 | Out-of-order responses: overlapping `loadNotes()` calls (create plus delete, or the C6 storm) can render an older response last | `app.js:4-8` | Stale list after rapid actions | Track a request counter, or abort the previous request |
| F3 | No contract for the API shape (`data.notes`, `note.id`, `note.title`, `note.body`) | `app.js` | Silent breakage when the server changes | `// @ts-check` plus a JSDoc typedef |
| F4 | Top-level `const list` and `const form` in a classic script; no `defer` or module | `app.js:1-2`, `index.html:31` | Pollutes global scope; works only because the script sits at the end of body | `<script type="module" src=...>` |
| F5 | Click filter uses `event.target.classList.contains("delete")` | `app.js:24` | Breaks if the control gains child nodes (an icon) | `event.target.closest("[data-id]")` |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Keep a `state` object (`page`, `pages`, `notes`) separate from the DOM | Needed for pagination (C14) |
| 2 | Re-render by diffing or by appending only the new note | Irrelevant at 20 items, useful later |

### Render Path Analysis
Trigger sources: page load, form submit, every delete click. Each trigger calls `loadNotes()`, which fetches, then `render()`, which clears `#notes` and rebuilds all cards, then adds one more document-level click listener. Because the listener is on `document`, it is never removed and not scoped to the list. After k deletes there are roughly 2^k listeners (traced, not executed): each fires its own DELETE and its own `loadNotes()`, and each of those calls adds a listener. Submits add one listener each too. There is no unmount concept in this page, so the leak is permanent for the tab's lifetime.

### Type Safety Assessment
There are no types. The response shape is implicit, `event.target.dataset.id` is a string interpolated into a URL, and `data.notes` is assumed present (an HTML error response would make `response.json()` throw). The server side has type hints but no schema shared with the client. React/Zod/strict-boolean checks are N/A.

### Verdict Details
- Component Architecture: CONCERNS (single render function mixes DOM building and event wiring)
- State Management: CONCERNS (no client state; pagination fields discarded)
- Type Safety: CONCERNS (no contract)
- Rendering Performance: CONCERNS (C6 request and listener growth)
- Bundle Impact: PASS (one 45-line file, no dependencies)

---

## 4. Backend Engineer

**Skipped**: relevance rule "No Rust/Tauri changes". The repo's backend is Python (Flask, sqlite3) with no Rust crates, Tauri commands, IPC protocol or sidecars. See the coverage note at the top: Python backend defects were covered by the Structural, Production Readiness, DX and Performance lenses only.

---

## 5. Structural Engineer

**Verdict**: APPROVE WITH CHANGES

# Structural Audit: jotter module layout

**Perspective**: Systems/Structural Architect
**Date**: 2026-11-21
**Plan**: n/a (Repo Health mode)

### Plan Summary
Seven small Python modules plus a static front end. The layering is almost right (config, pagination, store, server, cli) except that the data layer depends on the HTTP layer.

### Files Reviewed
| File | Structural Role | Layer | Risk |
|------|----------------|-------|------|
| `app/server.py` | Routes, identity (`current_user`), slug helper, entry point | HTTP | High |
| `app/store.py` | SQLite access | Data | High |
| `app/cache.py` | Search cache | Service (wrong place) | Medium |
| `app/cli.py` | Command line | Interface | High |
| `app/config.py` | Constants | Config | Low |
| `app/pagination.py` | Offset pagination | Pure helper | Low |
| `app/utils.py` | Slug and truncate helpers | Pure helper (unused) | Low |
| `app/static/*` | Web page | Client | Medium |

### Critical Issues (Must Fix)
| # | Issue | Files Involved | Structural Impact | Fix |
|---|-------|---------------|-------------------|-----|
| C1 | `store.py` imports `current_user` from `server.py` (`store.py:7`), inverting the dependency (data depends on HTTP) and creating a cycle (`server` lazily imports `store`; `store` imports `server`). The workaround is a `from app import store` inside six functions in `server.py`. The CLI imports `store`, so it drags in Flask and fails on `request` | `store.py`, `server.py`, `cli.py` | Wrong dependency direction, hidden global (Flask `request`) inside data access, CLI broken | `store` takes `owner` as a parameter; `current_user()` is called in routes only; import `store` at the top of `server.py` |

### Recommendations
| # | Issue | Why | Fix |
|---|-------|-----|-----|
| S1 | `store.init()` is invoked only from `server.py`'s `__main__` block | Any other entry point (CLI, WSGI) has no tables; `python -m app.server` also makes `store`'s `from app.server import ...` import the module a second time under the name `app.server` | App factory `create_app()` that calls `init()`, used by CLI and server |
| S2 | Slug logic exists twice: `server.make_slug` (drops non-ASCII) and `utils.slugify` (Unicode-aware); the second is unused | Duplication, divergent behaviour | Keep `utils.slugify`, delete `make_slug` |
| S3 | `cli.cmd_export` opens its own `sqlite3` connection and hard-codes the column list | Schema knowledge in two places; bypasses the row factory and owner filter, and exports every user's notes | `store.export_all(owner)` |
| S4 | Cache lives in the HTTP layer (`server.search`), so nothing that mutates notes can invalidate it | Staleness (deleted notes served up to 60 s) and the C2 key bug | Cache inside the store or a service function that also owns mutations |
| S5 | Input validation exists only in `PUT` (`server.py:52-57`) | Rules duplicated or missing per route | One `validate_note(data)` function used by create and update |
| S6 | Top-level package is named `app` while the project is `jotter` | Generic name collides when installed beside other projects | Rename to `jotter` |
| S7 | API surface is undocumented and partly unused by the client (`PUT`, `/api/search`, `tags`) | Contract only exists in the code | Document routes in the README or delete unused ones |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Introduce a `Note` dataclass instead of `dict` | Typed boundary between store and routes |
| 2 | Use Flask blueprints once the route count grows | Not needed at six routes |

### Dependency Map
```
            config  <------------------------------+
              ^                                    |
   cache      |                                    |
     ^   +----+-----+        pagination   utils    |
     |   |          |           ^        (unused)  |
  server -+--> store <--- cli ---+-------------+----+
     ^          |   \
     |          |    +--- sqlite3 (direct, from cli.cmd_export)
     +----------+   store --imports--> server   <-- cycle (C1)
                    server --lazy imports--> store (x6)
```
Concerning arrows: `store -> server` (data to HTTP; cycle), `cli -> sqlite3` (bypasses store), `utils` has no inbound arrows, `cache` is called from `server` only.

### Boundary Crossing Analysis
| Crossing | From -> To | Clean? | Notes |
|----------|-----------|--------|-------|
| Identity lookup | store -> server | No | Global `request` read in the data layer (C1) |
| Lazy store import | server -> store | No | Six function-level imports to avoid the cycle |
| Export | cli -> sqlite3 | No | Duplicates store, ignores owner |
| Cache use | server -> cache | Partly | Works but cannot be invalidated by writes |
| Client contract | app.js -> `/api/notes` | Partly | JSON shape implicit; `page`/`pages` ignored |
| Pagination | server -> pagination | Yes | Pure function, tested |

### Verdict Details
- Dependency Direction: CONCERNS (store -> server)
- Module Coupling: CONCERNS (cycle, direct sqlite use in CLI)
- Cohesion: CONCERNS (`server.py` holds identity, slug and routes; unused `utils.py`)
- Layer Boundaries: CONCERNS
- Change Propagation: CONCERNS (adding a note field touches four SQL statements in `store.py`, the hard-coded columns in `cli.cmd_export`, and the route)

---

## 6. Repo Maintainer

**Verdict**: APPROVE WITH CHANGES

# Repo Maintenance Audit: jotter

**Perspective**: Repo Maintainer
**Date**: 2026-11-21
**Plan**: n/a (Repo Health mode)

### Plan Summary
A small Python repo with one test file. The TypeScript-oriented convention list (barrel exports, `import type`, `@/` aliases, Clippy, knip) is mostly N/A; the equivalents (naming, dead code, reuse, lint, logging, docs) were checked instead. Git history and any CI or ignore files could not be checked because the directory is not a git repository.

### Files Reviewed
| File | Convention Status | Risk |
|------|------------------|------|
| `app/pagination.py`, `tests/test_pagination.py` | Good: typed, docstrings, tests | Low |
| `app/utils.py` | Well written but unused | Low |
| `app/store.py` | One camelCase name, dead function, broad except | Medium |
| `app/server.py` | Duplicate slug helper, repeated lazy imports, one long line (line 57, over 100 characters) | Medium |
| `app/cli.py` | Broad except, bypasses store | Medium |
| `app/cache.py` | Fine style, wrong layer | Low |
| `app/config.py` | Constants only | Low |
| `app/static/*` | Dead CSS, unused token | Low |
| `pyproject.toml`, `README.md` | Thin | Medium |

### Critical Issues (Must Fix)
None found. (Convention-level problems here are covered by correctness criticals in other lenses: C1, C4, C15.)

### Recommendations
| # | Issue | Why | Fix |
|---|-------|-----|-----|
| R1 | Dead code: `store.getNoteById` (no callers), `utils.slugify` and `utils.truncate` (no callers; only the README mentions the module), `Page.has_next` (used only by a test), `--muted` token, `button.primary:disabled` | Old helpers left behind | Delete, or wire in (see Reuse Opportunities) |
| R2 | `getNoteById` is the only camelCase name in a snake_case codebase | Convention drift | Rename `get_note_by_id` or delete |
| R3 | No lint, format or type tooling configured (`pyproject.toml` has no ruff/black/mypy section) and no dev dependency for pytest; no `[build-system]` table | Conventions are unenforced | Add ruff and a `dev` extra with pytest |
| R4 | Tests cover only `pagination.py` | The modules with defects (store, server, cache, CLI) have none | Add tests; start with C1, C2, C4 |
| R5 | No logging anywhere in the codebase | Nothing can be diagnosed in production | `logging.getLogger(__name__)` in server, store and CLI |
| R6 | Broad exception handling: `except Exception: pass` (`store.py:88`), `except Exception: print("Error")` (`cli.py:14`), `catch (error) {}` (`app.js:42`) | Equivalent of lint suppressions that hide failures | Catch specific exceptions and report |
| R7 | No `.gitignore`, LICENSE or CI visible (unverified: the directory is not a git repo) | A `notes.db` file could be committed | Add `.gitignore` with `notes.db`, `__pycache__/` |
| R8 | README covers run and CLI only: no config, API routes, auth model, tests or production notes | Onboarding gaps | Extend README |
| R9 | `app/static` is not declared as package data (unverified: no wheel was built) | A built wheel may omit the web page; editable installs hide this | Declare package data and test a built install |
| R10 | `parse_page` recomputes the page count (`-(-total // size)`) that `Page.pages` already computes | Duplicate arithmetic | Construct the page and clamp, or share one helper |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Rename route functions so they do not mirror store function names (`update_note`, `delete_note`) | Easier to read stack traces |
| 2 | Add return type annotations to routes and cache helpers consistently | Matches the typed style of `pagination.py` |

### Convention Compliance Checklist
| Convention | Status | Notes |
|-----------|--------|-------|
| File placement | OK | Python modules in `app/`, tests in `tests/`, static assets in `app/static/` |
| Naming conventions | CONCERNS | `getNoteById`; two slug helpers |
| Barrel exports | N/A | Python; `app/__init__.py` is empty, which is fine |
| Import ordering | OK | stdlib, third party, first party grouped in every file |
| Type imports separated | N/A | Python |
| Path aliases used | N/A | Python absolute imports used consistently |
| No dead code left | CONCERNS | R1 |
| Structured logging | FAIL | No logging at all (R5) |
| No lint suppressions | CONCERNS | Broad excepts act as suppressions (R6); no linter configured to flag them |
| CLAUDE.md present | N/A | Not required for this repo |

### Reuse Opportunities
- `utils.slugify` replaces `server.make_slug`, with better Unicode handling (NFKD normalisation versus stripping non-ASCII).
- `store` functions (with an owner argument) replace the raw SQL in `cli.cmd_export`.
- `utils.truncate` has a natural use in the CLI `list` output (`cli.py:20` prints full titles of up to 200 characters).

### Verdict Details
- File Organization: PASS
- Naming Consistency: CONCERNS
- Import Hygiene: PASS
- Code Reuse: CONCERNS
- Lint Compliance: CONCERNS (nothing configured, broad excepts)

---

## 7. Production Readiness

**Verdict**: NEEDS REWORK

# Production Readiness Audit: jotter

**Perspective**: Production Readiness Engineer
**Date**: 2026-11-21
**Plan**: n/a (Repo Health mode)

### Plan Summary
What ships is a Flask development server on `0.0.0.0:5000` with debug on, a hardcoded database path on one developer's machine, and an unauthenticated API. SQL is parameterized throughout (checked in every query), which rules out SQL injection.

### Files Reviewed
| File | Production Role | Risk |
|------|----------------|------|
| `app/config.py` | Environment settings | High |
| `app/server.py` | Public HTTP surface | High |
| `app/store.py` | Persistence | High |
| `app/cache.py` | Search cache | High |
| `app/cli.py` | Operations (export) | Medium |
| `pyproject.toml` | Packaging | Medium |
| `app/static/app.js` | Client error handling | High |

### Critical Issues (Must Fix)
| # | Issue | File(s) | Production Failure Mode | Fix |
|---|-------|---------|------------------------|-----|
| C1 | Store depends on Flask request context | `store.py:7,39,48,56,102` | CLI add/list crash outside a request; a background job calling the store would too | Pass `owner` explicitly |
| C2 | Search cache is not scoped to user | `cache.py`, `server.py:74-80` | One user's notes returned to another for 60 s | Key by owner |
| C3 | Cache never evicts | `cache.py:5-20` | Memory growth until the process is killed; a remote client can drive it with unique queries | Bound size, purge on write |
| C4 | `update_note` swallows errors, commits mid-way, leaks the connection | `store.py:74-89` | Lost tags and half-applied edits reported as success | One transaction, no swallow |
| C8 | `DEBUG = True`, `HOST = "0.0.0.0"` | `config.py:4-5` | Interactive debugger reachable from the network | Safe defaults, env overrides |
| C9 | Hardcoded `/Users/dev/...` DB path; init only in `__main__` | `config.py:3`, `server.py:83-87` | Process cannot start elsewhere; WSGI deployment has no tables | Env var, init on startup |
| C10 | No owner check on update and delete; identity is a client header | `store.py:68-95`, `server.py:13-14,48-67` | Any client can modify or delete any note | Owner in WHERE clauses; real auth or documented single-user mode |

### Recommendations
| # | Issue | Why | Fix |
|---|-------|-----|-----|
| P1 | `tags.note_id REFERENCES notes(id)` is declared but SQLite foreign keys are off by default; no cascade | Orphan tags (for example `update_note` on a missing id inserts tags for nothing) | `PRAGMA foreign_keys = ON` on each connection, `ON DELETE CASCADE` |
| P2 | No indexes on `notes(owner, updated_at)` or `tags(note_id)` | Full scans for list and for each `tags_for` call | `CREATE INDEX` in the schema |
| P3 | `with sqlite3.connect(...) as conn` commits or rolls back but does not close; `search()` and `update_note` never close at all | File-handle churn relies on garbage collection | `contextlib.closing`, or one connection per request in `g` |
| P4 | No logging, no request logs beyond Werkzeug defaults, errors are swallowed | Cannot diagnose a failure after the fact | Log at the boundaries |
| P5 | No `MAX_CONTENT_LENGTH`; create does not validate title or body length | Large payloads stored whole | Config limit plus shared validation |
| P6 | Flask development server is the only documented way to run | Not a production server; debug reloader doubles processes | Document waitress or gunicorn with an app factory |
| P7 | No schema version | The next column change has no migration path | `PRAGMA user_version` and a small migration step |
| P8 | Errors outside PUT validation return HTML (404, 415, 500, and the `KeyError` on `data["title"]` in create) | Client cannot parse them | `@app.errorhandler` returning JSON under `/api` |
| P9 | `PUT` and `DELETE` on a missing id answer success (`{"ok": true}`, 204) | Misleading to clients and to the UI | Check `rowcount`, return 404 |
| P10 | `jotter export` overwrites the target in place (not atomic), includes every user's notes, omits tags | A crash mid-write corrupts the backup; privacy leak across owners | Write temp file then rename; scope by owner; include tags |
| P11 | `flask>=3.0` with no upper bound or lockfile; no health endpoint | Non-reproducible builds; no liveness probe | Pin or lock; add `/healthz` |
| P12 | Port 5000 is taken by AirPlay Receiver on recent macOS, and the port is not configurable | "Address already in use" on a Mac | `PORT` from environment |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Turn on SQLite WAL mode | Better read/write concurrency for a multi-user server |
| 2 | Scheduled `jotter export` backup documented | Self-hosted data needs a backup story |
| 3 | `Cache-Control` for static assets | Fewer repeat fetches |

### Failure Mode Analysis
| Scenario | What Fails | User Impact | Recovery | Plan Handles It? |
|----------|-----------|-------------|----------|-------------------|
| Run on a machine without `/Users/dev/projects/jotter/` | `sqlite3.connect` cannot open the file | App will not start | Edit source | No |
| Run under gunicorn/waitress | `store.init()` never called | "no such table" on every request | Run init by hand | No |
| `jotter add` | `current_user()` raises outside a request; message is "Error" | Nothing is added, cause hidden | None | No |
| `jotter list` | Same exception, uncaught traceback | Crash | None | No |
| Edit fails after tags deleted | `update_note` swallows; tags gone | Silent data loss | Restore from backup (none) | No |
| Two users search the same term | Cache returns first user's notes | Data leak | Wait 60 s | No |
| Thousands of distinct queries | Cache dict grows forever | Memory exhaustion | Restart | No |
| Bad JSON body on POST | `KeyError` -> HTTP 500 HTML (debugger page in debug mode) | Generic failure, stack trace exposed | Fix request | No |
| Crash during `jotter export` | Partial file at the target | Corrupt backup | Re-run | No |
| Page used for a while, then delete clicked | Listener explosion (C6) | Browser slows, extra requests | Reload page | No |
| SQL injection attempt | Parameterized queries | None | n/a | Yes |
| Page past the last (`?page=99`) | Clamped by `parse_page` (tested) | None | n/a | Yes |

### Environment Checklist
| Concern | Dev | Prod | Gap? |
|---------|-----|------|------|
| File paths | `/Users/dev/projects/jotter/notes.db` | Unknown, no override | Yes |
| Network | `0.0.0.0:5000`, debug on | Needs loopback or reverse proxy, port configurable | Yes |
| Permissions | None; identity is a header | Needs auth or documented single-user | Yes |
| Config | Python constants | Needs environment variables | Yes |
| Build output | Editable install; static files via source tree | Wheel may omit `app/static` (unverified) | Possible |

### Verdict Details
- E2E Flow: CONCERNS (cannot start away from the author's machine)
- Error Recovery: CONCERNS (C4, P9, P10)
- Data Integrity: CONCERNS (C4, P1, P10)
- Environment Parity: CONCERNS (C8, C9, P12)
- Observability: CONCERNS (no logging, errors swallowed)

---

## 8. DX Engineer

**Verdict**: NEEDS REWORK

# DX Audit: jotter CLI and developer onboarding

**Perspective**: Developer Experience Engineer
**Date**: 2026-11-21
**Plan**: n/a (Repo Health mode)

### Plan Summary
A developer installs with `pip install -e .`, runs the server with `python -m app.server`, and uses a three-command CLI (`add`, `list`, `export`). Of these, only `export` can work, and only on the author's machine.

### Files Reviewed
| File | DX Role | Risk |
|------|---------|------|
| `app/cli.py` | CLI commands and help | High |
| `app/config.py` | Configuration | High |
| `README.md` | Onboarding | Medium |
| `app/server.py` | Error responses, entry point | Medium |
| `pyproject.toml` | Install and entry point | Low |

### Critical Issues (Must Fix)
| # | Issue | Impact on Developer | Fix |
|---|-------|-------------------|-----|
| C1 | `add` and `list` rely on `current_user()` (Flask `request`), so they cannot run outside the server | The README's own example `jotter add "Title" "Body text"` fails | Owner passed explicitly; CLI uses a configured default |
| C9 | No zero-config path: the database lives at a hardcoded `/Users/dev/...` path with no `--db` flag or environment variable | Fails on the first run on any other machine | `JOTTER_DB` env var with a local default; `--db` flag |
| C15 | `add` prints `Error` and exits 0 for any failure | The developer cannot tell what failed or fix it; scripts and CI treat it as success | Print cause to stderr, exit non-zero |

### Recommendations
| # | Issue | Why | Fix |
|---|-------|-----|-----|
| X1 | No `--db` or environment override anywhere | Cannot point the CLI at another file or a test database | Add `--db` and `JOTTER_DB` |
| X2 | `list` is hard-wired to 50 rows, prints a human column format, has no `--limit`, `--json` | Not composable with other tools | `--limit`, `--json`; tab-separated plain output |
| X3 | `add` requires the body as a positional argument | No stdin or editor, awkward for long text | Make body optional; read stdin when absent or `-` |
| X4 | `export` writes only to a file, overwrites silently, omits tags, exports other users' notes | Cannot pipe or review; surprising data | `-` for stdout, `--force` for overwrite, include tags |
| X5 | CLI has no `delete`, `search`, `edit` although the API has them | Terminal users cannot complete the lifecycle | Add subcommands |
| X6 | No examples in `--help` (epilog); no global `--version` | Developers try `--help` first | Add epilog examples, `--version` |
| X7 | Errors go to stdout and use exit code 0 (`add`); `list` raises a raw traceback | Violates the usual CLI contract | stderr plus non-zero exit codes, one top-level handler in `main()` |
| X8 | No `serve` subcommand, no port setting; `python -m app.server` is the only way; port 5000 collides on recent macOS | First-run failure on Macs | `jotter serve --port`, `PORT` env |
| X9 | Web form: no Cmd/Ctrl+Enter to submit from the textarea | Power-user friction | Key handler |
| X10 | API errors are inconsistent: `{"error": ...}` for PUT, HTML pages elsewhere | Client code cannot handle failures uniformly | JSON handlers for `/api` |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Shell completion (argcomplete) | Small tool, cheap to add |
| 2 | Colour only when stdout is a TTY | Respect pipes |
| 3 | A `jotter config` command printing the effective settings | Debuggability |

### Error Message Audit
| Error Scenario | Current Message | What Developer Needs | Suggested Message |
|---------------|----------------|---------------------|-------------------|
| `jotter add` fails (any cause) | `Error` (stdout, exit 0) | What failed, why, what to do | `jotter: could not add note: unable to open database file '/Users/dev/projects/jotter/notes.db'. Set JOTTER_DB or pass --db.` |
| `jotter list` outside server | Raw `RuntimeError` traceback ("Working outside of request context") | The real problem stated plainly | Same fix as C1; message should never appear |
| `jotter export` to unwritable path | Raw `PermissionError`/`OSError` traceback | Path and reason | `jotter: cannot write 'notes.json': permission denied` |
| `jotter export` overwrites an existing file | No message | Warning or refusal | `jotter: 'notes.json' exists; use --force to overwrite` |
| `POST /api/notes` with missing field | HTTP 500 HTML (`KeyError: 'title'`) | JSON 400 naming the field | `{"error": "title is required"}` (as PUT already does) |
| `PUT` with empty title | `{"error": "title is required"}` | Good as is | Keep |
| `PUT` with title over 200 characters | `{"error": "title must be at most 200 characters"}` | Good as is | Keep |
| Start server where the DB directory does not exist | `sqlite3.OperationalError: unable to open database file` traceback | Path and remedy | `jotter: cannot open database at <path>; set JOTTER_DB` |
| Port 5000 already in use | Werkzeug "Address already in use" | Hint to change the port | `Port 5000 is in use; set PORT or pass --port` |

### Developer Journey
First use: `pip install -e .` then `python -m app.server` fails to start unless `/Users/dev/projects/jotter/` exists; the README gives no hint about configuration. If it does start, the web page works for add and delete. `jotter add` then prints `Error`; `jotter list` crashes. Daily use: no way to read from or write to the same database from a script without editing `config.py`. Power use: no JSON output, no stdin, no search, no delete, no stable exit codes. The existing PUT validation messages are the best part of the current DX and should be the model for all errors.

### Verdict Details
- Error Quality: CONCERNS
- Defaults & Config: CONCERNS
- Keyboard Experience: CONCERNS (Delete not keyboard reachable; no submit shortcut)
- Discoverability: CONCERNS (no `--help` examples; edit/search not exposed)
- Workflow Integration: CONCERNS (no JSON, stdin, exit codes)

---

## 9. Performance Engineer

**Verdict**: APPROVE WITH CHANGES

# Performance Audit: jotter

**Perspective**: Performance Engineer
**Date**: 2026-11-21
**Plan**: n/a (Repo Health mode)

### Plan Summary
A long-running Flask process holding an in-memory cache, and a browser page that can stay open for hours. Table sizes are small, so query cost is a concern for growth rather than today; the two real defects are an unbounded cache and a listener leak. The lens text is desktop/Tauri flavoured; IPC items map to HTTP requests here.

### Files Reviewed
| File | Performance Role | Risk |
|------|-----------------|------|
| `app/cache.py` | Long-lived in-memory state | High |
| `app/static/app.js` | Long-lived page, event listeners | High |
| `app/store.py` | Query and connection patterns | Medium |
| `app/server.py` | Per-request fan-out | Medium |

### Critical Issues (Must Fix)
| # | Issue | File(s) | Impact | Fix |
|---|-------|---------|--------|-----|
| C3 | Cache never evicts; keys are arbitrary user strings with full result lists as values | `cache.py:5-20` | Memory grows with every distinct query for the life of the process | Cap entries and purge expired ones in `put`, or remove the cache |
| C6 | Delegated listener added on every `render()` | `app.js:23-27` | Roughly 2^k listeners after k deletes, each issuing DELETE plus a full list fetch (traced, not executed) | Register once |

### Recommendations
| # | Issue | File(s) | Why | Fix |
|---|-------|---------|-----|-----|
| Pf1 | N+1: for each of up to 20 notes, `tags_for` opens a new connection and runs a query | `server.py:33-35`, `store.py:60-65` | About 23 connections per page load (1 list, 1 count, up to 20 tags, plus `parse_page`'s count) | One query for all tags |
| Pf2 | A new `sqlite3.connect` for every store call, none reused within a request | `store.py:24-27` | Repeated open and close, handle churn | One connection per request |
| Pf3 | No indexes: `ORDER BY updated_at DESC` with `WHERE owner = ?` scans and sorts every time; `tags` lookups scan | `store.py:9-21,47` | Fine at hundreds of rows, degrades after thousands | Add `(owner, updated_at)` and `tags(note_id)` indexes |
| Pf4 | `search` has no LIMIT, uses `LIKE '%q%'` (full scan) and an empty query matches every row | `store.py:98-104` | Returns the entire table, cached whole | `LIMIT`, minimum query length, escape wildcards |
| Pf5 | Client has no guard against out-of-order or overlapping loads, and no debounce if a search box is added | `app.js:4-8` | Stale renders; request pile-up | Request token or abort; debounce 200-300 ms for future search input |
| Pf6 | `OFFSET` pagination is O(offset); debug reloader doubles the process | `pagination.py:14`, `config.py:4` | Acceptable at this size; note the ceiling | Keyset pagination if tables grow large; debug off in production |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Enable SQLite WAL | Reads do not block on writes |
| 2 | Compute the page count and the list in one query pair | Saves a round trip |

### Resource Budget
| Resource | Current | After Plan | Concern? |
|----------|---------|-----------|----------|
| HTTP requests per user action (delete) | 2 (DELETE plus list) | 2 x 2^k after k deletes (traced, not executed) | Yes, C6 |
| Event listeners added | 1 per render, never removed | Should be 1 total | Yes |
| Memory growth per hour | Unbounded (cache, one entry per distinct query) | Bounded cache | Yes, C3 |
| SQLite connections per list request | about 23 (up to 20 tag lookups, one list, one count) | 1 | Yes, Pf1/Pf2 |
| Startup time impact | Negligible (`store.init()` runs one `executescript`) | Unchanged | No |
| Bundle size impact | 45-line script, no dependencies | Unchanged | No |

### Hot Path Analysis
The hottest server path is `GET /api/notes`, hit on page load and after every create or delete: it runs list, count and one tags query per note, each opening a fresh connection, with no indexes. At today's data sizes that is milliseconds; it scales linearly in notes per page and in table size. The hottest client path is the delete click, and it is the one that degrades with use because of the listener leak. Search is the other hot path (unbounded `LIKE` plus the cache's unbounded growth).

### Verdict Details
- Memory Management: CONCERNS (C3)
- IPC Efficiency: CONCERNS (N+1, per-call connections)
- I/O Patterns: CONCERNS (no indexes, unbounded search)
- Startup Impact: PASS
- Long-Session Stability: CONCERNS (C6, C3)

---

## 10. Accessibility Engineer

**Verdict**: NEEDS REWORK

# Accessibility Audit: jotter web page

**Perspective**: Accessibility Engineer
**Date**: 2026-11-21
**Plan**: n/a (Repo Health mode)

### Plan Summary
A one-page form and list. Landmarks and heading order are good; the controls are not: an unlabelled field, a focus outline removed from inputs, and a delete "button" that is a div.

### Files Reviewed
| File | A11y Role | Risk |
|------|----------|------|
| `app/static/index.html` | Landmarks, form labels | Medium |
| `app/static/app.js` | Dynamic content, delete control | High |
| `app/static/style.css` | Focus and contrast | High |

### Critical Issues (Must Fix)
| # | Issue | WCAG Criterion | File(s) | Impact | Fix |
|---|-------|---------------|---------|--------|-----|
| C11 | `outline: none` on title input and textarea, no replacement | 2.4.7 Focus Visible | `style.css:63` | Keyboard users lose their place | Visible `:focus-visible` style |
| C12 | Delete is a `<div class="delete">` with a click handler | 2.1.1 Keyboard, 4.1.2 Name, Role, Value | `app.js:16`, `style.css:104-108` | Unreachable by Tab, not announced as a control | `<button type="button">` |
| C13 | Title `<input>` has only a placeholder; no `<label>` or `aria-label` | 1.3.1, 3.3.2, 4.1.2 | `index.html:19` | Screen readers read an unnamed field; placeholder disappears on input | Add a label (the textarea already has one) |

### Recommendations
| # | Issue | WCAG Criterion | Fix |
|---|-------|---------------|-----|
| A1 | List changes (add, delete, load failure) are not announced; `#notes` has no live region and there is no status text | 4.1.3 Status Messages | Add an `aria-live="polite"` status element and update it on each action |
| A2 | After a delete, the removed element held focus (once it is a button) and focus falls to `body` | 2.4.3 Focus Order | Move focus to the next note's controls or to the "Your notes" heading |
| A3 | Delete control text is about 18 px tall with no padding; Save button is about 37 px tall | 2.5.8 Target Size (Minimum, 24 px) | Pad the delete button to at least 24 by 24 px, preferably 40 px |
| A4 | Every delete control would read "Delete" with no indication of which note | 2.4.6, 4.1.2 | `aria-label="Delete note: {title}"` |
| A5 | Single-link `<nav aria-label="Main">` whose only link points at the current page | 2.4.8 Location (advisory) | Remove or add `aria-current="page"` |
| A6 | Header link is distinguished from surrounding text by colour only (no underline) | 1.4.1 Use of Colour | Underline links |
| A7 | When errors are added (C7 fix), associate them with the field | 3.3.1, 3.3.3 | `aria-describedby` and `aria-invalid` |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Skip link | Only worth it once the page has more than one section of repeated navigation |
| 2 | `autocomplete="off"` or a meaningful `name` on inputs | Clear form semantics |

### Keyboard Navigation Walkthrough
| Step | Action | Expected Focus | Expected Announcement | Plan Handles? |
|------|--------|---------------|----------------------|---------------|
| 1 | Tab from page load | "Notes" header link | "Notes, link" | Yes (default browser outline) |
| 2 | Tab | Title input | "Title, edit text" | **No** (no label; announces as unnamed edit field) |
| 3 | Type in title | Visible focus ring on the field | n/a | **No** (outline removed) |
| 4 | Tab | Textarea | "Note, edit text" | Partly (labelled; focus ring removed) |
| 5 | Tab | Save button | "Save, button" | Yes (`focus-visible` outline) |
| 6 | Press Enter on Save | Form submits; focus stays on Save | "list updated" | **No** (no announcement) |
| 7 | Tab into the list | Each note's Delete | "Delete note: {title}, button" | **No** (the div is skipped entirely) |
| 8 | Activate Delete | Focus moves sensibly after removal | "Note deleted" | **No** (not reachable; no focus management; no announcement) |

### ARIA Checklist
| Element | Role | Label | States | Keyboard | Notes |
|---------|------|-------|--------|----------|-------|
| `<header class="topbar">` | banner | n/a | n/a | n/a | Good |
| `<nav aria-label="Main">` | navigation | "Main" | n/a | Tab | Only one link; redundant |
| `<main>` | main | n/a | n/a | n/a | Good |
| `<h1>`, `<h2 id="notes-heading">`, `<h3>` per note | headings | Text | n/a | n/a | Order is correct (1, 2, 3) |
| `<section aria-labelledby="notes-heading">` | region | "Your notes" | n/a | n/a | Good |
| Title `<input>` | textbox | **None** | n/a | Tab | C13 |
| Body `<textarea>` | textbox | "Note" (label) | n/a | Tab | Good; focus ring removed (C11) |
| Save `<button>` | button | "Save" | n/a | Enter, Space | Good; target about 37 px |
| `#notes` container | none | n/a | no `aria-live` | n/a | A1 |
| Note `<article>` | article | no name | n/a | n/a | Acceptable; the heading names it implicitly |
| Delete `<div>` | **none** | text "Delete" | none | **Not focusable** | C12 |

Contrast (computed by hand, approximate): delete `#b91c1c` on `#fafafa` about 6.2:1 (passes AA); note text `#222222` on `#fafafa` above 14:1; Save button white on `#1d4ed8` about 6.7:1 in light, and `#1c1917` on `#93c5fd` well above 4.5:1 in dark; header link `#1d4ed8` on white about 6.7:1 and `#93c5fd` on `#1c1917` in dark. Both themes pass.

### Verdict Details
- Screen Reader Compatibility: CONCERNS (C13, C12, A1)
- Keyboard Navigation: CONCERNS (C12)
- Focus Management: CONCERNS (C11, A2)
- Color Contrast: PASS
- Motion Sensitivity: PASS (one 150 ms colour transition, no motion)

---

## Decisions Left for the Maintainer

These are product or taste calls, not defects, and are not made in this audit:

1. **Auth model.** Is jotter a single-user local tool (bind to loopback, drop the `X-User` header) or a multi-user service (needs real authentication)? C2 and C10 are fixed differently depending on the answer.
2. **Edit, search and tags in the UI.** Wire them into the page, or delete the unused endpoints and the `tags` table.
3. **Package name.** Rename `app` to `jotter` (recommendation 13) is a breaking change for anyone importing `app`.
4. **Delete behaviour.** Confirm dialog, or soft delete with undo.

## Audit Limits

- Nothing was executed: no tests, no server, no CLI, no browser. Behaviour claims were traced from source and are marked.
- Not a git repository, so no history, diff, branch, CI config or `.gitignore` could be examined.
- Packaging behaviour (static files in a built wheel) was not built or tested.
- The `web-design-guidelines` reference skill requires fetching an external URL and was not applied.

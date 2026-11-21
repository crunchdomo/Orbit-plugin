# Full Spectrum Audit: jotter (Python/Flask notes service + web page + CLI)

**Date**: 2026-11-21
**Mode**: Repo Health (general repo health, option 3)
**Source**: `/private/tmp/claude-501/-Users-oenfadam-Documents-Orbit-plugin/ec022de0-9140-4432-ae41-0c6144f29ec4/scratchpad/pr2` (whole directory treated as the repo; it is not a git repository, so there is no diff or history)
**Lenses Run**: 10/10
**Lenses Skipped**: none. Every lens had something in scope: a web UI (`app/static/`), a CLI (`app/cli.py`), an HTTP API with data access (`app/server.py`, `app/store.py`), several modules, and state/I/O (`app/cache.py`, SQLite).

**Method note**: this was a static read of all 14 source files (README, pyproject, 7 Python modules, 1 test file, 3 static files). Nothing was executed; claims about runtime behaviour (for example "the CLI always fails") are traced by reading the code and are marked as traced, not run. The `web-design-guidelines` reference skill's remote guideline list was fetched and applied to the three static files; other reference skills were read from the local skills folder.

**Stack brief** (used by every lens)
- Python >= 3.11, Flask >= 3.0 (only dependency), SQLite via stdlib `sqlite3`; vanilla HTML/CSS/JS front end with no build step, no framework (pyproject.toml, README).
- Runs as one Flask dev-server process (`python -m app.server`, README) plus a `jotter` CLI entry point (`app.cli:main`); the web page is `app/static/` served by Flask.
- UI lives in `app/static/index.html`, `app.js`, `style.css`; CSS uses custom-property tokens with a `prefers-color-scheme: dark` override.
- Documented conventions: only the README layout list (server = routes, store = SQLite access, cache = search cache, pagination/utils = helpers, static = web page, cli = command line). No CLAUDE.md, no linter/formatter/type-checker config, no CI. Observed conventions: snake_case, type hints, one-line module docstrings, parameterised SQL.
- Tests: `tests/test_pagination.py` only (6 tests, pure functions).

---

## Master Verdict: NEEDS REWORK

The service has a clean, well-tested pagination helper and well-tokenised CSS, but the parts that carry user data are unsafe and partly non-functional: stored XSS in the page, a Werkzeug debugger bound to every interface, per-note update/delete with no ownership check, an identity taken from a spoofable header, a search cache shared across users, a swallowed-exception update path, and a CLI that traced-fails on every command because the store imports the HTTP layer. One of these alone would block release; together they are the reason the verdict is not a vote of the ten lenses but a floor set by the worst of them.

## Verdict by Lens

| # | Lens | Verdict | Critical | Recommendations |
|---|------|---------|----------|-----------------|
| 1 | Design Engineer | APPROVE WITH CHANGES | 2 | 4 |
| 2 | UX Engineer | NEEDS REWORK | 3 | 5 |
| 3 | Frontend Engineer | NEEDS REWORK | 3 | 4 |
| 4 | Backend Engineer | NEEDS REWORK | 5 | 7 |
| 5 | Structural Engineer | APPROVE WITH CHANGES | 1 | 4 |
| 6 | Repo Maintainer | APPROVE WITH CHANGES | 0 | 6 |
| 7 | Production Readiness | NEEDS REWORK | 4 | 6 |
| 8 | DX Engineer | NEEDS REWORK | 2 | 5 |
| 9 | Performance Engineer | NEEDS REWORK | 2 | 4 |
| 10 | Accessibility Engineer | NEEDS REWORK | 3 | 5 |

## All Critical Issues (Must Fix)

Collected from every lens, deduplicated, ordered by severity:

| # | Issue | Lens(es) | File(s) | Impact | Fix |
|---|-------|----------|---------|--------|-----|
| 1 | Stored XSS: note `title` and `body` are interpolated into `innerHTML` unescaped | Frontend, UX, Backend (no server-side defence either) | `app/static/app.js:15-19` | Any note containing `<img src=x onerror=...>` runs script in every viewer's browser; notes are shared across the `X-User` boundary via the shared cache (#5) | Build the card with `createElement` + `textContent` (or escape), never `innerHTML` for user data |
| 2 | Flask debug mode on, bound to `0.0.0.0`, by default | Production Readiness, Backend | `app/config.py:4-5`, `app/server.py:87` | The Werkzeug interactive debugger is reachable from the network: remote code execution on any exception page | Default `DEBUG = False`, `HOST = "127.0.0.1"`, read both from env; serve with a real WSGI server in prod |
| 3 | No ownership check on update or delete (and `getNoteById`) | Backend, Production Readiness | `app/store.py:68-71,74-95`, `app/server.py:48-67` | Any caller can edit or delete any user's note by guessing its integer id (list/search are owner-scoped, mutations are not) | Add `AND owner = ?` to the `UPDATE`/`DELETE` statements and the tag statements; return 404 when no row matched |
| 4 | Identity is the `X-User` request header, trusted as-is, default `"local"` | Backend, Production Readiness | `app/server.py:13-14` | Any client can read and write any user's notes by setting a header; no authentication exists, and the app binds all interfaces | Document that a trusted reverse proxy must set/overwrite it, or add real auth; at minimum bind to localhost by default |
| 5 | Search cache is keyed by query text only, not by user | Backend, Structural, Performance | `app/cache.py:9-20`, `app/server.py:74-80` | User B searching the same string within 60 s receives User A's notes (cross-user data leak); stale results after writes | Key by `(owner, query)` or move the cache inside the owner-scoped store call; invalidate on write |
| 6 | `update_note` swallows every exception, never closes its connection, and commits the tag delete before the note update | Backend, Production Readiness, DX, UX | `app/store.py:74-89`, `app/server.py:58-59` | A failed update still returns `{"ok": true}`; tags are already deleted and committed, so a failure mid-way loses tags permanently with no log line | Use one `with connect()` transaction, drop the bare `except`, let errors reach a handler that logs and returns 500 |
| 7 | The CLI cannot work: `store` imports `current_user` from `app.server`, which reads Flask's `request` outside a request context (traced, not run) | Structural, DX, Backend, Production Readiness | `app/store.py:7,39,47,56,102`, `app/cli.py:10-20` | `jotter add` hits `RuntimeError` inside `add_note`, caught by `except Exception` and reported as the single word `Error` with exit code 0; `jotter list` dies with a traceback; also importing the CLI builds the Flask app | Make `owner` a parameter of every store function; the route passes `current_user()`, the CLI passes a configured owner |
| 8 | DB path is a developer's home directory and the schema is only created under `if __name__ == "__main__"` | Production Readiness, DX | `app/config.py:3`, `app/server.py:83-86`, `app/cli.py` (never calls `init`) | On any other machine startup fails with `unable to open database file`; when run via any WSGI server or the CLI, `notes` table never exists | Read the path from an env var with a sensible default (for example next to the package or in the user data dir), call `store.init()` at app creation and in the CLI |
| 9 | A click listener is added to `document` inside `render()`, so each reload adds another | Frontend, Performance, UX | `app/static/app.js:23-27` | Listener count doubles after every delete (each click fires N DELETEs and N `loadNotes()`, each of which adds a listener); after ~10 deletes one click sends ~1000 requests, each costing N+2 DB connections (traced) | Register the delegated listener once, outside `render()` |
| 10 | "Delete" is a `<div>` with a click handler: no keyboard access, no role, no accessible name, no confirmation, no undo | Accessibility, UX, Frontend, Design | `app/static/app.js:16,23-27`, `app/static/style.css:104-108` | Keyboard and screen-reader users cannot delete; mouse users lose a note on a mis-click | Use `<button type="button" aria-label="Delete note: {title}">`, add a confirm or an undo toast |
| 11 | `outline: none` on inputs and textarea with no replacement focus style | Accessibility, Design | `app/static/style.css:55-64` | Keyboard users cannot see which field has focus (WCAG 2.4.7) | Remove `outline: none` or add `:focus-visible` with the same ring the button already uses |
| 12 | A failed save silently wipes what the user typed | UX, Frontend, DX | `app/static/app.js:34-43` | `fetch` does not throw on 4xx/5xx, so `form.reset()` runs after a rejected or failed POST; the empty `catch {}` hides network errors; note lost with no message | Check `response.ok`; on failure keep the input and show the server's error |
| 13 | Notes beyond the first page are unreachable in the UI | UX, Frontend | `app/static/app.js:5-8`, `app/server.py:31-36` | The API returns `page`/`pages` but the page never sends `?page=` and has no controls; users with more than 20 notes cannot see the older ones | Add paging (or load-more) using `page`/`pages`, or raise the limit and say so |
| 14 | `.note` cards use a hard-coded light palette instead of the tokens | Design | `app/static/style.css:91-98,104-108` | In dark mode the page is `#1c1917` but every note is a near-white `#fafafa` slab with `#222` text; the token system exists but the main content bypasses it | Use `--surface`, `--text`, `--border`, and add a danger token for the delete colour with a dark value |
| 15 | The title input has no label (placeholder only) | Accessibility | `app/static/index.html:19` | Name disappears once the user types; the body field has a label, the title does not (inconsistent, WCAG 3.3.2/4.1.2 risk) | Add `<label for="title">` (visually hidden if desired) |
| 16 | `POST /api/notes` does no validation: missing key gives a 500, empty or over-long title is accepted, `MAX_TITLE_LENGTH` is only enforced on update | Backend, DX | `app/server.py:43-45` vs `:52-57` | `data["title"]` raises `KeyError` (HTML 500); non-JSON gives an HTML 415; creates blank notes; rule differs between create and update | Share one validator used by both routes; return JSON 400s |

## Cross-Cutting Concerns

Issues flagged by 2+ lenses — systemic problems:

| Concern | Flagged By | Root Cause | Unified Fix |
|---------|-----------|------------|-------------|
| Errors are swallowed instead of surfaced | Backend, Production Readiness, DX, UX, Frontend, Repo Maintainer | Four separate catch-alls (`store.update_note` `pass`, `cli.cmd_add` prints `Error`, `app.js` empty `catch {}`, no handling in `loadNotes`) and no logging anywhere | Remove the catch-alls; add one Flask error handler returning JSON + `logging`; give the CLI a single top-level handler that prints cause and exits non-zero; make the page show response errors |
| Ownership boundary is not enforced | Backend, Production Readiness, Structural | Identity comes from a header (`server.py:13`), read deep inside the store (`store.py:39`), and neither mutations nor the cache take it into account | Pass `owner` explicitly into store and cache; every statement filters on it; document where `X-User` comes from |
| The store depends on the HTTP layer | Structural, Backend, DX, Repo Maintainer | `store.py:7` imports `server.current_user`; routes then lazy-import `store` inside each function (6 places) to dodge the cycle | Invert it (owner is a parameter); the lazy imports and the CLI breakage both disappear |
| Unsafe and developer-only configuration | Production Readiness, DX, Backend | `config.py` is a module of constants with no env override: debug on, all interfaces, absolute home path | Env-driven settings with safe defaults and comments explaining each |
| The delete interaction is wrong in four ways | Accessibility, UX, Frontend, Design | One `<div class="delete">` plus a listener created in `render()` | One `<button>`, one listener at module level, a confirm/undo, and visible hover/focus styling |
| Per-note work done with no bound | Performance, Backend, Production Readiness | New DB connection per helper call, N+1 tags query, no index on `tags.note_id`, search with no `LIMIT`, cache that never evicts | One query for tags per page, two indexes, `LIMIT` on search, bounded cache |
| Pagination built on one side only | UX, Frontend, Performance | API computes `page`/`pages`; the page ignores them; the CLI hard-codes 50 | Pick one paging contract and use it in the page and CLI |
| Duplicated and dead helpers | Repo Maintainer, Structural | `server.make_slug` re-implements `utils.slugify`; `utils.slugify`/`truncate` and `store.getNoteById` are never called; `slug`/`tags` are returned but never rendered | Delete the dead code or wire it in (one slug function) |
| Test coverage sits where the risk is lowest | Repo Maintainer, Production Readiness, Backend | Only `parse_page` is tested; store, routes, cache and CLI (where every critical issue lives) have none | A small Flask test client file plus a store test against a temp DB would have caught #3, #5, #7 |

## All Recommendations

| # | Recommendation | Lens | File(s) | Fix |
|---|---------------|------|---------|-----|
| 1 | Remove the N+1 tags query | Performance, Backend | `server.py:33-35`, `store.py:60-65` | One `SELECT note_id, name FROM tags WHERE note_id IN (...)` per page |
| 2 | Add indexes | Performance, Backend | `store.py:9-21` | `CREATE INDEX ... ON tags(note_id)` and `ON notes(owner, updated_at)` |
| 3 | Bound and invalidate the cache | Performance, Backend | `cache.py` | Evict expired entries on `put`, cap size, clear the owner's entries on write |
| 4 | Close SQLite connections explicitly | Backend, Production Readiness | `store.py` (all) | `with sqlite3` only commits; wrap in `contextlib.closing` (3.13 emits ResourceWarning for unclosed connections) |
| 5 | Enable foreign keys, de-duplicate tags | Backend | `store.py:17-20` | `PRAGMA foreign_keys=ON`, `UNIQUE(note_id, name)` |
| 6 | Bound search and escape LIKE wildcards | Backend, Performance | `store.py:98-104` | Add `LIMIT`, escape `%` `_` or use `instr()`; search currently returns every match |
| 7 | 404 for unknown ids on update/delete | Backend, DX | `server.py:48-67` | Use affected row count |
| 8 | JSON errors for every API failure | DX, Backend | `server.py` | `@app.errorhandler(HTTPException)` and one for `Exception` |
| 9 | Add structured logging | Production Readiness, Repo Maintainer | all Python | `logging.getLogger(__name__)`; log write failures and request errors |
| 10 | Env-driven config, with comments | Production Readiness, DX | `config.py` | `JOTTER_DB`, `JOTTER_HOST`, `JOTTER_PORT`, `JOTTER_DEBUG` with safe defaults |
| 11 | One slug function | Repo Maintainer, Structural | `server.py:17-19`, `utils.py:9-13` | Use `utils.slugify` (handles accents, collapses runs) or delete both; `make_slug` turns "Café" into "caf" |
| 12 | Remove dead code and the camelCase name | Repo Maintainer | `store.py:68`, `utils.py:16-22` | Delete `getNoteById` and `truncate` or use them |
| 13 | Tests for store, routes, cache, CLI | Repo Maintainer, Production Readiness | `tests/` | Flask test client + temp DB; include an owner-isolation test |
| 14 | Add lint/format/type config, `.gitignore`, test extra | Repo Maintainer | `pyproject.toml` | `ruff`, `mypy` (or pyright); `[project.optional-dependencies] test = ["pytest"]`; ignore `*.db`, `__pycache__` |
| 15 | Fix packaging | Production Readiness | `pyproject.toml` | Add `[build-system]` and package-data for `app/static/*`; non-editable installs will otherwise ship without the page (unverified) |
| 16 | CLI ergonomics | DX | `cli.py` | Non-zero exit on failure, `--db`/env, `list --limit`, empty-list message, `search`/`delete` commands, read body from stdin |
| 17 | `export` should use the store and write atomically | DX, Structural, Production Readiness | `cli.py:23-33` | `store.all_notes()`; write temp file then rename; say which owner is exported |
| 18 | Empty, loading and error states | UX, Design | `app.js`, `index.html:27` | Show "No notes yet" text, an error line, and a pending state |
| 19 | Preserve note formatting and wrap long words | Design, UX | `style.css:91-103` | `white-space: pre-wrap; overflow-wrap: anywhere` on the body and title |
| 20 | Disable Save while the request is in flight | UX, Frontend, Design | `app.js:30-43` | The `:disabled` style already exists and is never used; double click creates duplicates |
| 21 | Validate the response shape and `response.ok` | Frontend | `app.js:4-8` | `if (!response.ok) throw ...` and handle missing `notes` |
| 22 | Announce changes and name the controls | Accessibility | `index.html`, `app.js` | `aria-live="polite"` status region; per-note delete label includes the title |
| 23 | Touch-target size | Accessibility, Design | `style.css:66-75,104-108` | At least 44 px hit area for Save and Delete |
| 24 | Declare `color-scheme` and gate hover | Design | `style.css:1-22,77` | `color-scheme: light dark;` and `@media (hover: hover)` for the button hover |
| 25 | Client-side title limits | UX, DX | `index.html:19` | `required` and `maxlength="200"` to match `MAX_TITLE_LENGTH` |
| 26 | Move cache behind the store | Structural | `server.py:75-79`, `cache.py` | The route currently coordinates two stores; one `store.search(owner, q)` hides the cache |
| 27 | CLI uses the configured page size | Structural | `cli.py:19` | `config.PAGE_SIZE` instead of a literal `50` |
| 28 | Document config, auth assumption and API | DX, Repo Maintainer | `README.md` | Add Config, Auth (`X-User`), and API sections; README says `localhost:5000` while the server binds `0.0.0.0` |
| 29 | Health endpoint and WSGI entry point | Production Readiness | `server.py` | `GET /healthz`; document `gunicorn app.server:app` (which also requires moving `init()`, see critical #8) |
| 30 | Expose edit and tags in the UI or drop them from the API | UX, Structural | `server.py:48-59` | `PUT` and `tags` and `slug` exist but nothing in the page uses them |

---

# Lens Reports

---

## 1. Design Engineer

**Verdict**: APPROVE WITH CHANGES

**Perspective**: Design Engineer | **Date**: 2026-11-21 | **Source**: repo health, `app/static/`

### Plan Summary
A single-page notes UI: a topbar, a composer form (title, body, Save), and a list of note cards. Tokenised colours with a dark-mode override, one primary button, one card style.

### Files Reviewed
| File | Visual Role | Risk |
|------|-------------|------|
| `app/static/style.css` | All tokens, layout and component styling | Medium (hard-coded note palette, focus removal) |
| `app/static/index.html` | Structure of topbar, composer, list | Low |
| `app/static/app.js` | Renders note cards (class names, markup) | Medium (no empty/loading/error markup) |

### Critical Issues (Must Fix)
| # | Issue | File(s) | Impact | Fix |
|---|-------|---------|--------|-----|
| D1 | `.note` uses raw values (`#e5e5e5`, `#fafafa`, `#222222`, delete `#b91c1c`) instead of the tokens defined at the top of the same file | `style.css:91-98,104-108` | Dark theme shows bright cards on a dark page, the main content ignores the theme; the delete colour has no dark value | `border: 1px solid var(--border); background: var(--surface); color: var(--text)`; add `--danger` with light/dark values |
| D2 | `outline: none` on `.composer input, .composer textarea` with no `:focus-visible` replacement | `style.css:55-64` | Fields have no focus indicator in either theme; the button gets one (line 81) so the pattern exists and is skipped | Delete `outline: none`, or add `.composer input:focus-visible, .composer textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }` |

### Recommendations
| # | Issue | File(s) | Why | Fix |
|---|-------|---------|-----|-----|
| D3 | No empty, loading or error visual for the list | `app.js:10-21`, `index.html:27` | A new user sees an empty region under "Your notes" | Add a placeholder row and an error line (see UX U4) |
| D4 | Long titles/bodies are not handled and newlines collapse | `style.css:91-103` | An unbroken string overflows the 640 px card; multi-line notes render on one line | `overflow-wrap: anywhere; white-space: pre-wrap;` |
| D5 | No `color-scheme` declaration | `style.css:1-22` | Native scrollbars and the textarea resize handle stay light in dark mode | `:root { color-scheme: light dark; }` |
| D6 | Delete control has no hover, focus or active style, only `cursor: pointer` | `style.css:104-108` | Not discoverable as interactive; no keyboard focus ring possible on a `div` | Make it a button (see A1) and style the states |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | `:active { transform: scale(0.97) }` on `button.primary` | Tactile press feedback (make-interfaces-feel-better, emil forms-controls) |
| 2 | `@media (hover: hover)` around `button.primary:hover` | Avoids sticky hover on touch |
| 3 | `text-wrap: balance` on headings, `-webkit-font-smoothing: antialiased` on `body` | Small polish items |
| 4 | Remove the unused `--muted` token or use it for timestamps | Dead token |

### Design System Compliance
The token layer is good: eight custom properties, a dark override, `var(--radius)` applied to inputs, button and card consistently, `transition` limited to `background-color` (no `transition: all`). The fragmentation is confined to one block: `.note` and `.note .delete` (lines 91-108) re-declare colours as literals, which is exactly the "colour outside the token system" failure. Contrast of the tokenised pairs is fine in both themes (computed: light accent `#1d4ed8` on white 6.7:1, dark `#93c5fd` on `#1c1917` about 9.8:1 for the button label); the note card's own pair (`#222` on `#fafafa`, about 15:1; delete `#b91c1c` on `#fafafa`, about 6.2:1) is readable but belongs to a different theme from its surroundings in dark mode. Placeholder contrast was not measured (browser default colour) and is unverified.

### Visual State Coverage
| Component/Element | Hover | Focus | Active | Disabled | Loading | Empty | Error | Dark Mode |
|-------------------|-------|-------|--------|----------|---------|-------|-------|-----------|
| Save button (`button.primary`) | Yes | Yes (`:focus-visible`) | No | Styled but never applied | No | n/a | n/a | Yes (tokens) |
| Title input / body textarea | No | **No (outline removed)** | n/a | No | n/a | n/a | No | Yes (tokens) |
| Note card (`.note`) | n/a | n/a | n/a | n/a | n/a | n/a | n/a | **No (hard-coded light)** |
| Delete control (`.delete`) | No | No (not focusable) | No | No | No | n/a | No | No (single red) |
| Notes list container | n/a | n/a | n/a | n/a | No | **No** | No | n/a |
| Topbar link | No | Browser default | No | n/a | n/a | n/a | n/a | Yes |

### Verdict Details
- Design Token Fidelity: CONCERNS (one block bypasses tokens)
- Visual State Coverage: CONCERNS (inputs, delete, list states)
- Dark Mode Parity: CONCERNS (note cards)
- Animation Quality: PASS (a single 150 ms colour transition on an interactive element; no layout-property animation; no `prefers-reduced-motion` query, acceptable because nothing moves)
- Visual Consistency: PASS (radius, spacing and card/button treatment are consistent)

---

## 2. UX Engineer

**Verdict**: NEEDS REWORK

**Perspective**: UX Engineer | **Date**: 2026-11-21 | **Source**: repo health, `app/static/*` and the API it uses

### Plan Summary
From the user's side: type a title and a note, press Save, see notes listed newest first, and delete them. Search, edit, tags and paging exist in the API but have no way in.

### User Journey Map
| Step | Trigger -> Action -> Feedback -> Outcome | Status |
|------|------------------------------------------|--------|
| First visit | Page loads, "Your notes" heading over an empty box | WARN: no empty state, no hint of what to do (`index.html:27`) |
| Add a note | Fill title (placeholder only) and body, press Save (Enter in the title also submits, since it is a form) | OK for the happy path |
| Save succeeds | Form clears, list reloads with the new note first | OK (implicit feedback only; no confirmation message) |
| Save fails (server 4xx/5xx) | `fetch` resolves, the code ignores the status, form is reset, list reloads without the note | **FAIL**: the user's text is gone, no message (`app.js:34-42`) |
| Save fails (network) | `catch (error) {}` swallows it; form not reset, but no message either | **FAIL**: silent |
| Save with empty title | Accepted; renders a blank heading | WARN: no validation message |
| Read notes (21+) | API returns `pages`; page shows first 20 only | **FAIL**: older notes unreachable |
| Read a multi-line note | Newlines collapse (no `white-space: pre-wrap`) | WARN |
| Delete | Click the red "Delete" text; note vanishes immediately | **FAIL**: no confirm, no undo, no feedback; small hit target |
| Find a note | No search box (endpoint `/api/search` exists) | **FAIL**: feature invisible |
| Edit a note | No edit control (endpoint `PUT` exists) | **FAIL**: only delete and re-create |
| Return later / interrupted | Notes persist server side; unsent draft is lost on reload | WARN (minor) |

### Critical Issues (Must Fix)
| # | Issue | Step in Journey | Impact on User | Fix |
|---|-------|----------------|----------------|-----|
| U1 | A failed save wipes the form and shows nothing | Save fails | Lost text, user thinks it saved | Check `response.ok`; keep the input; show the server message |
| U2 | Delete is instant and irreversible | Delete | One mis-click destroys a note | Confirm with the note title, or soft-delete with an "Undo" toast |
| U3 | Notes after the first 20 cannot be reached | Read notes | Data appears to disappear once the list grows | Add "Load more"/pager using `page` and `pages` from the API response |

### Recommendations
| # | Issue | Impact | Fix |
|---|-------|--------|-----|
| U4 | No empty, loading or error states | Blank screen reads as broken | "No notes yet. Write one above." plus an inline error line |
| U5 | Search and edit exist server-side but are not surfaced | Users cannot find or fix notes | Add a search box (debounced) and an edit action, or remove the unused endpoints |
| U6 | No title validation on the client | Blank-title notes | `required`, `maxlength` equal to the server limit |
| U7 | Save is not disabled during the request | Double-click creates duplicates | Disable the button while pending (the `:disabled` style already exists) |
| U8 | Notes lose line breaks | Multi-line content is unreadable | `white-space: pre-wrap` |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Cmd/Ctrl+Enter in the textarea submits | Power-user path for a note-taking tool |
| 2 | Show the updated time on each note | The API already returns `updated_at` |
| 3 | Keep an unsent draft in `localStorage` | Interrupted-user case |

### Interaction Consistency Check
The page has one pattern: form submit, then full list reload. Delete deviates from it (a bare text link that acts instantly, unlike the form's explicit Save) and nothing else is interactive, so there is no inconsistency to measure beyond that. The `<nav>` holds one link to the page the user is already on, which implies navigation that does not exist.

### Verdict Details
- Discoverability: CONCERNS (search and edit are invisible; delete looks like plain text)
- Flow Completeness: CONCERNS (no paging, no edit, no search)
- Error Recovery: CONCERNS (failed save loses input; no undo)
- Feedback & Status: CONCERNS (no saving/saved/failed signal)
- Consistency: PASS (single simple pattern)

---

## 3. Frontend Engineer

**Verdict**: NEEDS REWORK

**Perspective**: Frontend Engineer | **Date**: 2026-11-21 | **Source**: `app/static/app.js` (vanilla JS, no framework or build step)

### Plan Summary
A 45-line script that fetches `/api/notes`, rebuilds the list with `innerHTML` on every load, and wires submit and delete.

### Files Reviewed
| File | Frontend Role | Risk |
|------|--------------|------|
| `app/static/app.js` | All client logic | High |
| `app/static/index.html` | Markup and script include | Low |
| `app/static/style.css` | Styling (reviewed for tokens only) | Low |

### Critical Issues (Must Fix)
| # | Issue | File(s) | Why It Breaks | Code Fix |
|---|-------|---------|---------------|----------|
| F1 | Note `title` and `body` are inserted with `innerHTML` | `app.js:15-19` | Stored XSS: a note containing markup or an `onerror` attribute executes for everyone who loads the list | `const h = document.createElement("h3"); h.textContent = note.title;` (same for the body), or escape before interpolation |
| F2 | `document.addEventListener("click", ...)` is inside `render()` | `app.js:23-27` | Every `loadNotes()` adds another listener. One click then runs all of them: N DELETEs and N reloads, each reload adding N more listeners, so the count doubles on each delete (traced: 1 -> 2 -> 4 -> ...) | Move the listener to module level and delegate from `list`, not `document` |
| F3 | `response.ok` is never checked; submit success path runs on any HTTP status; `loadNotes` has no error handling | `app.js:4-8,34-43` | A 400/500 POST resets the form (data loss); a failed GET throws an unhandled rejection; `data.notes` undefined makes `render` throw | `if (!response.ok) throw new Error(...)` and handle it in one `try/catch` that shows a message |

### Recommendations
| # | Issue | File(s) | Why | Fix |
|---|-------|---------|-----|-----|
| F4 | The whole list is thrown away and rebuilt on each load | `app.js:11-21` | Fine at 20 items but resets scroll and focus; with a real delete button, focus is lost every time | Remove the one node on delete, or keep focus on the next item |
| F5 | Empty `catch (error) {}` | `app.js:42` | Hides every failure | Show the message, log to the console |
| F6 | Re-querying `document.getElementById("title")` on each submit | `app.js:32-33` | Trivial, but the `form` and `list` handles are cached at the top; use `form.elements` | `form.elements.title.value` |
| F7 | No guard against double submit | `app.js:30-43` | Duplicate POSTs | Disable the submit button while pending |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Use `<script type="module">` or `defer` | Script is at the end of body so it works; `defer` is more robust |
| 2 | JSDoc/`// @ts-check` on the payload shape | No type system exists on the client; the API contract is implicit |
| 3 | Move to a template element for the card | Keeps markup out of JS strings |

### Render Path Analysis
- Trigger points: page load (`loadNotes()` at line 45), after each successful POST (line 41), after each delete (line 26).
- Each trigger does one GET, then clears `list.innerHTML` and rebuilds up to 20 `<article>` nodes. At that size the DOM cost is negligible.
- The real cost is the listener: `render()` runs once per reload and each run attaches one more `click` listener to `document` that is never removed. After the first delete there are 2, after the second 4, and so on; each extra listener issues its own DELETE and its own reload, so the request volume per click grows as 2^k (traced).
- There are no stale-closure risks in the handlers themselves (they read `event.target` at call time), and no shared mutable client state.

### Type Safety Assessment
Plain JavaScript with no type checking and no runtime validation of the API response. The shape `{notes: [{id, title, body, tags, slug, ...}], page, pages}` is assumed. `tags`, `slug`, `page` and `pages` are received and ignored. Values are interpolated as strings without coercion or escaping.

### Verdict Details
- Component Architecture: CONCERNS (one function does fetch-adjacent rendering and event wiring)
- State Management: PASS (no client state beyond the DOM)
- Type Safety: CONCERNS (no response validation)
- Rendering Performance: CONCERNS (listener accumulation; the list rebuild itself is fine)
- Bundle Impact: PASS (no dependencies, one 45-line file)

---

## 4. Backend Engineer

**Verdict**: NEEDS REWORK

**Perspective**: Backend Engineer | **Date**: 2026-11-21 | **Source**: `app/server.py`, `app/store.py`, `app/cache.py`, `app/config.py`, `app/pagination.py`

### Plan Summary
Flask routes over a SQLite store: list (paginated), create, update, delete, search with a 60 s in-memory cache; identity comes from an `X-User` header and notes are scoped by an `owner` column.

### Files Reviewed
| File | Backend Role | Risk |
|------|-------------|------|
| `app/server.py` | HTTP routes, identity, validation | High |
| `app/store.py` | SQLite access, schema | High |
| `app/cache.py` | In-process search cache | High |
| `app/config.py` | Settings | High |
| `app/pagination.py` | Pure helper (clean, tested) | Low |
| `app/utils.py` | Unused helpers | Low |

### Critical Issues (Must Fix)
| # | Issue | File(s) | Failure Mode | Code Fix |
|---|-------|---------|-------------|----------|
| B1 | `update_note` and `delete_note` filter on `id` only; `getNoteById` too | `store.py:68-71,74-95`; `server.py:48-67` | Any user can overwrite or delete another user's note by id (list and search are owner-scoped, mutations are not) | `UPDATE notes SET ... WHERE id = ? AND owner = ?`; tags statements guarded by a subquery on owner; return 404 if `rowcount == 0` |
| B2 | Identity is `request.headers.get("X-User", "local")` | `server.py:13-14` | Spoofable: set the header to read or write anyone's notes; unauthenticated callers become `"local"` | Trust it only behind a proxy that sets it (documented), or add real authentication |
| B3 | Search cache keyed by `query` alone | `cache.py:9-20`, `server.py:74-80` | A second user's identical query returns the first user's notes for up to 60 s (cross-user leak); results also stale after any write | Key on `(owner, query)`; clear on write; or drop the cache |
| B4 | `update_note` catches `Exception` and `pass`es, never closes the connection, and commits the tag delete before the note update | `store.py:74-89` | Error is invisible, the route still answers `{"ok": true}`; a failure after the first `commit()` leaves the note without its tags; no rollback | One `with connect() as conn:` block, no catch-all |
| B5 | `create_note` indexes `data["title"]` and `data["body"]` with no validation | `server.py:43-45` | Missing key gives a KeyError 500 (HTML), `null` hits the `NOT NULL` constraint (500), no length limit (limit exists only on update), non-JSON gives an HTML 415 | Shared validator returning JSON 400s; same limit on create and update |

### Recommendations
| # | Issue | File(s) | Why | Fix |
|---|-------|---------|-----|-----|
| B6 | N+1: one connection and one query per note for tags | `server.py:33-35`, `store.py:60-65` | A 20-note page opens 22 connections | Single `IN (...)` query |
| B7 | `update_note` input handling: `data.get("title", "").strip()` raises on `null`/non-string; `tags` accepted unvalidated (a string iterates per character) | `server.py:52-58` | 500 instead of 400; garbage tags | Check types before use |
| B8 | Update/delete of a missing id return success | `server.py:59,67` | Misleading, hides B1 attempts | 404 from `rowcount` |
| B9 | Connections are never explicitly closed (`with conn` commits, it does not close); `search` has neither `with` nor `close` | `store.py` (all), `store.py:98-104` | Relies on refcount GC; 3.13 warns | `contextlib.closing(connect())` |
| B10 | Foreign key declared but not enforced; no unique constraint on tags; no indexes | `store.py:9-21` | Orphan or duplicate rows possible; scans on every lookup | `PRAGMA foreign_keys=ON`, `UNIQUE(note_id, name)`, indexes |
| B11 | Search has no limit and does not escape `%`/`_` | `store.py:98-104` | Empty query returns every note; wildcard characters act as patterns | `LIMIT`, escape |
| B12 | List and count are separate reads | `server.py:31-32` | Page can disagree with total under concurrent writes (minor) | Accept, or one read transaction |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | `PRAGMA journal_mode=WAL` | Better concurrent read/write behaviour for a threaded server |
| 2 | Return only public fields instead of `SELECT *` | The `owner` column is sent to the client |
| 3 | Module-level `import store` once the cycle is gone | Six function-level imports exist only to avoid the cycle |

### Error Path Analysis
- `POST /api/notes`: bad/missing JSON -> Flask HTML 400/415; missing key -> `KeyError` -> HTML 500 with traceback in debug mode; DB errors -> unhandled -> 500. Nothing is logged by the application. Client receives HTML, not JSON.
- `PUT /api/notes/<id>`: title checks produce clear JSON 400s (good); everything after `store.update_note` is lost into `except Exception: pass`, so DB-locked, disk-full, constraint and type errors all return `{"ok": true}`. The user is told it worked.
- `DELETE`: no `try`, runs two statements in one transaction (good); unknown id returns 204.
- `GET /api/search` and `/api/notes`: unhandled exceptions become HTML 500s; with `DEBUG = True` they show the interactive debugger (see Production Readiness P1).
- Parameterised queries are used throughout, so SQL injection is not present (PASS); LIKE wildcards are the only injection-like concern.
- Errors reach the client as HTML pages or as silence; none arrive as structured JSON with a cause.

### Resource Lifecycle Audit
| Resource | Allocated In | Cleaned Up In | Error Path Cleanup | Risk |
|----------|-------------|---------------|-------------------|------|
| SQLite connection (read/write helpers) | `store.connect()` per call | Implicit GC after the `with` block | `with` commits or rolls back, no `close()` | Low-Medium (GC dependent) |
| SQLite connection in `update_note` | `store.py:75` | Never closed explicitly | Swallowed exception, no rollback | Medium |
| SQLite connection in `search` | `store.py:99` | Never closed, no `with` | None | Medium |
| SQLite connection in `cmd_export` | `cli.py:24` | `conn.close()` on success path | No `finally` | Low |
| Search cache dict `_results` | `cache.py:5` | Never; expired entries stay until overwritten | n/a | High (unbounded, keyed by user-supplied text) |
| Export file handle | `cli.py:31` | `with open` | Yes (but non-atomic write) | Low |

### Verdict Details
- Error Handling: CONCERNS
- Concurrency Safety: CONCERNS (non-atomic tag replacement; separate count/list reads; SQLite default settings)
- Resource Management: CONCERNS
- Protocol Correctness: CONCERNS (API returns `owner`, `slug`, `tags` the page ignores; error shape varies between JSON and HTML)
- File System Safety: PASS for the server (no user-supplied paths; static served via `send_from_directory`); the CLI export writes to a user-chosen path in place (non-atomic), which is acceptable for an operator tool

---

## 5. Structural Engineer

**Verdict**: APPROVE WITH CHANGES

**Perspective**: Systems/Structural Architect | **Date**: 2026-11-21 | **Source**: whole repo import graph

### Plan Summary
A small, flat package whose intended layering (page -> routes -> store -> SQLite, with a CLI beside the routes) is inverted at one point (`store` imports `server`) and bypassed at two others (`cli` reads SQLite directly, `server` coordinates the cache).

### Files Reviewed
| File | Structural Role | Layer | Risk |
|------|----------------|-------|------|
| `app/server.py` | Routes, identity, slug helper | Interface | High |
| `app/store.py` | Persistence | Core/data | High |
| `app/cache.py` | Search cache | Core/data (but called from the interface layer) | Medium |
| `app/cli.py` | Second interface | Interface | High |
| `app/config.py` | Settings | Shared | Medium |
| `app/pagination.py`, `app/utils.py` | Helpers | Shared | Low |
| `app/static/*` | Client | Presentation | Low |

### Critical Issues (Must Fix)
| # | Issue | Files Involved | Structural Impact | Fix |
|---|-------|---------------|-------------------|-----|
| S1 | The data layer depends on the HTTP layer: `store.py` does `from app.server import current_user`; `server.py` then imports `store` inside each route function to avoid a cycle | `store.py:7`, `server.py:29,41,50,64,72,85`, `cli.py:7` | A circular dependency, hidden by lazy imports. Every store call needs a live Flask request, so the second interface (CLI) cannot use the store at all (traced), and importing `store` builds the Flask app | Pass `owner` into each store function; `server` calls `store.add_note(current_user(), ...)`; `cli` supplies its own owner; then `store` imports only `config` |

### Recommendations
| # | Issue | Why | Fix |
|---|-------|-----|-----|
| S2 | `cli.cmd_export` opens SQLite itself and hard-codes the column list | A schema change must be made in two files; the CLI bypasses the store contract | Add `store.all_notes()` and use it |
| S3 | The route layer coordinates the cache and the store (`server.py:75-79`) | Cache policy (key, invalidation) leaks into routes, which is how the missing owner in the key happened | Cache inside `store.search(owner, query)` |
| S4 | The CLI hard-codes `limit=50` while the server uses `config.PAGE_SIZE` | Two sources of truth for page size | Use the config value |
| S5 | API/page contract is implicit and half-used | `page`, `pages`, `tags`, `slug`, `owner` are produced and not consumed by the page | Decide the contract and trim the unused fields (or build the UI) |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Make `app.server` an app factory (`create_app()`) | Lets tests and WSGI servers call `init()` once and avoids import-time side effects |
| 2 | Put identity in one small module (`auth.py`) | Gives the `X-User` decision a single home |

### Dependency Map
```
static page ──HTTP──> server.py ──(lazy import, x6)──> store.py ──> config.py
                         │  ▲                              │
                         │  └──── current_user() ──────────┘   <-- store -> server (inverted; cycle)
                         ├──> cache.py                      (called by routes, not by store)
                         ├──> pagination.py
                         └──> config.py

cli.py ──> store.py ──> server.py ──> flask   (CLI drags in the web framework)
cli.py ──> sqlite3 (direct, bypasses store)
cli.py ──> config.py

utils.py  (no importers)
```
Concerning arrows: `store -> server` (inverted, cyclic), `cli -> sqlite3` (layer bypass), `server -> cache` (policy in the wrong layer). `utils.py` has no inbound arrows.

### Boundary Crossing Analysis
| Crossing | From -> To | Clean? | Notes |
|----------|-----------|--------|-------|
| Page to API | `app.js` -> `/api/*` | Partly | Untyped JSON; fields produced and not consumed |
| Routes to store | `server` -> `store` | No | Lazy imports to dodge the cycle |
| Store to routes | `store` -> `server.current_user` | **No** | Dependency inversion; needs a Flask request context |
| CLI to store | `cli` -> `store` | No | Inherits the same request-context dependency |
| CLI to database | `cli` -> `sqlite3` | No | Skips the store and re-states the schema |
| Routes to cache | `server` -> `cache` | Partly | Cache key omits owner |
| Config reads | all -> `config` | Yes | Constants only; no environment layer |

### Verdict Details
- Dependency Direction: CONCERNS
- Module Coupling: CONCERNS
- Cohesion: PASS (modules are small and single-purpose; `server.py` carries a stray slug helper)
- Layer Boundaries: CONCERNS
- Change Propagation: CONCERNS (a schema change touches `store.py` and `cli.py`; page-size change touches `config.py` and `cli.py`)

---

## 6. Repo Maintainer

**Verdict**: APPROVE WITH CHANGES

**Perspective**: Repo Maintainer | **Date**: 2026-11-21 | **Source**: whole repo, conventions inferred from the README layout and the code itself

### Plan Summary
A tidy small repo with a clear README layout, but with dead and duplicated helpers, one naming outlier, repeated lazy imports, swallowed exceptions, tests only for the one module that needs them least, and no tooling that would enforce any convention.

### Files Reviewed
| File | Convention Status | Risk |
|------|------------------|------|
| `README.md` | Layout list matches the files; omits config, auth, API | Low |
| `pyproject.toml` | Minimal; no lint/type/test-extra config | Medium |
| `app/server.py` | Lazy imports x6; duplicate slug helper | Medium |
| `app/store.py` | `getNoteById` camelCase and unused; bare `except` | Medium |
| `app/utils.py` | Two functions, zero callers | Medium |
| `app/cli.py` | Raw SQL duplicate of store; catch-all | Medium |
| `app/pagination.py`, `app/cache.py`, `app/config.py` | Conform | Low |
| `tests/test_pagination.py` | Good tests; sole test file | Medium |
| `app/static/*` | Consistent with each other | Low |

### Critical Issues (Must Fix)
None. Every item the convention lens found is a Recommendation. (Swallowed exceptions are a convention problem here too, but they are tracked as critical issues #6, #7 and #12 by the lenses that own their consequences.)

### Recommendations
| # | Issue | Why | Fix |
|---|-------|-----|-----|
| R1 | `server.make_slug` duplicates `utils.slugify`, and `make_slug` is the worse of the two (drops non-ASCII, does not collapse hyphens, so "Café" becomes "caf") | Two slug rules; the better one is unused | Use `utils.slugify` in the route (or delete both, since the page ignores `slug`) |
| R2 | `utils.truncate` and `utils.slugify` (as `slugify`) have no callers; `store.getNoteById` has none | Dead code | Delete or use |
| R3 | `getNoteById` is camelCase in a snake_case codebase | Convention drift (and it is the only such name) | Rename to `get_note_by_id` if kept |
| R4 | `from app import store` repeated inside six route bodies | Symptom of the `store <-> server` cycle | Fix the cycle, import once at the top |
| R5 | No lint/format/type config, no `.gitignore`, `pytest` not declared as a dev dependency, no CI | Nothing enforces anything; `notes.db` and `__pycache__` are not ignored | `ruff` + `mypy` config in `pyproject.toml`, a `test` extra, a `.gitignore` |
| R6 | Tests cover only `parse_page` | The store, routes, cache and CLI have no tests, and the critical issues live there | Add Flask-client and temp-DB tests |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Docstrings on `store.py` functions (other modules have them) | Small consistency gain |
| 2 | Remove the unused `--muted` CSS token and the never-applied `:disabled` style, or use them | Dead CSS |
| 3 | `pages` and `parse_page` both compute `-(-total // size)` | One small duplicate in `pagination.py` |
| 4 | Add a LICENSE and a short CONTRIBUTING/dev section to the README | Basic repo hygiene |

### Convention Compliance Checklist
| Convention | Status | Notes |
|-----------|--------|-------|
| File placement | OK | Matches the README layout; static assets under `app/static/` |
| Naming conventions | WARN | `getNoteById` is the only camelCase function; `cmd_*` and `make_slug` are consistent |
| Export/module convention | OK | No barrel/`__all__`; direct module imports everywhere |
| Import ordering | OK | stdlib, third-party, then local, in every file; function-level imports in `server.py` are the exception |
| Path aliases used | n/a | Absolute `app.` imports used consistently |
| No dead code left | FAIL | `getNoteById`, `utils.slugify`, `utils.truncate`, `make_slug` duplicate |
| Structured logging | FAIL | No logging anywhere; `cli.py:15` prints `Error` |
| No lint suppressions | WARN | No suppressions, but three empty/blanket catches (`store.py:88`, `cli.py:14`, `app.js:42`) |
| Docs for new directories | OK | README layout covers every directory |

### Reuse Opportunities
`utils.slugify` replaces `server.make_slug`. `store.list_notes` plus a new `store.all_notes()` replaces the raw SQL in `cli.cmd_export`. The `token` variables in `style.css` replace the literals in `.note`. `config.PAGE_SIZE` replaces the literal 50 in `cli.cmd_list`.

### Verdict Details
- File Organization: PASS
- Naming Consistency: CONCERNS (one outlier)
- Import Hygiene: CONCERNS (lazy imports caused by the cycle)
- Code Reuse: CONCERNS (duplicate slug, unused helpers)
- Lint Compliance: CONCERNS (no tooling; broad exception handlers)

---

## 7. Production Readiness

**Verdict**: NEEDS REWORK

**Perspective**: Production Readiness Engineer | **Date**: 2026-11-21 | **Source**: whole repo, as a self-hosted service

### Plan Summary
What ships: a Flask dev server on every interface with debug on, a SQLite file at a path from someone else's laptop, and a schema that is created only when the module is run directly. What could break: first start on any other machine, any error (RCE via the debugger), any failed update (silent).

### Files Reviewed
| File | Production Role | Risk |
|------|----------------|------|
| `app/config.py` | Runtime settings | High |
| `app/server.py` | Entry point, routes | High |
| `app/store.py` | Persistence and schema | High |
| `app/cache.py` | In-process state | Medium |
| `app/cli.py` | Operator tooling | High |
| `pyproject.toml` | Packaging | Medium |
| `README.md` | Run instructions | Medium |

### Critical Issues (Must Fix)
| # | Issue | File(s) | Production Failure Mode | Fix |
|---|-------|---------|------------------------|-----|
| P1 | `DEBUG = True` and `HOST = "0.0.0.0"` | `config.py:4-5`, `server.py:87` | The Werkzeug debugger (a Python console behind a PIN that is derivable on the host in some setups) is exposed to the network; any unhandled exception page becomes an RCE surface; the README tells the user to open `localhost`, hiding that it listens everywhere | Safe defaults (debug off, 127.0.0.1), env overrides, a WSGI server for real use |
| P2 | `DB_PATH = "/Users/dev/projects/jotter/notes.db"` | `config.py:3` | On any machine without that directory: `sqlite3.OperationalError: unable to open database file`, from `init()` at startup and from every CLI command | `JOTTER_DB` env var with a default under the user's data dir; create the parent directory |
| P3 | `store.init()` runs only in `server.py`'s `__main__` block; the CLI and any WSGI entry point never call it | `server.py:83-86`, `cli.py` | Under `gunicorn app.server:app`, or `jotter add` on a fresh DB, the first query fails with `no such table: notes`; a fresh database is unusable except through `python -m app.server` | Call `init()` from an app factory and from the CLI `main()` |
| P4 | A failed note update returns success and leaves the note half-updated | `store.py:74-89` | Disk full, DB locked or bad input: no log, no error, `{"ok": true}`; tags deleted and committed first, so data loss is permanent and silent | Single transaction, no blanket catch, an error handler that logs |

### Recommendations
| # | Issue | Why | Fix |
|---|-------|-----|-----|
| P5 | No logging at all | Cannot reconstruct what happened; user errors cannot be told from system errors | Standard `logging`, configure in the entry point |
| P6 | Dev server only; no documented production run command; no health endpoint | Flask's built-in server is not for production | Document `gunicorn`; add `/healthz` |
| P7 | Packaging: no `[build-system]`, no package-data for `app/static/` | A non-editable wheel will likely omit the page, CSS and JS (static files are not Python files; unverified, not built here) | Declare setuptools with `package-data`/`include-package-data` |
| P8 | Search cache is process-local, unbounded and never invalidated | Stale for 60 s after writes; memory grows with distinct queries; multi-worker deployments each hold their own | Bound it, invalidate on write, or remove |
| P9 | No schema versioning or migrations | `CREATE TABLE IF NOT EXISTS` cannot evolve the schema; rollback after a column change breaks | Add a `PRAGMA user_version` check |
| P10 | No backup or export-safety story; `jotter export` overwrites in place | Crash during export yields a truncated file; no restore path | Temp file + rename; document a backup command |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | WAL mode and a busy timeout | Fewer "database is locked" errors under concurrent use |
| 2 | Security headers (CSP, `X-Content-Type-Options`) | A strict CSP would have blunted the XSS in the page |
| 3 | Request-size limit (`MAX_CONTENT_LENGTH`) | A body of any size is read and stored today |

### Failure Mode Analysis
| Scenario | What Fails | User Impact | Recovery | Plan Handles It? |
|----------|-----------|-------------|----------|-------------------|
| First start on a new machine | `DB_PATH` directory missing | Server exits with a SQLite traceback | Edit source | No |
| Start via a WSGI server | `init()` never runs | Every request is a 500 (`no such table`) | Run `__main__` once | No |
| Unhandled exception with debug on | Debugger page served on 0.0.0.0 | Remote code execution | None | No |
| DB locked or disk full during update | Exception swallowed | UI says saved, note and tags inconsistent | None (silent) | No |
| Two users search the same text | Shared cache entry | One user sees the other's notes | Wait out TTL | No |
| Process killed mid-export | Partial JSON file | Corrupt export | Re-run | No |
| Long-running process, many distinct searches | Cache dict grows | Memory growth | Restart | No |
| Delete a note while others read | Separate statements in one transaction | Fine | n/a | Yes (delete runs in one `with`) |
| SQL input with quotes | Parameterised queries | No injection | n/a | Yes |

### Environment Checklist
| Concern | Dev | Prod | Gap? |
|---------|-----|------|------|
| File paths | `/Users/dev/projects/jotter/notes.db` | Any other path | **Yes**, hard-coded to one person's machine |
| Network | `0.0.0.0:5000`, debug on | Behind a proxy, ideally loopback | **Yes**, debug on, all interfaces |
| Permissions | Writable dev directory | Service user, may be read-only | Unchecked: no directory creation or error message |
| Config | Constants in `config.py` | Needs env overrides | **Yes**, none exist |
| Build output | Editable install, static in the tree | Wheel/sdist | **Likely**: static files not declared as package data (unverified) |

### Verdict Details
- E2E Flow: CONCERNS (works only via `python -m app.server` on one machine)
- Error Recovery: CONCERNS
- Data Integrity: CONCERNS (non-atomic update; unenforced foreign keys; no migrations)
- Environment Parity: CONCERNS
- Observability: CONCERNS (no logging)

---

## 8. DX Engineer

**Verdict**: NEEDS REWORK

**Perspective**: Developer Experience Engineer | **Date**: 2026-11-21 | **Source**: `app/cli.py`, `app/config.py`, the HTTP API, README

### Plan Summary
The operator touches three surfaces: the `jotter` CLI (`add`, `list`, `export`), a JSON API, and `config.py` constants. First use is `pip install -e .` then `python -m app.server` or `jotter add`.

### Files Reviewed
| File | DX Role | Risk |
|------|---------|------|
| `app/cli.py` | CLI | High |
| `app/config.py` | Configuration | High |
| `app/server.py` | API behaviour and errors | Medium |
| `README.md` | Onboarding docs | Medium |
| `pyproject.toml` | Entry point `jotter` | Low |

### Critical Issues (Must Fix)
| # | Issue | Impact on Developer | Fix |
|---|-------|-------------------|-----|
| X1 | `cmd_add` wraps everything in `except Exception: print("Error")`: no cause, no hint, exit code 0. Traced: with the current store this branch always fires, because `current_user()` raises outside a request context | The command that most users run first fails with one word, and `$?` says success, so scripts and CI cannot detect it; `jotter list` instead dies with a raw `RuntimeError: Working outside of request context` | Remove the catch-all; print `error: could not add note: <cause>` to stderr and `sys.exit(1)`; fix the cause (see Structural S1) |
| X2 | The DB path and every other setting can only be changed by editing `config.py`, and the default is `/Users/dev/projects/jotter/notes.db` | A first run anywhere else gives a bare `sqlite3.OperationalError: unable to open database file` with no mention of `config.DB_PATH`; no flag or env var to point the CLI at a different DB | `JOTTER_DB` env var and `--db` flag; catch the open error and say which path failed and how to change it |

### Recommendations
| # | Issue | Why | Fix |
|---|-------|-----|-----|
| X3 | `jotter list` prints nothing when empty, has no `--limit`/`--json`, and hard-codes 50 | Not scriptable, ambiguous when empty | `--limit`, `--json`, "No notes." message |
| X4 | `export` silently overwrites an existing file and exports every owner's notes (including the `owner` field) | Surprising for a destructive, wide operation | Warn or require `--force`; add `--owner` |
| X5 | CLI has no `delete`, `search` or `edit`; API has them | CLI/API parity gap | Add the commands (they are thin wrappers once the store takes `owner`) |
| X6 | API error format is inconsistent: JSON for update validation, HTML 400/415/500 elsewhere, success for unknown ids | A client cannot parse failures uniformly | JSON error handler for all API routes |
| X7 | `config.py` has six unexplained constants and no override mechanism | The config file is the documentation | Comment each field; document env vars in the README |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | `jotter add -` to read the body from stdin | Composes with pipes |
| 2 | `jotter --version` | Standard flag; version exists in `pyproject.toml` |
| 3 | README: a short API section (routes, payloads, the `X-User` header) | Integrators have to read the source today |

### Error Message Audit
| Error Scenario | Current Message | What Developer Needs | Suggested Message |
|---------------|----------------|---------------------|-------------------|
| `jotter add` fails (any reason) | `Error` (exit 0) | What failed, why, what to do | `error: could not add note: <cause>. Check that the database is reachable (JOTTER_DB=<path>).` (exit 1) |
| `jotter list` (traced) | Raw `RuntimeError: Working outside of request context` traceback | A readable cause | Fixed by passing an owner; otherwise `error: could not read notes: <cause>` |
| Start or CLI with a missing DB directory | `sqlite3.OperationalError: unable to open database file` | The path that failed and how to change it | `error: cannot open database at <path>. Set JOTTER_DB or create the directory.` |
| `jotter export` to a missing directory | `FileNotFoundError` traceback | Path and next step | `error: cannot write <path>: directory does not exist` |
| `jotter export` on a DB with no schema | `sqlite3.OperationalError: no such table: notes` | A suggestion to initialise | `error: database at <path> has no notes table; run the server once or call init` |
| `POST /api/notes` missing `title` | Flask HTML 500 | JSON 400 naming the field | `{"error": "title is required"}` (the update route already does this) |
| `POST /api/notes` non-JSON body | Flask HTML 415 | JSON explaining the content type | `{"error": "send application/json"}` |
| `PUT` with title over 200 chars | `{"error": "title must be at most 200 characters"}` | Same as now | Good as is |
| `PUT`/`DELETE` unknown id | `{"ok": true}` / 204 | 404 | `{"error": "note 42 not found"}` |
| Debug traceback page | Full interactive page | Nothing public | Debug off by default |

### Developer Journey
- First use: `pip install -e .` works; `python -m app.server` fails on any machine other than the author's (X2/P2). `jotter add "t" "b"` prints `Error` (X1). The README says nothing about either. Friction: severe.
- Daily use: the CLI offers three commands, none scriptable (no exit codes, no JSON, no filters). The web page is the only usable interface.
- Power use: no search or delete from the CLI, no way to select a database, no way to integrate with the API without reading `server.py`.

### Verdict Details
- Error Quality: CONCERNS
- Defaults & Config: CONCERNS
- Keyboard Experience: PASS for the CLI as far as it goes (argparse gives `--help` for every subcommand and Ctrl+C works); the web form submits on Enter
- Discoverability: CONCERNS (`--help` exists via argparse; README does not describe config, auth or API)
- Workflow Integration: CONCERNS (exit codes, JSON, stdin)

---

## 9. Performance Engineer

**Verdict**: NEEDS REWORK

**Perspective**: Performance Engineer | **Date**: 2026-11-21 | **Source**: whole repo; hot paths are the notes list, search and the page's click handling

### Plan Summary
Small data and a dev server, so steady-state cost is low, but two things grow without bound: the client's click listeners (request storm) and the server's search cache.

### Files Reviewed
| File | Performance Role | Risk |
|------|-----------------|------|
| `app/static/app.js` | Request generation, listener lifecycle | High |
| `app/cache.py` | Long-lived in-memory state | High |
| `app/store.py` | Queries and connections | Medium |
| `app/server.py` | List route with per-note queries | Medium |
| `app/cli.py` | Reads whole table for export | Low |

### Critical Issues (Must Fix)
| # | Issue | File(s) | Impact | Fix |
|---|-------|---------|--------|-----|
| E1 | `render()` registers a `document` click listener on every call | `app.js:23-27` | Traced: the number of listeners doubles with each delete. k deletes in one session means one click sends about 2^k DELETEs and 2^k reloads, each reload being N+2 DB connections and each adding listeners again. After about 10 deletes the tab is firing about a thousand requests per click | Register once at module level (event delegation on `list`) |
| E2 | `_results` grows without bound: keys are user-supplied query strings, values are full result sets, and expired entries are never removed (only skipped on read) | `cache.py:5-20` | Memory grows for the life of the process; any caller can fill it by searching distinct strings | Evict expired entries on `put`, cap the size (LRU), or use `functools.lru_cache` with a TTL wrapper; invalidate on write |

### Recommendations
| # | Issue | File(s) | Why | Fix |
|---|-------|---------|-----|-----|
| E3 | N+1: one connection and one `SELECT` per note for tags | `server.py:33-35`, `store.py:60-65` | A 20-note page = 22 connection opens | One `IN (...)` query per page |
| E4 | No index on `tags(note_id)` or `notes(owner, updated_at)` | `store.py:9-21` | Every `tags_for` scans the whole tags table, so the list cost is O(notes per page x total tags); `ORDER BY updated_at` sorts all of an owner's rows | Add both indexes |
| E5 | Search has no `LIMIT` and does `LIKE '%q%'` over title and body | `store.py:98-104` | Full scan; the empty query returns everything, and the cache then stores all of it | `LIMIT`, minimum query length |
| E6 | Every store call opens a new connection | `store.py` (all) | Connection setup per call, multiplied by E3 | One connection per request (Flask `g`) |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | WAL mode | Readers do not block the writer |
| 2 | Debounce when a search box is added | The endpoint has no UI today, so no hot path yet |
| 3 | `export` could stream rows rather than `fetchall()` | Only matters for very large tables |

### Resource Budget
| Resource | Current | After Plan | Concern? |
|----------|---------|-----------|----------|
| Cross-boundary calls per action (list page) | 1 GET to the API; 22 SQLite connection opens behind it | Same, no change proposed beyond fixes | Yes, N+1 |
| Cross-boundary calls per delete click | 1 DELETE + 1 GET for the first click; 2^k of each after k deletes | Should be 1 + 1 | **Yes**, exponential (E1) |
| Event listeners added | 1 per `render()` call, never removed | 1 total | **Yes** |
| Memory growth per hour | Search cache grows with every distinct query, never freed | Bounded | **Yes** |
| Startup time impact | One schema script; Flask import | None | No |
| Bundle size impact | 45-line JS, ~110 lines of CSS, no dependencies | None | No |

### Hot Path Analysis
The hot path is the list route (every page load and every post-action reload): `count_notes` (1 connection), `list_notes` (1 connection), then `tags_for` per note (N connections, each a full-table scan of `tags` because there is no index). With 20 notes per page that is 22 opens and 20 scans per request, multiplied by E1 after a few deletes. Search is not on the page's path, but when called it scans both text columns for every owner row and caches the whole result for 60 s regardless of size. The CLI paths are cold. Nothing on the keystroke path exists yet.

### Verdict Details
- Memory Management: CONCERNS (unbounded cache; listener accumulation)
- Boundary Efficiency: CONCERNS (N+1; request storm)
- I/O Patterns: CONCERNS (no indexes; full scans; connection per call)
- Startup Impact: PASS
- Long-Session Stability: CONCERNS (listener doubling, cache growth)

---

## 10. Accessibility Engineer

**Verdict**: NEEDS REWORK

**Perspective**: Accessibility Engineer | **Date**: 2026-11-21 | **Source**: `app/static/index.html`, `app.js`, `style.css`

### Plan Summary
A small form-and-list page with good bones (landmarks, `lang`, labelled body textarea, labelled nav, sequential headings, a visible focus ring on the Save button) and three blockers for keyboard and screen-reader users: an unfocusable Delete control, removed input focus rings, and an unlabelled title field.

### Files Reviewed
| File | A11y Role | Risk |
|------|----------|------|
| `app/static/index.html` | Landmarks, form labels, headings | Medium |
| `app/static/app.js` | Builds the note markup and the delete control | High |
| `app/static/style.css` | Focus, contrast, motion | High |

### Critical Issues (Must Fix)
| # | Issue | WCAG Criterion | File(s) | Impact | Fix |
|---|-------|---------------|---------|--------|-----|
| A1 | Delete is a `<div class="delete">` with a document-level click handler, no `tabindex`, no role, no key handler | 2.1.1 Keyboard, 4.1.2 Name/Role/Value | `app.js:16,23-27`, `style.css:104-108` | Keyboard-only and screen-reader users cannot delete notes at all; the control is announced as plain text "Delete" if reached | `<button type="button" class="delete" aria-label="Delete note: {title}" data-id="...">Delete</button>` |
| A2 | `outline: none` on the title input and textarea, with no replacement | 2.4.7 Focus Visible | `style.css:55-64` | A keyboard user cannot see which field has focus | Remove it, or add an equivalent `:focus-visible` style |
| A3 | The title input has only a placeholder; the body has a `<label>` | 3.3.2 Labels or Instructions, 1.3.1, 4.1.2 | `index.html:19` | The accessible name is the placeholder, which vanishes on typing and is not reliably announced; inconsistent with the body field | Add `<label for="title">Title</label>` (can be visually hidden) |

### Recommendations
| # | Issue | WCAG Criterion | Fix |
|---|-------|---------------|-----|
| A4 | List changes (add, delete, error) are not announced | 4.1.3 Status Messages | A `role="status"`/`aria-live="polite"` region updated on each action |
| A5 | Touch and pointer targets are small: Delete is bare text, Save is about 36 px high | 2.5.8 Target Size (and the 44 px guideline) | Padding or a pseudo-element hit area of at least 44 px |
| A6 | No error text tied to inputs; a failed save is silent | 3.3.1 Error Identification | Show an error message and link it with `aria-describedby`; move focus to it |
| A7 | When a note is deleted the list is rebuilt and focus falls to `<body>` | 2.4.3 Focus Order | After delete, move focus to the next note's Delete button, or to the heading |
| A8 | Hover-only styling on Save, and Delete has none | 1.4.13 / usability | Gate hover with `@media (hover: hover)`; give Delete focus and hover states |

### Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Skip link to `main` | The page is short; useful once navigation grows |
| 2 | Notes as a `<ul>` of `<li>` | Screen readers announce "list, 20 items" |
| 3 | Remove or give a purpose to `<nav>` with its single self-link | Avoids an empty navigation landmark |
| 4 | Measure placeholder contrast in both themes | Browser default colour; unverified |

### Keyboard Navigation Walkthrough
| Step | Action | Expected Focus | Expected Announcement | Plan Handles? |
|------|--------|---------------|----------------------|---------------|
| 1 | Tab from page load | "Notes" link in the topbar | "Notes, link" | Yes (default focus ring) |
| 2 | Tab | Title input | "Title, edit text" | **No**: no label (A3); no visible focus (A2) |
| 3 | Tab | Body textarea | "Note, edit text" | Label yes; **visible focus no** (A2) |
| 4 | Tab | Save button | "Save, button" | Yes (visible `:focus-visible` ring) |
| 5 | Press Enter on a field or Save | Form submits; focus stays | "Saved" or an error | **No**: nothing announced (A4, A6) |
| 6 | Tab onward through notes | Delete for each note | "Delete note: <title>, button" | **No**: Delete is not focusable at all (A1) |
| 7 | Activate delete (mouse only) | Focus should move to the next note | "Note deleted" | **No**: focus is lost, no announcement (A4, A7) |

### ARIA Checklist
| Element | Role | Label | States | Keyboard | Notes |
|---------|------|-------|--------|----------|-------|
| `<header class="topbar">` | banner (implicit) | none | n/a | n/a | OK |
| `<nav aria-label="Main">` | navigation | "Main" | n/a | Tab | OK; holds one link to the current page |
| `<main>` | main | none | n/a | n/a | OK |
| `<form id="new-note">` | form (unnamed) | none | n/a | Enter submits | Acceptable |
| Title `<input>` | textbox | **placeholder only** | no `required` | Yes | Fail (A3) |
| Body `<textarea>` | textbox | `<label for="body">` | n/a | Yes | Pass |
| Save `<button>` | button | "Save" | `:disabled` styled, never set | Yes | Pass |
| `<section aria-labelledby="notes-heading">` | region | "Your notes" | n/a | n/a | Pass; h1 -> h2 -> h3 order is correct |
| `<article class="note">` | article | none (title is the first heading) | n/a | n/a | Pass |
| `<div class="delete">` | **none** | text only, not unique | none | **None** | Fail (A1) |
| Notes container `#notes` | none | none | no live region | n/a | Gap (A4) |

### Verdict Details
- Screen Reader Compatibility: CONCERNS (A1, A3, A4)
- Keyboard Navigation: CONCERNS (A1)
- Focus Management: CONCERNS (A2, A7)
- Color Contrast: PASS for measured pairs in both themes (see Design System Compliance for the computed ratios); placeholder colour unverified
- Motion Sensitivity: PASS (one 150 ms background-colour transition, no movement)

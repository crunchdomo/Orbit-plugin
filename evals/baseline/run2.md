# Full Spectrum Audit: jotter (Flask notes service, web page and CLI)

**Date**: 2026-11-21
**Mode**: Repo Health (option 3, general repo health)
**Source**: `/private/tmp/claude-501/-Users-oenfadam-Documents-Orbit-plugin/ec022de0-9140-4432-ae41-0c6144f29ec4/scratchpad/run2` (not a git repository; the whole tree was treated as the repo)
**Lenses Run**: 9/10
**Lenses Skipped**: Backend Engineer (no Rust/Tauri changes; the relevance table skips this lens on that condition. The Python server and store code was still read, and its problems are reported under Structural, Repo Maintainer, Production Readiness and DX.)

Files read in full (14): `pyproject.toml`, `README.md`, `app/__init__.py` (empty), `app/config.py`, `app/store.py`, `app/cache.py`, `app/utils.py`, `app/pagination.py`, `app/cli.py`, `app/server.py`, `tests/test_pagination.py`, `app/static/index.html`, `app/static/style.css`, `app/static/app.js`.

---

## Master Verdict: NEEDS REWORK

The pagination module and the CSS token setup are solid, but the rest has several defects that each block shipping: search results are cached without regard to the user and leak between users, identity is an unauthenticated client header with no ownership check on update or delete, notes are rendered with `innerHTML` (stored XSS), and the only run path is Flask debug mode on `0.0.0.0`. The data layer imports from the HTTP layer, which breaks the CLI outright. The front end also has a listener leak that doubles the DELETE requests on every delete, swallows save failures, and never shows notes past the first 20. One critical NEEDS REWORK is enough to decide this verdict, and there are 17 deduplicated critical issues.

## Verdict by Lens

| # | Lens | Verdict | Critical | Recommendations |
|---|------|---------|----------|-----------------|
| 1 | Design Engineer | APPROVE WITH CHANGES | 2 | 5 |
| 2 | UX Engineer | NEEDS REWORK | 3 | 6 |
| 3 | Frontend Engineer | NEEDS REWORK | 3 | 4 |
| 4 | Backend Engineer | SKIPPED | - | - |
| 5 | Structural Engineer | NEEDS REWORK | 2 | 5 |
| 6 | Repo Maintainer | APPROVE WITH CHANGES | 2 | 8 |
| 7 | Production Readiness | NEEDS REWORK | 7 | 8 |
| 8 | DX Engineer | NEEDS REWORK | 2 | 7 |
| 9 | Performance Engineer | NEEDS REWORK | 2 | 4 |
| 10 | Accessibility Engineer | NEEDS REWORK | 3 | 6 |

## All Critical Issues (Must Fix)

Collected from every lens, deduplicated, ordered by severity:

| # | Issue | Lens(es) | File(s) | Impact | Fix |
|---|-------|----------|---------|--------|-----|
| 1 | Search cache is keyed by query string only, but results are per-user. User B searching a term user A searched in the last 60 s receives A's notes. | Production Readiness | `app/cache.py:9-20`, `app/server.py:74-80` | Cross-user data disclosure | Include the owner in the cache key (`(owner, query)`), or drop the cache. Best: move caching behind the store so the owner scope cannot be forgotten. |
| 2 | Identity is `request.headers.get("X-User", "local")`. Any client can claim any user, and there is no authentication. Combined with the `0.0.0.0` bind, "owner" scoping is decorative. | Production Readiness | `app/server.py:13-14`, `app/config.py:5` | Impersonation of any user, read and write | Authenticate at the edge (reverse proxy that sets the header and strips client copies, or real auth). Bind to `127.0.0.1` by default. Document the trust model in the README. |
| 3 | Update and delete have no ownership check: `UPDATE notes ... WHERE id = ?`, `DELETE ... WHERE id = ?`, and the unused `getNoteById` are unscoped. Read, list and search are scoped. Any user can edit or delete any note by id. | Production Readiness, Structural | `app/store.py:68-71, 74-95`, `app/server.py:48-67` | Cross-user tampering and deletion (IDOR) | Pass `owner` explicitly to every store function and add `AND owner = ?` to every statement. Return 404 when no row matches. |
| 3a | (see #3) tag rows are also written for an id the caller does not own, and for ids that do not exist (no foreign-key enforcement). | Production Readiness | `app/store.py:83-86`, `app/store.py:17-20` | Orphan and foreign tag rows | `PRAGMA foreign_keys = ON` in `connect()`; check the UPDATE rowcount before touching tags. |
| 4 | Stored XSS: note title and body are interpolated into `innerHTML` unescaped. | Frontend Engineer | `app/static/app.js:15-19` | Script execution for anyone who views a note; with #2 an attacker can plant notes in another user's list | Build nodes with `textContent`, or escape. Never use `innerHTML` for user text. |
| 5 | The only documented run path is `app.run(host="0.0.0.0", debug=True)` from `if __name__ == "__main__"`, with config hardcoded to debug on. The Werkzeug debugger is network-reachable, and `store.init()` runs only on this path, so any other server (gunicorn, `flask run`, a test client) hits "no such table". | Production Readiness | `app/server.py:83-87`, `app/config.py:4-5` | Remote code execution via debug console if PIN is guessed or leaked; every request 500s under a WSGI server | Read `DEBUG`, `HOST`, `PORT`, `DB_PATH` from environment with safe defaults (debug off, host 127.0.0.1). Create the schema from an app factory or on first connect. Document a gunicorn command. |
| 6 | `store.py` does `from app.server import current_user`, so the data layer depends on the HTTP layer. Server hides the cycle with function-level `from app import store` in six places. The CLI imports `store` and then calls `current_user()` outside a request context, so `jotter add` always fails and `jotter list` raises `RuntimeError: Working outside of request context`. | Structural, Repo Maintainer, Production Readiness, DX | `app/store.py:7, 39, 47, 56, 102`, `app/server.py:29, 41, 50, 64, 72, 84`, `app/cli.py:12, 19` | CLI is non-functional; layering inverted; cycle masked | Remove the import. Give store functions an explicit `owner: str` parameter (CLI passes its own, server passes `current_user()`). Then hoist the lazy imports to module top. |
| 7 | `update_note` commits the tag deletion first, then updates and re-inserts inside `try/except Exception: pass`. Any failure after the first commit leaves tags permanently deleted, the error is discarded, the connection is left open, and the route still returns `{"ok": true}`. | Production Readiness, Repo Maintainer | `app/store.py:74-89`, `app/server.py:58-59` | Silent data loss and false success | One transaction (`with connect() as conn:`), no first commit, no blanket except. Let errors propagate; map to 4xx/5xx in the route and log. |
| 8 | `render()` calls `document.addEventListener("click", ...)` on every render, and `render` runs on every `loadNotes()`. Each handler calls `loadNotes()`, so the listener count doubles on every delete (1, 2, 4, 8...) and each click sends that many DELETE requests and refetches. | Frontend Engineer, Performance Engineer | `app/static/app.js:23-27` | Request amplification and a slowdown that grows exponentially with normal use | Register the click handler once, outside `render()` (delegate on `#notes`). |
| 9 | Saves and deletes fail silently. `fetch` does not throw on HTTP 4xx/5xx, so `response.ok` is never checked, `form.reset()` runs even when the server rejected the note, and the empty `catch {}` hides network errors. Delete has no error handling at all. | UX Engineer, Frontend Engineer | `app/static/app.js:34-42, 25-26` | User loses typed text with no message; failed deletes look like they worked | Check `response.ok`, show an inline error (in an `aria-live` region), reset the form only on success, keep the draft on failure. |
| 10 | The UI fetches only `/api/notes` (page 1) and never shows `page`/`pages` or a pager. Once there are more than 20 notes, older notes cannot be reached from the web page. | UX Engineer | `app/static/app.js:5-8`, `app/server.py:31-36` | Notes appear to vanish | Add "Newer/Older" controls driven by `page` and `pages`, or load more on demand. |
| 11 | Delete is `<div class="delete">` with a click handler. It is not focusable, has no role or accessible name, and deletes instantly with no confirmation or undo, directly beside the title. | Accessibility Engineer, UX Engineer | `app/static/app.js:16`, `app/static/style.css:104-108` | Keyboard and screen-reader users cannot delete; any user can delete by accident with no recovery | `<button type="button" class="delete" aria-label="Delete note: TITLE">`; add confirmation (or an Undo toast) and move focus sensibly after removal. |
| 12 | `jotter add` wraps the call in `except Exception: print("Error")`: no message, no cause, stdout instead of stderr, exit code 0. | DX Engineer | `app/cli.py:10-15` | Scripts and CI cannot detect failure; the developer cannot tell why | Catch specific exceptions, print `jotter: could not add note: <reason>` to stderr, `sys.exit(1)`. |
| 13 | `DB_PATH` is an absolute path on one developer's machine: `/Users/dev/projects/jotter/notes.db`. On any other machine every request opens a nonexistent directory. No environment override exists. | Production Readiness | `app/config.py:3` | App cannot run anywhere but the author's laptop | `os.environ.get("JOTTER_DB", "notes.db")` or a user data dir; create the parent directory on first use. |
| 14 | The title `<input>` has only a `placeholder`, no `<label>` and no `aria-label` (the textarea does have a label). | Accessibility Engineer | `app/static/index.html:19` | Screen readers announce an unnamed edit field; placeholder disappears on typing | Add `<label for="title">Title</label>` (visible or visually hidden). |
| 15 | `.composer input, .composer textarea { outline: none; }` and no replacement `:focus` style, so keyboard focus is invisible in both fields. | Accessibility Engineer, Design Engineer | `app/static/style.css:55-64` | WCAG 2.4.7 failure; users cannot see where they are typing | Remove `outline: none`, or add `:focus-visible` using the same accent ring the button already uses. |
| 16 | The search cache never evicts. Expired entries are skipped on read but never deleted, and the key is any caller-supplied string, so memory grows without bound. | Performance Engineer | `app/cache.py:5-20` | Slow memory leak, and a trivial memory-exhaustion path via many distinct `q` values | Bound the size (e.g. `functools.lru_cache`-style with `maxsize`, or evict on `put`), or remove the cache; SQLite LIKE on a small table does not need it. |
| 17 | `.note` uses hardcoded hex (`#e5e5e5`, `#fafafa`, `#222222`, `#b91c1c`) instead of the tokens defined at the top of the file. In dark mode the page goes dark but the notes, the core content, stay light cards. | Design Engineer | `app/static/style.css:91-98, 104-108` | Dark mode parity broken; design tokens bypassed | Use `--surface`, `--border`, `--text`; add a `--danger` token with a dark-mode value for the delete color. |

(Row 3a is a sub-finding of #3, not counted separately: the critical count is 17.)

## Cross-Cutting Concerns

Issues flagged by 2+ lenses, systemic problems:

| Concern | Flagged By | Root Cause | Unified Fix |
|---------|-----------|------------|-------------|
| Errors are swallowed in every layer (`store.update_note`, `cli.cmd_add`, `app.js` empty catch, no `response.ok` check) | Production Readiness, DX, UX, Frontend, Repo Maintainer | No error-handling convention and no logging anywhere in the repo | Errors propagate to one boundary per layer (route, CLI main, UI), are logged with context (`logging` module), and are shown to the user with a reason |
| Identity is ambient HTTP state (`current_user()` reads `flask.request`) | Structural, Production Readiness, DX | Owner is not an explicit parameter, so it is forgotten in places (update/delete, cache key) and unavailable to the CLI | `owner` is an argument to every store function and part of every cache key; authentication happens only at the HTTP edge |
| The delete path is wrong end to end: div instead of button, no confirm, no owner check, listener leak with exponential requests, no error handling | UX, Accessibility, Frontend, Performance, Production Readiness | Delete was wired quickly and never reviewed as one flow | Rewrite as one flow: button with label, confirm/undo, one registered handler, `response.ok` check, owner-scoped SQL |
| Dev-only configuration shipped as defaults (absolute DB path, debug on, `0.0.0.0`, schema init only in `__main__`) | Production Readiness, Repo Maintainer, DX | `config.py` holds constants, not environment-driven settings | Environment-driven config with safe defaults and a documented production run command |
| Half-built features: pagination and search exist in the API but have no UI; `PUT` and tags have no UI; `utils.slugify`/`truncate` and `getNoteById` are unused | UX, Repo Maintainer, Structural, Performance | Features were added bottom-up without the UI or removal | Either finish the UI (pager, search box, edit) or delete the dead code |
| Search cache is wrong in three ways: not per-user, never evicts, never invalidated on writes (stale up to 60 s) | Production Readiness, Performance, UX | Cache was added as a standalone module with no owner or lifecycle | Remove it, or put it behind the store with owner key, size bound and invalidation on write |
| Design tokens bypassed and focus indication removed | Design, Accessibility | `.note` and `.composer` rules were written without using the token block above them | Use tokens everywhere; one shared `:focus-visible` rule |
| Duplicated slug logic (`server.make_slug` vs `utils.slugify`) with different behavior; slug is sent in the API and never used by the UI | Repo Maintainer, Structural | Helper written twice; one copy never wired in | Keep `utils.slugify`, delete `make_slug`, or drop the `slug` field if nothing consumes it |

## All Recommendations

| # | Recommendation | Lens | File(s) | Fix |
|---|---------------|------|---------|-----|
| 1 | Add structured logging (none exists anywhere) | Production Readiness, Repo Maintainer | all `app/*.py` | `logging.getLogger(__name__)`; log request errors and DB failures with context |
| 2 | Validate `POST /api/notes` the same way as `PUT`; today missing keys give 500 and `MAX_TITLE_LENGTH` is enforced only on update | Production Readiness, Repo Maintainer, DX | `app/server.py:43-45` vs `52-57` | Shared validator used by both routes; non-string types return 400 |
| 3 | Non-string `title`/`body`/`tags` reach `.strip()` or SQLite and produce 500 | Production Readiness | `app/server.py:52-58` | Type-check JSON fields before use |
| 4 | Fix N+1 in the list route: 1 count + 1 list + 20 `tags_for` queries, each on a new connection (22 connections per page load) | Performance | `app/server.py:31-36`, `app/store.py:60-65` | Single query with `GROUP_CONCAT` or one `WHERE note_id IN (...)` query; reuse one connection per request |
| 5 | Add indexes: `tags(note_id)`, `notes(owner, updated_at)` | Performance, Production Readiness | `app/store.py:9-21` | `CREATE INDEX IF NOT EXISTS ...` in `SCHEMA` |
| 6 | Search returns every match with no `LIMIT`, no `ORDER BY`; LIKE wildcards in the query are not escaped | Performance, Production Readiness | `app/store.py:98-104` | Add `ORDER BY updated_at DESC LIMIT ?`, escape `%`/`_` |
| 7 | Invalidate or bypass the search cache on create/update/delete | UX, Performance, Production Readiness | `app/cache.py`, `app/server.py` | Clear on write, or remove cache |
| 8 | Close connections explicitly (`with sqlite3.connect()` commits but does not close; `search` and `update_note` never close) | Production Readiness, Repo Maintainer | `app/store.py:24-27, 74-104` | `contextlib.closing`, or one connection per request via Flask `g` |
| 9 | Set `PRAGMA foreign_keys=ON`, WAL mode and a `busy_timeout` in `connect()` | Production Readiness | `app/store.py:24-27` | Add pragmas |
| 10 | No schema version or migration path; only `CREATE TABLE IF NOT EXISTS` | Production Readiness | `app/store.py:9-33` | `PRAGMA user_version` plus ordered migrations |
| 11 | Add a health endpoint and document backup of the SQLite file | Production Readiness | `app/server.py`, `README.md` | `GET /healthz`; README section |
| 12 | `export` reads every user's notes with raw sqlite, bypassing the store; overwrites the target silently; omits tags | Production Readiness, Structural, DX | `app/cli.py:23-33` | Go through a store function, add `--force`, include tags |
| 13 | `jotter list` hardcodes `limit=50`; no `--limit`/`--page`, no `--json` | DX | `app/cli.py:18-20, 45-46` | Flags with defaults |
| 14 | CLI positional args have no help text; no `--db` flag or env var; no `--version` | DX | `app/cli.py:36-53` | `help=`, `--db`, `--version` |
| 15 | CLI errors go to stdout and exit 0; use stderr and nonzero exit codes throughout | DX | `app/cli.py` | `sys.exit(1)` and stderr |
| 16 | API errors for POST/unhandled exceptions are Flask HTML pages; the PUT route returns JSON | DX, Production Readiness | `app/server.py` | `@app.errorhandler(Exception)` returning JSON |
| 17 | Empty state and loading state missing; failure state missing | Design, UX | `app/static/app.js`, `style.css` | "No notes yet. Write one above." and a "Loading..." / error line |
| 18 | Edit UI absent although `PUT` and tags exist; tags are never displayed | UX | `app/static/app.js` | Add edit-in-place and tag display, or delete the tag code |
| 19 | Search has no UI | UX, Repo Maintainer | `app/static/index.html` | Add a search input (with debounce) or remove the endpoint |
| 20 | Blank-title notes can be created (no required check client or server on POST) | UX | `index.html:19`, `server.py:43-45` | `required` on input plus server 400 |
| 21 | Save button is not disabled while the request is in flight (double-submit creates duplicates) | UX, Frontend | `app/static/app.js:30-43` | Disable during submit |
| 22 | One-item nav (`Notes` -> `/`) is a link to the current page | UX, Accessibility | `index.html:12-14` | Remove or add `aria-current="page"` |
| 23 | `loadNotes` and delete have no error handling; unhandled promise rejections; out-of-order responses can overwrite newer state | Frontend | `app/static/app.js:4-8, 23-27` | try/catch, track a request counter or `AbortController` |
| 24 | No JS lint or type check (`// @ts-check` + JSDoc would be cheap) | Frontend, Repo Maintainer | `app/static/app.js` | Add ESLint or ts-check |
| 25 | Add `color-scheme: light dark` so native controls and scrollbars follow the theme | Design | `app/static/style.css:1` | One line in `:root` |
| 26 | Input borders are about 1.5:1 against the page (hand-estimated, not tool-measured) in light and about 1.6:1 in dark, below the 3:1 non-text contrast for control boundaries | Design, Accessibility | `app/static/style.css:7, 17, 58` | Darken `--border` for inputs or add a stronger input border token |
| 27 | Delete control lacks hover/focus states and a 44px hit area; long titles and bodies have no `overflow-wrap` | Design, Accessibility | `app/static/style.css:100-108` | Button styles with padding; `overflow-wrap: anywhere` |
| 28 | Announce list changes and errors: add `aria-live="polite"` region; move focus after delete | Accessibility | `index.html`, `app.js` | Status region; focus the heading or next item |
| 29 | Remove duplicate and dead code: `make_slug` vs `utils.slugify`, `utils.truncate`, `store.getNoteById`, `.muted` token unused | Repo Maintainer, Structural | `server.py:17-19`, `utils.py`, `store.py:68-71`, `style.css:5` | Delete or wire in |
| 30 | `getNoteById` breaks the snake_case convention used everywhere else | Repo Maintainer | `app/store.py:68` | Rename or delete (unused) |
| 31 | Packaging: no `[build-system]`, no package data for `app/static`, pytest not declared as a dev dependency, generic top-level package name `app` | Repo Maintainer, Production Readiness | `pyproject.toml` | Add build-system and package-data; `[project.optional-dependencies] dev`; consider renaming package to `jotter` |
| 32 | Only `parse_page` is tested; store, server, cache, CLI and utils have no tests, including the two defects that would have been caught by a basic test (ownership, CLI) | Repo Maintainer | `tests/` | Add Flask test-client tests for ownership and cache scoping, and one CLI smoke test |
| 33 | No `.gitignore` (SQLite file and bytecode would be committed), no lint/format config (ruff), README layout omits `config.py` and `tests/` | Repo Maintainer | repo root, `README.md:22-29` | Add the files, update layout list |
| 34 | `Page.pages` and `parse_page` compute the page count twice | Repo Maintainer | `app/pagination.py:18, 33` | Build `Page` then clamp using `.pages` |

---

# Lens Reports

---

## 1. Design Engineer

**Verdict**: APPROVE WITH CHANGES

# Design Engineering Audit: jotter web page

**Perspective**: Design Engineer
**Date**: 2026-11-21
**Plan**: n/a (repo health; scope is `app/static/`)

## Plan Summary
A single-page notes UI: a top bar, a composer form and a list of note cards, styled with a small CSS custom-property token set and an automatic dark theme.

## Files Reviewed
| File | Visual Role | Risk |
|------|-------------|------|
| `app/static/style.css` | Tokens, layout, component styles | Medium: tokens exist but two rules bypass them |
| `app/static/index.html` | Structure of topbar, composer, list | Low |
| `app/static/app.js` | Builds note cards and the Delete control markup | Medium: markup determines visual states |

## Verdict: APPROVE WITH CHANGES

## Critical Issues (Must Fix)
| # | Issue | File(s) | Impact | Fix |
|---|-------|---------|--------|-----|
| 1 | `.note`, `.note .delete` use hardcoded hex (`#e5e5e5` border, `#fafafa` background, `#222222` text, `#b91c1c` delete) instead of the tokens in `:root`. Dark mode changes the page background but notes stay light. (Master #17) | `style.css:91-98, 104-108` | The main content breaks dark-mode parity and fragments the token system | Use `var(--surface)`, `var(--border)`, `var(--text)`; add `--danger` with a dark value |
| 2 | `outline: none` on inputs and textarea with no replacement focus style. (Master #15) | `style.css:55-64` | No visible keyboard focus on form fields | Remove it or add `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }` |

## Recommendations
| # | Issue | File(s) | Why | Fix |
|---|-------|---------|-----|-----|
| 1 | No loading, empty or error state for the notes list; the "Your notes" heading sits above an empty div | `index.html:25-28`, `app.js` | Real UIs need all three | Placeholder text and a styled error line |
| 2 | Native controls and scrollbars are not told about the dark scheme | `style.css:1-22` | Mismatched textarea scrollbar and autofill in dark mode | `color-scheme: light dark;` in `:root` |
| 3 | Input and card borders (`#d6d3d1` on `#ffffff`, about 1.5:1, hand-estimated) are very faint for control boundaries | `style.css:7, 58` | Fields hard to find, especially in dark (`#44403c` on `#1c1917`) | Stronger border token for form controls |
| 4 | Delete control has a pointer cursor only: no hover, focus, active or disabled treatment and no padding for a comfortable target | `style.css:104-108` | Interactive element with no state feedback | Style as a real button with all states |
| 5 | No overflow handling for long unbroken titles or bodies | `style.css:91-102` | Long strings overflow the 640px column | `overflow-wrap: anywhere` on `.note` |

## Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | `button.primary:active { transform: scale(0.97); }` | Tactile feedback per `make-interfaces-feel-better` |
| 2 | `text-wrap: balance` on `h1,h2,h3`, `-webkit-font-smoothing: antialiased` on `body` | Typographic polish |
| 3 | Wrap hover in `@media (hover: hover)` | Avoid sticky hover on touch devices |
| 4 | A `--danger` token pair for light and dark | Needed for the Delete fix |

## Design System Compliance
The token block is good: surface, text, muted, accent, accent-hover, border and radius, with a complete `prefers-color-scheme: dark` override. The composer and primary button use it correctly, the radius token is applied consistently (`--radius` on inputs, buttons and notes), the button transition names a specific property (`background-color`, 150ms, ease-out) and there is no `transition: all`. Fragmentation is limited to the `.note` block, which does not use any token, and `--muted` is defined but never used. Spacing values (8, 12, 16, 24) are consistent with an 4/8-based scale. Contrast pairs that I checked by hand-estimate pass: button text on accent in both themes, links in both themes, and the delete red on the light card (about 6.5:1, not tool-measured). Unverified: I did not render the page, so these are static estimates.

## Visual State Coverage
| Component/Element | Hover | Focus | Active | Disabled | Loading | Empty | Error | Dark Mode |
|-------------------|-------|-------|--------|----------|---------|-------|-------|-----------|
| Primary button (Save) | Yes | Yes (`:focus-visible`) | No | Styled, never applied | No | n/a | No | Yes |
| Title input | No | No (outline removed) | No | n/a | n/a | n/a | No | Yes |
| Note textarea | No | No (outline removed) | No | n/a | n/a | n/a | No | Yes |
| Note card | n/a | n/a | n/a | n/a | n/a | No | n/a | No (hardcoded light) |
| Delete control | No (cursor only) | No | No | No | No | n/a | No | Partial (fixed red, light card) |
| Nav link | Browser default | Browser default | Browser default | n/a | n/a | n/a | n/a | Yes |
| Notes list region | n/a | n/a | n/a | n/a | No | No | No | n/a |

## Verdict Details
- Design Token Fidelity: CONCERNS (`.note` block bypasses tokens)
- Visual State Coverage: CONCERNS (inputs and delete missing states; no loading/empty/error)
- Dark Mode Parity: CONCERNS (cards stay light)
- Animation Quality: PASS (one 150ms background-color transition; no motion needing a reduced-motion query)
- Visual Consistency: PASS

Reference skills consulted: `emil-design-engineering` (forms, touch targets, common-mistakes table), `make-interfaces-feel-better` (checklist), `web-animation-design` (150ms ease-out within the 100-300ms guidance).

---

## 2. UX Engineer

**Verdict**: NEEDS REWORK

# UX Audit: jotter notes page

**Perspective**: UX Engineer
**Date**: 2026-11-21
**Plan**: n/a (repo health)

## Plan Summary
A user writes a title and body, saves, sees a list of notes, and can delete a note. The API also supports editing, tags, search and paging, but the page exposes none of these.

## User Journey Map
| Step | Trigger -> Action -> Feedback -> Outcome | Status |
|------|------------------------------------------|--------|
| 1 | Open `/`: page loads, notes fetched, list rendered | WARN: no loading indicator, and for a new user the area under "Your notes" is blank (no empty state) |
| 2 | Type a title: field has placeholder only, no label | WARN: the placeholder is the only cue; it vanishes while typing |
| 3 | Click Save with a valid note: form clears and list reloads | WARN: only the list refresh signals success; no confirmation |
| 4 | Click Save when the server rejects it (400/500): form clears anyway | FAIL: no message, draft lost |
| 5 | Click Save with an empty title: a blank-title card is created | FAIL: no required-field feedback (`POST` has no validation) |
| 6 | Click Save twice quickly: duplicate notes | WARN: button not disabled while in flight |
| 7 | Have more than 20 notes: only the newest 20 show | FAIL: no pager, no "load more"; older notes unreachable |
| 8 | Edit a note | FAIL: no edit control (API `PUT` exists) |
| 9 | Add or view tags | FAIL: no UI (tags are stored and returned but never shown) |
| 10 | Search | FAIL: endpoint exists, no search box |
| 11 | Delete a note: click the "Delete" text | FAIL: no confirmation, no undo, adjacent to the title; no failure feedback |
| 12 | Click "Notes" in the nav | WARN: a link to the current page; reloads and drops the draft |
| 13 | Reload with a half-typed draft | WARN: draft lost (no persistence) |

## Verdict: NEEDS REWORK

## Critical Issues (Must Fix)
| # | Issue | Step in Journey | Impact on User | Fix |
|---|-------|----------------|----------------|-----|
| 1 | No paging in the UI; notes past the first 20 are unreachable (Master #10) | 7 | Notes appear to disappear | Pager from `page`/`pages` |
| 2 | Save and delete failures are silent and the form resets on server rejection (Master #9) | 4, 11 | Lost typing and false belief that a delete worked | Check `response.ok`, show reason, keep the draft |
| 3 | Delete is instant and unconfirmed (Master #11) | 11 | Accidental permanent loss | Confirmation or Undo toast; label the control |

## Recommendations
| # | Issue | Impact | Fix |
|---|-------|--------|-----|
| 1 | No empty or loading state | New users see a blank list | "No notes yet" message; "Loading..." |
| 2 | Edit and tags exist in the API only | Half the feature set is invisible | Add an Edit action or remove the unused API |
| 3 | Search has no UI | Feature undiscoverable | Search box (debounced) |
| 4 | Blank titles accepted | Cards with empty headings | `required` plus server validation |
| 5 | Save not disabled while submitting | Duplicate notes | Disable and relabel to "Saving..." |
| 6 | Single-link nav | Looks interactive but does nothing | Remove it or use `aria-current` |

## Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Show updated time on each note (the API returns `updated_at`) | Helps scanning; also explains why an edited note jumps to the top |
| 2 | Ctrl/Cmd+Enter submits from the textarea | Standard for note apps |
| 3 | Return focus to the title field after Save | Faster repeat entry |
| 4 | Persist the draft in `localStorage` | Covers reload and accidental navigation |

## Interaction Consistency Check
There is only one primary action pattern (the filled Save button) and Delete uses a different one (plain red text that is not a button), so the two actions do not look related to anything else. Editing a note changes `updated_at` and moves it to the top of the list, which is unexplained because no timestamps are shown. Search results come from a cache that is not cleared on writes, so a just-edited note can be missing from search for up to 60 s.

## Verdict Details
- Discoverability: CONCERNS (edit, tags, search, paging all invisible)
- Flow Completeness: CONCERNS (cannot reach older notes or edit)
- Error Recovery: CONCERNS (silent failures, draft lost)
- Feedback & Status: CONCERNS (no success, loading or error feedback)
- Consistency: CONCERNS (Delete treated differently from every other control)

Reference skills consulted: `emil-design-engineering/forms-controls.md` (disabled after submission, destructive confirmation, colocated errors), `web-design-guidelines` (its checklist is fetched from a remote URL; I did not fetch it because this run was restricted to local reads, so only the other reference material was applied).

---

## 3. Frontend Engineer

**Verdict**: NEEDS REWORK

# Frontend Engineering Audit: jotter web page

**Perspective**: Frontend Engineer
**Date**: 2026-11-21
**Plan**: n/a (repo health)

## Plan Summary
The front end is 45 lines of vanilla JavaScript (no React, TypeScript, Zustand, Tailwind or build step) that fetches notes, rebuilds the list with `innerHTML`, and posts or deletes notes. The React/Zustand/Zod-specific checks in this lens do not apply; the applicable ones (render path, listeners, error handling, type safety, bundle) are covered.

## Files Reviewed
| File | Frontend Role | Risk |
|------|--------------|------|
| `app/static/app.js` | All client logic | High |
| `app/static/index.html` | Markup, single script tag at end of body | Low |
| `app/static/style.css` | Styles | Medium (see Design lens) |

## Verdict: NEEDS REWORK

## Critical Issues (Must Fix)
| # | Issue | File(s) | Why It Breaks | Code Fix |
|---|-------|---------|---------------|----------|
| 1 | Stored XSS: `item.innerHTML` interpolates `note.title` and `note.body`. A note titled `<img src=x onerror=...>` runs script for every viewer. (Master #4) | `app.js:15-19` | HTML from the database is parsed as markup | `const h3 = document.createElement("h3"); h3.textContent = note.title;` (same for body) |
| 2 | `render()` registers a new `document` click listener on each call. `loadNotes()` runs on page load, after each save and after each delete, and every listener calls `loadNotes()` again, so listeners double on each delete. (Master #8) | `app.js:23-27` | One delete click sends 1, 2, 4, 8... DELETE requests and refetches | Move `document.addEventListener(...)` out of `render()` (or attach once to `list`) |
| 3 | Failures ignored: `fetch` resolves on 4xx/5xx and the code never checks `response.ok`; `form.reset()` then clears the user's text; `catch (error) {}` is empty; delete has no try/catch. (Master #9) | `app.js:34-42, 25-26` | Data loss and invisible errors | `if (!response.ok) { showError(...); return; }` before `form.reset()` |

## Recommendations
| # | Issue | File(s) | Why | Fix |
|---|-------|---------|-----|-----|
| 1 | `loadNotes` has no try/catch; network failure is an unhandled rejection and `response.json()` on an HTML error page throws | `app.js:4-8` | Blank page on failure | Handle and show an error state |
| 2 | Out-of-order responses: two overlapping `loadNotes()` calls can finish in reverse order and render stale data | `app.js:4-8` | Especially visible with the listener bug | Request counter or `AbortController` |
| 3 | Save button is not disabled during the request | `app.js:30-43` | Double submit | Disable until the fetch settles |
| 4 | No lint or type check for the script | `app.js` | Nothing catches typos like `dataset.id` misuse | `// @ts-check` with JSDoc or ESLint |

## Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Use `event.target.closest("button.delete")` once Delete is a button | Robust to nested markup |
| 2 | `defer` on the script tag instead of relying on end-of-body | Clearer intent |
| 3 | Render with a `<template>` | Separates markup from logic |

## Render Path Analysis
Triggers: page load, successful or failed POST (the `loadNotes()` call is only reached if the fetch did not throw), and every delete click. Each `loadNotes()` clears the list and rebuilds up to 20 `article` nodes, which is cheap on its own. The problem is the side effect inside `render()`: it adds one more click handler to `document` per call. A delete click runs all handlers; each sends a DELETE and then calls `loadNotes()`, which calls `render()`, which adds one more handler per call, so handlers double every delete. After 10 deletes, a single click fires about 1024 requests. Extra DELETEs on the same id return 204 (the SQL deletes zero rows), so the server accepts them silently, which hides the bug.

## Type Safety Assessment
There is no TypeScript or JSDoc. The code trusts the response shape (`data.notes`, `note.id`, `note.title`, `note.body`) with no validation. A malformed response (for example the HTML error page from a 500) will throw at `response.json()`. The `slug`, `tags`, `page` and `pages` fields the API sends are not consumed. Zod and Zustand checks are not applicable.

## Verdict Details
- Component Architecture: CONCERNS (`render` both renders and wires events)
- State Management: CONCERNS (no page state; relies on refetch; no error state)
- Type Safety: CONCERNS (untyped, unvalidated)
- Rendering Performance: CONCERNS (listener growth; otherwise fine at 20 nodes)
- Bundle Impact: PASS (no dependencies, about 1 KB of script)

Reference skill `vercel-react-best-practices` is React/Next.js specific and no React is present, so it was not applied.

---

## 4. Backend Engineer

**Skipped** — No Rust/Tauri changes in this repo; the relevance rule for this lens skips it when there are no Rust/Tauri changes. The Python server and store code was read in full and its findings appear under Structural, Repo Maintainer, Production Readiness, DX and Performance.

---

## 5. Structural Engineer

**Verdict**: NEEDS REWORK

# Structural Audit: jotter

**Perspective**: Systems/Structural Architect
**Date**: 2026-11-21
**Plan**: n/a (repo health)

## Plan Summary
Four Python layers (HTTP routes, SQLite store, cache, CLI) plus helpers and a static page. The main structural problem is that the store depends on the HTTP layer, producing an import cycle that the server hides with function-level imports and that makes the CLI unusable.

## Files Reviewed
| File | Structural Role | Layer | Risk |
|------|----------------|-------|------|
| `app/server.py` | Routes, `current_user`, `make_slug`, app entry | HTTP | High |
| `app/store.py` | SQLite access | Data | High |
| `app/cache.py` | In-memory search cache | Infrastructure | Medium |
| `app/cli.py` | Command line | Interface | High |
| `app/config.py` | Constants | Config | Medium |
| `app/pagination.py` | Pure helper | Domain helper | Low |
| `app/utils.py` | Text helpers (no importers) | Helper | Low |
| `app/static/*` | Client | Presentation | Medium |

## Verdict: NEEDS REWORK

## Critical Issues (Must Fix)
| # | Issue | Files Involved | Structural Impact | Fix |
|---|-------|---------------|-------------------|-----|
| 1 | `store` imports `current_user` from `server`: a lower layer depends on a higher one and on Flask's request context. `server` then imports `store` inside six functions to avoid the cycle. `cli` calls `store` outside a request, so `add_note` and `list_notes` fail. (Master #6) | `store.py:7,39,47,56,102`; `server.py:29,41,50,64,72,84`; `cli.py:12,19` | Inverted dependency, masked cycle, non-functional CLI | Make `owner` an explicit parameter; delete the import; move `from app import store` to module top in `server.py` |
| 2 | Owner scoping is a per-query convention rather than structure: four store functions take no owner (`tags_for`, `getNoteById`, `update_note`, `delete_note`) and the cache ignores it. Two of them are exposed by routes. (Master #3) | `store.py:60-95`, `server.py:48-67` | Any new function or route can silently forget the scope | One `owner` argument required by every store function that touches `notes` |

## Recommendations
| # | Issue | Why | Fix |
|---|-------|-----|-----|
| 1 | Lazy imports in six places | They are the symptom of the cycle and obscure the real dependency graph | Remove after fixing the cycle |
| 2 | Two slug implementations (`server.make_slug` is used, `utils.slugify` is not) with different behavior (`make_slug` drops accented letters; `slugify` transliterates and collapses hyphens) | Duplicated responsibility, one dead | Keep one in `utils`, call it from the route (or drop `slug` if unused by the UI) |
| 3 | Cache lives beside the routes and is keyed by raw query | Its correctness depends on callers knowing about identity and invalidation | Own the cache inside the store or a service function that takes `owner` |
| 4 | `cli export` opens SQLite directly | Bypasses the store boundary; duplicates the schema columns | Add `store.export_notes()` |
| 5 | API contract is implicit: `notes`, `page`, `pages`, and per-note `tags`, `slug` appear only in `server.py` | Client and server can drift | Document the response shape in the README, or remove unused fields |

## Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | `create_app()` factory | Lets tests and WSGI servers create and initialize an app without `__main__` |
| 2 | Move `current_user()` into its own small module | Isolates the future auth change |

## Dependency Map
```
cli.py ---------> store.py ---------> server.py   <-- inverted: data layer -> HTTP layer
  |                  |                  |  |  \
  |                  v                  |  |   +-> pagination.py   (clean, pure)
  +--> config.py <---+                  |  +-----> cache.py        (key ignores owner)
  +--> sqlite3 (export bypasses store)  +--(lazy import x6)--> store.py   <-- completes the cycle
utils.py  (imported by nothing)
static/app.js --HTTP--> /api/notes  (JSON shape defined only in server.py)
```
Concerning arrows: `store -> server` (inversion), `server => store` via function-level imports (hidden cycle), `cli -> sqlite3` directly for export, and no arrow at all into `utils.py`.

## Boundary Crossing Analysis
| Crossing | From -> To | Clean? | Notes |
|----------|-----------|--------|-------|
| Identity into data layer | store -> server (`current_user`) | No | HTTP request state read from storage code; fails outside Flask |
| Route to store | server -> store | Partly | Works, but via lazy imports |
| Cache key | server -> cache | No | Key lacks owner |
| CLI export | cli -> sqlite3 | No | Bypasses store, ignores owner |
| Client to API | app.js -> `/api/*` | Partly | Shape implicit; extra fields unused |
| Pagination | server -> pagination | Yes | Pure functions, tested |

## Verdict Details
- Dependency Direction: CONCERNS
- Module Coupling: CONCERNS
- Cohesion: PASS (each module has a clear job apart from identity living in `server`)
- Layer Boundaries: CONCERNS
- Change Propagation: CONCERNS (changing how identity works touches `store` x5, `server`, the cache key and `cli`)

---

## 6. Repo Maintainer

**Verdict**: APPROVE WITH CHANGES

# Repo Maintenance Audit: jotter

**Perspective**: Repo Maintainer
**Date**: 2026-11-21
**Plan**: n/a (repo health)

## Plan Summary
A small, mostly tidy Python repo with consistent snake_case, module docstrings and type hints. Convention drift is limited to a few spots, but there is dead and duplicated code, blanket exception handling, and almost no tests, lint config or hygiene files.

## Files Reviewed
| File | Convention Status | Risk |
|------|------------------|------|
| `app/store.py` | Mixed: `getNoteById` naming, `except Exception: pass`, unused function | High |
| `app/server.py` | Duplicate slug helper, lazy imports | Medium |
| `app/cli.py` | Blanket except printing "Error" | Medium |
| `app/utils.py` | Two functions, neither used | Medium |
| `app/cache.py`, `app/pagination.py`, `app/config.py` | Conforming | Low |
| `tests/test_pagination.py` | Conforming, sole test file | Medium |
| `pyproject.toml`, `README.md` | Missing pieces (see below) | Medium |

## Verdict: APPROVE WITH CHANGES

## Critical Issues (Must Fix)
| # | Issue | File(s) | Convention Violated | Fix |
|---|-------|---------|-------------------|-----|
| 1 | `except Exception: pass` in `update_note` discards every error. (Master #7) | `store.py:88-89` | No swallowed exceptions (ruff `S110`/`BLE001` class) | Remove the try/except; let the route handle errors |
| 2 | Circular import between `store` and `server` hidden behind six function-level imports. (Master #6) | `store.py:7`, `server.py` | Import hygiene: imports at top, no cycles | Break the cycle, hoist imports |

## Recommendations
| # | Issue | Why | Fix |
|---|-------|-----|-----|
| 1 | `DB_PATH` is a developer's absolute path (Master #13) | Machine-specific value committed in config | Environment variable with relative default |
| 2 | `utils.slugify` and `utils.truncate` are unused; `server.make_slug` duplicates `slugify`; `store.getNoteById` is unused | Dead and duplicated code | Delete, or wire in `slugify` and delete `make_slug` |
| 3 | `getNoteById` is camelCase in a snake_case codebase | Naming convention drift | Rename (or delete per #2) |
| 4 | `cmd_add` catches `Exception` and prints "Error" (Master #12) | Same swallowing pattern as `update_note` | Catch specific errors, print reason |
| 5 | No `logging` use anywhere | No structured-logging convention exists | Add `logging.getLogger(__name__)` |
| 6 | `pyproject.toml` has no `[build-system]`, no package-data for `app/static`, no dev extra for pytest, and the package is named `app` | Packaging hygiene; static files may be missing from a built wheel (unverified: I did not build one) | Add the missing tables; consider renaming the package |
| 7 | Tests cover only `parse_page`; nothing for store, server, cache, CLI | The defects in this audit would fail basic tests | Add Flask test-client tests (ownership, cache scoping, validation) and a CLI smoke test |
| 8 | No `.gitignore`, no ruff/format config, README layout omits `config.py` and `tests/`, no CLAUDE.md for contributors | Repo hygiene | Add files; update the README layout list |

## Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | `Page.pages` and `parse_page` both compute the page count | One source of truth |
| 2 | Unused `--muted` CSS token | Remove or use |
| 3 | Name the import-order convention (stdlib, third party, local) in a lint config; current files already follow it | Keeps it that way |

## Convention Compliance Checklist
| Convention | Status | Notes |
|-----------|--------|-------|
| File placement | OK | Routes, store, cache, CLI, helpers each in their own module; static assets under `app/static/` |
| Naming conventions | Concern | snake_case everywhere except `getNoteById` |
| Barrel exports | N/A | Python package; `__init__.py` is empty, which is fine |
| Import ordering | OK | stdlib, third party, local in every file |
| Type imports separated | N/A | Python |
| Path aliases used | N/A | Absolute `from app import ...` is used consistently |
| No dead code left | Fail | `getNoteById`, `slugify`, `truncate`, `--muted` |
| Structured logging | Fail | No logging at all |
| No lint suppressions | Concern | No suppression comments, but a blanket `except Exception: pass` and `except Exception: print("Error")` do the same job |
| CLAUDE.md present | Absent | Not required here; a short contributor doc would help |

## Reuse Opportunities
`utils.slugify` already does what `server.make_slug` re-implements, and does it more correctly (Unicode normalization, hyphen collapsing, edge trimming). `utils.truncate` would suit long note titles in the CLI `list` output. `parse_page` already exposes `Page.pages`, which `parse_page` recomputes. The `PUT` validation block in `server.update_note` could be the shared validator that `POST` is missing.

## Verdict Details
- File Organization: PASS
- Naming Consistency: CONCERNS
- Import Hygiene: CONCERNS (hidden cycle)
- Code Reuse: CONCERNS (duplicate slug logic, dead helpers)
- Lint Compliance: CONCERNS (swallowed exceptions, no config)

---

## 7. Production Readiness

**Verdict**: NEEDS REWORK

# Production Readiness Audit: jotter

**Perspective**: Production Readiness Engineer
**Date**: 2026-11-21
**Plan**: n/a (repo health)

## Plan Summary
A Flask app backed by a SQLite file that is run with the Werkzeug dev server in debug mode, with configuration hardcoded for one developer's machine. Several data-isolation and integrity defects would surface on the first real deployment.

## Files Reviewed
| File | Production Role | Risk |
|------|----------------|------|
| `app/config.py` | Runtime settings (hardcoded) | High |
| `app/server.py` | HTTP entry point, identity | High |
| `app/store.py` | Persistence | High |
| `app/cache.py` | Search cache | High |
| `app/cli.py` | Admin and export path | Medium |
| `pyproject.toml`, `README.md` | Packaging and run docs | Medium |

## Verdict: NEEDS REWORK

## Critical Issues (Must Fix)
| # | Issue | File(s) | Production Failure Mode | Fix |
|---|-------|---------|------------------------|-----|
| 1 | Search cache keyed by query only (Master #1) | `cache.py:9-20`, `server.py:74-80` | User B sees user A's notes for 60 s | Key by `(owner, query)` or remove |
| 2 | Identity from unauthenticated `X-User` header (Master #2) | `server.py:13-14` | Anyone who can reach the port can act as any user | Authenticate at the edge; bind to localhost by default |
| 3 | Update and delete not scoped by owner (Master #3) | `store.py:74-95` | Any user edits or deletes any note by guessing ids | Owner in every statement; 404 on no match |
| 4 | Debug on, `0.0.0.0`, dev server, schema creation only under `__main__` (Master #5) | `config.py:4-5`, `server.py:83-87` | Debugger console exposed to the network; WSGI deployment has no tables | Env-driven config, safe defaults, init on startup, gunicorn docs |
| 5 | Hardcoded DB path `/Users/dev/projects/jotter/notes.db` (Master #13) | `config.py:3` | Every request fails on any other host | Env var plus creating the parent directory |
| 6 | `update_note` commits tag deletion before update and swallows all errors (Master #7) | `store.py:74-89` | Partial update, tags lost, 200 `{"ok": true}` | Single transaction, no blanket except |
| 7 | Store imports from server; CLI add fails with "Error", list raises `RuntimeError` (Master #6) | `store.py:7`, `cli.py:10-20` | The documented CLI does not work | Explicit owner parameter |

## Recommendations
| # | Issue | Why | Fix |
|---|-------|-----|-----|
| 1 | No logging; failures are swallowed or surface as bare 500s | Cannot diagnose anything remotely | `logging` with request context, errors logged once at the boundary |
| 2 | `POST /api/notes` has no validation (`data["title"]` KeyError, non-JSON body, no title limit) | 500s with a Werkzeug traceback in debug | Shared validator, return 400 |
| 3 | Connections are not closed explicitly (`with sqlite3.connect` commits but does not close; `search` and `update_note` never close); no WAL, no `busy_timeout`, no foreign-key pragma | Lock errors under concurrent use; orphan rows | Close via `contextlib.closing` or per-request connection; set pragmas |
| 4 | No schema version or migration path | Cannot evolve the schema without manual SQL; rollback unclear | `PRAGMA user_version` and ordered migrations |
| 5 | No health endpoint, no backup guidance for the SQLite file | Ops cannot probe or restore | `/healthz`; README section |
| 6 | `export` includes every user's notes, writes in place (not temp-and-rename), omits tags | Export can leak other users' data and leave a truncated file on crash | Owner filter or admin flag; atomic write |
| 7 | Search has no limit and cache is never invalidated on writes | Large result sets; stale results for 60 s | `LIMIT`, clear cache on write |
| 8 | Packaging: no `[build-system]` or package-data for `app/static`; generic package name `app` | A built install may lack the static page (unverified: no wheel was built); name collisions | Add build config and package data |

## Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Pin an upper bound or lock file for Flask | Reproducible installs |
| 2 | Request size limit (`MAX_CONTENT_LENGTH`) | Basic abuse protection |
| 3 | Security headers (CSP in particular, given the `innerHTML` rendering) | Defense in depth |

## Failure Mode Analysis
| Scenario | What Fails | User Impact | Recovery | Plan Handles It? |
|----------|-----------|-------------|----------|-------------------|
| Two users search the same term | Shared cache entry | User sees another user's notes | Restart clears it | No |
| Deployed on any other machine | `sqlite3.connect` on a nonexistent directory | All requests 500 | Edit source | No |
| Started under gunicorn or `flask run` | Schema never created | "no such table" on every request | Run `__main__` once | No |
| `update_note` fails after the first commit | Tags already deleted, error swallowed | Silent tag loss, API says ok | None (data gone) | No |
| Process killed mid-update | Committed tag deletion, uncommitted rest | Note without its tags | None | No |
| `POST` with missing `title` or bad JSON | `KeyError` / 415 / 400 as HTML | 500 page, debug traceback in debug mode | Resubmit | No |
| Another user guesses a note id | No owner check on update/delete | Note changed or deleted | None | No |
| Concurrent writers | Default 5 s lock timeout, no WAL | Intermittent "database is locked" | Retry | Partly (sqlite defaults) |
| Large data set, broad search | Unbounded result list, `LIKE '%q%'` scan | Slow response and memory | Add `LIMIT` | No |
| App restart | Cache cold, data persists | None | n/a | Yes |

## Environment Checklist
| Concern | Dev | Prod | Gap? |
|---------|-----|------|------|
| File paths | `/Users/dev/projects/jotter/notes.db` | Needs a configurable writable path | Yes |
| Network | `0.0.0.0:5000`, debug | Behind a proxy, localhost bind, no debug | Yes |
| Permissions | Parent directory assumed to exist and be writable | Not checked | Yes |
| Config | Python constants, no env overrides | Needs env-driven settings | Yes |
| Build output | Editable install serves `app/static` from the source tree | Static assets may not be packaged (unverified) | Likely |

## Verdict Details
- E2E Flow: CONCERNS (works only via `python -m app.server` on the author's machine; CLI broken)
- Error Recovery: CONCERNS
- Data Integrity: CONCERNS
- Environment Parity: CONCERNS
- Observability: CONCERNS

---

## 8. DX Engineer

**Verdict**: NEEDS REWORK

# DX Audit: jotter CLI and API

**Perspective**: Developer Experience Engineer
**Date**: 2026-11-21
**Plan**: n/a (repo health)

## Plan Summary
Developers interact with jotter through three commands (`add`, `list`, `export`), a small JSON API and a README. The README is clear, but two of the three commands do not work and the failure output tells the developer nothing.

## Files Reviewed
| File | DX Role | Risk |
|------|---------|------|
| `app/cli.py` | CLI commands and help | High |
| `app/server.py` | API errors and responses | Medium |
| `README.md` | Onboarding | Low |
| `app/config.py` | Configuration | Medium |

## Verdict: NEEDS REWORK

## Critical Issues (Must Fix)
| # | Issue | Impact on Developer | Fix |
|---|-------|-------------------|-----|
| 1 | `jotter add` and `jotter list` fail because `store` calls `current_user()` outside a request (Master #6). `add` prints `Error`; `list` prints a Python traceback ending in `RuntimeError: Working outside of request context`. | The README's own quick start fails | Pass owner explicitly |
| 2 | `cmd_add` swallows everything: `except Exception: print("Error")`, on stdout, exit code 0 (Master #12) | Cannot tell what went wrong, and scripts think it succeeded | Specific exceptions, message to stderr with cause and hint, `sys.exit(1)` |

Statements about the failure output are from reading the code; I could not run it (Flask and pytest are not installed in this environment).

## Recommendations
| # | Issue | Why | Fix |
|---|-------|-----|-----|
| 1 | `list` hardcodes 50 notes; no `--limit`, `--page` or `--json` | Cannot script or page through notes | Flags with defaults |
| 2 | `title` and `body` positional arguments have no `help=`; no examples in `--help` | Developers type `--help` first | Add help text and an epilog example |
| 3 | No `--db` flag or environment variable for the database path | Cannot point the CLI at another file; the default is another person's absolute path | `--db` and `JOTTER_DB` |
| 4 | `export` silently overwrites an existing file and omits tags | Surprising data loss | Refuse without `--force`; include tags |
| 5 | Error reporting goes to stdout; no non-zero exit anywhere | Breaks shell composition and CI | stderr plus exit codes |
| 6 | API errors: `PUT` returns JSON with a clear message, but `POST` failures and unhandled exceptions return HTML | API clients get inconsistent errors | JSON error handler for all routes |
| 7 | Web form: Enter submits from the title field, but Ctrl/Cmd+Enter does not from the textarea | Keyboard-first users expect it | Key handler |

## Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | `--version` | Standard |
| 2 | A short "Configuration" section in the README (db path, host, port, debug) | Config is the documentation |
| 3 | Print the listening URL at server start | Confirmation for the developer |

## Error Message Audit
| Error Scenario | Current Message | What Developer Needs | Suggested Message |
|---------------|----------------|---------------------|-------------------|
| `jotter add` fails for any reason | `Error` (stdout, exit 0) | What failed, why, what to do | `jotter: could not add note: unable to open database file /Users/dev/.../notes.db. Set JOTTER_DB or pass --db.` (stderr, exit 1) |
| `jotter list` | Python traceback: `RuntimeError: Working outside of request context` | A usable listing | (fix the cause) |
| `jotter list` on a fresh DB | Not handled; `init()` is never called from the CLI, so `no such table: notes` | Auto-initialize or tell the developer | `jotter: database not initialized; run 'jotter init'` or create on first use |
| `PUT` with empty title | `{"error": "title is required"}` (400) | Good as is | Keep |
| `PUT` with title over limit | `{"error": "title must be at most 200 characters"}` (400) | Good as is | Keep |
| `POST` with missing `title` | Flask HTML 500 page (traceback in debug) | JSON 400 naming the field | `{"error": "title is required"}` |
| `POST` without a JSON content type | Flask HTML 415 page | JSON error | `{"error": "send Content-Type: application/json"}` |
| `jotter export` to an unwritable path | Python traceback | One-line error | `jotter: cannot write /path: Permission denied` |

## Developer Journey
First use: install and run instructions are in the README and clear; the web page then works when started on the author's machine, but the path is not configurable and the CLI fails immediately, so the first impression of the CLI is a bare "Error". Daily use: no way to page, filter or script `list`; every failure prints nothing useful. Power use: `export` to JSON composes well with other tools, which is the one good piece, but it leaks all users' notes and drops tags.

## Verdict Details
- Error Quality: CONCERNS
- Defaults & Config: CONCERNS
- Keyboard Experience: CONCERNS
- Discoverability: PASS (README documents the commands)
- Workflow Integration: CONCERNS

---

## 9. Performance Engineer

**Verdict**: NEEDS REWORK

# Performance Audit: jotter

**Perspective**: Performance Engineer
**Date**: 2026-11-21
**Plan**: n/a (repo health)

## Plan Summary
A small service where the real performance risks are request amplification in the browser, per-request connection churn and an N+1 on the list route, and an unbounded in-memory cache. Scale is small, so most issues are cheap to fix.

## Files Reviewed
| File | Performance Role | Risk |
|------|-----------------|------|
| `app/static/app.js` | Listener registration, refetch after each action | High |
| `app/cache.py` | Unbounded in-process cache | High |
| `app/store.py` | Connection per call, N+1, unindexed queries | Medium |
| `app/server.py` | List and search routes | Medium |

## Verdict: NEEDS REWORK

## Critical Issues (Must Fix)
| # | Issue | File(s) | Impact | Fix |
|---|-------|---------|--------|-----|
| 1 | Click listener added on every `render()`; listener count doubles per delete and each does a DELETE plus a refetch (Master #8) | `app.js:23-27` | Requests grow 1, 2, 4... per click; the page and server slow down with normal use | Register once |
| 2 | Search cache never evicts and has no size bound; the key is any user-supplied string (Master #16) | `cache.py:5-20` | Unbounded memory growth over a long-running process; easy to exhaust deliberately | Bound or remove |

## Recommendations
| # | Issue | File(s) | Why | Fix |
|---|-------|---------|-----|-----|
| 1 | N+1: list route runs 1 count + 1 list + one `tags_for` per note (22 connections per page load at the default page size of 20) | `server.py:31-36`, `store.py:24-65` | Each call opens a new SQLite connection | One tag query for all ids; one connection per request |
| 2 | No indexes on `tags(note_id)` or `notes(owner, updated_at)` | `store.py:9-21` | Full scans on tag lookup, delete and list ordering as data grows | `CREATE INDEX IF NOT EXISTS` |
| 3 | Search: `LIKE '%q%'` on title and body with no `LIMIT` or `ORDER BY`, returns the whole match set and caches it | `store.py:98-104` | Linear scan, unbounded response | `LIMIT`, optionally FTS5 later |
| 4 | Cache is not invalidated on write, so it also returns stale results | `cache.py`, `server.py` | Correctness cost of the cache outweighs its benefit at this scale | Clear on write or drop it |

## Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Debounce the search input when a UI is added | The endpoint is a table scan |
| 2 | WAL mode | Readers do not block the writer |
| 3 | Cache headers for `/static/*` | Minor; Flask already supports conditional requests |

## Resource Budget
| Resource | Current | After Plan | Concern? |
|----------|---------|-----------|----------|
| HTTP calls per page load | 1 (`/api/notes`) | 1 | No |
| DB connections per page load | 22 (1 count, 1 list, 20 tag lookups) | 2 after a tag batch fix | Yes |
| Click listeners on `document` | 1 after load, doubling after each delete | 1 | Yes (critical) |
| DELETE requests per click | equals the listener count (1, 2, 4, 8...) | 1 | Yes (critical) |
| Memory growth per hour | One cache entry per distinct query, never freed | Bounded | Yes |
| Startup time impact | Negligible | Negligible | No |
| Bundle size | About 1 KB JS, about 2 KB CSS, no dependencies | Same | No |

## Hot Path Analysis
The hot paths are page load (`GET /api/notes`, 22 connections and queries), delete (client amplification) and search (full table scan with caching that is both unbounded and unsafe). There is no streaming, no per-keystroke work and no heavy startup import. The page-load N+1 is harmless at 20 notes per page on a local SQLite file, but it is the first thing to change if the note count grows.

## Verdict Details
- Memory Management: CONCERNS
- IPC Efficiency: CONCERNS (N+1; duplicate DELETEs)
- I/O Patterns: CONCERNS (connection per call, no indexes)
- Startup Impact: PASS
- Long-Session Stability: CONCERNS (listener growth in the browser, cache growth on the server)

Reference skill `web-animation-design` (GPU-only properties) was consulted; the only transition is `background-color` on one button and is not a concern. `vercel-react-best-practices` is React-specific and not applicable.

---

## 10. Accessibility Engineer

**Verdict**: NEEDS REWORK

# Accessibility Audit: jotter web page

**Perspective**: Accessibility Engineer
**Date**: 2026-11-21
**Plan**: n/a (repo health)

## Plan Summary
The page has a sound base (`lang`, landmarks, heading order, a labelled textarea, a visible focus ring on the Save button) but the Delete control, the title field and the focus styling on inputs fail basic keyboard and screen-reader requirements, and nothing that changes dynamically is announced.

## Files Reviewed
| File | A11y Role | Risk |
|------|----------|------|
| `app/static/index.html` | Landmarks, labels, headings | Medium |
| `app/static/app.js` | Generates the Delete control and list content | High |
| `app/static/style.css` | Focus, contrast | High |

## Verdict: NEEDS REWORK

## Critical Issues (Must Fix)
| # | Issue | WCAG Criterion | File(s) | Impact | Fix |
|---|-------|---------------|---------|--------|-----|
| 1 | Delete is a `<div class="delete">` with a click handler: not in the tab order, no role, no key handler, accessible name is only the generic word "Delete" (Master #11) | 2.1.1 Keyboard, 4.1.2 Name, Role, Value | `app.js:16`, `style.css:104-108` | Keyboard and screen-reader users cannot delete notes | `<button type="button" aria-label="Delete note: TITLE">` |
| 2 | Title input has no label, only a placeholder (Master #14) | 1.3.1, 3.3.2, 4.1.2 | `index.html:19` | Field announced without a name | Add `<label for="title">` |
| 3 | `outline: none` on inputs and textarea with no replacement focus style (Master #15) | 2.4.7 Focus Visible | `style.css:55-64` | Keyboard users cannot see focus in the form fields | Restore or restyle with `:focus-visible` |

## Recommendations
| # | Issue | WCAG Criterion | Fix |
|---|-------|---------------|-----|
| 1 | List updates and save/delete errors are not announced; the notes container is a plain div | 4.1.3 Status Messages | `aria-live="polite"` status region for "Note saved", "Note deleted" and errors |
| 2 | Input boundaries are low contrast (about 1.5:1 light, 1.6:1 dark, hand-estimated, not tool-measured) | 1.4.11 Non-text Contrast | Stronger border token for controls |
| 3 | The Delete target is unpadded text of roughly line height | 2.5.8 Target Size (Minimum), and 44px guidance in the reference skill | Padding or `min-height: 44px` |
| 4 | After a delete the list is rebuilt and the focused element disappears; focus falls to the body | 2.4.3 Focus Order | Move focus to the notes heading or the next note |
| 5 | The single "Notes" nav link points to the current page and has no `aria-current` | 2.4.8 Location (informational) | Remove or mark current |
| 6 | The Save button's 150ms hover transition is not wrapped in a reduced-motion query | 2.3.3 (AAA, advisory) | `@media (prefers-reduced-motion: reduce) { * { transition: none } }` |

## Nice-to-Haves
| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | Render the list as `<ul>` of `<li>` | Screen readers announce item count |
| 2 | `autocomplete="off"` and `spellcheck` choices on the title field | Fewer unwanted suggestions |
| 3 | `touch-action: manipulation` on controls | Avoids double-tap zoom delays |

## Keyboard Navigation Walkthrough
| Step | Action | Expected Focus | Expected Announcement | Plan Handles? |
|------|--------|---------------|----------------------|---------------|
| 1 | Tab from page start | "Notes" nav link | "Notes, link, navigation" | Yes (default focus ring) |
| 2 | Tab | Title input | "Title, edit text" | No: unnamed field; no visible focus (outline removed) |
| 3 | Tab | Textarea | "Note, edit text" | Label yes; no visible focus |
| 4 | Tab | Save button | "Save, button" | Yes (focus-visible ring) |
| 5 | Press Enter in the title field | Submits the form | Ideally "Note saved" | Submits; no announcement |
| 6 | Tab to the first note's Delete | Delete button | "Delete note: TITLE, button" | No: not focusable at all |
| 7 | Activate Delete | Focus moves to a sensible target | "Note deleted" | No |
| 8 | Reach older notes | A pager | n/a | No: no pager |

## ARIA Checklist
| Element | Role | Label | States | Keyboard | Notes |
|---------|------|-------|--------|----------|-------|
| `header.topbar` | banner (implicit) | n/a | n/a | n/a | OK |
| `nav` | navigation | `aria-label="Main"` | none | Tab | OK; single link to the current page |
| `main` | main | n/a | n/a | n/a | OK |
| `h1`, `h2`, `h3` | headings | text | n/a | n/a | Hierarchy correct: h1, h2 "Your notes", h3 per note |
| `section[aria-labelledby]` | region | "Your notes" | n/a | n/a | OK |
| Title `<input>` | textbox | None | none | Tab | Missing name |
| Textarea | textbox | `<label for="body">Note</label>` | none | Tab | Named; no focus style |
| Save `<button>` | button | text "Save" | `disabled` styled, never used | Tab/Enter/Space | OK |
| Note `article` | article | n/a | n/a | n/a | OK |
| Delete `<div>` | none | text "Delete" | none | None | Fails 2.1.1 and 4.1.2 |
| Notes container `div#notes` | none | n/a | no live region | n/a | Dynamic content not announced |

## Verdict Details
- Screen Reader Compatibility: CONCERNS
- Keyboard Navigation: CONCERNS
- Focus Management: CONCERNS
- Color Contrast: CONCERNS (text pairs pass by estimate; control boundaries fail 3:1)
- Motion Sensitivity: PASS (one short, non-essential color transition)

Reference skills consulted: `emil-design-engineering` (touch targets, icon-button labels, semantic buttons, reduced motion), `web-animation-design` (reduced-motion), `web-design-guidelines` (remote guidelines not fetched; see limitations).

---

## Audit Limitations

- This audit is static: I read all 14 files but did not run anything. Flask and pytest are not installed in this environment, so the claims about CLI failures, request amplification, cross-user cache leakage, and rendering are derived from reading the code, not from execution. Contrast ratios are hand-estimates, not tool-measured.
- The `web-design-guidelines` reference skill fetches its rules from a remote URL; this run was restricted to local reads, so those rules were not applied.
- The packaging concern (static files missing from a built wheel) is unverified; no wheel was built.
- The project directory was not modified.

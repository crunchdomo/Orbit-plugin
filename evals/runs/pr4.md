# Full Spectrum Audit: jotter

**Date**: 2026-11-21
**Mode**: Repo Health (general repo health, option 3)
**Source**: /private/tmp/claude-501/-Users-oenfadam-Documents-Orbit-plugin/ec022de0-9140-4432-ae41-0c6144f29ec4/scratchpad/pr4 (whole repo; no git history present)
**Stack**:
- Python >=3.11, Flask >=3.0, stdlib `sqlite3`; vanilla HTML/CSS/JS front end in `app/static/` (no build step, no framework).
- A web service plus a CLI (`jotter` -> `app.cli:main`) over one SQLite file; started with `python -m app.server` (Flask dev server) per the README.
- UI is one page (`index.html`, `app.js`, `style.css`); light and dark themes through CSS custom properties.
- Documented conventions: README layout list (server = routes, store = SQLite, cache, helpers, static, cli); tests with pytest in `tests/`. No `CLAUDE.md`, so no `## Audit gotchas`. No lint, format or type-check config.
- All findings come from reading the code; nothing was executed.

**Lenses Run**: 10/10
**Lenses Skipped**: none (the repo has a web UI, a CLI, a server with data access, several modules, I/O and a cache, so every relevance rule says run)

## Master Verdict: NEEDS REWORK

The app has no working identity or authorization model: the user is a spoofable header, search results are cached across users, and update and delete ignore ownership. Stored XSS in the page, silent data loss on failed saves, a hardcoded developer-machine DB path, and a CLI whose `add` and `list` cannot work at all mean it does not run correctly outside the author's machine. The pagination module and its tests are the one solid part.

## Verdict by Lens

| # | Lens | Verdict | Critical | Recommendations |
|---|------|---------|----------|-----------------|
| 1 | Design Engineer | APPROVE WITH CHANGES | 0 | 3 |
| 2 | UX Engineer | NEEDS REWORK | 2 | 4 |
| 3 | Frontend Engineer | NEEDS REWORK | 5 | 1 |
| 4 | Backend Engineer | NEEDS REWORK | 5 | 4 |
| 5 | Structural Engineer | APPROVE WITH CHANGES | 1 | 1 |
| 6 | Repo Maintainer | APPROVE WITH CHANGES | 0 | 5 |
| 7 | Production Readiness | NEEDS REWORK | 4 | 4 |
| 8 | DX Engineer | NEEDS REWORK | 2 | 4 |
| 9 | Performance Engineer | NEEDS REWORK | 2 | 2 |
| 10 | Accessibility Engineer | APPROVE WITH CHANGES | 1 | 3 |

Counts are per lens for the issues listed in the master tables below; an issue flagged by two lenses counts for both.

## Critical Issues (Must Fix)

Deduplicated, ordered by severity (12 distinct issues):

| # | Issue | Lens(es) | File:line | What breaks, and when | Fix |
|---|-------|----------|-----------|-----------------------|-----|
| 1 | Identity is the client-supplied `X-User` header, default `"local"`, with no authentication | Backend, Prod | app/server.py:13-14 | Anyone who can reach the port sends `X-User: <victim>` and reads, edits and deletes that user's notes; with `HOST = "0.0.0.0"` that is the whole network. | Real authentication (session or token) behind `current_user()`; reject requests without it; if single-user is intended, drop the owner concept. |
| 2 | `update_note` and `delete_note` have no owner check (`WHERE id = ?` only); update also inserts tags for any id | Backend | app/store.py:74-95, app/server.py:48-67 | Any user can overwrite or delete another user's note by guessing sequential integer ids; PUT or DELETE on a missing id still returns success. | Add `AND owner = ?` to the UPDATE, tag DELETE and note DELETE, check `rowcount`, return 404 when 0. |
| 3 | Search cache is keyed by query only but results are per user | Backend, Perf | app/cache.py:9-20, app/server.py:74-79 | User A searches "invoice"; for the next 60 s user B searching "invoice" is served A's notes. Edits and deletes also keep showing for 60 s. | Key on `(owner, query)`; invalidate the owner's entries on add, update and delete; or delete the cache. |
| 4 | Flask `debug=True` bound to `0.0.0.0`, and the README's run command uses it | Prod | app/config.py:4-5, app/server.py:87 | The Werkzeug interactive debugger is exposed to the network; it allows remote code execution to anyone who gets past or learns the PIN, and any 500 leaks source. | Default `DEBUG = False`, `HOST = "127.0.0.1"`; read both from environment variables; document a WSGI server for real deployment. |
| 5 | Stored XSS: note title and body are written into `innerHTML` unescaped | Frontend | app/static/app.js:15-19 | A note titled `<img src=x onerror=...>` runs script in every viewer's browser on next load (combined with #1, in any user's). | Build nodes with `textContent`, or escape before templating. |
| 6 | `update_note` deletes and commits tags first, swallows every exception, never rolls back or closes | Backend, Prod | app/store.py:77-78, 88-89 (and app/server.py:58-59) | If the UPDATE or an INSERT fails (locked DB, bad `tags` value), the old tags are already permanently deleted, and the API still answers `{"ok": true}`. | One transaction (`with connect() as conn:`), no bare `except`, validate `tags` as a list of strings, return an error the UI can show. |
| 7 | `DB_PATH` is an absolute path on the author's machine; tables are only created when run as `python -m app.server` | Prod, DX | app/config.py:3, app/server.py:83-86 | On any other machine the directory does not exist, so every request fails with `unable to open database file`; under `flask run` or a WSGI server `init()` never runs, so every query fails with `no such table`; the CLI never calls `init()` either. | `DB_PATH = os.environ.get("JOTTER_DB", "notes.db")` (or a per-user data dir); call `store.init()` on app startup and from the CLI. |
| 8 | `jotter add` always prints "Error" and `jotter list` crashes: `store` calls `server.current_user()`, which reads Flask `request` outside a request | Backend, Structural, DX | app/store.py:7,39,48,56,102; app/server.py:13-14; app/cli.py:12-15,19 | Every CLI `add` raises `RuntimeError: Working outside of request context`, caught and reduced to "Error" (exit code 0); every CLI `list` dies with that traceback. Only `export` works. | Make `store` functions take `owner` as a parameter; the server passes `current_user()`, the CLI passes a configured local owner; remove the `app.server` import from `store.py`. |
| 9 | Failed saves silently lose the user's text: `form.reset()` runs even on HTTP errors, `fetch` does not throw on 4xx/5xx, and the `catch` is empty | Frontend, UX | app/static/app.js:34-43, 4-8 | On any server error (for example the DB problem in #7) the title and body vanish from the form and nothing is saved or shown; `loadNotes` also throws on a non-JSON error page and leaves a blank list. | Check `response.ok`; reset the form only on success; show an error message and keep the input; guard `loadNotes` the same way. |
| 10 | The UI only ever fetches page 1 of notes | UX, Frontend | app/static/app.js:5, app/server.py:31-36 | With more than 20 notes (`PAGE_SIZE = 20`) the older ones are not shown anywhere and cannot be reached or deleted; the response's `pages` field is ignored and there is no search UI. | Pass `?page=`, render next and previous controls (or load more), and use the `pages` value. |
| 11 | The Delete control is a `<div>` with a click handler: no keyboard focus, no role, no accessible name beyond its text | A11y, Frontend | app/static/app.js:16; app/static/style.css:104-108 | Keyboard and switch users, and screen-reader users navigating by controls, cannot delete a note at all (WCAG 2.1.1, 4.1.2). | Render `<button type="button" class="delete" aria-label="Delete note: <title>">` with a `:focus-visible` style and a 44px hit area. |
| 12 | A new document-level click listener is added inside `render()` on every load | Frontend, Perf | app/static/app.js:23-27 | Each render adds a listener; each delete click then runs every listener, each calling `loadNotes()` which adds another, so the number of DELETE and list requests doubles with every delete (about 1000 after ten). | Register one delegated listener once on `#notes`, outside `render()`. |

## Cross-Cutting Concerns

Issues flagged by 2+ lenses:

| Concern | Flagged By | Root Cause | Unified Fix |
|---------|-----------|------------|-------------|
| No identity or authorization model (criticals 1, 2, 3) | Backend, Prod, Perf | Ownership is a trusted header string, applied to some queries and not others, and left out of the cache key | One authenticated `owner` passed explicitly into every store call; every query and cache key scoped by it |
| Request context hidden inside the data layer (critical 8) | Structural, Backend, DX | `store.py` imports the HTTP layer (`current_user`), which forces six function-local `from app import store` imports in `server.py` and breaks the CLI | `store` takes `owner` as an argument and imports nothing from `server`; CLI export goes through a `store.export_notes()` instead of raw SQL |
| Failures are swallowed instead of reported (criticals 6, 8, 9) | Backend, DX, Frontend, UX, Prod | Bare `except Exception: pass` (store.py:88-89), `print("Error")` (cli.py:14-15), empty `catch` (app.js:42), unchecked `response.ok` | Catch narrowly, log with context, return real errors, show them to the user |
| Environment assumptions baked in (criticals 4, 7) | Prod, DX, Backend | `config.py` holds dev-machine constants: absolute DB path, debug on, bind all interfaces | Env-driven config with safe defaults; init on startup |
| Keyboard access and focus (critical 11) | A11y, Design, UX | Delete is a `div`; inputs set `outline: none` with no replacement (style.css:63) | Real buttons; `:focus-visible` on every control |
| Cache with no key scoping, eviction or invalidation (critical 3, rec 5) | Backend, Perf | `cache.py` is a bare dict keyed by query; expired entries are never removed | Scope key by owner, evict on write and on size, or remove it until search is measured as slow |
| Missing UI states and feedback (rec 2) | UX, Design, A11y, Frontend | No empty, loading, error or success states; list is not a live region; Save is never disabled while submitting | One small status area (`role="status"`) plus disabled-while-saving |
| Hardcoded colors outside the token system (rec 14) | Design, Repo Maintainer | `.note` and `.delete` use raw hex in a themed page | Add `--card-bg`, `--card-text`, `--danger` tokens with dark values |

## Recommendations

Deduplicated, most valuable first. At most 15 shown.

| # | Recommendation | Lens(es) | File:line | Fix |
|---|---------------|----------|-----------|-----|
| 1 | Validate input on create and update: missing `title` gives a `KeyError` 500, empty and over-length titles are accepted on POST though PUT rejects them (`MAX_TITLE_LENGTH` unused there), a non-string title makes `.strip()` raise, `request.json` rejects non-JSON with an HTML error, and `silent=True` on PUT hides parse errors behind "title is required" | Backend, UX, DX | app/server.py:43-44, 52-58 | One shared validator; return JSON `{"error": ...}` with 400 for all routes; add a JSON error handler for 500 |
| 2 | Add the missing UI states: empty list message, loading, visible error, save confirmation, disable Save while submitting (double click creates duplicates), `aria-live` region for results | UX, Design, A11y, Frontend | app/static/app.js:4-8, 30-43; app/static/index.html:22,27 | Small status element and an empty-state paragraph; `button.disabled = true` during the request |
| 3 | No logging anywhere and no health endpoint; the swallowed errors leave nothing to debug from | Prod, Repo Maintainer | app/store.py:88-89, app/cli.py:14-15, app/server.py | `logging.getLogger(__name__)`, log exceptions with context, add `/healthz` |
| 4 | N+1 and unindexed reads: `list_notes` runs 1 count + 1 list + up to 20 `tags_for` queries, each opening its own connection; `tags` has no index on `note_id`, `notes` none on `(owner, updated_at)` | Perf, Backend | app/server.py:33-35; app/store.py:17-20, 60-65 | One `WHERE note_id IN (...)` query for the page; `CREATE INDEX` on `tags(note_id)` and `notes(owner, updated_at)` |
| 5 | Cache never evicts expired entries and has no size bound, so distinct `q` values grow memory for the life of the process | Perf, Backend | app/cache.py:14-20 | `functools.lru_cache`-style bound, or drop expired entries on `put` |
| 6 | CLI errors carry no cause or exit code: `except Exception: print("Error")` exits 0 | DX, Repo Maintainer | app/cli.py:14-15 | Print the cause to stderr (`jotter: could not add note: ...`), `sys.exit(1)`; remove the blanket catch |
| 7 | CLI `export` bypasses the store with raw SQL and its own column list, dumps every owner's notes including the `owner` column, writes non-atomically, and has no error handling for a missing table or bad path | Structural, DX, Backend | app/cli.py:23-33 | `store.export_notes()`; write to a temp file then rename; catch `OSError` and `sqlite3.Error` with a message |
| 8 | README documents only the Flask dev server and `pip install -e .`; no WSGI entry, no config documentation, no mention of the debug flag or the DB location | Prod, DX | README.md:5-12; app/config.py | Add a production run section (for example `gunicorn app.server:app`) and an env var table |
| 9 | Delete has no confirmation and no undo, and fires on a single click | UX | app/static/app.js:23-27 | Confirm with the note title (or an undo toast), after the button fix in critical 11 |
| 10 | Inputs set `outline: none` and define no replacement focus style, so keyboard focus is invisible there (WCAG 2.4.7) | Design, A11y | app/static/style.css:55-64 | `.composer input:focus-visible, .composer textarea:focus-visible { outline: 2px solid var(--accent); }` |
| 11 | Title input has only a placeholder, no `<label>` (the textarea has one); placeholder colour is browser default and not themed, estimated below 4.5:1 in dark mode (not measured) | A11y, UX | app/static/index.html:19 | Add `<label for="title">`; set `::placeholder { color: var(--muted); }` |
| 12 | Packaging: `pyproject.toml` has no `[build-system]` and no package-data for `app/static/*`; a non-editable install may ship without the web page (not verified here) | Prod | pyproject.toml:1-13 | Add `[build-system]` and `[tool.setuptools.package-data] app = ["static/*"]`; test a wheel install |
| 13 | Tests cover only `pagination`; none for store, routes, cache or CLI (which is why critical 8 shipped); `pytest` is not declared as a dependency | Repo Maintainer, Prod | tests/test_pagination.py; pyproject.toml:6 | Add `[project.optional-dependencies] dev = ["pytest"]`; test routes with Flask's test client against a temp DB |
| 14 | `.note` and `.delete` use hardcoded hex colours; in dark mode the page is dark and the cards are bright light grey; long titles and bodies have no wrapping rule | Design, Repo Maintainer | app/static/style.css:91-98, 104-108 | Move to tokens with dark values; `overflow-wrap: anywhere` on `.note` |
| 15 | Dead and duplicated code: `make_slug` duplicates (worse) `utils.slugify`; `utils.truncate` and `slugify` are unused; `getNoteById` is unused and breaks snake_case naming; the `slug` field is sent but never read by the UI | Repo Maintainer | app/server.py:17-19, 35; app/utils.py:9-22; app/store.py:68-71 | Delete the unused helpers, or use `utils.slugify` in the server |

4 more recommendations were left out (explicit connection close in `store`, unescaped `LIKE` wildcards and unbounded search results, no schema versioning or foreign-key enforcement, and the UI exposing no edit, tag or search controls although the API has them).

---

# Lens Reports

## 1. Design Engineer

**Verdict**: APPROVE WITH CHANGES

**Visual State Coverage**

| Component/Element | Hover | Focus | Active | Disabled | Loading | Empty | Error | Dark Mode |
|-------------------|-------|-------|--------|----------|---------|-------|-------|-----------|
| Save button (`button.primary`) | yes (token) | yes (`:focus-visible`) | no | styled, never applied | no | n/a | no | yes (tokens) |
| Title input / note textarea | no | removed (`outline: none`) | no | no | no | n/a | no | yes (tokens) |
| Delete control (`.delete`) | no | no (not focusable) | no | n/a | no | n/a | no | fixed `#b91c1c` on light card |
| Note card (`.note`) | n/a | n/a | n/a | n/a | no | no | no | hardcoded light card on a dark page |
| Notes list | n/a | n/a | n/a | n/a | no | no | no | ok |
| Nav link | browser default | browser default | no | n/a | n/a | n/a | n/a | yes (tokens) |

Verdict details: Token Fidelity CONCERNS (`.note`, `.delete` raw hex); State Coverage CONCERNS; Dark Mode Parity CONCERNS; Animation Quality PASS (one 150ms ease-out colour transition on a named property, no motion needing a reduced-motion query); Consistency PASS (one `--radius` throughout).

## 2. UX Engineer

**Verdict**: NEEDS REWORK

**User Journey Map** (OK = clear, WARN = ambiguous, FAIL = missing)

| Step | Trigger -> Action -> Feedback -> Outcome | Mark |
|------|-------------------------------------------|------|
| Open page | Load -> list fetched -> no loading or empty state | WARN |
| Write a note | Type title and body; title not required | WARN |
| Save (success) | Submit -> form clears, list refreshes, no confirmation | OK |
| Save (server error) | Submit -> form clears anyway, nothing shown, text lost | FAIL |
| Find an older note | More than 20 notes -> only page 1 shown, no paging, no search UI | FAIL |
| Delete a note | One click -> gone, no confirm, no undo | WARN |
| Edit a note | No UI (API exists) | FAIL |
| CLI add | `jotter add` -> "Error", exit 0 | FAIL |
| CLI list | `jotter list` -> Python traceback | FAIL |

Interaction consistency: the page uses click-to-act on a non-control element, unlike its own `button.primary`; error handling in the UI and CLI is silent in both places.

## 3. Frontend Engineer

**Verdict**: NEEDS REWORK

**Render Path Analysis**: Page load, a successful submit and each delete call `loadNotes()`, which fetches `/api/notes` (page 1 only), then `render()` clears `#notes` and rebuilds every card via `innerHTML` with unescaped `title` and `body`. Each `render()` also registers another `document` click handler, so listeners accumulate and the delete path multiplies itself (critical 12). `response.ok` is never checked, so a 4xx or 5xx either renders nothing (HTML body makes `response.json()` throw, unhandled) or, on a submit, resets the form after a failure (critical 9). Types: plain JS, the response shape is never validated (`data.notes` undefined would throw in `for...of`). No framework state, so no stale-closure or memoization concerns; the list has no keys because it is rebuilt wholesale.

## 4. Backend Engineer

**Verdict**: NEEDS REWORK

**Error Path Analysis**: `create_note` (server.py:43-44) lets `KeyError` and Flask's 400/415 surface as HTML 500 or 4xx pages the UI cannot parse. `update_note` validates title length and presence, then calls `store.update_note`, which catches everything and does nothing (store.py:88-89), so the route reports success for every failure, after the tags were already deleted and committed (critical 6). `delete_note` and PUT return success for ids that do not exist or belong to someone else (critical 2). `search` and `list_notes` have no error handling at all; a `sqlite3.OperationalError` (bad path, locked, missing table) becomes an HTML 500 that never reaches the user in a readable form. In the CLI, `add_note` raises `RuntimeError` from `current_user()` and the blanket catch turns it into "Error" (critical 8). Connections are opened per call and closed only when garbage collected: `with connect()` commits but does not close an sqlite3 connection, and `search` and `update_note` do not use `with` at all.

## 5. Structural Engineer

**Verdict**: APPROVE WITH CHANGES

**Dependency Map**

```
cli.py ----------> store.py ----------> server.py (current_user, HTTP layer)   <-- inverted arrow
  |                   |                    |
  +--> sqlite3 (raw)  +--> config.py        +--> cache.py, config.py, pagination.py
  +--> config.py                           +--> store.py (function-local imports x6, to dodge the cycle)
utils.py: imported by nothing
```

Concerning arrows: `store -> server` (data layer depends on the web layer, and pulls in Flask plus a second copy of the app when run as `__main__`); `cli -> sqlite3` skipping the store; `server.make_slug` duplicating `utils.slugify`. Boundary crossings: HTTP to store is clean except for the implicit request context; CLI to store is broken by that context; CLI to DB is unclean (raw SQL, own column list).

## 6. Repo Maintainer

**Verdict**: APPROVE WITH CHANGES

**Convention Compliance Checklist**

| Convention | Status | Notes |
|-----------|--------|-------|
| File placement | PASS | Layout matches the README list; static files under `app/static/` |
| Naming conventions | FAIL | `getNoteById` is camelCase in an otherwise snake_case module (store.py:68) |
| Export/module convention | CONCERNS | `__init__.py` empty (fine); six function-local imports in server.py exist only to dodge the store/server cycle |
| Import ordering | PASS | stdlib, third party, local in every file |
| Path aliases used | n/a | Absolute `from app import ...` used consistently |
| No dead code left | FAIL | `utils.slugify`, `utils.truncate`, `getNoteById`, duplicate `make_slug`, unused `Page.has_next` outside tests |
| Structured logging | FAIL | No logging module anywhere |
| No lint suppressions | PASS | None found; no linter or type checker configured either |
| Docs for new directories | PASS | README layout is accurate, except it advertises a CLI that cannot add or list |

## 7. Production Readiness

**Verdict**: NEEDS REWORK

**Failure Mode Analysis**

| Scenario | What Fails | User Impact | Recovery | Plan Handles It? |
|----------|-----------|-------------|----------|-------------------|
| Run on any machine but the author's | `DB_PATH` directory does not exist | Every request 500s | Edit source | No |
| Started with `flask run` or a WSGI server | `init()` never runs, no tables | `no such table` on every call | Run `python -m app.server` once | No |
| Reachable from the network | Debug on, bound to all interfaces, spoofable user | Debugger exposure, any user's notes readable and deletable | None | No |
| Process killed or DB locked inside `update_note` | Tags already deleted and committed | Note loses its tags, API says ok | Manual | No |
| Two users run the same search | Shared cache entry | A's notes shown to B for 60 s | Wait out the TTL | No |
| Non-editable install | Static files possibly not packaged (not verified) | Blank page and 404 on `/static/*` | Reinstall editable | No |
| Disk full or DB locked on write | `sqlite3.OperationalError` | HTML 500, UI shows nothing, form cleared | Retry by hand | No |
| Something breaks in production | No logs, no health check | Cannot be diagnosed | n/a | No |

## 8. DX Engineer

**Verdict**: NEEDS REWORK

**Error Message Audit**

| Error Scenario | Current Message | What Developer Needs | Suggested Message |
|---------------|----------------|---------------------|-------------------|
| `jotter add` (any failure, including the always-failing request-context bug) | `Error`, exit code 0 | Cause and a non-zero exit | `jotter: could not add note: <cause>` on stderr, exit 1 |
| `jotter list` | `RuntimeError: Working outside of request context` traceback | Never reachable once fixed; until then a clear message | (fix the cause) |
| `jotter export` with no database or table | `sqlite3.OperationalError: no such table: notes` traceback | DB path and a hint | `jotter: no database at <path>; run any command that creates it, or set JOTTER_DB` |
| `jotter export /bad/dir/x.json` | `FileNotFoundError` traceback | Path and reason | `jotter: cannot write /bad/dir/x.json: <reason>` |
| POST `/api/notes` without `title` | HTML 500 page | JSON error with field name | `{"error": "title is required"}`, 400 |
| PUT `/api/notes/<id>` with invalid JSON | "title is required" (parse error hidden by `silent=True`) | The real problem | `{"error": "request body must be valid JSON"}` |
| PUT with empty or too-long title | "title is required" / "title must be at most 200 characters" | Already good | keep |
| Save fails in the web page | Nothing shown, form cleared | Visible error, input kept | "Could not save note: <reason>" |

Journey: first use fails (CLI `add` and `list` broken; the README example in "CLI" does not work); daily use (web) works on the author's machine only; no `--db` flag or env override, no `--help` examples, no machine-readable `list` output.

## 9. Performance Engineer

**Verdict**: NEEDS REWORK

**Resource Budget** (repo mode: there is no change set, so "After Plan" is not applicable)

| Resource | Current | After Plan | Concern? |
|----------|---------|-----------|----------|
| Cross-boundary calls per action | Page load: 1 HTTP request, then 22 SQLite connections and queries (1 count + 1 list + up to 20 tags); search: 1 connection, full table scan with leading-wildcard `LIKE`, no limit | n/a | Yes: N+1, no indexes (rec 4) |
| Event listeners added | 1 document click listener per `render()`, doubling per delete click | n/a | Yes: critical 12 |
| Memory growth per hour | Cache dict grows with each distinct query and never evicts | n/a | Yes: rec 5 |
| Startup time impact | CLI imports `app.server`, so each CLI run builds a Flask app | n/a | Minor |
| Bundle size impact | None (no bundler, one small script and stylesheet) | n/a | No |

Hot path: `GET /api/notes` is the only frequently run path and carries the N+1; nothing runs per keystroke. The cache also serves wrong data across users (critical 3), which matters more than its performance.

## 10. Accessibility Engineer

**Verdict**: APPROVE WITH CHANGES

**Keyboard Navigation Walkthrough**

| Step | Action | Expected Focus | Expected Announcement | Plan Handles? |
|------|--------|---------------|----------------------|---------------|
| 1 | Tab from page load | "Notes" nav link, visible | link, "Notes" | Yes (browser default) |
| 2 | Tab | Title input, visible ring | "Title, edit text" | No: ring removed (`outline: none`), name comes from placeholder only |
| 3 | Tab | Note textarea | "Note, edit text" | Label yes, ring no |
| 4 | Tab, Enter | Save button, ring visible; Enter submits | "Save, button" | Yes |
| 5 | After save | Focus stays on Save; new note appears | Should announce an update | No: no live region, no status message |
| 6 | Tab into notes list | Delete control for each note | "Delete note: <title>, button" | No: the delete is a `div`, not focusable |
| 7 | Activate Delete | Focus moves to a sensible place after the list re-renders | Announce "Note deleted" | No: unreachable, and the list is rebuilt wholesale |

Colour contrast, from the declared colours: link and primary button in light mode about 6.7:1, dark about 9:1; card text about 16:1; delete red on card about 6:1 (all estimated, none measured with a tool). Landmarks and headings are sound (`header`, `nav` with label, `main`, h1 -> h2 -> h3). No animations beyond a 150ms colour change, so `prefers-reduced-motion` is not needed.

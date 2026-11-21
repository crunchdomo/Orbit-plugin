# Answer key for `fixture/` (jotter)

Never show this file to an agent running an audit. Copy `fixture/` somewhere else and audit the copy.

## Scores

1. **Found**: planted defects named in the report (any lens, any severity), out of 20. Report tune and hold-out separately.
2. **False alarms**: critical issues raised against a clean file.
3. **Proof**: share of critical issues that cite a file and line.

Runs differ; a difference of one defect is noise.

## Planted defects

Set T is used while tuning lenses. Set H is hold-out: score it only at baseline and at the end.

| ID | Set | Lens | Where | Defect |
|----|-----|------|-------|--------|
| B1 | T | Backend | `app/store.py` `update_note` | Deletes tags and commits before the update, then swallows every exception: a failed update silently loses the tags |
| B2 | H | Backend | `app/store.py` `search` | Connection opened and never closed |
| P1 | T | Performance | `app/cache.py` | Cache never evicts; expired entries stay, one entry per distinct query forever |
| P2 | H | Performance | `app/server.py` `list_notes` | N+1: one `tags_for` query per note |
| S1 | T | Structural | `app/store.py` import | Data layer imports `current_user` from the web layer; circular, hidden by function-level imports in `server.py` |
| S2 | H | Structural | `app/cli.py` `cmd_export` | Raw SQL straight to SQLite, bypassing `store` |
| R1 | T | Repo | `app/server.py` `make_slug` | Reimplements `utils.slugify`, with different behaviour |
| R2 | H | Repo | `app/store.py` `getNoteById` | camelCase in a snake_case module (and never called) |
| PR1 | T | Production | `app/config.py` | `DEBUG = True` with `HOST = "0.0.0.0"` hardcoded |
| PR2 | H | Production | `app/config.py` `DB_PATH` | Absolute path on a developer's machine, no environment override |
| DX1 | T | DX | `app/cli.py` `cmd_add` | Prints `Error` with no cause and exits 0 |
| DX2 | H | DX | `app/server.py` `create_note` | Missing `title`/`body` raises `KeyError`: a 500 where a 400 with a message belongs |
| F1 | T | Frontend | `app/static/app.js` `render` | Adds a document click listener on every render; they pile up and one click fires many deletes |
| F2 | H | Frontend | `app/static/app.js` `render` | Note title and body go into `innerHTML` unescaped (XSS) |
| DE1 | T | Design | `app/static/style.css` `.note` | Hardcoded colours beside the token set; unreadable in dark mode |
| DE2 | H | Design | `app/static/style.css` `.delete` | No hover or focus state, unlike `button.primary` |
| U1 | T | UX | `app/static/app.js` delete | Deletes at once, no confirmation and no undo |
| U2 | H | UX | `app/static/app.js` submit | Empty `catch`, `response.ok` never checked: a failed save looks like a success |
| A1 | T | Accessibility | `app/static/app.js` delete | A `div`, not a button: no keyboard access, no role |
| A2 | H | Accessibility | `index.html` `#title`, `style.css` | Title input has only a placeholder, and inputs have `outline: none` |

## Clean files (the control)

A critical issue against any of these is a false alarm:

- `app/utils.py`
- `app/pagination.py`
- `tests/test_pagination.py`

## Real but not planted

Do not count these as found or as false alarms: identity comes from an unauthenticated `X-User` header, and update, delete and get-by-id never check the owner.

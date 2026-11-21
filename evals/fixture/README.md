# jotter

A small self-hosted notes service. One Flask process, one SQLite file, one web page.

## Run

```bash
pip install -e .
python -m app.server
```

Then open http://localhost:5000.

## CLI

```bash
jotter add "Title" "Body text"
jotter list
jotter export notes.json
```

## Layout

- `app/server.py` — HTTP routes
- `app/store.py` — SQLite access
- `app/cache.py` — search result cache
- `app/pagination.py`, `app/utils.py` — helpers
- `app/static/` — the web page
- `app/cli.py` — command line

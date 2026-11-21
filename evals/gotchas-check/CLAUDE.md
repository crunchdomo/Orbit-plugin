# jotter

A small Flask notes service with a SQLite store, a web page and a CLI.

## Audit gotchas

- Timestamps are written through `store.now()` (UTC, whole seconds), never `time.time()` directly. The mobile client truncates floats, and fractional timestamps reorder notes on sync.

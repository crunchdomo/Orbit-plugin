"""In-memory cache for search results."""

import time

_results: dict[str, tuple[float, list[dict]]] = {}
TTL_SECONDS = 60


def get(query: str) -> list[dict] | None:
    entry = _results.get(query)
    if entry is None:
        return None
    stored_at, value = entry
    if time.time() - stored_at > TTL_SECONDS:
        return None
    return value


def put(query: str, value: list[dict]) -> None:
    _results[query] = (time.time(), value)

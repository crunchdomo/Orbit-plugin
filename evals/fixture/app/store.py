"""SQLite access for notes and tags."""

import sqlite3
import time

from app import config
from app.server import current_user

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tags (
    note_id INTEGER NOT NULL REFERENCES notes(id),
    name TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def add_note(title: str, body: str) -> int:
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO notes (owner, title, body, updated_at) VALUES (?, ?, ?, ?)",
            (current_user(), title, body, time.time()),
        )
        return cursor.lastrowid


def list_notes(limit: int, offset: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM notes WHERE owner = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (current_user(), limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]


def count_notes() -> int:
    with connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM notes WHERE owner = ?", (current_user(),)
        ).fetchone()[0]


def tags_for(note_id: int) -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT name FROM tags WHERE note_id = ?", (note_id,)
        ).fetchall()
        return [row["name"] for row in rows]


def getNoteById(note_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return dict(row) if row else None


def update_note(note_id: int, title: str, body: str, tags: list[str]) -> None:
    conn = connect()
    try:
        conn.execute("DELETE FROM tags WHERE note_id = ?", (note_id,))
        conn.commit()
        conn.execute(
            "UPDATE notes SET title = ?, body = ?, updated_at = ? WHERE id = ?",
            (title, body, time.time(), note_id),
        )
        for name in tags:
            conn.execute(
                "INSERT INTO tags (note_id, name) VALUES (?, ?)", (note_id, name)
            )
        conn.commit()
    except Exception:
        pass


def delete_note(note_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM tags WHERE note_id = ?", (note_id,))
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))


def search(query: str) -> list[dict]:
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM notes WHERE owner = ? AND (title LIKE ? OR body LIKE ?)",
        (current_user(), f"%{query}%", f"%{query}%"),
    ).fetchall()
    return [dict(row) for row in rows]

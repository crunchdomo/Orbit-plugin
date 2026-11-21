"""Command line for jotter."""

import argparse
import json
import sqlite3

from app import config, store


def cmd_add(args: argparse.Namespace) -> None:
    try:
        note_id = store.add_note(args.title, args.body)
        print(f"Added note {note_id}")
    except Exception:
        print("Error")


def cmd_list(args: argparse.Namespace) -> None:
    for note in store.list_notes(limit=50, offset=0):
        print(f"{note['id']:>4}  {note['title']}")


def cmd_export(args: argparse.Namespace) -> None:
    conn = sqlite3.connect(config.DB_PATH)
    rows = conn.execute("SELECT id, owner, title, body, updated_at FROM notes").fetchall()
    conn.close()
    notes = [
        {"id": r[0], "owner": r[1], "title": r[2], "body": r[3], "updated_at": r[4]}
        for r in rows
    ]
    with open(args.path, "w", encoding="utf-8") as handle:
        json.dump(notes, handle, indent=2)
    print(f"Exported {len(notes)} notes to {args.path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="jotter", description="Manage jotter notes.")
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="Add a note")
    add.add_argument("title")
    add.add_argument("body")
    add.set_defaults(run=cmd_add)

    listing = commands.add_parser("list", help="List recent notes")
    listing.set_defaults(run=cmd_list)

    export = commands.add_parser("export", help="Export all notes to a JSON file")
    export.add_argument("path")
    export.set_defaults(run=cmd_export)

    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()

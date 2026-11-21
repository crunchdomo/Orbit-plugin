"""HTTP routes for jotter."""

import re

from flask import Flask, jsonify, request, send_from_directory

from app import cache, config
from app.pagination import parse_page

app = Flask(__name__, static_folder="static")


def current_user() -> str:
    return request.headers.get("X-User", "local")


def make_slug(title: str) -> str:
    slug = title.lower().replace(" ", "-")
    return re.sub(r"[^a-z0-9-]", "", slug)


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/notes")
def list_notes():
    from app import store

    page = parse_page(request.args.get("page"), config.PAGE_SIZE, store.count_notes())
    notes = store.list_notes(page.size, page.offset)
    for note in notes:
        note["tags"] = store.tags_for(note["id"])
        note["slug"] = make_slug(note["title"])
    return jsonify({"notes": notes, "page": page.number, "pages": page.pages})


@app.post("/api/notes")
def create_note():
    from app import store

    data = request.json
    note_id = store.add_note(data["title"], data["body"])
    return jsonify({"id": note_id}), 201


@app.put("/api/notes/<int:note_id>")
def update_note(note_id: int):
    from app import store

    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    if len(title) > config.MAX_TITLE_LENGTH:
        return jsonify({"error": f"title must be at most {config.MAX_TITLE_LENGTH} characters"}), 400
    store.update_note(note_id, title, data.get("body", ""), data.get("tags", []))
    return jsonify({"ok": True})


@app.delete("/api/notes/<int:note_id>")
def delete_note(note_id: int):
    from app import store

    store.delete_note(note_id)
    return "", 204


@app.get("/api/search")
def search():
    from app import store

    query = request.args.get("q", "")
    cached = cache.get(query)
    if cached is not None:
        return jsonify({"notes": cached})
    results = store.search(query)
    cache.put(query, results)
    return jsonify({"notes": results})


if __name__ == "__main__":
    from app import store

    store.init()
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)

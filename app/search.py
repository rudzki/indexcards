from markupsafe import escape

from app import db
from app.markdown import strip_markdown


def _fts_text(value):
    """HTML-escape text before it enters the FTS index. The search view renders
    snippet() output as safe Markup, so any raw HTML in a title/body would
    otherwise survive into results as live markup (stored XSS)."""
    return str(escape(value or ''))


def create_fts_table():
    # Older databases carry a 3-column index (title, aliases, body). Aliases
    # were removed, so drop and rebuild the index when the stale schema is
    # found — otherwise the 2-column INSERTs below fail against it.
    row = db.session.execute(db.text(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='entry_fts'"
    )).fetchone()
    if row and row[0] and 'aliases' in row[0]:
        db.session.execute(db.text('DROP TABLE entry_fts'))
        db.session.commit()
        row = None

    db.session.execute(db.text(
        "CREATE VIRTUAL TABLE IF NOT EXISTS entry_fts USING fts5("
        "title, body"
        ")"
    ))
    db.session.commit()

    if row is None:
        # Table was just (re)created; populate it from existing entries.
        rebuild_fts()


def update_fts_entry(entry, commit=True):
    body = _fts_text(strip_markdown(entry.body_markdown))
    title = _fts_text(entry.title)

    db.session.execute(db.text(
        'DELETE FROM entry_fts WHERE rowid = :id'
    ), {'id': entry.id})
    db.session.execute(db.text(
        'INSERT INTO entry_fts(rowid, title, body) '
        'VALUES (:id, :title, :body)'
    ), {'id': entry.id, 'title': title, 'body': body})
    if commit:
        db.session.commit()


def delete_fts_entry(entry_id, commit=True):
    db.session.execute(db.text(
        'DELETE FROM entry_fts WHERE rowid = :id'
    ), {'id': entry_id})
    if commit:
        db.session.commit()


def rebuild_fts():
    from app.models import Entry
    db.session.execute(db.text('DELETE FROM entry_fts'))
    for entry in Entry.query.all():
        body = _fts_text(strip_markdown(entry.body_markdown))
        title = _fts_text(entry.title)
        db.session.execute(db.text(
            'INSERT INTO entry_fts(rowid, title, body) '
            'VALUES (:id, :title, :body)'
        ), {'id': entry.id, 'title': title, 'body': body})
    db.session.commit()


def search_entries(query, limit=50):
    if not query or not query.strip():
        return []

    safe_query = query.strip().replace('"', '""')
    terms = safe_query.split()
    fts_query = ' '.join(f'"{t}"*' for t in terms)

    results = db.session.execute(db.text(
        'SELECT rowid, rank, snippet(entry_fts, -1, "<mark>", "</mark>", "…", 30) as excerpt '
        'FROM entry_fts WHERE entry_fts MATCH :query '
        'ORDER BY rank LIMIT :limit'
    ), {'query': fts_query, 'limit': limit}).fetchall()

    return results

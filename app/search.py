from app import db
from app.markdown import strip_markdown


def create_fts_table():
    db.session.execute(db.text(
        "CREATE VIRTUAL TABLE IF NOT EXISTS entry_fts USING fts5("
        "title, aliases, body"
        ")"
    ))
    db.session.commit()


def update_fts_entry(entry, commit=True):
    aliases = ', '.join(a.title for a in entry.aliases)
    body = strip_markdown(entry.body_markdown)

    db.session.execute(db.text(
        'DELETE FROM entry_fts WHERE rowid = :id'
    ), {'id': entry.id})
    db.session.execute(db.text(
        'INSERT INTO entry_fts(rowid, title, aliases, body) '
        'VALUES (:id, :title, :aliases, :body)'
    ), {'id': entry.id, 'title': entry.title, 'aliases': aliases, 'body': body})
    if commit:
        db.session.commit()


def delete_fts_entry(entry_id):
    db.session.execute(db.text(
        'DELETE FROM entry_fts WHERE rowid = :id'
    ), {'id': entry_id})
    db.session.commit()


def rebuild_fts():
    from app.models import Entry
    db.session.execute(db.text('DELETE FROM entry_fts'))
    for entry in Entry.query.all():
        aliases = ', '.join(a.title for a in entry.aliases)
        body = strip_markdown(entry.body_markdown)
        db.session.execute(db.text(
            'INSERT INTO entry_fts(rowid, title, aliases, body) '
            'VALUES (:id, :title, :aliases, :body)'
        ), {'id': entry.id, 'title': entry.title, 'aliases': aliases, 'body': body})
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

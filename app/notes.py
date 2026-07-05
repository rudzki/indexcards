from flask import flash, redirect, url_for, request
from flask_login import current_user

from app import db
from app.models import Note, NoteBacklink, Entry, log_audit, utcnow
from app.markdown import render_markdown, extract_internal_links


def save_note(note):
    body_markdown = request.form.get('body_markdown', '')
    is_draft = 'is_draft' in request.form

    is_new = note is None

    if is_new:
        note = Note(created_by=current_user.id)
        db.session.add(note)

    note.body_markdown = body_markdown
    note.body_html = render_markdown(body_markdown)
    note.is_draft = is_draft

    if not is_draft and not note.published_at:
        note.published_at = utcnow()

    db.session.flush()

    sync_note_backlinks(note)

    db.session.commit()

    log_audit('note_created' if is_new else 'note_edited', detail=f'Note #{note.id}',
              user_id=current_user.id)

    flash('Note saved.', 'success')
    return redirect(url_for('admin.edit_note', note_id=note.id))


def sync_note_backlinks(note):
    NoteBacklink.query.filter_by(note_id=note.id).delete()

    linked_slugs = extract_internal_links(note.body_markdown)
    for slug in linked_slugs:
        target = Entry.query.filter_by(slug=slug).first()
        if target:
            db.session.add(NoteBacklink(note_id=note.id, target_entry_id=target.id))

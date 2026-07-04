from datetime import datetime, timezone

from flask import render_template, redirect, url_for, request, flash, abort
from flask_login import current_user

from app import db
from app.models import Note, SiteSettings, log_audit
from app.locks import acquire_lock, active_locks
from app.notes import save_note
from app.views.admin import admin_bp, writer_required


def _notes_enabled_or_redirect():
    site_settings = SiteSettings.query.get(1)
    if not site_settings or not site_settings.notes_enabled:
        flash('Notes are not enabled. Enable them in Settings.', 'error')
        return redirect(url_for('admin.settings'))
    return None


@admin_bp.route('/notes/')
@writer_required
def notes_list():
    guard = _notes_enabled_or_redirect()
    if guard:
        return guard
    page = request.args.get('page', 1, type=int)
    pagination = Note.query.order_by(Note.created_at.desc()).paginate(page=page, per_page=25, error_out=False)
    locked_notes = active_locks('note')
    return render_template('admin/notes.html', notes=pagination.items,
                           pagination=pagination, locked_notes=locked_notes)


@admin_bp.route('/notes/new/', methods=['GET', 'POST'])
@writer_required
def new_note():
    guard = _notes_enabled_or_redirect()
    if guard:
        return guard
    if request.method == 'POST':
        return save_note(None)
    return render_template('admin/note_editor.html', note=None)


@admin_bp.route('/notes/<int:note_id>/edit/', methods=['GET', 'POST'])
@writer_required
def edit_note(note_id):
    guard = _notes_enabled_or_redirect()
    if guard:
        return guard
    note = Note.query.get_or_404(note_id)
    if not current_user.can_modify(note):
        abort(403)
    if request.method == 'POST':
        return save_note(note)
    blocker = acquire_lock('note', note_id)
    if blocker:
        flash(f'This note is currently being edited by {blocker}.', 'warning')
        return redirect(url_for('admin.notes_list'))
    return render_template('admin/note_editor.html', note=note, lock_type='note', lock_id=note_id)


@admin_bp.route('/notes/<int:note_id>/delete/', methods=['POST'])
@writer_required
def delete_note(note_id):
    note = Note.query.get_or_404(note_id)
    if not current_user.can_modify(note):
        abort(403)
    db.session.delete(note)
    db.session.commit()
    log_audit('note_deleted', detail=f'Note #{note.id}', user_id=current_user.id)
    flash('Note deleted.', 'success')
    return redirect(url_for('admin.notes_list'))


@admin_bp.route('/notes/<int:note_id>/publish/', methods=['POST'])
@writer_required
def publish_note(note_id):
    note = Note.query.get_or_404(note_id)
    if not current_user.can_modify(note):
        abort(403)
    note.is_draft = not note.is_draft
    if not note.is_draft and not note.published_at:
        note.published_at = datetime.now(timezone.utc)
    db.session.commit()
    status = 'unpublished' if note.is_draft else 'published'
    flash(f'Note {status}.', 'success')
    return redirect(url_for('admin.edit_note', note_id=note.id))

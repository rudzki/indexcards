from datetime import datetime, timezone

from flask import render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from markupsafe import Markup

from app import db
from app.models import Entry, EditLog, log_audit, entry_url
from app.markdown import render_markdown
from app.search import delete_fts_entry, update_fts_entry
from app.locks import acquire_lock, active_locks
from app.entries import save_entry, sync_backlinks
from app.revisions import build_revisions
from app.views.admin import admin_bp, admin_required, writer_required


@admin_bp.route('/')
@login_required
def dashboard():
    if not current_user.can_write:
        return redirect(url_for('main.index'))

    sort = request.args.get('sort', 'updated')
    order = request.args.get('order', 'desc')
    page = request.args.get('page', 1, type=int)

    if current_user.is_admin or current_user.is_editor:
        q = Entry.query
    else:
        q = Entry.query.filter_by(created_by=current_user.id)

    sort_col = {'title': Entry.sort_title, 'status': Entry.is_draft, 'updated': Entry.updated_at}.get(sort, Entry.updated_at)
    q = q.order_by(sort_col.asc() if order == 'asc' else sort_col.desc())

    pagination = q.paginate(page=page, per_page=25, error_out=False)
    locked_entries = active_locks('entry')
    return render_template('admin/dashboard.html', entries=pagination.items,
                           pagination=pagination, sort=sort, order=order,
                           locked_entries=locked_entries)


@admin_bp.route('/entry/new/', methods=['GET', 'POST'])
@writer_required
def new_entry():
    if request.method == 'POST':
        return save_entry(None)
    prefill_title = request.args.get('title', '').replace('-', ' ').strip().title()
    return render_template('admin/editor.html', entry=None, prefill_title=prefill_title)


@admin_bp.route('/entry/<int:entry_id>/edit/', methods=['GET', 'POST'])
@writer_required
def edit_entry(entry_id):
    entry = Entry.query.get_or_404(entry_id)
    if not current_user.can_modify(entry):
        abort(403)
    if request.method == 'POST':
        return save_entry(entry)
    blocker = acquire_lock('entry', entry_id)
    if blocker:
        flash(f'"{entry.title}" is currently being edited by {blocker}.', 'warning')
        return redirect(url_for('admin.dashboard'))
    return render_template('admin/editor.html', entry=entry, lock_type='entry', lock_id=entry_id)


@admin_bp.route('/entry/<int:entry_id>/delete/', methods=['POST'])
@writer_required
def delete_entry(entry_id):
    entry = Entry.query.get_or_404(entry_id)
    if not current_user.can_modify(entry):
        abort(403)
    entry_title = entry.title
    delete_fts_entry(entry.id)
    db.session.delete(entry)
    db.session.commit()
    log_audit('entry_deleted', detail=entry_title, user_id=current_user.id)
    flash('Entry deleted.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/entries/<int:entry_id>/publish/', methods=['POST'])
@login_required
def publish_entry(entry_id):
    entry = Entry.query.get_or_404(entry_id)
    if not current_user.can_modify(entry):
        abort(403)
    entry.is_draft = False
    if not entry.published_at:
        entry.published_at = datetime.now(timezone.utc)
    db.session.commit()
    flash(f'"{entry.title}" published.', 'success')
    return redirect(entry_url(entry))


@admin_bp.route('/preview/<int:entry_id>/')
@login_required
def preview_entry(entry_id):
    entry = Entry.query.get_or_404(entry_id)
    if not current_user.can_modify(entry):
        abort(403)
    from app.markdown import mark_missing_links, extract_toc
    existing_slugs = {e.slug for e in Entry.query.with_entities(Entry.slug).all()}
    body_html = mark_missing_links(entry.body_html, existing_slugs)
    toc = extract_toc(body_html)
    backlinks = (Entry.query
                 .join(Entry.outgoing_links)
                 .filter(Entry.outgoing_links.any(target_entry_id=entry.id))
                 .all())
    last_edit_log = (EditLog.query
                     .filter_by(entry_id=entry.id)
                     .filter(EditLog.is_import == False)  # noqa: E712
                     .order_by(EditLog.edited_at.desc())
                     .first())
    last_editor = last_edit_log.user if last_edit_log else None
    return render_template('entry.html', entry=entry, body_html=Markup(body_html),
                           backlinks=backlinks, note_backlinks=[], toc=toc, is_preview=True,
                           last_editor=last_editor,
                           ancestors=[], children=[], prev_entry=None, next_entry=None)


@admin_bp.route('/entries/bulk/', methods=['POST'])
@admin_required
def bulk_entries():
    entry_ids = request.form.getlist('entry_ids', type=int)
    action = request.form.get('bulk_action', '')

    if not entry_ids:
        flash('No entries selected.', 'error')
        return redirect(url_for('admin.dashboard'))

    entries = Entry.query.filter(Entry.id.in_(entry_ids)).all()
    count = 0

    if action == 'publish':
        for entry in entries:
            if current_user.can_modify(entry):
                entry.is_draft = False
                if not entry.published_at:
                    entry.published_at = datetime.now(timezone.utc)
                count += 1
        db.session.commit()
        flash(f'{count} entries published.', 'success')
    elif action == 'unpublish':
        for entry in entries:
            if current_user.can_modify(entry):
                entry.is_draft = True
                count += 1
        db.session.commit()
        flash(f'{count} entries unpublished.', 'success')
    elif action == 'delete':
        for entry in entries:
            if current_user.can_modify(entry):
                delete_fts_entry(entry.id)
                db.session.delete(entry)
                count += 1
        db.session.commit()
        flash(f'{count} entries deleted.', 'success')
    else:
        flash('Invalid action.', 'error')

    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/entry/<int:entry_id>/history/')
@writer_required
def entry_history(entry_id):
    entry = Entry.query.get_or_404(entry_id)
    if not current_user.can_modify(entry):
        abort(403)
    logs = (EditLog.query
            .filter_by(entry_id=entry_id)
            .order_by(EditLog.edited_at.desc())
            .all())
    revisions = build_revisions(logs)
    return render_template('admin/entry_history.html', entry=entry, revisions=revisions)


@admin_bp.route('/entry/<int:entry_id>/history/<int:log_id>/restore/', methods=['POST'])
@writer_required
def restore_entry_revision(entry_id, log_id):
    entry = Entry.query.get_or_404(entry_id)
    if not current_user.can_modify(entry):
        abort(403)
    log = EditLog.query.filter_by(id=log_id, entry_id=entry_id).first_or_404()
    if not log.body_snapshot:
        flash('This revision has no saved content to restore.', 'error')
        return redirect(url_for('admin.entry_history', entry_id=entry_id))
    entry.body_markdown = log.body_snapshot
    entry.body_html = render_markdown(log.body_snapshot)
    restore_note = f'Restored from revision on {log.edited_at.strftime("%Y-%m-%d %H:%M")}'
    db.session.add(EditLog(
        entry_id=entry.id,
        user_id=current_user.id,
        body_snapshot=log.body_snapshot,
        changelog=restore_note,
    ))
    db.session.flush()
    sync_backlinks(entry)
    db.session.commit()
    update_fts_entry(entry)
    flash('Entry restored to selected revision.', 'success')
    return redirect(url_for('admin.edit_entry', entry_id=entry_id))

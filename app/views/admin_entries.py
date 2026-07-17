from flask import render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from markupsafe import Markup

from app import db
from app.models import (Entry, EditLog, NavItem, log_audit, entry_url, set_published,
                        assignable_groups, accessible_entries_filter)
from app.search import delete_fts_entry
from app.locks import acquire_lock, active_locks
from app.entries import save_content
from app.views.admin import admin_bp, writer_required
from app.views._helpers import apply_sort


def build_revisions(items):
    """Build revision display dicts from a list of EditLog rows, ordered
    most-recent-first. Each row is a changelog entry (message, timestamp,
    author) — the history view is a plain audit list."""
    return [{
        'id': item.id,
        'changelog': item.changelog,
        'edited_at': item.edited_at,
        'user': item.user,
    } for item in items]


@admin_bp.route('/')
@login_required
def dashboard():
    if not current_user.can_write:
        return redirect(url_for('main.index'))

    page = request.args.get('page', 1, type=int)
    # Independent, combinable filter axes:
    #   status  — publication state via is_draft (published vs draft)
    #   listed  — listing visibility via is_listed (former entries vs former pages)
    #   stub    — placeholder state via is_stub (stubs vs full entries)
    # They combine, so a viewer can narrow to e.g. draft + unlisted stubs.
    status = request.args.get('status', 'all')
    listed = request.args.get('listed', 'all')
    stub = request.args.get('stub', 'all')

    if current_user.is_admin or current_user.is_editor:
        q = Entry.query
    else:
        q = Entry.query.filter_by(created_by=current_user.id)

    # Hide grouped entries the viewer can't read (admins bypass via the filter).
    q = q.filter(accessible_entries_filter(current_user))

    if status == 'published':
        q = q.filter(Entry.is_draft == False)  # noqa: E712
    elif status == 'draft':
        q = q.filter(Entry.is_draft == True)  # noqa: E712

    if listed == 'listed':
        q = q.filter(Entry.is_listed == True)  # noqa: E712
    elif listed == 'unlisted':
        q = q.filter(Entry.is_listed == False)  # noqa: E712

    if stub == 'stub':
        q = q.filter(Entry.is_stub == True)  # noqa: E712
    elif stub == 'full':
        q = q.filter(Entry.is_stub == False)  # noqa: E712

    q, sort, order = apply_sort(q, request, {
        'title': Entry.sort_title, 'status': Entry.is_draft, 'updated': Entry.updated_at,
    }, 'updated')

    pagination = q.paginate(page=page, per_page=25, error_out=False)
    locked_entries = active_locks('entry')
    return render_template('admin/dashboard.html', entries=pagination.items,
                           pagination=pagination, sort=sort, order=order,
                           status=status, listed=listed, stub=stub,
                           locked_entries=locked_entries)


@admin_bp.route('/entry/new/', methods=['GET', 'POST'])
@writer_required
def new_entry():
    if request.method == 'POST':
        return save_content(None)
    prefill_title = request.args.get('title', '').replace('-', ' ').strip().title()
    return render_template('admin/editor.html', entry=None, prefill_title=prefill_title,
                           assignable_groups=assignable_groups(current_user),
                           entry_group_ids=set())


@admin_bp.route('/entry/<int:entry_id>/edit/', methods=['GET', 'POST'])
@writer_required
def edit_entry(entry_id):
    entry = db.get_or_404(Entry, entry_id)
    if not current_user.can_modify(entry):
        abort(403)
    if request.method == 'POST':
        return save_content(entry)
    blocker = acquire_lock('entry', entry_id)
    if blocker:
        flash(f'"{entry.title}" is currently being edited by {blocker}.', 'warning')
        return redirect(url_for('admin.dashboard'))
    return render_template('admin/editor.html', entry=entry, lock_type='entry', lock_id=entry_id,
                           assignable_groups=assignable_groups(current_user),
                           entry_group_ids={g.id for g in entry.groups})


@admin_bp.route('/entry/<int:entry_id>/delete/', methods=['POST'])
@writer_required
def delete_entry(entry_id):
    entry = db.get_or_404(Entry, entry_id)
    if not current_user.can_modify(entry):
        abort(403)
    entry_title = entry.title
    # Detach children first — SQLite FK enforcement is off, so a dangling
    # parent_id would otherwise persist and 500 pages that dereference
    # entry.parent. Drop any nav slot pointing here for the same reason.
    Entry.query.filter_by(parent_id=entry.id).update({'parent_id': None})
    NavItem.query.filter_by(entry_id=entry.id).delete()
    delete_fts_entry(entry.id)
    db.session.delete(entry)
    db.session.commit()
    log_audit('entry_deleted', detail=entry_title, user_id=current_user.id)
    flash('Entry deleted.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/entries/<int:entry_id>/publish/', methods=['POST'])
@login_required
def publish_entry(entry_id):
    entry = db.get_or_404(Entry, entry_id)
    if not current_user.can_modify(entry):
        abort(403)
    was_unpublished = entry.is_draft
    is_first_publish = set_published(entry, True)
    db.session.commit()
    # Announce to Slack / webhooks — the common draft-then-publish flow never
    # goes through save_content() as non-draft, so integrations must fire here too.
    if was_unpublished:
        from app.entries import _fire_integrations
        _fire_integrations(entry, is_new=is_first_publish, changelog=None)
    flash(f'"{entry.title}" published.', 'success')
    return redirect(entry_url(entry))


@admin_bp.route('/entries/bulk/', methods=['POST'])
@writer_required
def bulk_entries():
    # Any writer may run bulk actions; the per-entry can_modify checks below
    # scope each action to what the caller is actually allowed to touch, so an
    # author only affects their own entries while editors/admins affect all.
    entry_ids = request.form.getlist('entry_ids', type=int)
    action = request.form.get('bulk_action', '')

    if not entry_ids:
        flash('No entries selected.', 'error')
        return redirect(url_for('admin.dashboard'))

    entries = Entry.query.filter(Entry.id.in_(entry_ids)).all()
    count = 0

    if action == 'publish':
        newly_published = []
        for entry in entries:
            if current_user.can_modify(entry):
                was_draft = entry.is_draft
                first_publish = set_published(entry, True)
                if was_draft:
                    newly_published.append((entry, first_publish))
                count += 1
        db.session.commit()
        from app.entries import _fire_integrations
        for entry, is_first in newly_published:
            _fire_integrations(entry, is_new=is_first, changelog=None)
        flash(f'{count} entries published.', 'success')
    elif action == 'unpublish':
        for entry in entries:
            if current_user.can_modify(entry):
                set_published(entry, False)
                count += 1
        db.session.commit()
        flash(f'{count} entries unpublished.', 'success')
    elif action == 'delete':
        for entry in entries:
            if current_user.can_modify(entry):
                # Detach children, drop nav slots, and defer the FTS commit so
                # the whole batch commits atomically with the entry deletions.
                Entry.query.filter_by(parent_id=entry.id).update({'parent_id': None})
                NavItem.query.filter_by(entry_id=entry.id).delete()
                delete_fts_entry(entry.id, commit=False)
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
    entry = db.get_or_404(Entry, entry_id)
    if not current_user.can_modify(entry):
        abort(403)
    logs = (EditLog.query
            .filter_by(entry_id=entry_id)
            .order_by(EditLog.edited_at.desc())
            .all())
    revisions = build_revisions(logs)
    return render_template('admin/entry_history.html', entry=entry, revisions=revisions)

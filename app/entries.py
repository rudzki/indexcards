from datetime import datetime, timezone

from flask import flash, render_template, redirect, url_for, request
from flask_login import current_user

from app import db
from app.models import Entry, Alias, Backlink, EditLog, SiteSettings, make_slug, log_audit
from app.markdown import render_markdown, extract_internal_links
from app.search import update_fts_entry

RESERVED_SLUGS = {
    'feed', 'search', 'login', 'logout', 'signup', 'subscribe',
    'confirm', 'unsubscribe', 'random', 'healthz', 'admin', 'dashboard',
    'static', 'favicon', 'site-image', 'uploads',
}


def save_entry(entry):
    title = request.form.get('title', '').strip()
    summary = request.form.get('summary', '').strip()
    body_markdown = request.form.get('body_markdown', '')
    aliases_raw = request.form.get('aliases', '').strip()
    changelog = request.form.get('changelog', '').strip() or None
    is_draft = 'is_draft' in request.form
    is_stub = 'is_stub' in request.form
    parent_id_raw = request.form.get('parent_id', '').strip()

    if not title:
        flash('Title is required.', 'error')
        return render_template('admin/editor.html', entry=entry)

    slug_input = request.form.get('slug', '').strip()
    slug = make_slug(slug_input) if slug_input else make_slug(title)

    if slug in RESERVED_SLUGS:
        flash(f'"{slug}" is a reserved path and cannot be used as an entry slug.', 'error')
        return render_template('admin/editor.html', entry=entry)

    is_new = entry is None

    if is_new:
        existing = Entry.query.filter_by(slug=slug).first()
        existing_alias = Alias.query.filter_by(slug=slug).first()
        if existing or existing_alias:
            flash('An entry with this title (or slug) already exists.', 'error')
            return render_template('admin/editor.html', entry=entry)
        entry = Entry(slug=slug, created_by=current_user.id)
        db.session.add(entry)
    else:
        if slug != entry.slug:
            conflict = Entry.query.filter(Entry.slug == slug, Entry.id != entry.id).first()
            conflict_alias = Alias.query.filter_by(slug=slug).first()
            if conflict or conflict_alias:
                flash('An entry with this title (or slug) already exists.', 'error')
                return render_template('admin/editor.html', entry=entry)
            entry.slug = slug

    entry.title = title
    entry.summary = summary
    entry.body_markdown = body_markdown
    entry.body_html = render_markdown(body_markdown)
    entry.is_draft = is_draft
    entry.is_stub = is_stub
    entry.update_sort_title()

    if not is_draft and not entry.published_at:
        entry.published_at = datetime.now(timezone.utc)

    if parent_id_raw and parent_id_raw.isdigit():
        proposed_parent_id = int(parent_id_raw)
        parent_entry = Entry.query.get(proposed_parent_id)
        if (parent_entry and parent_entry.id != (entry.id or -1) and not parent_entry.parent_id
                and not _creates_cycle(entry, parent_entry)):
            entry.parent_id = parent_entry.id
        else:
            entry.parent_id = None
    else:
        entry.parent_id = None

    sync_aliases(entry, aliases_raw)

    db.session.flush()

    sync_backlinks(entry)

    last_log = (EditLog.query
                .filter_by(entry_id=entry.id)
                .order_by(EditLog.edited_at.desc())
                .first())
    content_changed = is_new or (last_log is None) or (last_log.body_snapshot != body_markdown)
    log = EditLog(
        entry_id=entry.id,
        user_id=current_user.id,
        changelog=changelog,
        body_snapshot=body_markdown if content_changed else None,
    )
    db.session.add(log)

    # Keep at most 50 snapshots per entry; prune oldest beyond the limit
    snapshot_count = (EditLog.query
                      .filter(EditLog.entry_id == entry.id,
                              EditLog.body_snapshot.isnot(None))
                      .count())
    if snapshot_count > 50:
        oldest = (EditLog.query
                  .filter(EditLog.entry_id == entry.id,
                          EditLog.body_snapshot.isnot(None))
                  .order_by(EditLog.edited_at.asc())
                  .limit(snapshot_count - 50)
                  .all())
        for old in oldest:
            old.body_snapshot = None

    db.session.commit()

    update_fts_entry(entry)

    if is_new:
        log_audit('entry_created', detail=entry.title, user_id=current_user.id)
    else:
        log_audit('entry_edited', detail=entry.title, user_id=current_user.id)

    if not is_draft:
        _fire_integrations(entry, is_new=is_new, changelog=changelog)

    flash('Entry saved.', 'success')
    return redirect(url_for('admin.edit_entry', entry_id=entry.id))


def _creates_cycle(entry, proposed_parent):
    """Return True if proposed_parent is entry itself or one of its
    descendants — adopting it as a parent would create a cycle in the
    hierarchy."""
    if entry.id is None:
        return False
    cursor = proposed_parent
    seen = set()
    for _ in range(50):
        if cursor.id == entry.id:
            return True
        if cursor.id in seen or not cursor.parent_id:
            return False
        seen.add(cursor.id)
        cursor = Entry.query.get(cursor.parent_id)
        if not cursor:
            return False
    return False


def sync_aliases(entry, aliases_raw):
    new_aliases = [a.strip() for a in aliases_raw.split(',') if a.strip()]
    new_slugs = {make_slug(a) for a in new_aliases}
    existing_slugs = {a.slug for a in entry.aliases}

    for alias in list(entry.aliases):
        if alias.slug not in new_slugs:
            db.session.delete(alias)

    for alias_title in new_aliases:
        alias_slug = make_slug(alias_title)
        if alias_slug not in existing_slugs and alias_slug != entry.slug:
            conflict = Entry.query.filter_by(slug=alias_slug).first()
            conflict_alias = Alias.query.filter(
                Alias.slug == alias_slug, Alias.entry_id != entry.id
            ).first()
            if not conflict and not conflict_alias:
                db.session.add(Alias(entry_id=entry.id, title=alias_title, slug=alias_slug))


def sync_backlinks(entry):
    Backlink.query.filter_by(source_entry_id=entry.id).delete()

    linked_slugs = extract_internal_links(entry.body_markdown)
    for slug in linked_slugs:
        target = Entry.query.filter_by(slug=slug).first()
        if target and target.id != entry.id:
            db.session.add(Backlink(source_entry_id=entry.id, target_entry_id=target.id))


def _fire_integrations(entry, is_new, changelog):
    from app.integrations import notify_slack_entry, fire_outgoing_webhook
    site_settings = SiteSettings.query.get(1)
    if not site_settings:
        return
    event = 'entry.published' if is_new else 'entry.updated'
    notify_slack_entry(entry, is_new=is_new, changelog=changelog, settings=site_settings)
    if site_settings.site_visibility == 'public':
        fire_outgoing_webhook(entry, event=event, changelog=changelog, settings=site_settings)


def import_entry(title, slug, body_markdown, summary='', is_draft=False, published_at=None):
    if not title or not slug:
        return None
    if Entry.query.filter_by(slug=slug).first() or Alias.query.filter_by(slug=slug).first():
        return None
    entry = Entry(
        slug=slug,
        title=title,
        summary=summary,
        body_markdown=body_markdown,
        body_html=render_markdown(body_markdown),
        is_draft=is_draft,
        published_at=published_at,
        created_by=current_user.id,
    )
    entry.update_sort_title()
    db.session.add(entry)
    db.session.flush()
    sync_backlinks(entry)
    db.session.add(EditLog(entry_id=entry.id, user_id=current_user.id,
                           changelog='Imported', is_import=True))
    update_fts_entry(entry, commit=False)
    return entry

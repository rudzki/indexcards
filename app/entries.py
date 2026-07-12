from flask import flash, render_template, redirect, url_for, request
from flask_login import current_user

from app import db
from app.models import Entry, Alias, Backlink, EditLog, Page, SiteSettings, make_slug, log_audit, set_published, utcnow
from app.markdown import render_markdown, extract_internal_links
from app.search import update_fts_entry

RESERVED_SLUGS = {
    'feed', 'search', 'login', 'logout', 'signup', 'subscribe',
    'confirm', 'unsubscribe', 'random', 'healthz', 'admin', 'dashboard',
    'static', 'favicon', 'site-image', 'uploads',
    'notes', 'account', 'setup', 'api',
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
        # Entries, aliases and pages share the /<slug>/ namespace, so a new
        # entry must not collide with an existing page (which would silently
        # shadow it in the resolver).
        existing_page = Page.query.filter_by(slug=slug).first()
        if existing or existing_alias or existing_page:
            flash('An entry, alias, or page with this title (or slug) already exists.', 'error')
            return render_template('admin/editor.html', entry=entry)
        entry = Entry(slug=slug, created_by=current_user.id)
        db.session.add(entry)
    else:
        if slug != entry.slug:
            conflict = Entry.query.filter(Entry.slug == slug, Entry.id != entry.id).first()
            conflict_alias = Alias.query.filter_by(slug=slug).first()
            conflict_page = Page.query.filter_by(slug=slug).first()
            if conflict or conflict_alias or conflict_page:
                flash('An entry, alias, or page with this title (or slug) already exists.', 'error')
                return render_template('admin/editor.html', entry=entry)
            entry.slug = slug

    entry.title = title
    entry.summary = summary
    entry.body_markdown = body_markdown
    entry.body_html = render_markdown(body_markdown)
    first_publish = set_published(entry, not is_draft)
    entry.is_stub = is_stub
    entry.update_sort_title()

    # An entry that already has children can't itself become a child — that
    # would create a three-level chain, and the index nesting, entry_url, and
    # breadcrumb walk all assume the two-level cap. The picker enforces this
    # client-side; enforce it here too so a crafted POST can't bypass it.
    entry_has_children = (entry.id is not None
                          and Entry.query.filter_by(parent_id=entry.id).first() is not None)
    if parent_id_raw and parent_id_raw.isdigit() and not entry_has_children:
        proposed_parent_id = int(parent_id_raw)
        parent_entry = db.session.get(Entry, proposed_parent_id)
        if (parent_entry and parent_entry.id != (entry.id or -1) and not parent_entry.parent_id
                and not _creates_cycle(entry, parent_entry)):
            entry.parent_id = parent_entry.id
        else:
            entry.parent_id = None
    else:
        entry.parent_id = None

    conflicts = alias_conflicts(entry, aliases_raw)
    if conflicts:
        joined = ', '.join(conflicts)
        flash(f'Alias "{joined}" conflicts with an existing entry, alias, or page.', 'error')
        # A new entry was added to the session but never committed; render the
        # form as "new" (not the transient object) and let the POST values
        # repopulate it. The uncommitted entry is discarded on session teardown.
        return render_template('admin/editor.html', entry=None if is_new else entry)

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

    # Announce as "new" on the first publish (whether the row is brand-new or a
    # pre-existing draft being published), not merely when the row was created —
    # otherwise unchecking Draft + Save fires as an "update" and disagrees with
    # the dedicated Publish button. is_new (row-created) still drives the audit
    # log above; only the integration signal is first-publish.
    #
    # An "updated" announcement only makes sense when the body actually changed;
    # a metadata-only or no-op re-save of a published entry shouldn't re-notify.
    # The first publish always fires (there's nothing to compare against yet).
    if not is_draft and (first_publish or content_changed):
        _fire_integrations(entry, is_new=first_publish, changelog=changelog)

    flash('Entry saved.', 'success')
    return redirect(url_for('admin.edit_entry', entry_id=entry.id))


def _creates_cycle(entry, proposed_parent):
    """Return True if proposed_parent is entry itself or one of its
    descendants — adopting it as a parent would create a cycle in the
    hierarchy.

    Belt-and-suspenders: the caller already requires the proposed parent to be
    top-level and the entry itself to be childless (the two-level cap), which
    makes a cycle structurally impossible. Kept as a guard against those
    invariants changing."""
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
        cursor = db.session.get(Entry, cursor.parent_id)
        if not cursor:
            return False
    return False


def alias_conflicts(entry, aliases_raw):
    """Return a list of alias titles whose slug collides with an existing
    entry slug, page slug, or another entry's alias. These can't be added,
    so callers should surface an error rather than silently drop them."""
    new_aliases = [a.strip() for a in aliases_raw.split(',') if a.strip()]
    existing_slugs = {a.slug for a in entry.aliases}

    conflicts = []
    for alias_title in new_aliases:
        alias_slug = make_slug(alias_title)
        if alias_slug in existing_slugs or alias_slug == entry.slug:
            continue
        conflict = Entry.query.filter_by(slug=alias_slug).first()
        conflict_alias = Alias.query.filter(
            Alias.slug == alias_slug, Alias.entry_id != entry.id
        ).first()
        conflict_page = Page.query.filter_by(slug=alias_slug).first()
        if conflict or conflict_alias or conflict_page:
            conflicts.append(alias_title)
    return conflicts


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
            entry.aliases.append(Alias(title=alias_title, slug=alias_slug))


def sync_backlinks(entry):
    Backlink.query.filter_by(source_entry_id=entry.id).delete()

    linked_slugs = extract_internal_links(entry.body_markdown)
    for slug in linked_slugs:
        target = Entry.query.filter_by(slug=slug).first()
        if target and target.id != entry.id:
            db.session.add(Backlink(source_entry_id=entry.id, target_entry_id=target.id))


def _fire_integrations(entry, is_new, changelog):
    from app.integrations import notify_slack_entry, fire_outgoing_webhook
    site_settings = db.session.get(SiteSettings, 1)
    if not site_settings:
        return
    event = 'entry.published' if is_new else 'entry.updated'
    notify_slack_entry(entry, is_new=is_new, changelog=changelog, settings=site_settings)
    if site_settings.site_visibility == 'public':
        fire_outgoing_webhook(entry, event=event, changelog=changelog, settings=site_settings)


def import_entry(title, slug, body_markdown, summary='', is_draft=False, published_at=None,
                 aliases=None, created_at=None, updated_at=None):
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
    # Preserve original timestamps on a backup/restore round-trip.
    if created_at:
        entry.created_at = created_at
    if updated_at:
        entry.updated_at = updated_at
    # A published import with no explicit date still needs published_at stamped,
    # or it shows on the index yet vanishes from feeds/digest/heatmap (which all
    # filter on published_at). Fall back to the created date to preserve ordering.
    if not is_draft and entry.published_at is None:
        entry.published_at = entry.created_at or utcnow()
    entry.update_sort_title()
    db.session.add(entry)
    db.session.flush()

    for alias_title in (aliases or []):
        alias_title = (alias_title or '').strip()
        if not alias_title:
            continue
        alias_slug = make_slug(alias_title)
        if not alias_slug or alias_slug == slug:
            continue
        if Entry.query.filter_by(slug=alias_slug).first() or Alias.query.filter_by(slug=alias_slug).first():
            continue
        entry.aliases.append(Alias(title=alias_title, slug=alias_slug))

    sync_backlinks(entry)
    db.session.add(EditLog(entry_id=entry.id, user_id=current_user.id,
                           changelog='Imported', is_import=True))
    update_fts_entry(entry, commit=False)
    return entry

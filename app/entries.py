from flask import flash, render_template, redirect, url_for, request
from flask_login import current_user

from app import db
from app.models import (Entry, Backlink, EditLog, Group, SiteSettings, RESERVED_SLUGS,
                        make_slug, log_audit, set_published, utcnow,
                        groups_feature_enabled, assignable_groups, accessible_entries_filter)
from app.markdown import render_markdown, extract_internal_links
from app.search import update_fts_entry


def save_content(entry):
    """Save a card (create or update) from the editor form. One write path for
    all cards, since the Entry/Page split collapsed into a single model."""
    title = request.form.get('title', '').strip()
    summary = request.form.get('summary', '').strip()
    body_markdown = request.form.get('body_markdown', '')
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
        flash(f'"{slug}" is a reserved path and cannot be used as a slug.', 'error')
        return render_template('admin/editor.html', entry=entry)

    is_new = entry is None
    # The last-saved body, captured before we overwrite it, so we can tell
    # whether this save actually changed content (drives the "updated"
    # integration signal below).
    old_body = entry.body_markdown if entry else ''

    # Single-table slug uniqueness now that all cards live in `entry`.
    if is_new:
        if Entry.query.filter_by(slug=slug).first():
            flash('A card with this title (or slug) already exists.', 'error')
            return render_template('admin/editor.html', entry=entry)
        entry = Entry(slug=slug, created_by=current_user.id)
        db.session.add(entry)
    else:
        if slug != entry.slug:
            if Entry.query.filter(Entry.slug == slug, Entry.id != entry.id).first():
                flash('A card with this title (or slug) already exists.', 'error')
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

    # Group assignment. Only when the feature is on. A writer may only assign
    # groups they can read (assignable_groups), unioned with the groups already on
    # the entry — so editing an entry that carries a group you're not in keeps
    # that group rather than silently stripping it, and no one can lock themselves
    # out of their own entry.
    if groups_feature_enabled(SiteSettings.get()):
        existing_ids = {g.id for g in entry.groups} if entry.id else set()
        allowed_ids = {g.id for g in assignable_groups(current_user)} | existing_ids
        submitted_ids = set(request.form.getlist('group_ids', type=int))
        chosen_ids = submitted_ids & allowed_ids
        entry.groups = Group.query.filter(Group.id.in_(chosen_ids)).all() if chosen_ids else []

    db.session.flush()

    sync_backlinks(entry)

    content_changed = is_new or (old_body != body_markdown)
    db.session.add(EditLog(
        entry_id=entry.id,
        user_id=current_user.id,
        changelog=changelog,
    ))

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
    #
    # Stubs never notify either: a stub is an explicit "still being written"
    # placeholder (the same category as a draft for announcement purposes), so
    # it shouldn't fire a "new entry" webhook/Slack. The announcement lands later
    # when the stub is fleshed out and saved un-stubbed (as an "updated" event,
    # since published_at was already stamped when it first went public).
    if not is_draft and not is_stub and (first_publish or content_changed):
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


def sync_backlinks(entry):
    Backlink.query.filter_by(source_entry_id=entry.id).delete()

    linked_slugs = extract_internal_links(entry.body_markdown)
    for slug in linked_slugs:
        target = Entry.query.filter_by(slug=slug).first()
        if target and target.id != entry.id:
            db.session.add(Backlink(source_entry_id=entry.id, target_entry_id=target.id))


def entry_backlinks(entry, include_drafts=False, user=None):
    """Cards that link to `entry`. Public views exclude drafts; the admin
    preview passes include_drafts=True so a draft link target still shows as a
    live backlink (its intentional difference from the public view). When `user`
    is given, grouped source cards the user can't read are excluded so a gated
    entry never leaks through a backlink."""
    q = (Entry.query
         .join(Entry.outgoing_links)
         .filter(Entry.outgoing_links.any(target_entry_id=entry.id)))
    if not include_drafts:
        q = q.filter(Entry.is_draft == False)  # noqa: E712
    if user is not None:
        q = q.filter(accessible_entries_filter(user))
    return q.all()


def last_editor_of(entry):
    """The user who last edited `entry`, ignoring import log rows; None if the
    only history is an import (or there's none)."""
    log = (EditLog.query
           .filter_by(entry_id=entry.id)
           .filter(EditLog.is_import == False)  # noqa: E712
           .order_by(EditLog.edited_at.desc())
           .first())
    return log.user if log else None


def _fire_integrations(entry, is_new, changelog):
    from app.integrations import notify_slack_entry, fire_outgoing_webhook
    site_settings = SiteSettings.get()
    if not site_settings:
        return
    # A grouped (restricted) entry is private — never broadcast it to Slack or an
    # outgoing webhook, which are public announcement channels.
    if entry.groups:
        return
    event = 'entry.published' if is_new else 'entry.updated'
    notify_slack_entry(entry, is_new=is_new, changelog=changelog, settings=site_settings)
    if site_settings.site_visibility == 'public':
        fire_outgoing_webhook(entry, event=event, changelog=changelog, settings=site_settings)


def import_entry(title, slug, body_markdown, summary='', is_draft=False, published_at=None,
                 created_at=None, updated_at=None):
    if not title or not slug:
        return None
    if Entry.query.filter_by(slug=slug).first():
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

    sync_backlinks(entry)
    db.session.add(EditLog(entry_id=entry.id, user_id=current_user.id,
                           changelog='Imported', is_import=True))
    update_fts_entry(entry, commit=False)
    return entry

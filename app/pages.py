from flask import flash, render_template, redirect, url_for, request
from flask_login import current_user

from app import db
from app.entries import RESERVED_SLUGS
from app.models import Page, PageRevision, Entry, Alias, make_slug, log_audit, utcnow
from app.markdown import render_markdown


def save_page(page):
    title = request.form.get('title', '').strip()
    summary = request.form.get('summary', '').strip()
    body_markdown = request.form.get('body_markdown', '')
    changelog = request.form.get('changelog', '').strip() or None
    is_draft = 'is_draft' in request.form
    is_stub = 'is_stub' in request.form
    show_in_nav = 'show_in_nav' in request.form
    nav_position_raw = request.form.get('nav_position', '').strip()
    nav_position = int(nav_position_raw) if nav_position_raw.isdigit() else None

    if not title:
        flash('Title is required.', 'error')
        return render_template('admin/page_editor.html', page=page)

    slug_input = request.form.get('slug', '').strip()
    slug = make_slug(slug_input) if slug_input else make_slug(title)

    if slug in RESERVED_SLUGS:
        flash(f'"{slug}" is a reserved path and cannot be used as a page slug.', 'error')
        return render_template('admin/page_editor.html', page=page)

    is_new = page is None

    # Pages share the /<slug>/ namespace with entries and aliases; an entry
    # slug wins in the resolver, so a page created under one would be
    # unreachable. Reject the collision up front.
    def _entry_conflict():
        return (Entry.query.filter_by(slug=slug).first()
                or Alias.query.filter_by(slug=slug).first())

    if is_new:
        if Page.query.filter_by(slug=slug).first() or _entry_conflict():
            flash('A page, entry, or alias with this slug already exists.', 'error')
            return render_template('admin/page_editor.html', page=page)
        page = Page(slug=slug, created_by=current_user.id)
        db.session.add(page)
    else:
        if slug != page.slug:
            if Page.query.filter(Page.slug == slug, Page.id != page.id).first() or _entry_conflict():
                flash('A page, entry, or alias with this slug already exists.', 'error')
                return render_template('admin/page_editor.html', page=page)
            page.slug = slug

    page.title = title
    page.summary = summary
    page.body_markdown = body_markdown
    page.body_html = render_markdown(body_markdown)
    page.is_draft = is_draft
    page.is_stub = is_stub
    page.show_in_nav = show_in_nav
    page.nav_position = nav_position if show_in_nav else None
    page.update_sort_title()

    if not is_draft and not page.published_at:
        page.published_at = utcnow()

    db.session.flush()

    last_rev = (PageRevision.query
                .filter_by(page_id=page.id)
                .order_by(PageRevision.edited_at.desc())
                .first())
    content_changed = is_new or (last_rev is None) or (last_rev.body_snapshot != body_markdown)
    db.session.add(PageRevision(
        page_id=page.id,
        user_id=current_user.id,
        body_snapshot=body_markdown if content_changed else None,
        changelog=changelog,
    ))

    # Keep at most 50 snapshots per page
    snap_count = (PageRevision.query
                  .filter(PageRevision.page_id == page.id,
                          PageRevision.body_snapshot.isnot(None))
                  .count())
    if snap_count > 50:
        oldest = (PageRevision.query
                  .filter(PageRevision.page_id == page.id,
                          PageRevision.body_snapshot.isnot(None))
                  .order_by(PageRevision.edited_at.asc())
                  .limit(snap_count - 50)
                  .all())
        for old in oldest:
            old.body_snapshot = None

    db.session.commit()

    action = 'page_created' if is_new else 'page_edited'
    log_audit(action, detail=page.title, user_id=current_user.id)
    flash('Page saved.', 'success')
    return redirect(url_for('admin.edit_page', page_id=page.id))

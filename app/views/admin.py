from datetime import datetime, timezone
from functools import wraps

import html as html_lib
import io
import json
import os
import secrets
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, send_file, current_app
from flask_login import login_required, current_user
from markupsafe import Markup

from app import db
from app.models import Entry, Alias, EditLog, Backlink, User, Registration, SiteSettings, AuditLog, Page, PageRevision, EditLock, make_slug, log_audit
from app.markdown import render_markdown, extract_internal_links
from app.search import update_fts_entry, delete_fts_entry
from app.mail import send_email, render_email

admin_bp = Blueprint('admin', __name__, url_prefix='/dashboard')


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def writer_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.can_write:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def editor_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not (current_user.is_admin or current_user.is_editor):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _compute_diff(old_text, new_text):
    import difflib
    old_lines = (old_text or '').splitlines()
    new_lines = (new_text or '').splitlines()
    result = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_lines, new_lines).get_opcodes():
        if op == 'equal':
            for line in old_lines[i1:i2]:
                result.append(('=', line))
        elif op == 'insert':
            for line in new_lines[j1:j2]:
                result.append(('+', line))
        elif op == 'delete':
            for line in old_lines[i1:i2]:
                result.append(('-', line))
        elif op == 'replace':
            for line in old_lines[i1:i2]:
                result.append(('-', line))
            for line in new_lines[j1:j2]:
                result.append(('+', line))
    return result


RESERVED_SLUGS = {
    'feed', 'search', 'login', 'logout', 'signup', 'subscribe',
    'confirm', 'unsubscribe', 'random', 'healthz', 'admin', 'dashboard',
    'static', 'favicon', 'site-image', 'uploads',
}


_LOCK_TTL = 60


def _acquire_lock(content_type, content_id):
    """Acquire or refresh a lock. Returns the display name of the blocking user, or None on success."""
    from datetime import timedelta
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires = now + timedelta(seconds=_LOCK_TTL)

    EditLock.query.filter(EditLock.expires_at < now).delete()

    existing = EditLock.query.filter_by(content_type=content_type, content_id=content_id).first()
    if existing and existing.user_id != current_user.id:
        exp = existing.expires_at.replace(tzinfo=None) if existing.expires_at.tzinfo else existing.expires_at
        if exp > now:
            return existing.user.display_name if existing.user else 'Someone'
        existing.user_id = current_user.id
        existing.expires_at = expires
    elif existing:
        existing.expires_at = expires
    else:
        db.session.add(EditLock(content_type=content_type, content_id=content_id,
                                user_id=current_user.id, expires_at=expires))
    db.session.commit()
    return None


def _active_locks(content_type):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    locks = EditLock.query.filter_by(content_type=content_type).filter(EditLock.expires_at > now).all()
    return {lock.content_id: lock.user.display_name if lock.user else 'Someone' for lock in locks}


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
    locked_entries = _active_locks('entry')
    return render_template('admin/dashboard.html', entries=pagination.items,
                           pagination=pagination, sort=sort, order=order,
                           locked_entries=locked_entries)


@admin_bp.route('/entry/new/', methods=['GET', 'POST'])
@writer_required
def new_entry():
    if request.method == 'POST':
        return _save_entry(None)
    prefill_title = request.args.get('title', '').replace('-', ' ').strip().title()
    return render_template('editor.html', entry=None, prefill_title=prefill_title)


@admin_bp.route('/entry/<int:entry_id>/edit/', methods=['GET', 'POST'])
@writer_required
def edit_entry(entry_id):
    entry = Entry.query.get_or_404(entry_id)
    if not current_user.can_modify(entry):
        abort(403)
    if request.method == 'POST':
        return _save_entry(entry)
    blocker = _acquire_lock('entry', entry_id)
    if blocker:
        flash(f'"{entry.title}" is currently being edited by {blocker}.', 'warning')
        return redirect(url_for('admin.dashboard'))
    return render_template('editor.html', entry=entry, lock_type='entry', lock_id=entry_id)


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


def _save_entry(entry):
    title = request.form.get('title', '').strip()
    summary = request.form.get('summary', '').strip()
    body_markdown = request.form.get('body_markdown', '')
    aliases_raw = request.form.get('aliases', '').strip()
    changelog = request.form.get('changelog', '').strip() or None
    is_draft = 'is_draft' in request.form
    parent_id_raw = request.form.get('parent_id', '').strip()

    if not title:
        flash('Title is required.', 'error')
        return render_template('editor.html', entry=entry)

    slug_input = request.form.get('slug', '').strip()
    slug = make_slug(slug_input) if slug_input else make_slug(title)

    if slug in RESERVED_SLUGS:
        flash(f'"{slug}" is a reserved path and cannot be used as an entry slug.', 'error')
        return render_template('editor.html', entry=entry)

    is_new = entry is None

    if is_new:
        existing = Entry.query.filter_by(slug=slug).first()
        existing_alias = Alias.query.filter_by(slug=slug).first()
        if existing or existing_alias:
            flash('An entry with this title (or slug) already exists.', 'error')
            return render_template('editor.html', entry=entry)
        entry = Entry(slug=slug, created_by=current_user.id)
        db.session.add(entry)
    else:
        if slug != entry.slug:
            conflict = Entry.query.filter(Entry.slug == slug, Entry.id != entry.id).first()
            conflict_alias = Alias.query.filter_by(slug=slug).first()
            if conflict or conflict_alias:
                flash('An entry with this title (or slug) already exists.', 'error')
                return render_template('editor.html', entry=entry)
            entry.slug = slug

    entry.title = title
    entry.summary = summary
    old_body = entry.body_markdown
    entry.body_markdown = body_markdown
    entry.body_html = render_markdown(body_markdown)
    entry.is_draft = is_draft
    entry.update_sort_title()

    if not is_draft and not entry.published_at:
        entry.published_at = datetime.now(timezone.utc)

    if parent_id_raw and parent_id_raw.isdigit():
        proposed_parent_id = int(parent_id_raw)
        parent_entry = Entry.query.get(proposed_parent_id)
        if parent_entry and parent_entry.id != (entry.id or -1):
            entry.parent_id = parent_entry.id
        else:
            entry.parent_id = None
    else:
        entry.parent_id = None

    _sync_aliases(entry, aliases_raw)

    db.session.flush()

    _sync_backlinks(entry)

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


def _sync_aliases(entry, aliases_raw):
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


def _sync_backlinks(entry):
    Backlink.query.filter_by(source_entry_id=entry.id).delete()

    linked_slugs = extract_internal_links(entry.body_markdown)
    for slug in linked_slugs:
        target = Entry.query.filter_by(slug=slug).first()
        if target and target.id != entry.id:
            db.session.add(Backlink(source_entry_id=entry.id, target_entry_id=target.id))


@admin_bp.route('/settings/', methods=['GET', 'POST'])
@admin_required
def settings():
    site_settings = SiteSettings.query.get(1)
    if request.method == 'POST':
        site_settings.site_title = request.form.get('site_title', '').strip()
        site_settings.footer_text = request.form.get('footer_text', '').strip()

        site_settings.search_enabled = 'search_enabled' in request.form
        site_settings.subscribe_enabled = 'subscribe_enabled' in request.form

        site_settings.multiuser_enabled = 'multiuser_enabled' in request.form
        site_settings.registration_method = request.form.get('registration_method', 'invite')
        site_settings.registration_domain = request.form.get('registration_domain', '').strip()
        site_settings.default_role = request.form.get('default_role', 'viewer')
        site_settings.site_visibility = request.form.get('site_visibility', 'public')

        site_settings.smtp_host = request.form.get('smtp_host', '').strip() or None
        port = request.form.get('smtp_port', '').strip()
        site_settings.smtp_port = int(port) if port else None
        site_settings.smtp_username = request.form.get('smtp_username', '').strip() or None
        site_settings.smtp_password = request.form.get('smtp_password', '').strip() or None
        site_settings.smtp_use_tls = 'smtp_use_tls' in request.form
        site_settings.smtp_from_address = request.form.get('smtp_from_address', '').strip() or None

        site_settings.show_authors = 'show_authors' in request.form
        site_settings.show_history = 'show_history' in request.form
        site_settings.alpha_jump_enabled = 'alpha_jump_enabled' in request.form
        site_settings.feeds_enabled = 'feeds_enabled' in request.form
        site_settings.site_icon = request.form.get('site_icon', '').strip()

        valid_themes = {'default', 'forest', 'sepia', 'midnight', 'stone'}
        raw_theme = request.form.get('site_theme', 'default').strip()
        site_settings.site_theme = raw_theme if raw_theme in valid_themes else 'default'

        site_settings.digest_include_edits = 'digest_include_edits' in request.form
        day = request.form.get('digest_day', '0')
        site_settings.digest_day = int(day) if day else 0

        site_settings.custom_css = request.form.get('custom_css', '')
        site_settings.custom_head_html = request.form.get('custom_head_html', '')
        site_settings.custom_footer_html = request.form.get('custom_footer_html', '')

        db.session.commit()
        flash('Settings saved.', 'success')
        return redirect(url_for('admin.settings'))

    from app.icons import ICONS
    icon_names = sorted(ICONS.keys())
    themes = [
        {'id': 'default',  'name': 'Default',  'dark_bg': '#0d1117', 'surface_bg': '#161b22', 'light_bg': '#ffffff', 'brand': '#9aa7b4'},
        {'id': 'forest',   'name': 'Forest',   'dark_bg': '#0c1410', 'surface_bg': '#141f18', 'light_bg': '#f4f7f4', 'brand': '#4caf7d'},
        {'id': 'sepia',    'name': 'Sepia',    'dark_bg': '#1a1410', 'surface_bg': '#231c17', 'light_bg': '#f8f4ed', 'brand': '#c0956a'},
        {'id': 'midnight', 'name': 'Midnight', 'dark_bg': '#080c16', 'surface_bg': '#0e1424', 'light_bg': '#f0f4ff', 'brand': '#6b8fff'},
        {'id': 'stone',    'name': 'Stone',    'dark_bg': '#111110', 'surface_bg': '#1a1917', 'light_bg': '#f9f8f6', 'brand': '#b0a890'},
    ]
    return render_template('settings.html', settings=site_settings, icon_names=icon_names, themes=themes)


ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}


@admin_bp.route('/settings/upload-image/', methods=['POST'])
@admin_required
def upload_site_image():
    f = request.files.get('site_image')
    if not f or not f.filename:
        flash('No file selected.', 'error')
        return redirect(url_for('admin.settings'))

    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        flash('Only PNG, JPEG, and WebP images are allowed.', 'error')
        return redirect(url_for('admin.settings'))

    filename = f'site-image.{ext}'
    upload_dir = current_app.config['UPLOAD_DIR']

    site_settings = SiteSettings.query.get(1)
    if site_settings.site_image:
        old_path = os.path.join(upload_dir, site_settings.site_image)
        try:
            os.remove(old_path)
        except FileNotFoundError:
            pass

    f.save(os.path.join(upload_dir, filename))
    site_settings.site_image = filename
    db.session.commit()
    flash('Site image updated.', 'success')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/settings/remove-image/', methods=['POST'])
@admin_required
def remove_site_image():
    site_settings = SiteSettings.query.get(1)
    if site_settings.site_image:
        path = os.path.join(current_app.config['UPLOAD_DIR'], site_settings.site_image)
        if os.path.exists(path):
            os.remove(path)
        site_settings.site_image = ''
        db.session.commit()
    flash('Site image removed.', 'success')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/users/', methods=['GET', 'POST'])
@admin_required
def users():
    site_settings = SiteSettings.query.get(1)
    if not site_settings or not site_settings.multiuser_enabled:
        return redirect(url_for('admin.settings'))

    if request.method == 'POST' and site_settings.registration_method == 'invite':
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('Email is required.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('A user with this email already exists.', 'error')
        elif Registration.query.filter_by(email=email, accepted=False).first():
            flash('An invitation for this email is already pending.', 'error')
        else:
            invited_role = request.form.get('role', '').strip()
            if invited_role not in ('viewer', 'author', 'editor', 'admin'):
                invited_role = None
            reg = Registration(email=email, invited_by=current_user.id, role=invited_role)
            db.session.add(reg)
            db.session.commit()
            log_audit('invite_sent', detail=email, user_id=current_user.id)

            signup_url = url_for('auth.signup_token', token=reg.token, _external=True)
            site_title = site_settings.site_title or 'Index Cards'
            text, html = render_email('invite', site_title=site_title, signup_url=signup_url,
                                      invited_by=current_user.display_name)
            if send_email(to=email, subject=f'You\'ve been invited to {site_title}',
                          body_text=text, body_html=html):
                flash(f'Invite sent to {email}.', 'success')
            else:
                flash(f'Invite created but the email to {email} could not be sent.', 'error')

        return redirect(url_for('admin.users'))

    sort = request.args.get('sort', 'joined')
    order = request.args.get('order', 'desc')
    sort_col = {'name': User.display_name, 'email': User.email, 'role': User.role, 'joined': User.created_at}.get(sort, User.created_at)
    all_users = User.query.order_by(sort_col.asc() if order == 'asc' else sort_col.desc()).all()
    pending = Registration.query.filter_by(accepted=False).order_by(Registration.created_at.desc()).all()
    admin_count = User.query.filter_by(role='admin').count()
    return render_template('admin/users.html', users=all_users, pending=pending,
                           settings=site_settings, admin_count=admin_count, sort=sort, order=order)


@admin_bp.route('/users/<int:user_id>/role/', methods=['POST'])
@admin_required
def change_role(user_id):
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role', '')
    if new_role not in ('viewer', 'author', 'editor', 'admin'):
        flash('Invalid role.', 'error')
        return redirect(url_for('admin.users'))

    if user.id == current_user.id:
        flash('You cannot change your own role.', 'error')
        return redirect(url_for('admin.users'))

    if user.is_admin and User.query.filter_by(role='admin').count() <= 1:
        flash('Cannot demote the last admin.', 'error')
        return redirect(url_for('admin.users'))

    old_role = user.role
    user.role = new_role
    db.session.commit()
    log_audit('role_changed', detail=f'{user.display_name}: {old_role} -> {new_role}', user_id=current_user.id)
    flash(f'{user.display_name} is now {new_role}.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/delete/', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin.users'))

    if user.is_admin and User.query.filter_by(role='admin').count() <= 1:
        flash('Cannot delete the last admin.', 'error')
        return redirect(url_for('admin.users'))

    user_name = user.display_name
    EditLog.query.filter_by(user_id=user.id).update({'user_id': None})
    Entry.query.filter_by(created_by=user.id).update({'created_by': None})
    Registration.query.filter_by(invited_by=user.id).update({'invited_by': None})
    AuditLog.query.filter_by(user_id=user.id).update({'user_id': None})
    db.session.delete(user)
    db.session.commit()
    log_audit('user_deleted', detail=user_name, user_id=current_user.id)
    flash(f'{user_name} has been removed.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/registration/<int:reg_id>/resend/', methods=['POST'])
@admin_required
def resend_invite(reg_id):
    reg = Registration.query.get_or_404(reg_id)
    if reg.accepted:
        flash('This registration has already been accepted.', 'info')
        return redirect(url_for('admin.users'))

    signup_url = url_for('auth.signup_token', token=reg.token, _external=True)
    site_settings = SiteSettings.query.get(1)
    site_title = (site_settings.site_title if site_settings else 'Index Cards') or 'Index Cards'
    inviter = User.query.get(reg.invited_by) if reg.invited_by else None
    invited_by_name = inviter.display_name if inviter else site_title
    text, html = render_email('invite', site_title=site_title, signup_url=signup_url,
                              invited_by=invited_by_name)
    if send_email(to=reg.email, subject=f'You\'ve been invited to {site_title}',
                  body_text=text, body_html=html):
        flash(f'Invite resent to {reg.email}.', 'success')
    else:
        flash(f'Could not send email to {reg.email}.', 'error')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/registration/<int:reg_id>/revoke/', methods=['POST'])
@admin_required
def revoke_invite(reg_id):
    reg = Registration.query.get_or_404(reg_id)
    db.session.delete(reg)
    db.session.commit()
    flash(f'Invitation for {reg.email} revoked.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/entries/<int:entry_id>/publish/', methods=['POST'])
@login_required
def publish_entry(entry_id):
    entry = Entry.query.get_or_404(entry_id)
    if not current_user.can_modify(entry):
        abort(403)
    from datetime import datetime, timezone
    entry.is_draft = False
    if not entry.published_at:
        entry.published_at = datetime.now(timezone.utc)
    db.session.commit()
    flash(f'"{entry.title}" published.', 'success')
    return redirect(url_for('main.entry_page', slug=entry.slug))


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
                     .order_by(EditLog.edited_at.desc())
                     .first())
    last_editor = last_edit_log.user if last_edit_log else None
    return render_template('entry.html', entry=entry, body_html=Markup(body_html),
                           backlinks=backlinks, toc=toc, is_preview=True, last_editor=last_editor,
                           ancestors=[], children=[], prev_entry=None, next_entry=None)


@admin_bp.route('/export/markdown/')
@admin_required
def export_markdown():
    entries = Entry.query.filter_by(is_draft=False).all()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for entry in entries:
            def _yaml_str(s):
                return (s or '').replace('\\', '\\\\').replace('"', '\\"')
            frontmatter = f'---\ntitle: "{_yaml_str(entry.title)}"\nsummary: "{_yaml_str(entry.summary)}"\nslug: {entry.slug}\n'
            if entry.aliases:
                aliases = ', '.join(a.title for a in entry.aliases)
                frontmatter += f'aliases: [{aliases}]\n'
            if entry.published_at:
                frontmatter += f'published: {entry.published_at.isoformat()}\n'
            frontmatter += '---\n\n'
            zf.writestr(f'{entry.slug}.md', frontmatter + (entry.body_markdown or ''))
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name='entries.zip')


@admin_bp.route('/export/json/')
@admin_required
def export_json():
    entries = Entry.query.all()
    data = []
    for entry in entries:
        data.append({
            'title': entry.title,
            'slug': entry.slug,
            'summary': entry.summary,
            'body_markdown': entry.body_markdown,
            'is_draft': entry.is_draft,
            'aliases': [a.title for a in entry.aliases],
            'published_at': entry.published_at.isoformat() if entry.published_at else None,
            'created_at': entry.created_at.isoformat() if entry.created_at else None,
            'updated_at': entry.updated_at.isoformat() if entry.updated_at else None,
        })
    buf = io.BytesIO()
    buf.write(json.dumps(data, indent=2, ensure_ascii=False).encode('utf-8'))
    buf.seek(0)
    return send_file(buf, mimetype='application/json', as_attachment=True,
                     download_name='entries.json')


class _HTMLToMarkdown(HTMLParser):
    def __init__(self):
        super().__init__()
        self._out_stack = [[]]
        self._stack = []
        self._li_count = []
        self._href = None
        self._pre = False

    @property
    def _out(self):
        return self._out_stack[-1]

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self._stack.append(tag)
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            level = int(tag[1])
            self._out.append('\n\n' + '#' * level + ' ')
        elif tag == 'p':
            self._out.append('\n\n')
        elif tag == 'br':
            self._out.append('\n')
        elif tag == 'strong' or tag == 'b':
            self._out.append('**')
        elif tag == 'em' or tag == 'i':
            self._out.append('*')
        elif tag == 'cite' or tag == 'q':
            self._out.append(f'<{tag}>')
        elif tag == 'abbr':
            title = attrs.get('title', '')
            if title:
                self._out.append(f'<abbr title="{html_lib.escape(title, quote=True)}">')
            else:
                self._out.append('<abbr>')
        elif tag == 'a':
            self._href = attrs.get('href', '')
            self._out.append('[')
        elif tag == 'img':
            alt = attrs.get('alt', '')
            src = attrs.get('src', '')
            self._out.append(f'![{alt}]({src})')
        elif tag == 'ul':
            self._out.append('\n')
            self._li_count.append(None)
        elif tag == 'ol':
            self._out.append('\n')
            self._li_count.append(0)
        elif tag == 'li':
            if self._li_count and self._li_count[-1] is not None:
                self._li_count[-1] += 1
                self._out.append(f'{self._li_count[-1]}. ')
            else:
                self._out.append('- ')
        elif tag == 'blockquote':
            self._out.append('\n\n')
            self._out_stack.append([])
        elif tag == 'pre':
            self._pre = True
            self._out.append('\n\n```\n')
        elif tag == 'code' and not self._pre:
            self._out.append('`')
        elif tag == 'hr':
            self._out.append('\n\n---\n\n')

    def handle_endtag(self, tag):
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._out.append('\n')
        elif tag in ('strong', 'b'):
            self._out.append('**')
        elif tag in ('em', 'i'):
            self._out.append('*')
        elif tag in ('cite', 'q', 'abbr'):
            self._out.append(f'</{tag}>')
        elif tag == 'a':
            self._out.append(f']({self._href})')
            self._href = None
        elif tag in ('ul', 'ol'):
            if self._li_count:
                self._li_count.pop()
            self._out.append('\n')
        elif tag == 'li':
            self._out.append('\n')
        elif tag == 'blockquote':
            import re
            buf = self._out_stack.pop()
            text = re.sub(r'\n{3,}', '\n\n', ''.join(buf)).strip('\n')
            quoted = '\n'.join(('> ' + line if line else '>') for line in text.split('\n'))
            self._out.append('\n\n' + quoted + '\n\n')
        elif tag == 'pre':
            self._pre = False
            self._out.append('\n```\n')
        elif tag == 'code' and not self._pre:
            self._out.append('`')

    def handle_data(self, data):
        self._out.append(data)

    def get_markdown(self):
        import re
        text = ''.join(self._out).strip()
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text


def _html_to_markdown(html):
    parser = _HTMLToMarkdown()
    parser.feed(html)
    return parser.get_markdown()


def _import_entry(title, slug, body_markdown, summary='', is_draft=False, published_at=None):
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
    _sync_backlinks(entry)
    db.session.add(EditLog(entry_id=entry.id, user_id=current_user.id, changelog='Imported'))
    update_fts_entry(entry)
    return entry


@admin_bp.route('/import/json/', methods=['POST'])
@admin_required
def import_json():
    f = request.files.get('file')
    if not f:
        flash('No file uploaded.', 'error')
        return redirect(url_for('admin.settings'))
    try:
        data = json.loads(f.read().decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        flash('Invalid JSON file.', 'error')
        return redirect(url_for('admin.settings'))

    if not isinstance(data, list):
        flash('JSON must be an array of entry objects.', 'error')
        return redirect(url_for('admin.settings'))

    count = 0
    try:
        for item in data:
            title = (item.get('title') or '').strip()
            if not title:
                continue
            slug = item.get('slug') or make_slug(title)
            body_markdown = item.get('body_markdown', '')
            summary = item.get('summary', '')
            is_draft = item.get('is_draft', False)
            published_at = None
            if item.get('published_at'):
                try:
                    published_at = datetime.fromisoformat(item['published_at'])
                except ValueError:
                    pass
            if _import_entry(title, slug, body_markdown, summary, is_draft, published_at):
                count += 1
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Import failed partway through — no entries were saved.', 'error')
        return redirect(url_for('admin.settings'))

    log_audit('import_json', detail=f'{count} entries imported', user_id=current_user.id)
    flash(f'{count} entries imported.', 'success')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/import/wordpress/', methods=['POST'])
@admin_required
def import_wordpress():
    f = request.files.get('file')
    if not f:
        flash('No file uploaded.', 'error')
        return redirect(url_for('admin.settings'))
    try:
        tree = ET.parse(f)
    except ET.ParseError:
        flash('Invalid XML file.', 'error')
        return redirect(url_for('admin.settings'))

    root = tree.getroot()
    ns = {
        'wp': 'http://wordpress.org/export/1.2/',
        'content': 'http://purl.org/rss/1.0/modules/content/',
        'dc': 'http://purl.org/dc/elements/1.1/',
    }
    alt_ns = {
        'wp': 'http://wordpress.org/export/1.1/',
    }

    channel = root.find('channel')
    if channel is None:
        flash('Invalid WordPress export file.', 'error')
        return redirect(url_for('admin.settings'))

    count = 0
    for item in channel.findall('item'):
        post_type = item.find('wp:post_type', ns)
        if post_type is None:
            post_type = item.find('wp:post_type', alt_ns)
        if post_type is not None and post_type.text not in ('post', 'page'):
            continue

        title_el = item.find('title')
        title = (title_el.text or '').strip() if title_el is not None else ''
        if not title:
            continue

        slug_el = item.find('wp:post_name', ns)
        if slug_el is None:
            slug_el = item.find('wp:post_name', alt_ns)
        slug = (slug_el.text or '').strip() if slug_el is not None else ''
        if not slug:
            slug = make_slug(title)

        content_el = item.find('content:encoded', ns)
        html_content = (content_el.text or '') if content_el is not None else ''
        body_markdown = _html_to_markdown(html_content) if html_content else ''

        status_el = item.find('wp:status', ns)
        if status_el is None:
            status_el = item.find('wp:status', alt_ns)
        status = (status_el.text or '') if status_el is not None else ''
        is_draft = status != 'publish'

        published_at = None
        date_el = item.find('wp:post_date', ns)
        if date_el is None:
            date_el = item.find('wp:post_date', alt_ns)
        if date_el is not None and date_el.text:
            try:
                published_at = datetime.strptime(date_el.text, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        if _import_entry(title, slug, body_markdown, is_draft=is_draft, published_at=published_at):
            count += 1

    db.session.commit()
    log_audit('import_wordpress', detail=f'{count} entries imported', user_id=current_user.id)
    flash(f'{count} entries imported from WordPress.', 'success')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/test-data/add/', methods=['POST'])
@admin_required
def add_test_data():
    from app.testdata import seed_test_data
    _, message = seed_test_data(current_user.id)
    flash(message, 'success')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/test-data/remove/', methods=['POST'])
@admin_required
def remove_test_data():
    from app.testdata import clear_test_data
    _, message = clear_test_data()
    flash(message, 'success')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/subscribers/')
@admin_required
def subscribers():
    all_subscribers = User.query.filter_by(subscribed=True).order_by(User.created_at.desc()).all()
    return render_template('subscribers.html', subscribers=all_subscribers)


@admin_bp.route('/logs/')
@admin_required
def logs():
    sort = request.args.get('sort', 'time')
    order = request.args.get('order', 'desc')
    q = AuditLog.query
    if sort == 'action':
        col = AuditLog.action
    elif sort == 'user':
        q = q.outerjoin(User, AuditLog.user_id == User.id)
        col = User.email
    else:
        col = AuditLog.created_at
    entries = q.order_by(col.asc() if order == 'asc' else col.desc()).limit(200).all()
    return render_template('admin/logs.html', logs=entries, sort=sort, order=order)


@admin_bp.route('/pages/')
@editor_required
def pages_list():
    pages = Page.query.order_by(Page.sort_title).all()
    locked_pages = _active_locks('page')
    return render_template('admin/pages.html', pages=pages, locked_pages=locked_pages)


@admin_bp.route('/pages/new/', methods=['GET', 'POST'])
@editor_required
def new_page():
    if request.method == 'POST':
        return _save_page(None)
    return render_template('admin/page_editor.html', page=None)


@admin_bp.route('/pages/<int:page_id>/edit/', methods=['GET', 'POST'])
@editor_required
def edit_page(page_id):
    page = Page.query.get_or_404(page_id)
    if request.method == 'POST':
        return _save_page(page)
    blocker = _acquire_lock('page', page_id)
    if blocker:
        flash(f'"{page.title}" is currently being edited by {blocker}.', 'warning')
        return redirect(url_for('admin.pages_list'))
    return render_template('admin/page_editor.html', page=page, lock_type='page', lock_id=page_id)


@admin_bp.route('/pages/<int:page_id>/delete/', methods=['POST'])
@admin_required
def delete_page(page_id):
    page = Page.query.get_or_404(page_id)
    page_title = page.title
    db.session.delete(page)
    db.session.commit()
    log_audit('page_deleted', detail=page_title, user_id=current_user.id)
    flash('Page deleted.', 'success')
    return redirect(url_for('admin.pages_list'))


@admin_bp.route('/pages/<int:page_id>/publish/', methods=['POST'])
@editor_required
def publish_page(page_id):
    page = Page.query.get_or_404(page_id)
    page.is_draft = not page.is_draft
    if not page.is_draft and not page.published_at:
        page.published_at = datetime.now(timezone.utc)
    db.session.commit()
    status = 'unpublished' if page.is_draft else 'published'
    flash(f'"{page.title}" {status}.', 'success')
    return redirect(url_for('admin.edit_page', page_id=page.id))


def _save_page(page):
    title = request.form.get('title', '').strip()
    summary = request.form.get('summary', '').strip()
    body_markdown = request.form.get('body_markdown', '')
    changelog = request.form.get('changelog', '').strip() or None
    is_draft = 'is_draft' in request.form
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

    if is_new:
        if Page.query.filter_by(slug=slug).first():
            flash('A page with this slug already exists.', 'error')
            return render_template('admin/page_editor.html', page=page)
        page = Page(slug=slug, created_by=current_user.id)
        db.session.add(page)
    else:
        if slug != page.slug:
            if Page.query.filter(Page.slug == slug, Page.id != page.id).first():
                flash('A page with this slug already exists.', 'error')
                return render_template('admin/page_editor.html', page=page)
            page.slug = slug

    page.title = title
    page.summary = summary
    page.body_markdown = body_markdown
    page.body_html = render_markdown(body_markdown)
    page.is_draft = is_draft
    page.show_in_nav = show_in_nav
    page.nav_position = nav_position if show_in_nav else None
    page.update_sort_title()

    if not is_draft and not page.published_at:
        page.published_at = datetime.now(timezone.utc)

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
    revisions = []
    for i, log in enumerate(logs):
        prev_snapshot = logs[i + 1].body_snapshot if i + 1 < len(logs) else ''
        curr_snapshot = log.body_snapshot or ''
        revisions.append({
            'id': log.id,
            'snapshot': curr_snapshot,
            'changelog': log.changelog,
            'edited_at': log.edited_at,
            'user': log.user,
            'diff_lines': _compute_diff(prev_snapshot or '', curr_snapshot),
            'char_delta': len(curr_snapshot) - len(prev_snapshot or ''),
        })
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
    _sync_backlinks(entry)
    db.session.commit()
    update_fts_entry(entry)
    flash('Entry restored to selected revision.', 'success')
    return redirect(url_for('admin.edit_entry', entry_id=entry_id))


@admin_bp.route('/pages/<int:page_id>/history/')
@editor_required
def page_history(page_id):
    page = Page.query.get_or_404(page_id)
    revs = (PageRevision.query
            .filter_by(page_id=page_id)
            .order_by(PageRevision.edited_at.desc())
            .all())
    revisions = []
    for i, rev in enumerate(revs):
        prev_snapshot = revs[i + 1].body_snapshot if i + 1 < len(revs) else ''
        curr_snapshot = rev.body_snapshot or ''
        revisions.append({
            'id': rev.id,
            'snapshot': curr_snapshot,
            'changelog': rev.changelog,
            'edited_at': rev.edited_at,
            'user': rev.user,
            'diff_lines': _compute_diff(prev_snapshot or '', curr_snapshot),
            'char_delta': len(curr_snapshot) - len(prev_snapshot or ''),
        })
    return render_template('admin/page_history.html', page=page, revisions=revisions)


@admin_bp.route('/pages/<int:page_id>/history/<int:rev_id>/restore/', methods=['POST'])
@editor_required
def restore_page_revision(page_id, rev_id):
    page = Page.query.get_or_404(page_id)
    rev = PageRevision.query.filter_by(id=rev_id, page_id=page_id).first_or_404()
    if not rev.body_snapshot:
        flash('This revision has no saved content to restore.', 'error')
        return redirect(url_for('admin.page_history', page_id=page_id))
    page.body_markdown = rev.body_snapshot
    page.body_html = render_markdown(rev.body_snapshot)
    restore_note = f'Restored from revision on {rev.edited_at.strftime("%Y-%m-%d %H:%M")}'
    db.session.add(PageRevision(
        page_id=page.id,
        user_id=current_user.id,
        body_snapshot=rev.body_snapshot,
        changelog=restore_note,
    ))
    db.session.commit()
    flash('Page restored to selected revision.', 'success')
    return redirect(url_for('admin.edit_page', page_id=page_id))


def _fire_integrations(entry, is_new, changelog):
    from app.integrations import notify_slack_entry, fire_outgoing_webhook
    site_settings = SiteSettings.query.get(1)
    if not site_settings:
        return
    base_url = request.host_url.rstrip('/')
    event = 'entry.published' if is_new else 'entry.updated'
    notify_slack_entry(entry, is_new=is_new, changelog=changelog,
                       settings=site_settings, base_url=base_url)
    if site_settings.site_visibility == 'public':
        fire_outgoing_webhook(entry, event=event, changelog=changelog,
                              settings=site_settings, base_url=base_url)


@admin_bp.route('/integrations/', methods=['GET', 'POST'])
@admin_required
def integrations():
    site_settings = SiteSettings.query.get(1)
    if request.method == 'POST':
        site_settings.mailchimp_api_key = request.form.get('mailchimp_api_key', '').strip()
        site_settings.mailchimp_server_prefix = request.form.get('mailchimp_server_prefix', '').strip()
        site_settings.mailchimp_list_id = request.form.get('mailchimp_list_id', '').strip()
        site_settings.slack_webhook_url = request.form.get('slack_webhook_url', '').strip()
        site_settings.slack_announce_new = 'slack_announce_new' in request.form
        site_settings.slack_announce_updates = 'slack_announce_updates' in request.form
        site_settings.outgoing_webhook_url = request.form.get('outgoing_webhook_url', '').strip()
        if 'regenerate_webhook_secret' in request.form or not site_settings.outgoing_webhook_secret:
            site_settings.outgoing_webhook_secret = secrets.token_hex(32)
        db.session.commit()
        flash('Integrations saved.', 'success')
        return redirect(url_for('admin.integrations'))
    if not site_settings.outgoing_webhook_secret:
        site_settings.outgoing_webhook_secret = secrets.token_hex(32)
        db.session.commit()
    return render_template('admin/integrations.html', settings=site_settings)


@admin_bp.route('/data/')
@admin_required
def data():
    from app.testdata import has_test_data
    return render_template('admin/data.html', has_test_data=has_test_data())


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
        from datetime import datetime, timezone
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

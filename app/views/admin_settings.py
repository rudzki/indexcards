import os
import secrets

from flask import render_template, redirect, url_for, request, flash, current_app

from sqlalchemy import func, nullslast

from app import db
from app.models import SiteSettings, Entry, NavItem, entry_groups
from app.registration import VALID_ROLES
from app.views.admin import admin_bp, admin_required
from app.views._helpers import validated_image_ext


def _nav_items():
    """Nav slots in menu order (position, nulls last)."""
    return (NavItem.query
            .order_by(nullslast(NavItem.position.asc()), NavItem.id.asc())
            .all())

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

# Enum settings: field name -> (allowed values, default). One place documenting
# every constrained setting; validated_choice() rejects anything off the
# allowlist on save (e.g. an unknown registration_method would otherwise behave
# like open registration in signup_form()).
_ENUM_SETTINGS = {
    'registration_method': ({'invite', 'domain', 'open'}, 'invite'),
    'default_role': (set(VALID_ROLES), 'viewer'),
    'site_visibility': ({'public', 'registered', 'admin'}, 'public'),
    'subpage_display': ({'separate', 'nested', 'both'}, 'both'),
    'site_theme': ({'default', 'forest', 'sepia', 'midnight', 'stone'}, 'default'),
    'default_color_mode': ({'auto', 'light', 'dark'}, 'dark'),
}


def validated_choice(form, field):
    """Return the submitted value for an enum setting when it's in the field's
    allowlist, else the field's default."""
    allowed, default = _ENUM_SETTINGS[field]
    raw = form.get(field, default).strip()
    return raw if raw in allowed else default


@admin_bp.route('/settings/', methods=['GET', 'POST'])
@admin_required
def settings():
    site_settings = SiteSettings.get()
    if request.method == 'POST':
        site_settings.site_title = request.form.get('site_title', '').strip()

        site_settings.search_enabled = 'search_enabled' in request.form
        site_settings.subscribe_enabled = 'subscribe_enabled' in request.form
        site_settings.footer_credit = 'footer_credit' in request.form

        site_settings.multiuser_enabled = 'multiuser_enabled' in request.form
        # Groups depend on multi-user; force off if multi-user is off so the two
        # can't drift out of sync from a hand-posted form.
        site_settings.groups_enabled = (
            'groups_enabled' in request.form and site_settings.multiuser_enabled)

        # Enums are validated against their allowlists (see _ENUM_SETTINGS).
        site_settings.registration_method = validated_choice(request.form, 'registration_method')
        site_settings.registration_domain = request.form.get('registration_domain', '').strip()
        site_settings.default_role = validated_choice(request.form, 'default_role')
        site_settings.site_visibility = validated_choice(request.form, 'site_visibility')

        site_settings.show_authors = 'show_authors' in request.form
        site_settings.show_history = 'show_history' in request.form
        site_settings.alpha_jump_enabled = 'alpha_jump_enabled' in request.form

        site_settings.subpage_display = validated_choice(request.form, 'subpage_display')
        site_settings.feeds_enabled = 'feeds_enabled' in request.form
        site_settings.site_icon = request.form.get('site_icon', '').strip()

        site_settings.site_theme = validated_choice(request.form, 'site_theme')
        site_settings.default_color_mode = validated_choice(request.form, 'default_color_mode')

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
    nav_items = _nav_items()
    in_nav = {n.entry_id for n in nav_items}
    # Any published card may be added to the nav; exclude those already in it.
    nav_candidates = [e for e in Entry.query
                      .filter(Entry.is_draft == False)  # noqa: E712
                      .order_by(Entry.sort_title).all()
                      if e.id not in in_nav]
    # How many entries are currently restricted to a group — drives the confirm
    # dialog when an admin turns groups off (option A re-exposes them).
    grouped_entry_count = db.session.query(entry_groups.c.entry_id).distinct().count()
    return render_template('admin/settings.html', settings=site_settings, icon_names=icon_names,
                           themes=themes,
                           nav_items=nav_items, nav_candidates=nav_candidates,
                           grouped_entry_count=grouped_entry_count)


@admin_bp.route('/content/', methods=['GET', 'POST'])
@admin_required
def content():
    """Site Content — the site's editorial prose (epigraph, About page, and the
    footer colophon), kept apart from operational Settings."""
    site_settings = SiteSettings.get()
    if request.method == 'POST':
        site_settings.announcement_banner = request.form.get('announcement_banner', '').strip()
        site_settings.epigraph = request.form.get('epigraph', '').strip()
        site_settings.about_markdown = request.form.get('about_markdown', '').strip()
        site_settings.footer_text = request.form.get('footer_text', '').strip()
        db.session.commit()
        flash('Site content saved.', 'success')
        return redirect(url_for('admin.content'))
    return render_template('admin/content.html', settings=site_settings)


@admin_bp.route('/nav/add/', methods=['POST'])
@admin_required
def nav_add():
    entry_id = request.form.get('entry_id', type=int)
    entry = db.session.get(Entry, entry_id) if entry_id else None
    if not entry:
        flash('Card not found.', 'error')
        return redirect(url_for('admin.settings'))
    if NavItem.query.filter_by(entry_id=entry.id).first():
        flash('That card is already in the navigation.', 'error')
        return redirect(url_for('admin.settings'))
    max_pos = db.session.query(func.max(NavItem.position)).scalar()
    db.session.add(NavItem(entry_id=entry.id, position=(max_pos or 0) + 1))
    db.session.commit()
    flash('Added to navigation.', 'success')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/nav/<int:nav_id>/remove/', methods=['POST'])
@admin_required
def nav_remove(nav_id):
    item = db.session.get(NavItem, nav_id)
    if item:
        db.session.delete(item)
        db.session.commit()
        flash('Removed from navigation.', 'success')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/nav/<int:nav_id>/move/', methods=['POST'])
@admin_required
def nav_move(nav_id):
    direction = request.form.get('direction')
    items = _nav_items()
    # Normalize to contiguous 0..n-1 first (positions can be NULL after the
    # page migration), then swap the target with its neighbor.
    for i, it in enumerate(items):
        it.position = i
    idx = next((i for i, it in enumerate(items) if it.id == nav_id), None)
    if idx is not None:
        swap = idx - 1 if direction == 'up' else idx + 1 if direction == 'down' else None
        if swap is not None and 0 <= swap < len(items):
            items[idx].position, items[swap].position = items[swap].position, items[idx].position
    db.session.commit()
    return redirect(url_for('admin.settings'))


@admin_bp.route('/settings/upload-image/', methods=['POST'])
@admin_required
def upload_site_image():
    f = request.files.get('site_image')
    if not f or not f.filename:
        flash('No file selected.', 'error')
        return redirect(url_for('admin.settings'))

    ext = validated_image_ext(f, ALLOWED_IMAGE_EXTENSIONS)
    if not ext:
        flash('Only PNG, JPEG, and WebP images are allowed.', 'error')
        return redirect(url_for('admin.settings'))

    filename = f'site-image.{ext}'
    upload_dir = current_app.config['UPLOAD_DIR']

    site_settings = SiteSettings.get()
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
    site_settings = SiteSettings.get()
    if site_settings.site_image:
        path = os.path.join(current_app.config['UPLOAD_DIR'], site_settings.site_image)
        if os.path.exists(path):
            os.remove(path)
        site_settings.site_image = ''
        db.session.commit()
    flash('Site image removed.', 'success')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/integrations/', methods=['GET', 'POST'])
@admin_required
def integrations():
    site_settings = SiteSettings.get()
    if request.method == 'POST':
        site_settings.smtp_host = request.form.get('smtp_host', '').strip() or None
        port = request.form.get('smtp_port', '').strip()
        site_settings.smtp_port = int(port) if port.isdigit() else None
        site_settings.smtp_username = request.form.get('smtp_username', '').strip() or None
        # The password field is rendered blank (see integrations.html); only
        # overwrite the stored value when the admin actually types a new one,
        # so a normal save doesn't wipe the existing password.
        new_smtp_password = request.form.get('smtp_password', '').strip()
        if new_smtp_password:
            site_settings.smtp_password = new_smtp_password
        site_settings.smtp_use_tls = 'smtp_use_tls' in request.form
        site_settings.smtp_from_address = request.form.get('smtp_from_address', '').strip() or None

        site_settings.digest_include_edits = 'digest_include_edits' in request.form
        day = request.form.get('digest_day', '0').strip()
        site_settings.digest_day = int(day) if (day.isdigit() and 0 <= int(day) <= 6) else 0

        site_settings.custom_css = request.form.get('custom_css', '')
        site_settings.custom_head_html = request.form.get('custom_head_html', '')
        site_settings.custom_footer_html = request.form.get('custom_footer_html', '')

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
    from app.mail import smtp_env_configured
    return render_template('admin/integrations.html', settings=site_settings,
                           smtp_env_configured=smtp_env_configured())

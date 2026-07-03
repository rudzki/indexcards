import os
import secrets

from flask import render_template, redirect, url_for, request, flash, current_app

from app import db
from app.models import SiteSettings
from app.views.admin import admin_bp, admin_required

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}


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

        valid_subpage_display = {'separate', 'nested', 'both'}
        raw_subpage_display = request.form.get('subpage_display', 'both')
        site_settings.subpage_display = raw_subpage_display if raw_subpage_display in valid_subpage_display else 'both'
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
    return render_template('admin/settings.html', settings=site_settings, icon_names=icon_names, themes=themes)


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

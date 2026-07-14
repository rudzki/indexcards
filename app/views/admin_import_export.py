import io
import json
import zipfile
from datetime import datetime

from flask import render_template, redirect, url_for, request, flash, send_file
from flask_login import current_user

from app import db
from app.models import Entry, log_audit, make_slug
from app.entries import import_entry
from app.views.admin import admin_bp, admin_required


def _yaml_str(s):
    # Double-quoted YAML scalar: escape backslash/quote and fold newlines so a
    # title/alias containing them can't corrupt the frontmatter.
    return (s or '').replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ').replace('\r', ' ')


@admin_bp.route('/export/markdown/')
@admin_required
def export_markdown():
    entries = Entry.query.filter_by(is_draft=False).all()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for entry in entries:
            frontmatter = f'---\ntitle: "{_yaml_str(entry.title)}"\nsummary: "{_yaml_str(entry.summary)}"\nslug: {entry.slug}\n'
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
            'published_at': entry.published_at.isoformat() if entry.published_at else None,
            'created_at': entry.created_at.isoformat() if entry.created_at else None,
            'updated_at': entry.updated_at.isoformat() if entry.updated_at else None,
        })
    buf = io.BytesIO()
    buf.write(json.dumps(data, indent=2, ensure_ascii=False).encode('utf-8'))
    buf.seek(0)
    return send_file(buf, mimetype='application/json', as_attachment=True,
                     download_name='entries.json')


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

    def _parse_dt(value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None

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

            if import_entry(title, slug, body_markdown, summary, is_draft,
                            published_at=_parse_dt(item.get('published_at')),
                            created_at=_parse_dt(item.get('created_at')),
                            updated_at=_parse_dt(item.get('updated_at'))):
                count += 1
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Import failed partway through — no entries were saved.', 'error')
        return redirect(url_for('admin.settings'))

    log_audit('import_json', detail=f'{count} entries imported', user_id=current_user.id)
    flash(f'{count} entries imported.', 'success')
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


@admin_bp.route('/data/')
@admin_required
def data():
    from app.testdata import has_test_data
    return render_template('admin/data.html', has_test_data=has_test_data())

from flask import Blueprint, jsonify, request
from flask_login import login_required

from app.models import Entry, Alias
from app.markdown import render_markdown

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/entries/search')
def search_entries():
    q = request.args.get('q', '').strip().lower()
    if not q or len(q) < 1:
        return jsonify([])

    q_escaped = q.replace('%', r'\%').replace('_', r'\_')

    entries = Entry.query.filter(
        Entry.title.ilike(f'%{q_escaped}%', escape='\\'),
        Entry.is_draft == False  # noqa: E712
    ).limit(10).all()

    aliases = Alias.query.filter(
        Alias.title.ilike(f'%{q_escaped}%', escape='\\')
    ).limit(10).all()

    results = []
    seen = set()

    for entry in entries:
        if entry.id not in seen:
            seen.add(entry.id)
            results.append({
                'title': entry.title,
                'slug': entry.slug,
                'summary': entry.summary,
            })

    for alias in aliases:
        if alias.entry_id not in seen and not alias.entry.is_draft:
            seen.add(alias.entry_id)
            results.append({
                'title': f'{alias.title} → {alias.entry.title}',
                'slug': alias.entry.slug,
                'summary': alias.entry.summary,
            })

    return jsonify(results[:15])


@api_bp.route('/entry/<slug>/preview')
def entry_preview(slug):
    entry = Entry.query.filter_by(slug=slug, is_draft=False).first()
    if not entry:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'title': entry.title, 'summary': entry.summary or ''})


@api_bp.route('/preview', methods=['POST'])
@login_required
def preview():
    data = request.get_json()
    markdown = data.get('markdown', '') if data else ''
    html = render_markdown(markdown)
    return jsonify({'html': html})

import os
import secrets
from datetime import datetime, timezone, timedelta

from flask import Blueprint, jsonify, request, current_app, url_for
from flask_login import login_required, current_user

from app.models import Entry, Alias, SiteSettings, EditLock, make_slug, log_audit
from app.markdown import render_markdown
from app.search import update_fts_entry
from app.entries import RESERVED_SLUGS
from app import db, limiter, csrf

LOCK_TTL = 60  # seconds

api_bp = Blueprint('api', __name__, url_prefix='/api')


def _check_visibility():
    """Return a 401 response if the site is private and the caller is not authenticated."""
    settings = SiteSettings.query.get(1)
    if settings and settings.site_visibility == 'registered':
        if not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required'}), 401
    return None


def _fmt(dt):
    if not dt:
        return None
    from datetime import timezone
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def _entry_summary(entry):
    return {
        'slug': entry.slug,
        'title': entry.title,
        'summary': entry.summary or '',
        'published_at': _fmt(entry.published_at),
        'updated_at': _fmt(entry.updated_at),
        'url': url_for('main.entry_page', slug=entry.slug, _external=True),
    }


def _entry_full(entry):
    d = _entry_summary(entry)
    d['body_html'] = entry.body_html or ''
    d['aliases'] = [a.title for a in entry.aliases]
    return d


# --- Public read-only API ---

@api_bp.route('/v1/entries')
@limiter.limit('120 per minute')
@csrf.exempt
def public_entries():
    denied = _check_visibility()
    if denied:
        return denied

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    q = (Entry.query
         .filter_by(is_draft=False)
         .order_by(Entry.sort_title))

    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'entries': [_entry_summary(e) for e in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': per_page,
        'pages': pagination.pages,
    })


@api_bp.route('/v1/entries/<slug>')
@limiter.limit('120 per minute')
@csrf.exempt
def public_entry(slug):
    denied = _check_visibility()
    if denied:
        return denied

    entry = Entry.query.filter_by(slug=slug, is_draft=False).first()
    if not entry:
        alias = Alias.query.filter_by(slug=slug).first()
        if alias and not alias.entry.is_draft:
            entry = alias.entry
    if not entry:
        return jsonify({'error': 'Not found'}), 404

    return jsonify(_entry_full(entry))


# --- Internal endpoints (editor, autocomplete, hover cards) ---

@api_bp.route('/entries/search')
def search_entries():
    err = _check_visibility()
    if err:
        return err
    q = request.args.get('q', '').strip().lower()

    if not q:
        entries = (Entry.query
                   .filter(Entry.is_draft == False)  # noqa: E712
                   .order_by(Entry.sort_title)
                   .limit(20).all())
        return jsonify([{
            'id': entry.id,
            'title': entry.title,
            'slug': entry.slug,
            'summary': entry.summary,
        } for entry in entries])

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
                'id': entry.id,
                'title': entry.title,
                'slug': entry.slug,
                'summary': entry.summary,
            })

    for alias in aliases:
        if alias.entry_id not in seen and not alias.entry.is_draft:
            seen.add(alias.entry_id)
            results.append({
                'id': alias.entry_id,
                'title': f'{alias.title} → {alias.entry.title}',
                'slug': alias.entry.slug,
                'summary': alias.entry.summary,
            })

    return jsonify(results[:15])


@api_bp.route('/entries/quick-create', methods=['POST'])
@login_required
def quick_create_entry():
    if not current_user.can_write:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json(silent=True) or request.form
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'Title is required.'}), 400

    slug = make_slug(title)
    if not slug or slug in RESERVED_SLUGS:
        return jsonify({'error': 'That title cannot be used.'}), 400

    existing = Entry.query.filter_by(slug=slug).first()
    if existing:
        return jsonify({'id': existing.id, 'title': existing.title, 'slug': existing.slug})
    existing_alias = Alias.query.filter_by(slug=slug).first()
    if existing_alias:
        return jsonify({
            'id': existing_alias.entry_id,
            'title': existing_alias.entry.title,
            'slug': existing_alias.entry.slug,
        })

    entry = Entry(slug=slug, title=title, is_draft=True, created_by=current_user.id)
    entry.update_sort_title()
    db.session.add(entry)
    db.session.commit()

    update_fts_entry(entry)
    log_audit('entry_created', detail=entry.title, user_id=current_user.id)

    return jsonify({'id': entry.id, 'title': entry.title, 'slug': entry.slug}), 201


@api_bp.route('/entry/<slug>/preview')
def entry_preview(slug):
    denied = _check_visibility()
    if denied:
        return denied
    entry = Entry.query.filter_by(slug=slug, is_draft=False).first()
    if not entry:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'title': entry.title, 'summary': entry.summary or ''})


_ALLOWED_IMAGE_TYPES = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


@api_bp.route('/upload-image', methods=['POST'])
@login_required
def upload_image():
    if not current_user.can_write:
        return jsonify({'error': 'Forbidden'}), 403
    f = request.files.get('image')
    if not f or not f.filename:
        return jsonify({'error': 'No file provided'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in _ALLOWED_IMAGE_TYPES:
        return jsonify({'error': 'Invalid file type'}), 400
    filename = secrets.token_hex(16) + '.' + ext
    f.save(os.path.join(current_app.config['UPLOAD_DIR'], filename))
    return jsonify({'url': f'/uploads/{filename}'})


@api_bp.route('/lock/<content_type>/<int:content_id>', methods=['POST'])
@login_required
def acquire_lock(content_type, content_id):
    if content_type not in ('entry', 'page'):
        return jsonify({'error': 'Invalid type'}), 400

    now = datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)
    expires_naive = (now + timedelta(seconds=LOCK_TTL)).replace(tzinfo=None)

    EditLock.query.filter(EditLock.expires_at < now_naive).delete()

    existing = EditLock.query.filter_by(content_type=content_type, content_id=content_id).first()
    if existing and existing.user_id != current_user.id:
        exp = existing.expires_at.replace(tzinfo=timezone.utc) if existing.expires_at.tzinfo is None else existing.expires_at
        if exp > now:
            name = existing.user.display_name if existing.user else 'Someone'
            return jsonify({'error': 'locked', 'locked_by': name}), 423

    if existing:
        existing.user_id = current_user.id
        existing.expires_at = expires_naive
    else:
        db.session.add(EditLock(content_type=content_type, content_id=content_id,
                                user_id=current_user.id, expires_at=expires_naive))
    db.session.commit()
    return jsonify({'ok': True})


@api_bp.route('/lock/<content_type>/<int:content_id>/release', methods=['POST'])
@login_required
def release_lock(content_type, content_id):
    EditLock.query.filter_by(
        content_type=content_type, content_id=content_id, user_id=current_user.id
    ).delete()
    db.session.commit()
    return jsonify({'ok': True})


@api_bp.route('/preview', methods=['POST'])
@login_required
def preview():
    data = request.get_json()
    markdown = data.get('markdown', '') if data else ''
    html = render_markdown(markdown)
    return jsonify({'html': html})

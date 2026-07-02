import re
from collections import defaultdict, OrderedDict
from datetime import datetime, timezone, timedelta

import os

from flask import Blueprint, render_template, redirect, request, flash, url_for, abort, jsonify, Response, send_file, make_response, current_app
from flask_login import current_user, login_user
from markupsafe import Markup

from app import db, limiter
from app.models import Entry, Alias, User, SiteSettings, EditLog, Page, sort_key
from app.markdown import mark_missing_links, extract_toc, INTERNAL_LINK_RE
from app.search import search_entries
from app.mail import send_email, render_email

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    entries = (Entry.query
               .filter_by(is_draft=False)
               .order_by(Entry.sort_title)
               .all())

    site_settings = SiteSettings.query.get(1)
    subpage_display = site_settings.subpage_display if site_settings and site_settings.subpage_display else 'both'

    children_by_parent = defaultdict(list)
    for entry in entries:
        if entry.parent_id:
            children_by_parent[entry.parent_id].append(entry)

    index_items = []
    for entry in entries:
        # Only hide an entry when it will actually be reachable by nesting it
        # under its parent (the index only nests one level deep), so entries
        # more than one level deep aren't dropped from the list entirely.
        if subpage_display == 'nested' and entry.parent_id and not entry.parent.parent_id:
            continue
        show_children = children_by_parent.get(entry.id, []) if subpage_display != 'separate' else []
        index_items.append({'type': 'entry', 'entry': entry, 'sort_title': entry.sort_title,
                            'children': show_children})
        for alias in entry.aliases:
            index_items.append({'type': 'alias', 'entry': entry, 'alias': alias,
                                'sort_title': sort_key(alias.title)})
    index_items.sort(key=lambda x: x['sort_title'])

    today = datetime.now(timezone.utc)
    start_month = today.month - 11
    start_year = today.year
    if start_month <= 0:
        start_month += 12
        start_year -= 1
    cutoff = datetime(start_year, start_month, 1)
    all_logs = (
        db.session.query(EditLog, Entry)
        .join(Entry, EditLog.entry_id == Entry.id)
        .filter(Entry.is_draft == False)  # noqa: E712
        .filter(EditLog.edited_at >= cutoff)
        .order_by(EditLog.edited_at.desc())
        .all()
    )

    day_map = defaultdict(OrderedDict)
    for log, entry in all_logs:
        date_str = log.edited_at.strftime('%Y-%m-%d')
        if entry.id not in day_map[date_str]:
            day_map[date_str][entry.id] = {
                'title': entry.title,
                'slug': entry.slug,
                'changelog': log.changelog or '',
                'is_new': log.changelog is None and len(entry.edit_logs) <= 1,
            }

    heatmap_data = {ds: list(items.values()) for ds, items in day_map.items()}

    return render_template('index.html', entries=entries, index_items=index_items, heatmap_data=heatmap_data)


@main_bp.route('/<slug>/')
def entry_page(slug):
    entry = Entry.query.filter_by(slug=slug, is_draft=False).first()
    if entry:
        linked_slugs = set(INTERNAL_LINK_RE.findall(entry.body_html or ''))
        if linked_slugs:
            existing_slugs = {r[0] for r in Entry.query.with_entities(Entry.slug)
                              .filter(Entry.slug.in_(linked_slugs)).all()}
        else:
            existing_slugs = set()
        body_html = mark_missing_links(entry.body_html, existing_slugs)
        backlinks = (Entry.query
                     .join(Entry.outgoing_links)
                     .filter(
                         Entry.outgoing_links.any(target_entry_id=entry.id),
                         Entry.is_draft == False  # noqa: E712
                     )
                     .all())
        toc = extract_toc(body_html)
        last_edit_log = (EditLog.query
                         .filter_by(entry_id=entry.id)
                         .order_by(EditLog.edited_at.desc())
                         .first())
        last_editor = last_edit_log.user if last_edit_log else None

        prev_entry = (Entry.query
                      .filter(Entry.is_draft == False,  # noqa: E712
                              Entry.sort_title < entry.sort_title)
                      .order_by(Entry.sort_title.desc())
                      .first())
        next_entry = (Entry.query
                      .filter(Entry.is_draft == False,  # noqa: E712
                              Entry.sort_title > entry.sort_title)
                      .order_by(Entry.sort_title.asc())
                      .first())

        ancestors = []
        cursor = entry
        for _ in range(10):
            if not cursor.parent_id:
                break
            p = Entry.query.get(cursor.parent_id)
            if not p or p.id in {a.id for a in ancestors}:
                break
            ancestors.append(p)
            cursor = p
        ancestors.reverse()

        children = (Entry.query
                    .filter_by(parent_id=entry.id, is_draft=False)
                    .order_by(Entry.sort_title)
                    .all())

        return render_template('entry.html', entry=entry, body_html=Markup(body_html),
                               backlinks=backlinks, toc=toc, last_editor=last_editor,
                               prev_entry=prev_entry, next_entry=next_entry,
                               ancestors=ancestors, children=children)

    alias = Alias.query.filter_by(slug=slug).first()
    if alias:
        return redirect(url_for('main.entry_page', slug=alias.entry.slug), code=301)

    page = Page.query.filter_by(slug=slug, is_draft=False).first()
    if page:
        return render_template('page.html', page=page)

    if current_user.is_authenticated and current_user.can_write:
        return redirect(url_for('admin.new_entry', title=slug))

    abort(404)


@main_bp.route('/search')
def search():
    query = request.args.get('q', '').strip()
    results = []
    if query:
        fts_results = search_entries(query)
        entry_ids = [r[0] for r in fts_results]
        excerpts = {r[0]: r[2] for r in fts_results}
        if entry_ids:
            entries = Entry.query.filter(
                Entry.id.in_(entry_ids),
                Entry.is_draft == False  # noqa: E712
            ).all()
            entry_map = {e.id: e for e in entries}
            results = [
                {'entry': entry_map[eid], 'excerpt': Markup(excerpts.get(eid, ''))}
                for eid in entry_ids if eid in entry_map
            ]

        def highlight_terms(text, q):
            if not text:
                return text
            terms = q.split()
            for term in terms:
                escaped = re.escape(term)
                text = re.sub(
                    rf'\b({escaped})\b',
                    r'<mark>\1</mark>',
                    text,
                    flags=re.IGNORECASE,
                )
            return Markup(text)

        for item in results:
            item['highlighted_title'] = highlight_terms(item['entry'].title, query)
            item['highlighted_summary'] = highlight_terms(item['entry'].summary, query)

    return render_template('search.html', query=query, results=results)


@main_bp.route('/random')
def random_entry():
    from sqlalchemy.sql.expression import func
    entry = Entry.query.filter_by(is_draft=False).order_by(func.random()).first()
    if entry:
        return redirect(url_for('main.entry_page', slug=entry.slug))
    return redirect(url_for('main.index'))


@main_bp.route('/healthz')
def healthz():
    try:
        db.session.execute(db.text('SELECT 1'))
        return jsonify(status='ok'), 200
    except Exception:
        return jsonify(status='error'), 503


@main_bp.route('/subscribe', methods=['POST'])
@limiter.limit("5 per minute")
def subscribe():
    email = request.form.get('email', '').strip().lower()
    if not email:
        flash('Please enter an email address.', 'error')
        return redirect(request.referrer or url_for('main.index'))

    user = User.query.filter_by(email=email).first()
    if user:
        if user.subscribed:
            flash('This email is already subscribed.', 'info')
            return redirect(request.referrer or url_for('main.index'))
        token = user.generate_login_token()
        db.session.commit()
        confirm_url = url_for('main.confirm_subscription', token=token, _external=True)
    else:
        display_name = email.split('@')[0]
        user = User(email=email, display_name=display_name, role='viewer')
        db.session.add(user)
        db.session.flush()
        token = user.generate_login_token()
        db.session.commit()
        confirm_url = url_for('main.confirm_subscription', token=token, _external=True)

    settings = SiteSettings.query.get(1)
    site_title = (settings.site_title if settings else None) or 'Index Cards'
    text, html = render_email('subscription_confirm', site_title=site_title, confirm_url=confirm_url)
    if not send_email(to=email, subject='Confirm your subscription', body_text=text, body_html=html):
        flash('Something went wrong sending the confirmation email. Please try again later.', 'error')
        return redirect(request.referrer or url_for('main.index'))

    flash('Check your email to confirm your subscription.', 'success')
    return redirect(request.referrer or url_for('main.index'))


@main_bp.route('/confirm/<token>')
def confirm_subscription(token):
    user = User.query.filter_by(login_token=token).first_or_404()
    if not user.token_valid:
        flash('This confirmation link has expired. Please subscribe again.', 'error')
        return redirect(url_for('auth.login'))
    user.subscribed = True
    user.clear_login_token()
    db.session.commit()
    login_user(user)

    from app.integrations import notify_mailchimp_subscribe
    notify_mailchimp_subscribe(user.email, SiteSettings.query.get(1))

    flash('Subscription confirmed!', 'success')
    return redirect(url_for('main.index'))


@main_bp.route('/unsubscribe/<token>')
def unsubscribe(token):
    user = User.query.filter_by(unsubscribe_token=token).first_or_404()
    user.subscribed = False
    db.session.commit()
    flash('You have been unsubscribed.', 'success')
    return redirect(url_for('main.index'))


@main_bp.route('/favicon.svg')
def favicon():
    settings = SiteSettings.query.get(1)
    icon_name = settings.site_icon if settings else ''
    if icon_name:
        from app.icons import get_icon_svg
        svg = get_icon_svg(icon_name, size=32, color='%231a1a1a')
    else:
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"'
               ' viewBox="0 0 16 16" fill="%231a1a1a">'
               '<rect x="2" y="1" width="12" height="14" rx="1" fill="none"'
               ' stroke="%231a1a1a" stroke-width="1.2"/>'
               '<line x1="5" y1="5" x2="11" y2="5" stroke="%231a1a1a" stroke-width="1"/>'
               '<line x1="5" y1="8" x2="11" y2="8" stroke="%231a1a1a" stroke-width="1"/>'
               '<line x1="5" y1="11" x2="9" y2="11" stroke="%231a1a1a" stroke-width="1"/>'
               '</svg>')
    return Response(svg, mimetype='image/svg+xml', headers={'Cache-Control': 'public, max-age=3600'})


def _feeds_available(settings):
    return settings and settings.site_visibility == 'public' and settings.feeds_enabled


def _feed_entries():
    db_entries = (Entry.query
                  .filter_by(is_draft=False)
                  .filter(Entry.published_at.isnot(None))
                  .order_by(Entry.updated_at.desc())
                  .limit(20)
                  .all())

    def fmt(dt):
        if not dt:
            return ''
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

    entries = [{
        'title': e.title,
        'url': url_for('main.entry_page', slug=e.slug, _external=True),
        'published': fmt(e.published_at),
        'updated': fmt(e.updated_at),
        'summary': e.summary or '',
        'body_html': e.body_html or '',
        'author': e.author.display_name if e.author else '',
    } for e in db_entries]

    most_recent = fmt(db_entries[0].updated_at) if db_entries else fmt(datetime.now(timezone.utc))
    return entries, most_recent


@main_bp.route('/feed.xml')
def feed():
    settings = SiteSettings.query.get(1)
    if not _feeds_available(settings):
        abort(404)
    entries, most_recent = _feed_entries()
    xml = render_template('feed.xml',
                          site_title=(settings.site_title if settings else None) or 'Index Cards',
                          feed_url=url_for('main.feed', _external=True),
                          index_url=url_for('main.index', _external=True),
                          updated=most_recent,
                          entries=entries)
    return Response(xml, mimetype='application/atom+xml',
                    headers={'Cache-Control': 'public, max-age=300'})


@main_bp.route('/feed.json')
def feed_json():
    settings = SiteSettings.query.get(1)
    if not _feeds_available(settings):
        abort(404)
    entries, _ = _feed_entries()
    site_title = (settings.site_title if settings else None) or 'Index Cards'
    payload = {
        'version': 'https://jsonfeed.org/version/1.1',
        'title': site_title,
        'home_page_url': url_for('main.index', _external=True),
        'feed_url': url_for('main.feed_json', _external=True),
        'items': [{
            'id': e['url'],
            'url': e['url'],
            'title': e['title'],
            'summary': e['summary'],
            'content_html': e['body_html'],
            'date_published': e['published'],
            'date_modified': e['updated'],
            **(({'authors': [{'name': e['author']}]} if e['author'] else {})),
        } for e in entries],
    }
    return current_app.response_class(
        __import__('json').dumps(payload, ensure_ascii=False),
        mimetype='application/feed+json',
        headers={'Cache-Control': 'public, max-age=300'},
    )


@main_bp.route('/uploads/<filename>')
def uploaded_file(filename):
    import re
    if not re.match(r'^[0-9a-f]{32}\.[a-z]{2,4}$', filename):
        abort(404)
    path = os.path.join(current_app.config['UPLOAD_DIR'], filename)
    if not os.path.exists(path):
        abort(404)
    response = make_response(send_file(path))
    response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response


@main_bp.route('/site-image')
def site_image():
    settings = SiteSettings.query.get(1)
    if not settings or not settings.site_image:
        abort(404)
    path = os.path.join(current_app.config['UPLOAD_DIR'], settings.site_image)
    if not os.path.exists(path):
        abort(404)
    response = make_response(send_file(path))
    response.headers['Cache-Control'] = 'public, max-age=3600'
    return response

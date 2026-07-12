import json
import re
from collections import defaultdict, OrderedDict
from datetime import datetime

import os

from flask import Blueprint, render_template, redirect, request, flash, url_for, abort, jsonify, Response, send_file, make_response, current_app
from flask_login import current_user, login_user
from markupsafe import Markup, escape

from app import db, limiter
from app.models import Entry, Alias, User, SiteSettings, EditLog, Page, PageRevision, Note, sort_key, entry_url, utcnow
from app.markdown import mark_missing_links, extract_toc, INTERNAL_LINK_RE
from app.search import search_entries
from app.mail import send_email, render_email
from app.feeds import feeds_available, feed_entries

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    entries = (Entry.query
               .filter_by(is_draft=False)
               .order_by(Entry.sort_title)
               .all())

    site_settings = db.session.get(SiteSettings, 1)
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
        if (subpage_display == 'nested' and entry.parent_id
                and entry.parent and not entry.parent.parent_id):
            continue
        show_children = children_by_parent.get(entry.id, []) if subpage_display != 'separate' else []
        index_items.append({'type': 'entry', 'entry': entry, 'sort_title': entry.sort_title,
                            'children': show_children})
        for alias in entry.aliases:
            index_items.append({'type': 'alias', 'entry': entry, 'alias': alias,
                                'sort_title': sort_key(alias.title)})
    index_items.sort(key=lambda x: x['sort_title'])

    show_history = bool(site_settings and site_settings.show_history)
    heatmap_data = {}
    if show_history:
        today = utcnow()
        start_month = today.month - 11
        start_year = today.year
        if start_month <= 0:
            start_month += 12
            start_year -= 1
        cutoff = datetime(start_year, start_month, 1)
        events = _build_activity_events(
            since=cutoff,
            notes_enabled=bool(site_settings and site_settings.notes_enabled),
            show_history=True,
        )
        heatmap_data = _group_events_by_day(events)

    return render_template('index.html', entries=entries, index_items=index_items, heatmap_data=heatmap_data)


@main_bp.route('/<slug>/')
def entry_page(slug):
    entry = Entry.query.filter_by(slug=slug, is_draft=False).first()
    if entry:
        if entry.parent_id:
            return redirect(entry_url(entry), code=301)
        return _render_entry_page(entry)

    alias = Alias.query.filter_by(slug=slug).first()
    if alias:
        return redirect(url_for('main.entry_page', slug=alias.entry.slug), code=301)

    page = Page.query.filter_by(slug=slug, is_draft=False).first()
    if page:
        last_revision = (PageRevision.query
                         .filter_by(page_id=page.id)
                         .order_by(PageRevision.edited_at.desc())
                         .first())
        last_editor = last_revision.user if last_revision else None
        return render_template('page.html', page=page, last_editor=last_editor)

    if current_user.is_authenticated and current_user.can_write:
        return redirect(url_for('admin.new_entry', title=slug))

    abort(404)


@main_bp.route('/<parent_slug>/<slug>/')
def child_entry_page(parent_slug, slug):
    entry = Entry.query.filter_by(slug=slug, is_draft=False).first()
    if not entry or not entry.parent_id:
        abort(404)
    # A child whose parent was deleted (orphaned parent_id) has no canonical
    # nested URL — fall back to its flat page instead of crashing on parent.slug.
    if not entry.parent or entry.parent.slug != parent_slug:
        return redirect(entry_url(entry), code=301)
    return _render_entry_page(entry)


def _render_entry_page(entry):
    linked_slugs = set(INTERNAL_LINK_RE.findall(entry.body_html or ''))
    if linked_slugs:
        existing_slugs = {r[0] for r in Entry.query.with_entities(Entry.slug)
                          .filter(Entry.slug.in_(linked_slugs)).all()}
        # Aliases resolve via a 301, so a link to an alias slug is not "missing".
        existing_slugs |= {r[0] for r in Alias.query.with_entities(Alias.slug)
                           .filter(Alias.slug.in_(linked_slugs)).all()}
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
    note_backlinks = (Note.query
                      .join(Note.outgoing_links)
                      .filter(
                          Note.outgoing_links.any(target_entry_id=entry.id),
                          Note.is_draft == False  # noqa: E712
                      )
                      .all())
    toc = extract_toc(body_html)
    last_edit_log = (EditLog.query
                     .filter_by(entry_id=entry.id)
                     .filter(EditLog.is_import == False)  # noqa: E712
                     .order_by(EditLog.edited_at.desc())
                     .first())
    last_editor = last_edit_log.user if last_edit_log else None

    # Order by (sort_title, id) and compare on the whole tuple so entries whose
    # titles normalize to the same sort_title still have a stable, complete
    # ordering — a plain `sort_title <` would skip a same-key sibling entirely.
    prev_entry = (Entry.query
                  .filter(Entry.is_draft == False,  # noqa: E712
                          db.or_(Entry.sort_title < entry.sort_title,
                                 db.and_(Entry.sort_title == entry.sort_title,
                                         Entry.id < entry.id)))
                  .order_by(Entry.sort_title.desc(), Entry.id.desc())
                  .first())
    next_entry = (Entry.query
                  .filter(Entry.is_draft == False,  # noqa: E712
                          db.or_(Entry.sort_title > entry.sort_title,
                                 db.and_(Entry.sort_title == entry.sort_title,
                                         Entry.id > entry.id)))
                  .order_by(Entry.sort_title.asc(), Entry.id.asc())
                  .first())

    ancestors = []
    cursor = entry
    for _ in range(10):
        if not cursor.parent_id:
            break
        p = db.session.get(Entry, cursor.parent_id)
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
                           backlinks=backlinks, note_backlinks=note_backlinks, toc=toc,
                           last_editor=last_editor,
                           prev_entry=prev_entry, next_entry=next_entry,
                           ancestors=ancestors, children=children)


def _notes_enabled(site_settings):
    return bool(site_settings and site_settings.notes_enabled)


def _build_activity_events(since=None, notes_enabled=False, show_history=True):
    """Build the unified activity feed — note publications plus entry
    publish/edit events — shared by the homepage heatmap and the /notes/
    timeline so both draw from the same source instead of independent
    heuristics for what counts as "new" vs "edited"."""
    events = []

    if notes_enabled:
        note_q = Note.query.filter_by(is_draft=False)
        if since:
            note_q = note_q.filter(Note.published_at >= since)
        for note in note_q.all():
            events.append({'kind': 'note', 'ts': note.published_at, 'note': note})

    entry_q = Entry.query.filter_by(is_draft=False)
    if since:
        entry_q = entry_q.filter(Entry.published_at >= since)
    entries = entry_q.all()

    logs_by_entry = defaultdict(list)
    if entries:
        log_q = EditLog.query.filter(EditLog.entry_id.in_([e.id for e in entries]),
                                      EditLog.is_import == False)  # noqa: E712
        if since:
            log_q = log_q.filter(EditLog.edited_at >= since)
        for log in log_q.order_by(EditLog.edited_at.asc()).all():
            logs_by_entry[log.entry_id].append(log)

    for entry in entries:
        entry_logs = logs_by_entry.get(entry.id, [])
        first_log = entry_logs[0] if entry_logs else None
        events.append({'kind': 'published', 'ts': entry.published_at, 'entry': entry,
                       'changelog': first_log.changelog if first_log else None})
        if show_history:
            for log in entry_logs[1:]:
                events.append({'kind': 'edited', 'ts': log.edited_at, 'entry': entry,
                               'changelog': log.changelog})

    events.sort(key=lambda x: x['ts'] or datetime.min, reverse=True)
    return _collapse_activity_events(events)


def _collapse_activity_events(events):
    """Merge consecutive 'published'/'edited' events for the same entry
    that land on the same calendar day into one event (folding in any
    distinct changelog messages), so a flurry of same-day saves doesn't
    spam the feed with near-identical entries."""
    collapsed = []
    for event in events:
        if event['kind'] in ('published', 'edited') and collapsed:
            prev = collapsed[-1]
            same_status = (prev['kind'] == event['kind']
                          and prev.get('entry') and event.get('entry')
                          and prev['entry'].id == event['entry'].id
                          and prev['ts'] and event['ts']
                          and prev['ts'].date() == event['ts'].date())
            if same_status:
                if event['changelog'] and event['changelog'] not in prev['changelogs']:
                    prev['changelogs'].append(event['changelog'])
                continue
        merged = dict(event)
        if event['kind'] in ('published', 'edited'):
            merged['changelogs'] = [event['changelog']] if event.get('changelog') else []
        collapsed.append(merged)
    return collapsed


def _group_events_by_day(events):
    """Group activity events by calendar day for the heatmap, keeping at
    most one cell entry per entry/note per day (the most recent event that
    day, since events are already sorted newest-first)."""
    day_map = defaultdict(OrderedDict)
    for event in events:
        if not event['ts']:
            continue
        date_str = event['ts'].strftime('%Y-%m-%d')
        if event['kind'] == 'note':
            key = ('note', event['note'].id)
            if key in day_map[date_str]:
                continue
            excerpt = (event['note'].body_markdown or '').strip().replace('\n', ' ')
            title = (excerpt[:60] + '…') if len(excerpt) > 60 else (excerpt or 'Note')
            day_map[date_str][key] = {
                'title': title,
                'url': url_for('main.note_page', note_id=event['note'].id),
                'changelog': '',
                'is_new': True,
            }
        else:
            key = ('entry', event['entry'].id)
            if key in day_map[date_str]:
                continue
            day_map[date_str][key] = {
                'title': event['entry'].title,
                'url': entry_url(event['entry']),
                'changelog': ' · '.join(event.get('changelogs') or []),
                'is_new': event['kind'] == 'published',
            }
    return {ds: list(items.values()) for ds, items in day_map.items()}


@main_bp.route('/notes/')
def notes_list():
    site_settings = db.session.get(SiteSettings, 1)
    if not _notes_enabled(site_settings):
        abort(404)

    page = request.args.get('page', 1, type=int)
    per_page = 50
    show_history = bool(site_settings.show_history)

    items = _build_activity_events(notes_enabled=True, show_history=show_history)
    total = len(items)
    start = (page - 1) * per_page
    page_items = items[start:start + per_page]

    heatmap_data = _group_events_by_day(items) if show_history else {}

    return render_template('timeline.html', items=page_items, page=page,
                           has_next=start + per_page < total, has_prev=page > 1,
                           heatmap_data=heatmap_data)


@main_bp.route('/notes/<int:note_id>/')
def note_page(note_id):
    site_settings = db.session.get(SiteSettings, 1)
    if not _notes_enabled(site_settings):
        abort(404)

    note = Note.query.filter_by(id=note_id, is_draft=False).first_or_404()
    return render_template('note.html', note=note)


@main_bp.route('/search')
def search():
    site_settings = db.session.get(SiteSettings, 1)
    if site_settings and not site_settings.search_enabled:
        abort(404)
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
            # Escape the source text *before* injecting <mark> so raw HTML in a
            # title/summary can't execute when rendered as Markup (stored XSS).
            text = str(escape(text))
            terms = q.split()
            for term in terms:
                escaped = re.escape(str(escape(term)))
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
        return redirect(entry_url(entry))
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

    # Same message on every path below so the endpoint doesn't reveal whether
    # an address is already a known/subscribed account (cf. /login).
    generic_msg = 'Check your email to confirm your subscription.'

    user = User.query.filter_by(email=email).first()
    if user and user.subscribed:
        flash(generic_msg, 'success')
        return redirect(request.referrer or url_for('main.index'))

    if not user:
        display_name = email.split('@')[0]
        user = User(email=email, display_name=display_name, role='viewer')
        db.session.add(user)
        db.session.flush()
    token = user.generate_login_token()
    db.session.commit()
    confirm_url = url_for('main.confirm_subscription', token=token, _external=True)

    settings = db.session.get(SiteSettings, 1)
    site_title = (settings.site_title if settings else None) or 'Index Cards'
    text, html = render_email('subscription_confirm', site_title=site_title, confirm_url=confirm_url)
    if not send_email(to=email, subject='Confirm your subscription', body_text=text, body_html=html):
        flash('Something went wrong sending the confirmation email. Please try again later.', 'error')
        return redirect(request.referrer or url_for('main.index'))

    flash(generic_msg, 'success')
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
    notify_mailchimp_subscribe(user.email, db.session.get(SiteSettings, 1))

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
    settings = db.session.get(SiteSettings, 1)
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


@main_bp.route('/feed.xml')
def feed():
    settings = db.session.get(SiteSettings, 1)
    if not feeds_available(settings):
        abort(404)
    entries, most_recent = feed_entries()
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
    settings = db.session.get(SiteSettings, 1)
    if not feeds_available(settings):
        abort(404)
    entries, _ = feed_entries()
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
        json.dumps(payload, ensure_ascii=False),
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
    settings = db.session.get(SiteSettings, 1)
    if not settings or not settings.site_image:
        abort(404)
    path = os.path.join(current_app.config['UPLOAD_DIR'], settings.site_image)
    if not os.path.exists(path):
        abort(404)
    response = make_response(send_file(path))
    response.headers['Cache-Control'] = 'public, max-age=3600'
    return response

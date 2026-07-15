from datetime import timedelta

from app import db
from app.models import (
    Entry, EditLog, Backlink, Registration, User, SiteSettings,
    make_slug, sort_key, utcnow,
)
from app.markdown import render_markdown, extract_internal_links
from app.search import update_fts_entry, delete_fts_entry
from app.testdata_content import (
    TEST_EMAIL_DOMAIN, TEST_USERS, TEST_ENTRIES, TEST_SUBSCRIBERS, TEST_INVITES,
    TEST_CUSTOM_CSS, TEST_CUSTOM_HEAD_HTML, TEST_CUSTOM_FOOTER_HTML,
)

TEST_SLUG_PREFIX = '_test-'

_now = utcnow()


def _ago(**kwargs):
    return _now - timedelta(**kwargs)


def _test_slug(title):
    return TEST_SLUG_PREFIX + make_slug(title)


def has_test_data():
    return Entry.query.filter(Entry.slug.like(f'{TEST_SLUG_PREFIX}%')).count() > 0


def seed_test_data(user_id):
    if has_test_data():
        return 0, 'Test data already exists. Remove it first.'

    test_user_ids = [user_id]
    users_created = 0
    for user_spec in TEST_USERS:
        if User.query.filter_by(email=user_spec['email']).first():
            continue
        user = User(
            email=user_spec['email'],
            display_name=user_spec['display_name'],
            role=user_spec['role'],
        )
        user.created_at = _ago(days=user_spec['days_ago'])
        db.session.add(user)
        db.session.flush()
        test_user_ids.append(user.id)
        users_created += 1

    entry_map = {}
    entries_created = 0

    for spec in TEST_ENTRIES:
        slug = _test_slug(spec['title'])
        is_draft = spec.get('is_draft', False)

        author_idx = spec.get('author_index')
        if author_idx is not None and author_idx + 1 < len(test_user_ids):
            author_id = test_user_ids[author_idx + 1]
        else:
            author_id = user_id

        body_md = spec['body']
        for other in TEST_ENTRIES:
            old_slug = make_slug(other['title'])
            new_slug = _test_slug(other['title'])
            body_md = body_md.replace(f'(/{old_slug}/)', f'(/{new_slug}/)')

        entry = Entry(
            slug=slug,
            title=spec['title'],
            summary=spec['summary'],
            body_markdown=body_md,
            body_html=render_markdown(body_md),
            is_draft=is_draft,
            sort_title=sort_key(spec['title']),
            created_by=author_id,
        )

        if spec['published_days_ago'] is not None and not is_draft:
            entry.published_at = _ago(days=spec['published_days_ago'])
            entry.created_at = _ago(days=spec['published_days_ago'])
        else:
            entry.created_at = _ago(days=spec['edits'][0]['days_ago'])

        if spec['edits']:
            most_recent = min(e['days_ago'] for e in spec['edits'])
            entry.updated_at = _ago(days=most_recent)

        db.session.add(entry)
        db.session.flush()
        entry_map[spec['title']] = entry

        for edit_spec in spec.get('edits', []):
            log = EditLog(
                entry_id=entry.id,
                user_id=author_id,
                changelog=edit_spec['changelog'],
            )
            log.edited_at = _ago(days=edit_spec['days_ago'])
            db.session.add(log)

        entries_created += 1

    db.session.flush()

    for spec in TEST_ENTRIES:
        entry = entry_map[spec['title']]
        linked_slugs = extract_internal_links(entry.body_markdown)
        for target_slug in linked_slugs:
            target = Entry.query.filter_by(slug=target_slug).first()
            if target and target.id != entry.id:
                db.session.add(Backlink(
                    source_entry_id=entry.id,
                    target_entry_id=target.id,
                ))

    subs_created = 0
    for sub_spec in TEST_SUBSCRIBERS:
        if User.query.filter_by(email=sub_spec['email']).first():
            continue
        sub_user = User(
            email=sub_spec['email'],
            display_name=sub_spec['email'].split('@')[0],
            role='viewer',
            subscribed=sub_spec['confirmed'],
        )
        sub_user.created_at = _ago(days=sub_spec['days_ago'])
        db.session.add(sub_user)
        subs_created += 1

    invites_created = 0
    for inv_spec in TEST_INVITES:
        inv = Registration(
            email=inv_spec['email'],
            invited_by=user_id,
            accepted=inv_spec['accepted'],
        )
        inv.created_at = _ago(days=inv_spec['days_ago'])
        db.session.add(inv)
        invites_created += 1

    site_settings = SiteSettings.get()
    if site_settings and not site_settings.custom_css:
        site_settings.custom_css = TEST_CUSTOM_CSS
        site_settings.custom_head_html = TEST_CUSTOM_HEAD_HTML
        site_settings.custom_footer_html = TEST_CUSTOM_FOOTER_HTML

    db.session.commit()

    for entry in entry_map.values():
        update_fts_entry(entry)

    parts = [
        f'{entries_created} entries (with backlinks and edit history)',
    ]
    if users_created:
        parts.insert(0, f'{users_created} users')
    parts.append(f'{subs_created} subscribers')
    parts.append(f'{invites_created} invites')
    return entries_created + subs_created + invites_created + users_created, f'Added {", ".join(parts)}.'


def clear_test_data():
    entries = Entry.query.filter(Entry.slug.like(f'{TEST_SLUG_PREFIX}%')).all()
    entry_count = len(entries)
    for entry in entries:
        delete_fts_entry(entry.id)
        db.session.delete(entry)

    invites = Registration.query.filter(Registration.email.like(f'%{TEST_EMAIL_DOMAIN}')).all()
    invite_count = len(invites)
    for inv in invites:
        db.session.delete(inv)

    test_users = User.query.filter(User.email.like(f'%{TEST_EMAIL_DOMAIN}')).all()
    user_count = len(test_users)
    for u in test_users:
        db.session.delete(u)

    site_settings = SiteSettings.get()
    if site_settings:
        if site_settings.custom_css == TEST_CUSTOM_CSS:
            site_settings.custom_css = ''
        if site_settings.custom_head_html == TEST_CUSTOM_HEAD_HTML:
            site_settings.custom_head_html = ''
        if site_settings.custom_footer_html == TEST_CUSTOM_FOOTER_HTML:
            site_settings.custom_footer_html = ''

    db.session.commit()

    total = entry_count + invite_count + user_count
    if total == 0:
        return 0, 'No test data found.'

    parts = []
    if entry_count:
        parts.append(f'{entry_count} entries')
    if user_count:
        parts.append(f'{user_count} users')
    if invite_count:
        parts.append(f'{invite_count} invites')
    return total, f'Removed {", ".join(parts)}.'

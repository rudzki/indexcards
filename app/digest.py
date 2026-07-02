from datetime import datetime, timezone, timedelta

import click
from flask import current_app
from flask.cli import with_appcontext

from app import db
from app.models import Entry, EditLog, User, SiteSettings
from app.mail import send_email, render_email


def register_cli(app):
    app.cli.add_command(send_digest)
    app.cli.add_command(rebuild_fts_cmd)


@click.command('send-digest')
@click.option('--force', is_flag=True, help="Send even if today isn't the configured digest day.")
@with_appcontext
def send_digest(force):
    settings = SiteSettings.query.get(1)
    if not settings:
        click.echo('No site settings found.')
        return

    today = datetime.now(timezone.utc).weekday()  # Monday=0 .. Sunday=6, matches digest_day
    if not force and settings.digest_day != today:
        click.echo(f'Not the configured digest day (today={today}, configured={settings.digest_day}). Skipping.')
        return

    since = datetime.now(timezone.utc) - timedelta(days=7)

    new_entries = (Entry.query
                   .filter(Entry.published_at >= since, Entry.is_draft == False)  # noqa: E712
                   .order_by(Entry.published_at.desc())
                   .all())

    edited_entries = []
    if settings.digest_include_edits:
        logs = (EditLog.query
                .filter(EditLog.edited_at >= since)
                .order_by(EditLog.edited_at.desc())
                .all())
        seen = {e.id for e in new_entries}
        for log in logs:
            entry = Entry.query.get(log.entry_id)
            if entry and not entry.is_draft and entry.id not in seen:
                seen.add(entry.id)
                edited_entries.append((entry, log.changelog))

    if not new_entries and not edited_entries:
        click.echo('Nothing new to send.')
        return

    subscribers = User.query.filter_by(subscribed=True).all()
    if not subscribers:
        click.echo('No subscribers.')
        return

    site_title = settings.site_title or 'Index Cards'
    site_url = current_app.config.get('SITE_URL', 'http://localhost:5000').rstrip('/')

    sent = 0
    for subscriber in subscribers:
        text, html = render_email(
            'digest',
            site_title=site_title,
            site_url=site_url,
            new_entries=new_entries,
            edited_entries=edited_entries,
            unsub_token=subscriber.unsubscribe_token,
        )
        if send_email(
            to=subscriber.email,
            subject=f'{site_title} — Weekly Digest',
            body_text=text,
            body_html=html,
        ):
            sent += 1

    click.echo(f'Digest sent to {sent}/{len(subscribers)} subscriber(s).')


@click.command('rebuild-fts')
@with_appcontext
def rebuild_fts_cmd():
    from app.search import create_fts_table, rebuild_fts
    create_fts_table()
    rebuild_fts()
    click.echo('FTS index rebuilt.')

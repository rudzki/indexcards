from app.models import Entry, entry_url, iso_utc, utcnow


def feeds_available(settings):
    return settings and settings.site_visibility == 'public' and settings.feeds_enabled


def feed_entries():
    db_entries = (Entry.query
                  .filter_by(is_draft=False, is_stub=False, is_listed=True)
                  .filter(Entry.published_at.isnot(None))
                  .order_by(Entry.updated_at.desc())
                  .limit(20)
                  .all())

    def fmt(dt):
        return iso_utc(dt) or ''

    entries = [{
        'title': e.title,
        'url': entry_url(e, external=True),
        'published': fmt(e.published_at),
        'updated': fmt(e.updated_at),
        'summary': e.summary or '',
        'body_html': e.body_html or '',
        'author': e.author.display_name if e.author else '',
    } for e in db_entries]

    most_recent = fmt(db_entries[0].updated_at) if db_entries else fmt(utcnow())
    return entries, most_recent

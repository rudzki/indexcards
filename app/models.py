import re
import secrets
from datetime import datetime, timezone, timedelta

from flask import url_for
from flask_login import UserMixin

from app import db, login_manager

STOP_WORDS = {'the', 'a', 'an'}

DEFAULT_SITE_TITLE = 'Index Cards'


def utcnow():
    """The single datetime convention: naive UTC at the storage boundary.

    SQLite (via SQLAlchemy's DateTime) drops tzinfo on write and returns naive
    values on read, so reloaded rows are always naive. Producing naive UTC here
    too means in-memory objects match reloaded ones — no more mixing aware
    (`+00:00`) and naive values, and no per-call-site tzinfo re-attachment."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso_utc(dt):
    """Serialize a naive-UTC datetime as ISO-8601 with a literal Z, or None when
    dt is falsy. Single convention shared by feeds, the API, and timeago; stored
    timestamps are naive UTC (see utcnow), so the Z is appended, not computed."""
    if not dt:
        return None
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def make_slug(title):
    slug = title.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


# Paths the app owns; a card slug must not collide with one or it would be
# shadowed by (or shadow) a real route. Lives here beside make_slug so both the
# save path and the API quick-create share one list.
RESERVED_SLUGS = {
    'feed', 'search', 'login', 'logout', 'signup', 'subscribe',
    'confirm', 'unsubscribe', 'random', 'healthz', 'admin', 'dashboard',
    'static', 'favicon', 'site-image', 'uploads',
    'notes', 'account', 'setup', 'api',
}


def sort_key(title):
    key = re.sub(r'^[^a-z0-9]+', '', title.lower())
    words = key.split()
    if words:
        first_alpha = re.sub(r'[^a-z0-9]', '', words[0])
        if first_alpha in STOP_WORDS:
            words = words[1:]
            if words:
                words[0] = re.sub(r'^[^a-z0-9]+', '', words[0])
    return ' '.join(words)


def site_requires_login(settings):
    """True when the site restricts viewing to logged-in users — either
    'registered' (any account) or 'admin' (administrators only). Single source of
    truth for the private-site check shared by the request gate (app/__init__.py)
    and the API gate (app/api.py)."""
    return bool(settings and settings.site_visibility in ('registered', 'admin'))


def site_requires_admin(settings):
    """True when the site restricts viewing to administrators only. Implies
    site_requires_login; a logged-in non-admin is still denied."""
    return bool(settings and settings.site_visibility == 'admin')


def set_published(obj, published):
    """Set draft/published state on a card.

    published_at is stamped once, on the first transition into published state,
    and never cleared. Returns True only when this call performed that first
    publish — callers pass it as the 'new entry' signal to integrations."""
    obj.is_draft = not published
    first_publish = published and obj.published_at is None
    if first_publish:
        obj.published_at = utcnow()
    return first_publish


class Entry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.Text, unique=True, nullable=False)
    title = db.Column(db.Text, nullable=False)
    summary = db.Column(db.Text, default='')
    body_markdown = db.Column(db.Text, default='')
    body_html = db.Column(db.Text, default='')
    is_draft = db.Column(db.Boolean, default=False)
    is_stub = db.Column(db.Boolean, default=False)
    # Whether the card joins the stream: index + feeds + digest + API, and fires
    # integrations on publish. An unlisted card (is_listed=False) is standalone
    # content — reachable by direct URL, [[wikilink]], backlink, or the nav — but
    # kept out of the stream. This is what a "page" became when Entry/Page merged.
    is_listed = db.Column(db.Boolean, default=True)
    published_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow,
                           onupdate=utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    sort_title = db.Column(db.Text, default='')
    parent_id = db.Column(db.Integer, db.ForeignKey('entry.id'), nullable=True)

    edit_logs = db.relationship('EditLog', backref='entry', cascade='all, delete-orphan',
                                order_by='EditLog.edited_at.desc()')
    outgoing_links = db.relationship('Backlink', foreign_keys='Backlink.source_entry_id',
                                     backref='source_entry', cascade='all, delete-orphan')
    incoming_links = db.relationship('Backlink', foreign_keys='Backlink.target_entry_id',
                                     backref='target_entry', cascade='all, delete-orphan')
    author = db.relationship('User', backref='entries')

    __table_args__ = (
        db.Index('ix_entry_parent_id', 'parent_id'),
        db.Index('ix_entry_created_by', 'created_by'),
    )

    def update_sort_title(self):
        self.sort_title = sort_key(self.title)

    @property
    def edited_after_publish(self):
        """True only if the entry was meaningfully edited after publication.
        published_at and updated_at are written microseconds apart on the first
        save, so a plain inequality is always true — require a real gap."""
        if not self.updated_at or not self.published_at:
            return False
        return (self.updated_at - self.published_at).total_seconds() > 60


def entry_url(obj, external=False):
    """Build the canonical URL for a card. A child entry (one with a parent) is
    addressed as /<parent-slug>/<child-slug>/ instead of the flat /<slug>/ so
    the URL reflects the hierarchy already present in the data."""
    parent = getattr(obj, 'parent', None)
    if parent:
        return url_for('main.child_entry_page', parent_slug=parent.slug, slug=obj.slug, _external=external)
    return url_for('main.entry_page', slug=obj.slug, _external=external)


class EditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('entry.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    changelog = db.Column(db.Text)
    is_import = db.Column(db.Boolean, default=False)
    edited_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship('User')

    __table_args__ = (
        db.Index('ix_edit_log_entry_id', 'entry_id'),
    )


class Backlink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source_entry_id = db.Column(db.Integer, db.ForeignKey('entry.id'), nullable=False)
    target_entry_id = db.Column(db.Integer, db.ForeignKey('entry.id'), nullable=False)

    __table_args__ = (
        db.Index('ix_backlink_source_entry_id', 'source_entry_id'),
        db.Index('ix_backlink_target_entry_id', 'target_entry_id'),
    )


class EditLock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content_type = db.Column(db.Text, nullable=False)  # 'entry' or 'page'
    content_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)

    user = db.relationship('User')

    __table_args__ = (
        db.UniqueConstraint('content_type', 'content_id', name='uq_edit_lock_content'),
    )


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.Text, unique=True, nullable=False)
    display_name = db.Column(db.Text, nullable=False)
    role = db.Column(db.Text, default='author')
    bio = db.Column(db.Text, default='')
    link = db.Column(db.Text, default='')
    subscribed = db.Column(db.Boolean, default=False)
    unsubscribe_token = db.Column(db.Text, unique=True,
                                  default=lambda: secrets.token_urlsafe(32))
    login_token = db.Column(db.Text, unique=True)
    login_token_expires = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_editor(self):
        return self.role == 'editor'

    @property
    def is_author(self):
        return self.role == 'author'

    @property
    def is_viewer(self):
        return self.role == 'viewer'

    @property
    def can_write(self):
        return self.role in ('admin', 'editor', 'author')

    def can_modify(self, entry):
        if self.role == 'admin':
            return True
        if self.role == 'editor':
            # Editors are trusted with all content, including entries and pages
            # authored by an admin — they can edit and delete anything.
            return True
        if self.role == 'author':
            return entry.created_by == self.id
        return False

    def generate_login_token(self):
        self.login_token = secrets.token_urlsafe(32)
        self.login_token_expires = utcnow() + timedelta(minutes=15)
        return self.login_token

    def clear_login_token(self):
        self.login_token = None
        self.login_token_expires = None

    @property
    def token_valid(self):
        if not self.login_token or not self.login_token_expires:
            return False
        return utcnow() < self.login_token_expires


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


REGISTRATION_TTL = timedelta(days=14)


class Registration(db.Model):
    __tablename__ = 'registration'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.Text, nullable=False)
    token = db.Column(db.Text, unique=True, nullable=False,
                      default=lambda: secrets.token_urlsafe(32))
    invited_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    role = db.Column(db.Text, nullable=True)
    accepted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    inviter = db.relationship('User')

    @property
    def is_expired(self):
        """Invite/signup tokens are only valid for REGISTRATION_TTL after
        creation — a leaked old invite email must not stay a usable
        account-creation credential forever."""
        if self.accepted:
            return True
        if not self.created_at:
            return False
        return utcnow() > self.created_at + REGISTRATION_TTL


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.Text, nullable=False)
    detail = db.Column(db.Text, default='')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship('User')


def log_audit(action, detail='', user_id=None):
    entry = AuditLog(action=action, detail=detail, user_id=user_id)
    db.session.add(entry)
    db.session.commit()


class NavItem(db.Model):
    """A curated nav slot pointing at a card. Nav membership/position is a
    site-layout decision, orthogonal to is_listed — any published card (listed
    or not) can be added. Ordered by position (nulls last)."""
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('entry.id'), nullable=False)
    position = db.Column(db.Integer, nullable=True)

    entry = db.relationship('Entry')

    __table_args__ = (
        db.Index('ix_nav_item_entry_id', 'entry_id'),
    )


class SiteSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    site_title = db.Column(db.Text, default=DEFAULT_SITE_TITLE)
    digest_include_edits = db.Column(db.Boolean, default=False)
    digest_day = db.Column(db.Integer, default=0)
    search_enabled = db.Column(db.Boolean, default=True)
    subscribe_enabled = db.Column(db.Boolean, default=True)
    footer_text = db.Column(db.Text, default='')
    announcement_banner = db.Column(db.Text, default='')
    multiuser_enabled = db.Column(db.Boolean, default=False)
    registration_method = db.Column(db.Text, default='invite')
    registration_domain = db.Column(db.Text, default='')
    default_role = db.Column(db.Text, default='viewer')
    site_visibility = db.Column(db.Text, default='public')
    show_authors = db.Column(db.Boolean, default=False)
    show_history = db.Column(db.Boolean, default=True)
    alpha_jump_enabled = db.Column(db.Boolean, default=True)
    subpage_display = db.Column(db.Text, default='both')
    feeds_enabled = db.Column(db.Boolean, default=True)
    site_icon = db.Column(db.Text, default='')
    site_image = db.Column(db.Text, default='')
    smtp_host = db.Column(db.Text)
    smtp_port = db.Column(db.Integer)
    smtp_username = db.Column(db.Text)
    smtp_password = db.Column(db.Text)
    smtp_use_tls = db.Column(db.Boolean, default=True)
    smtp_from_address = db.Column(db.Text)

    site_theme = db.Column(db.Text, default='default')
    default_color_mode = db.Column(db.Text, default='dark')
    custom_css = db.Column(db.Text, default='')
    custom_head_html = db.Column(db.Text, default='')
    custom_footer_html = db.Column(db.Text, default='')

    # Integrations
    mailchimp_api_key = db.Column(db.Text, default='')
    mailchimp_server_prefix = db.Column(db.Text, default='')
    mailchimp_list_id = db.Column(db.Text, default='')
    slack_webhook_url = db.Column(db.Text, default='')
    slack_announce_new = db.Column(db.Boolean, default=True)
    slack_announce_updates = db.Column(db.Boolean, default=False)
    outgoing_webhook_url = db.Column(db.Text, default='')
    outgoing_webhook_secret = db.Column(db.Text, default='')

    @classmethod
    def get(cls):
        """The site-settings singleton (row 1). Single accessor so the row-1
        convention lives in exactly one place instead of 27 call sites."""
        return db.session.get(cls, 1)

    @property
    def display_title(self):
        """The site title with the default applied — never blank."""
        return self.site_title or DEFAULT_SITE_TITLE

    @property
    def mailchimp_configured(self):
        return bool(self.mailchimp_api_key and self.mailchimp_server_prefix and self.mailchimp_list_id)

    @property
    def slack_configured(self):
        return bool(self.slack_webhook_url)

    @property
    def smtp_configured(self):
        return bool(self.smtp_host and self.smtp_from_address)


# Self-referential adjacency list for Entry hierarchy
Entry.children = db.relationship(
    'Entry',
    foreign_keys=[Entry.parent_id],
    backref=db.backref('parent', remote_side=[Entry.id]),
    order_by=Entry.sort_title,
)

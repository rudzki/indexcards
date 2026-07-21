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
    'notes', 'account', 'setup', 'api', 'groups', 'about',
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


def groups_feature_enabled(settings):
    """True when the groups feature is active. Gated by BOTH the multi-user
    switch and the groups switch — groups need real user accounts to mean
    anything, so multi-user is a genuine dependency, not just UI nesting. Single
    source of truth for every groups surface (access filtering, admin UI, the
    public /groups page, badges)."""
    return bool(settings and settings.multiuser_enabled and settings.groups_enabled)


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


# Many-to-many join tables for the groups feature. Defined before Entry/User so
# they're in scope for the relationship() calls below. Rows cascade on delete so
# removing a group (or entry/user) doesn't leave dangling association rows —
# SQLite FK enforcement is off, so the cascade is enforced by us deleting the
# owning row via the ORM, which issues the secondary DELETEs.
entry_groups = db.Table(
    'entry_groups',
    db.Column('entry_id', db.Integer, db.ForeignKey('entry.id', ondelete='CASCADE'), primary_key=True),
    db.Column('group_id', db.Integer, db.ForeignKey('group.id', ondelete='CASCADE'), primary_key=True),
)

group_members = db.Table(
    'group_members',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True),
    db.Column('group_id', db.Integer, db.ForeignKey('group.id', ondelete='CASCADE'), primary_key=True),
)


class Entry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.Text, unique=True, nullable=False)
    title = db.Column(db.Text, nullable=False)
    summary = db.Column(db.Text, default='')
    body_markdown = db.Column(db.Text, default='')
    body_html = db.Column(db.Text, default='')
    is_draft = db.Column(db.Boolean, default=False)
    is_stub = db.Column(db.Boolean, default=False)
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
    # Groups this entry is restricted to. Empty == public (subject to the usual
    # is_draft/site_visibility gates). Non-empty == readable only by
    # members of one of these groups (plus admins / All-Groups users). See
    # user_can_read_entry / accessible_entries_filter.
    groups = db.relationship('Group', secondary=entry_groups, backref='entries')

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
    # All-Groups grant: this user can read every grouped entry regardless of
    # explicit membership (distinct from admin, which also bypasses).
    all_groups = db.Column(db.Boolean, default=False)
    # Uploaded avatar filename (lives in the uploads dir, served via
    # /uploads/<filename>). Empty/None when the user hasn't set one.
    avatar = db.Column(db.Text, default='')

    groups = db.relationship('Group', secondary=group_members, backref='members')

    @property
    def avatar_url(self):
        """Public URL of the user's avatar, or None when unset. The stored
        filename is a random 32-hex name so it serves through the existing
        /uploads/ route (which validates that shape)."""
        if not self.avatar:
            return None
        return url_for('main.uploaded_file', filename=self.avatar)

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
    site-layout decision — any published card can be added. Ordered by position
    (nulls last)."""
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('entry.id'), nullable=False)
    position = db.Column(db.Integer, nullable=True)

    entry = db.relationship('Entry')

    __table_args__ = (
        db.Index('ix_nav_item_entry_id', 'entry_id'),
    )


class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, unique=True, nullable=False)
    slug = db.Column(db.Text, unique=True, nullable=False)
    description = db.Column(db.Text, default='')
    color = db.Column(db.Text, default='#6b7785')  # hex, for the badge
    created_at = db.Column(db.DateTime, default=utcnow)


class GroupJoinRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.Text, default='pending')  # pending | approved | denied
    created_at = db.Column(db.DateTime, default=utcnow)
    decided_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    decided_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', foreign_keys=[user_id], backref='join_requests')
    group = db.relationship('Group', backref='join_requests')
    decider = db.relationship('User', foreign_keys=[decided_by])

    __table_args__ = (
        db.Index('ix_join_request_group_status', 'group_id', 'status'),
        db.Index('ix_join_request_user', 'user_id'),
    )


def user_can_read_entry(user, entry):
    """Whether `user` may read `entry` under the groups predicate. Used for the
    single-entry 404 decision. Layered on top of is_draft/site visibility —
    this only ever *removes* access for a grouped entry.

    When the feature is off, groups are ignored entirely (option A): grouped
    entries fall back to normal visibility."""
    settings = SiteSettings.get()
    if not groups_feature_enabled(settings):
        return True
    if not entry.groups:  # public (ungrouped) content
        return True
    if user and user.is_authenticated and (user.is_admin or user.all_groups):
        return True
    if user and user.is_authenticated:
        member_ids = {g.id for g in user.groups}
        return any(g.id in member_ids for g in entry.groups)
    return False


def accessible_entries_filter(user):
    """A SQLAlchemy clause to `.filter()` any Entry query so grouped entries the
    `user` can't read are dropped. Mirrors user_can_read_entry in set form. When
    the feature is off, returns a true() no-op so callers need no branching."""
    from sqlalchemy import true
    settings = SiteSettings.get()
    if not groups_feature_enabled(settings):
        return true()
    if user and user.is_authenticated and (user.is_admin or user.all_groups):
        return true()
    ungrouped = ~Entry.groups.any()
    if user and user.is_authenticated:
        member_ids = [g.id for g in user.groups]
        if member_ids:
            return db.or_(ungrouped, Entry.groups.any(Group.id.in_(member_ids)))
    return ungrouped


def assignable_groups(user):
    """Groups `user` may tag an entry with. A writer can only assign groups they
    can already read, so they can never lock themselves out of their own entry:
    admins / All-Groups users get every group; everyone else gets the groups they
    belong to. Empty when the feature is off. Ordered by name for the picker."""
    settings = SiteSettings.get()
    if not groups_feature_enabled(settings):
        return []
    if user and user.is_authenticated and (user.is_admin or user.all_groups):
        return Group.query.order_by(Group.name).all()
    if user and user.is_authenticated:
        return sorted(user.groups, key=lambda g: g.name)
    return []


class SiteSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    site_title = db.Column(db.Text, default=DEFAULT_SITE_TITLE)
    digest_include_edits = db.Column(db.Boolean, default=False)
    digest_day = db.Column(db.Integer, default=0)
    search_enabled = db.Column(db.Boolean, default=True)
    subscribe_enabled = db.Column(db.Boolean, default=True)
    footer_text = db.Column(db.Text, default='')          # "Colophon" in the UI
    announcement_banner = db.Column(db.Text, default='')
    epigraph = db.Column(db.Text, default='')             # homepage intro
    about_markdown = db.Column(db.Text, default='')       # /about page body
    multiuser_enabled = db.Column(db.Boolean, default=False)
    # "Enable groups" — only meaningful when multiuser_enabled is also on (see
    # groups_feature_enabled). Off by default.
    groups_enabled = db.Column(db.Boolean, default=False)
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

import re
import secrets
from datetime import datetime, timezone, timedelta

from flask_login import UserMixin

from app import db, login_manager

STOP_WORDS = {'the', 'a', 'an'}


def _hex_to_hsl(hex_color):
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        return 0.0, 0.0, l
    d = mx - mn
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        hue = (g - b) / d + (6 if g < b else 0)
    elif mx == g:
        hue = (b - r) / d + 2
    else:
        hue = (r - g) / d + 4
    return hue / 6, s, l


def _hsl_to_hex(hue, s, l):
    if s == 0:
        v = int(round(l * 255))
        return f'#{v:02x}{v:02x}{v:02x}'
    def _c(p, q, t):
        t = t % 1
        if t < 1 / 6: return p + (q - p) * 6 * t
        if t < 1 / 2: return q
        if t < 2 / 3: return p + (q - p) * (2 / 3 - t) * 6
        return p
    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    r = int(round(_c(p, q, hue + 1 / 3) * 255))
    g = int(round(_c(p, q, hue) * 255))
    b = int(round(_c(p, q, hue - 1 / 3) * 255))
    return f'#{r:02x}{g:02x}{b:02x}'


def make_slug(title):
    slug = title.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


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


class Entry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.Text, unique=True, nullable=False)
    title = db.Column(db.Text, nullable=False)
    summary = db.Column(db.Text, default='')
    body_markdown = db.Column(db.Text, default='')
    body_html = db.Column(db.Text, default='')
    is_draft = db.Column(db.Boolean, default=False)
    published_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    sort_title = db.Column(db.Text, default='')

    aliases = db.relationship('Alias', backref='entry', cascade='all, delete-orphan')
    edit_logs = db.relationship('EditLog', backref='entry', cascade='all, delete-orphan',
                                order_by='EditLog.edited_at.desc()')
    outgoing_links = db.relationship('Backlink', foreign_keys='Backlink.source_entry_id',
                                     backref='source_entry', cascade='all, delete-orphan')
    incoming_links = db.relationship('Backlink', foreign_keys='Backlink.target_entry_id',
                                     backref='target_entry', cascade='all, delete-orphan')
    author = db.relationship('User', backref='entries')

    def update_sort_title(self):
        self.sort_title = sort_key(self.title)


class Alias(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('entry.id'), nullable=False)
    title = db.Column(db.Text, nullable=False)
    slug = db.Column(db.Text, unique=True, nullable=False)


class EditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('entry.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    changelog = db.Column(db.Text)
    edited_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User')


class Backlink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source_entry_id = db.Column(db.Integer, db.ForeignKey('entry.id'), nullable=False)
    target_entry_id = db.Column(db.Integer, db.ForeignKey('entry.id'), nullable=False)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.Text, unique=True, nullable=False)
    display_name = db.Column(db.Text, nullable=False)
    role = db.Column(db.Text, default='author')
    bio = db.Column(db.Text, default='')
    subscribed = db.Column(db.Boolean, default=False)
    unsubscribe_token = db.Column(db.Text, unique=True,
                                  default=lambda: secrets.token_urlsafe(32))
    login_token = db.Column(db.Text, unique=True)
    login_token_expires = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

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
            return not entry.author or entry.author.role != 'admin'
        if self.role == 'author':
            return entry.created_by == self.id
        return False

    def generate_login_token(self):
        self.login_token = secrets.token_urlsafe(32)
        self.login_token_expires = datetime.now(timezone.utc) + timedelta(minutes=15)
        return self.login_token

    def clear_login_token(self):
        self.login_token = None
        self.login_token_expires = None

    @property
    def token_valid(self):
        if not self.login_token or not self.login_token_expires:
            return False
        now = datetime.now(timezone.utc)
        expires = self.login_token_expires
        if expires.tzinfo is None:
            from datetime import timezone as tz
            expires = expires.replace(tzinfo=tz.utc)
        return now < expires


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Registration(db.Model):
    __tablename__ = 'registration'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.Text, nullable=False)
    token = db.Column(db.Text, unique=True, nullable=False,
                      default=lambda: secrets.token_urlsafe(32))
    invited_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    role = db.Column(db.Text, nullable=True)
    accepted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    inviter = db.relationship('User')


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.Text, nullable=False)
    detail = db.Column(db.Text, default='')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User')


def log_audit(action, detail='', user_id=None):
    entry = AuditLog(action=action, detail=detail, user_id=user_id)
    db.session.add(entry)
    db.session.commit()


class SiteSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    site_title = db.Column(db.Text, default='Index Cards')
    about_markdown = db.Column(db.Text, default='')
    about_html = db.Column(db.Text, default='')
    digest_include_edits = db.Column(db.Boolean, default=False)
    digest_day = db.Column(db.Integer, default=0)
    search_enabled = db.Column(db.Boolean, default=True)
    subscribe_enabled = db.Column(db.Boolean, default=True)
    footer_text = db.Column(db.Text, default='')
    multiuser_enabled = db.Column(db.Boolean, default=False)
    registration_method = db.Column(db.Text, default='invite')
    registration_domain = db.Column(db.Text, default='')
    default_role = db.Column(db.Text, default='viewer')
    site_visibility = db.Column(db.Text, default='public')
    show_authors = db.Column(db.Boolean, default=False)
    show_history = db.Column(db.Boolean, default=True)
    site_icon = db.Column(db.Text, default='')
    site_image = db.Column(db.Text, default='')
    smtp_host = db.Column(db.Text)
    smtp_port = db.Column(db.Integer)
    smtp_username = db.Column(db.Text)
    smtp_password = db.Column(db.Text)
    smtp_use_tls = db.Column(db.Boolean, default=True)
    smtp_from_address = db.Column(db.Text)

    brand_color = db.Column(db.Text, default='')
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

    @property
    def mailchimp_configured(self):
        return bool(self.mailchimp_api_key and self.mailchimp_server_prefix and self.mailchimp_list_id)

    @property
    def slack_configured(self):
        return bool(self.slack_webhook_url)

    @property
    def smtp_configured(self):
        return bool(self.smtp_host and self.smtp_from_address)

    @property
    def brand_color_light(self):
        """Darkened version of brand_color for use on light backgrounds."""
        if not self.brand_color:
            return ''
        h, s, l = _hex_to_hsl(self.brand_color)
        target_l = min(l, 0.42)
        return _hsl_to_hex(h, min(s, 0.85), target_l)

    @property
    def brand_color_ink(self):
        """Contrasting ink color for text on a brand-colored background."""
        if not self.brand_color:
            return ''
        _, _, l = _hex_to_hsl(self.brand_color)
        return '#0d1117' if l > 0.5 else '#ffffff'

    @property
    def brand_color_bg(self):
        """Semi-transparent tint for focus rings and active backgrounds."""
        if not self.brand_color:
            return ''
        h = self.brand_color.lstrip('#')
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f'rgba({r}, {g}, {b}, .12)'

import os

from app import db

try:
    import fcntl
except ImportError:  # non-POSIX (e.g. Windows); locking is best-effort
    fcntl = None


def run_migrations():
    """Run the hand-rolled migrations under a cross-process file lock.

    create_app() calls this on every boot, and gunicorn starts several worker
    processes at once. Without a lock, two workers can both pass has_column()
    and both ALTER TABLE, crashing one with "duplicate column name". An
    exclusive flock serializes them: the first migrates, the rest wait and then
    find the work already done. Covers the sort_title rewrite loop too."""
    if fcntl is None:
        return _run_migrations()

    db_path = db.engine.url.database
    lock_dir = os.path.dirname(os.path.abspath(db_path)) if db_path else '.'
    os.makedirs(lock_dir, exist_ok=True)
    lock_path = os.path.join(lock_dir, '.migrate.lock')

    with open(lock_path, 'w') as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            _run_migrations()
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _run_migrations():
    conn = db.engine.raw_connection()
    cursor = conn.cursor()

    def has_column(table, column):
        cursor.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cursor.fetchall())

    def has_table(name):
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
        return cursor.fetchone() is not None

    if has_table('user') and not has_column('user', 'role'):
        cursor.execute("ALTER TABLE user ADD COLUMN role TEXT DEFAULT 'author'")
        cursor.execute("UPDATE user SET role = 'admin' WHERE is_admin = 1")
        cursor.execute("UPDATE user SET role = 'author' WHERE is_admin = 0 OR is_admin IS NULL")

    if has_table('invite') and not has_table('registration'):
        cursor.execute("ALTER TABLE invite RENAME TO registration")

    if has_table('registration') and not has_column('registration', 'invited_by'):
        cursor.execute("ALTER TABLE registration ADD COLUMN invited_by INTEGER")

    if has_table('registration') and not has_column('registration', 'role'):
        cursor.execute("ALTER TABLE registration ADD COLUMN role TEXT")

    if has_table('user') and not has_column('user', 'subscribed'):
        cursor.execute("ALTER TABLE user ADD COLUMN subscribed BOOLEAN DEFAULT 0")
        cursor.execute("ALTER TABLE user ADD COLUMN unsubscribe_token TEXT")

    if has_table('subscriber') and has_table('user') and has_column('user', 'subscribed'):
        cursor.execute("SELECT email, unsubscribe_token FROM subscriber WHERE confirmed = 1")
        for row in cursor.fetchall():
            email, unsub_token = row
            cursor.execute("SELECT id FROM user WHERE email = ?", (email,))
            existing = cursor.fetchone()
            if existing:
                cursor.execute("UPDATE user SET subscribed = 1, unsubscribe_token = ? WHERE id = ?",
                               (unsub_token, existing[0]))
            else:
                import secrets
                display_name = email.split('@')[0]
                cursor.execute(
                    "INSERT INTO user (email, display_name, role, subscribed, unsubscribe_token) "
                    "VALUES (?, ?, 'viewer', 1, ?)",
                    (email, display_name, unsub_token))

    if has_table('user') and not has_column('user', 'bio'):
        cursor.execute("ALTER TABLE user ADD COLUMN bio TEXT DEFAULT ''")

    if has_table('site_settings'):
        if not has_column('site_settings', 'multiuser_enabled'):
            cursor.execute("ALTER TABLE site_settings ADD COLUMN multiuser_enabled BOOLEAN DEFAULT 0")
            if has_column('site_settings', 'invites_enabled'):
                cursor.execute("UPDATE site_settings SET multiuser_enabled = invites_enabled")
        if not has_column('site_settings', 'registration_method'):
            cursor.execute("ALTER TABLE site_settings ADD COLUMN registration_method TEXT DEFAULT 'invite'")
        if not has_column('site_settings', 'registration_domain'):
            cursor.execute("ALTER TABLE site_settings ADD COLUMN registration_domain TEXT DEFAULT ''")
        if not has_column('site_settings', 'default_role'):
            cursor.execute("ALTER TABLE site_settings ADD COLUMN default_role TEXT DEFAULT 'viewer'")
        if not has_column('site_settings', 'site_visibility'):
            cursor.execute("ALTER TABLE site_settings ADD COLUMN site_visibility TEXT DEFAULT 'public'")
        if not has_column('site_settings', 'show_authors'):
            cursor.execute("ALTER TABLE site_settings ADD COLUMN show_authors BOOLEAN DEFAULT 0")
        if not has_column('site_settings', 'show_history'):
            cursor.execute("ALTER TABLE site_settings ADD COLUMN show_history BOOLEAN DEFAULT 1")
        if not has_column('site_settings', 'alpha_jump_enabled'):
            cursor.execute("ALTER TABLE site_settings ADD COLUMN alpha_jump_enabled BOOLEAN DEFAULT 1")
        if not has_column('site_settings', 'feeds_enabled'):
            cursor.execute("ALTER TABLE site_settings ADD COLUMN feeds_enabled BOOLEAN DEFAULT 1")

    if has_table('site_settings') and not has_column('site_settings', 'site_icon'):
        cursor.execute("ALTER TABLE site_settings ADD COLUMN site_icon TEXT DEFAULT ''")
    if has_table('site_settings') and not has_column('site_settings', 'site_image'):
        cursor.execute("ALTER TABLE site_settings ADD COLUMN site_image TEXT DEFAULT ''")

    if has_table('site_settings') and not has_column('site_settings', 'brand_color'):
        cursor.execute("ALTER TABLE site_settings ADD COLUMN brand_color TEXT DEFAULT ''")

    if has_table('site_settings'):
        if not has_column('site_settings', 'mailchimp_api_key'):
            cursor.execute("ALTER TABLE site_settings ADD COLUMN mailchimp_api_key TEXT DEFAULT ''")
        if not has_column('site_settings', 'mailchimp_server_prefix'):
            cursor.execute("ALTER TABLE site_settings ADD COLUMN mailchimp_server_prefix TEXT DEFAULT ''")
        if not has_column('site_settings', 'mailchimp_list_id'):
            cursor.execute("ALTER TABLE site_settings ADD COLUMN mailchimp_list_id TEXT DEFAULT ''")
        if not has_column('site_settings', 'slack_webhook_url'):
            cursor.execute("ALTER TABLE site_settings ADD COLUMN slack_webhook_url TEXT DEFAULT ''")
        if not has_column('site_settings', 'slack_announce_new'):
            cursor.execute("ALTER TABLE site_settings ADD COLUMN slack_announce_new INTEGER DEFAULT 1")
        if not has_column('site_settings', 'slack_announce_updates'):
            cursor.execute("ALTER TABLE site_settings ADD COLUMN slack_announce_updates INTEGER DEFAULT 0")
        if not has_column('site_settings', 'outgoing_webhook_url'):
            cursor.execute("ALTER TABLE site_settings ADD COLUMN outgoing_webhook_url TEXT DEFAULT ''")
        if not has_column('site_settings', 'outgoing_webhook_secret'):
            cursor.execute("ALTER TABLE site_settings ADD COLUMN outgoing_webhook_secret TEXT DEFAULT ''")

    if not has_table('page'):
        cursor.execute("""
            CREATE TABLE page (
                id INTEGER PRIMARY KEY,
                slug TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                summary TEXT DEFAULT '',
                body_markdown TEXT DEFAULT '',
                body_html TEXT DEFAULT '',
                is_draft BOOLEAN DEFAULT 0,
                is_stub BOOLEAN DEFAULT 0,
                published_at DATETIME,
                created_at DATETIME,
                updated_at DATETIME,
                created_by INTEGER REFERENCES user(id),
                sort_title TEXT DEFAULT '',
                show_in_nav BOOLEAN DEFAULT 0,
                nav_position INTEGER
            )
        """)

    if not has_table('edit_lock'):
        cursor.execute("""
            CREATE TABLE edit_lock (
                id INTEGER PRIMARY KEY,
                content_type TEXT NOT NULL,
                content_id INTEGER NOT NULL,
                user_id INTEGER REFERENCES user(id),
                expires_at DATETIME NOT NULL
            )
        """)
        cursor.execute("CREATE UNIQUE INDEX uq_edit_lock_content ON edit_lock (content_type, content_id)")

    if has_table('entry'):
        from app.models import sort_key as _sort_key
        cursor.execute("SELECT id, title, sort_title FROM entry")
        for entry_id, title, old_key in cursor.fetchall():
            new_key = _sort_key(title)
            if new_key != old_key:
                cursor.execute("UPDATE entry SET sort_title = ? WHERE id = ?", (new_key, entry_id))

    if has_table('edit_log') and not has_column('edit_log', 'body_snapshot'):
        cursor.execute("ALTER TABLE edit_log ADD COLUMN body_snapshot TEXT")

    if has_table('entry') and not has_column('entry', 'parent_id'):
        cursor.execute("ALTER TABLE entry ADD COLUMN parent_id INTEGER REFERENCES entry(id)")

    if has_table('site_settings') and not has_column('site_settings', 'site_theme'):
        cursor.execute("ALTER TABLE site_settings ADD COLUMN site_theme TEXT DEFAULT 'default'")

    if has_table('user') and not has_column('user', 'link'):
        cursor.execute("ALTER TABLE user ADD COLUMN link TEXT DEFAULT ''")

    if not has_table('page_revision'):
        cursor.execute("""
            CREATE TABLE page_revision (
                id INTEGER PRIMARY KEY,
                page_id INTEGER NOT NULL REFERENCES page(id),
                user_id INTEGER REFERENCES user(id),
                body_snapshot TEXT DEFAULT '',
                changelog TEXT,
                edited_at DATETIME
            )
        """)

    if has_table('site_settings') and not has_column('site_settings', 'subpage_display'):
        cursor.execute("ALTER TABLE site_settings ADD COLUMN subpage_display TEXT DEFAULT 'both'")

    if has_table('site_settings') and not has_column('site_settings', 'default_color_mode'):
        cursor.execute("ALTER TABLE site_settings ADD COLUMN default_color_mode TEXT DEFAULT 'dark'")

    if has_table('entry') and not has_column('entry', 'is_stub'):
        cursor.execute("ALTER TABLE entry ADD COLUMN is_stub BOOLEAN DEFAULT 0")

    if has_table('page') and not has_column('page', 'is_stub'):
        cursor.execute("ALTER TABLE page ADD COLUMN is_stub BOOLEAN DEFAULT 0")

    if has_table('site_settings') and not has_column('site_settings', 'notes_enabled'):
        cursor.execute("ALTER TABLE site_settings ADD COLUMN notes_enabled BOOLEAN DEFAULT 0")

    if not has_table('note'):
        cursor.execute("""
            CREATE TABLE note (
                id INTEGER PRIMARY KEY,
                body_markdown TEXT DEFAULT '',
                body_html TEXT DEFAULT '',
                is_draft BOOLEAN DEFAULT 0,
                published_at DATETIME,
                created_at DATETIME,
                updated_at DATETIME,
                created_by INTEGER REFERENCES user(id)
            )
        """)

    if not has_table('note_backlink'):
        cursor.execute("""
            CREATE TABLE note_backlink (
                id INTEGER PRIMARY KEY,
                note_id INTEGER NOT NULL REFERENCES note(id),
                target_entry_id INTEGER NOT NULL REFERENCES entry(id)
            )
        """)

    if has_table('edit_log') and not has_column('edit_log', 'is_import'):
        cursor.execute("ALTER TABLE edit_log ADD COLUMN is_import BOOLEAN DEFAULT 0")
        cursor.execute("UPDATE edit_log SET is_import = 1 WHERE changelog = 'Imported'")

    def ensure_index(name, table, column):
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,))
        if not cursor.fetchone():
            cursor.execute(f"CREATE INDEX {name} ON {table} ({column})")

    if has_table('backlink'):
        ensure_index('ix_backlink_source_entry_id', 'backlink', 'source_entry_id')
        ensure_index('ix_backlink_target_entry_id', 'backlink', 'target_entry_id')
    if has_table('edit_log'):
        ensure_index('ix_edit_log_entry_id', 'edit_log', 'entry_id')
    if has_table('entry'):
        ensure_index('ix_entry_parent_id', 'entry', 'parent_id')
        ensure_index('ix_entry_created_by', 'entry', 'created_by')

    conn.commit()
    conn.close()

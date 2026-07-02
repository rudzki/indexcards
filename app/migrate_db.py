from app import db


def run_migrations():
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

    conn.commit()
    conn.close()

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

    if has_table('site_settings') and not has_column('site_settings', 'site_icon'):
        cursor.execute("ALTER TABLE site_settings ADD COLUMN site_icon TEXT DEFAULT ''")
    if has_table('site_settings') and not has_column('site_settings', 'site_image'):
        cursor.execute("ALTER TABLE site_settings ADD COLUMN site_image TEXT DEFAULT ''")

    if has_table('site_settings') and not has_column('site_settings', 'brand_color'):
        cursor.execute("ALTER TABLE site_settings ADD COLUMN brand_color TEXT DEFAULT ''")

    if has_table('site_settings'):
        for col, defval in [
            ('mailchimp_api_key', "''"),
            ('mailchimp_server_prefix', "''"),
            ('mailchimp_list_id', "''"),
            ('slack_webhook_url', "''"),
            ('slack_announce_new', '1'),
            ('slack_announce_updates', '0'),
            ('outgoing_webhook_url', "''"),
            ('outgoing_webhook_secret', "''"),
        ]:
            if not has_column('site_settings', col):
                cursor.execute(f"ALTER TABLE site_settings ADD COLUMN {col} TEXT DEFAULT {defval}")

    if has_table('entry'):
        from app.models import sort_key as _sort_key
        cursor.execute("SELECT id, title, sort_title FROM entry")
        for entry_id, title, old_key in cursor.fetchall():
            new_key = _sort_key(title)
            if new_key != old_key:
                cursor.execute("UPDATE entry SET sort_title = ? WHERE id = ?", (new_key, entry_id))

    conn.commit()
    conn.close()

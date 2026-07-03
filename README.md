# Index Cards

Index Cards is a mindfully designed self-hosted web app for keeping a personal or small-team knowledge base. Pages link to each other like a wiki (aliases, backlinks, hierarchy), but entries are drafted, published, and shipped out over feeds and a weekly email digest, like a blog.

Passwordless login (email magic links), full-text search, a modern WYSIWYG
editor with Markdown import/export, and optional integrations with Slack,
Mailchimp, and webhooks.

## Features

- **Wiki-style entries** — titles, aliases, automatic backlinks, optional parent/child hierarchy
- **Blog-style publishing** — drafts, publish dates, edit history with restore, RSS/Atom/JSON feeds
- **Passwordless auth** — magic-link login by email, roles: admin / editor / author / viewer
- **Full-text search** — SQLite FTS5 with ranked results and highlighted snippets
- **WYSIWYG editing** — Modern ProseMirror-based editor with Markdown import/export
- **Email digest** — weekly roundup of new/updated entries for subscribers
- **Integrations** — Slack announcements, Mailchimp subscriber sync, outgoing webhooks (HMAC-signed)
- **Static pages** — Pages with their own nav placement and history
- **Themeable** — several built-in color themes plus custom CSS/head/footer injection

See [TECHNICAL.md](TECHNICAL.md) for architecture details, the data model, and
the full route inventory.

## Requirements

- Python 3.11+
- SQLite (bundled with Python; no separate server needed)

## Local development

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp env.example .env
# generate a SECRET_KEY and paste it into .env:
python3 -c "import secrets; print(secrets.token_hex(32))"

python3 run.py
```

Open `http://localhost:5000`. The first request routes you to a setup wizard
that creates the initial admin account. Database tables are created
automatically on first boot — no manual migration step needed.

## Deployment

`deploy/setup.sh` provisions a standalone Ubuntu/Debian server: nginx, gunicorn,
systemd (including a timer for the weekly digest), and a Let's Encrypt
certificate. Works from any install path — clone or copy the repo to wherever
you want it to live, then run the script from inside that checkout. See
[deploy/README.md](deploy/README.md) for the full walkthrough and
[TECHNICAL.md](TECHNICAL.md) for architecture details.

```bash
sudo bash deploy/setup.sh
```

## Project layout

```
app/
  views/               blueprints (routes only — business logic lives in the modules below)
    auth.py             login, signup, setup wizard
    account.py           /account — user profile
    main.py               public site — entries, pages, search, feeds, uploads
    admin.py               /dashboard blueprint + admin_required/writer_required/editor_required decorators
    admin_entries.py        entry CRUD, publish, history
    admin_pages.py           page CRUD, publish, history
    admin_users.py            users, roles, registrations
    admin_settings.py          site settings, image upload
    admin_import_export.py      markdown/JSON export, JSON/WordPress import
  entries.py           entry save/validate/import logic + backlink sync
  pages.py             page save/validate logic
  revisions.py          shared diff/history helpers used by entries and pages
  locks.py               soft edit-locking (EditLock)
  registration.py          invite/signup role resolution
  feeds.py                RSS/Atom/JSON feed data
  wordpress_import.py      WordPress export XML parser
  api.py               JSON API (public read endpoints + editor helpers)
  models.py             SQLAlchemy models
  markdown.py           Markdown rendering + sanitization
  search.py             SQLite FTS5 full-text search
  digest.py             weekly digest CLI command
  mail.py               SMTP sending (falls back to console output if unconfigured)
  integrations.py       Slack / Mailchimp / webhook outbound integrations
  templates/            Jinja2 templates (admin/ for the /dashboard CMS, email/, errors/)
  static/               CSS, JS, vendored ProseMirror bundle
deploy/                setup/upgrade scripts, systemd units (app + digest timer), nginx config
migrations/            (placeholder — see TECHNICAL.md, schema changes are hand-rolled)
```

## License

MIT — see [LICENSE](LICENSE).

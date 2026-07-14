# Index Cards

A self-hosted personal wiki and blog engine. Every entry is one card: it
links to other cards, knows which cards link back to it, and keeps its own
edit history. The whole thing is one Flask app and one SQLite file.

For architecture and developer documentation, see
[TECHNICAL.md](TECHNICAL.md).

## What it does

- **Linked entries with backlinks.** Wiki-style internal links; every entry
  lists what references it. Links to entries that don't exist yet render as
  *red links* — click one and you're already writing it.
- **Hierarchy.** Entries can nest one level under a parent, with nested URLs
  (`/parent/child/`) and breadcrumbs.
- **Full-text search.** SQLite FTS5 over titles and bodies, with ranked
  results and highlighted excerpts.
- **Revision history.** Every save records a changelog entry you can review.
  Soft edit-locks keep two people from clobbering each other. An
  edit-activity heatmap sits on the homepage.
- **Publishing.** Drafts, stubs, scheduled-looking published dates, Atom and
  JSON feeds, a weekly email digest for subscribers, and a read-only JSON
  API.
- **Integrations.** Slack announcements on publish, Mailchimp subscriber
  sync, and HMAC-signed outgoing webhooks.
- **Passwordless auth.** Login is an email magic link — no passwords are
  ever stored. Optional multi-user mode with roles (admin / editor / author
  / viewer), invites or domain-restricted/open registration, and an audit
  log.
- **Private mode.** Flip the whole site to registered-readers-only.
- **Import & export.** Import from JSON; export everything as Markdown files
  with front-matter or as JSON.
- **Themes.** Five built-in color themes, dark/light modes, custom CSS, and
  custom head/footer HTML.

## Quick start (local)

Requires Python 3.11+.

```bash
git clone <this-repo> indexcards && cd indexcards
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python run.py
```

Open <http://localhost:5000> — the first visit walks you through creating
the admin account. Emails (login links, invites) print to the console until
you configure SMTP in **Dashboard → Settings**.

Optionally seed demo content from **Dashboard → Data → Add test data**.

## Deploying to a server

A complete single-server setup for Ubuntu/Debian lives in
[`deploy/`](deploy/):

```bash
sudo git clone <this-repo> /srv/indexcards
cd /srv/indexcards/deploy && sudo ./setup.sh
```

`setup.sh` installs nginx, gunicorn, and certbot, creates a service user,
writes an `.env` with a random `SECRET_KEY`, installs the systemd service
and the daily digest timer, and obtains a TLS certificate. See
[`deploy/README.md`](deploy/README.md) for details and
[`upgrade.sh`](deploy/upgrade.sh) for updates.

## Configuration

Environment variables (see [`env.example`](env.example)):

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Flask session/CSRF key — **required in production** | dev-only fallback |
| `SITE_URL` | Public base URL, used in emails and feeds | `http://localhost:5000` |
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///instance/indexcards.db` |
| `FLASK_DEBUG` | Enable dev mode | off |

Everything else — site title, themes, SMTP, registration policy, visibility,
integrations, digest schedule — is configured in the admin dashboard and
stored in the database.

## CLI

```bash
flask send-digest [--force]   # email the weekly digest (timer-driven in deploy)
flask rebuild-fts             # rebuild the full-text search index
```

## License

See [LICENSE](LICENSE).

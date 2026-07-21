# Index Cards

A self-hosted personal wiki and blog engine. Every piece of content is one
card: it links to other cards, knows which cards link back to it, and keeps a
changelog of its edits. The whole thing is a single Flask app backed by one
SQLite file — to back it up, copy the file.

For architecture and developer documentation, see [TECHNICAL.md](TECHNICAL.md);
for the database schema, see [models.md](models.md).

## What it does

- **Linked cards with backlinks.** Write wiki-style internal links with a `[[`
  autocomplete. Every card lists what links to it. A link to a card that
  doesn't exist yet renders as a red *"not yet written"* link — pick **Create
  new entry** from the autocomplete and you leave behind a followable **stub**,
  styled amber until it's fleshed out.
- **Hierarchy.** A card can nest one level under a parent, giving nested URLs
  (`/parent/child/`) and breadcrumbs. The A–Z index can show children nested,
  flat, or both.
- **Full-text search.** SQLite FTS5 over titles and bodies with ranked results
  and highlighted excerpts, plus an A–Z jump bar and a *random card* button.
- **Reading aids.** Each card page has a table of contents built from its
  headings, previous/next links across the index order, hover previews of
  linked cards, and footnotes.
- **Edit history.** Every save records a changelog note (who, when, what
  changed). Soft edit-locks stop two people clobbering each other, and an
  edit-activity heatmap sits on the homepage.
- **Drafts and stubs.** Drafts are unpublished and hidden everywhere public.
  Stubs are published but skeletal — visible and linkable, but held back from
  feeds, the digest, and integrations until finished.
- **Publishing.** Atom and JSON feeds, a weekly email digest for subscribers,
  and a read-only JSON API. Drafts, stubs, and group-restricted cards are held
  back from all three.
- **Access groups.** Optionally restrict individual cards to one or more groups
  so only their members (plus admins) can read them, with a public discovery
  page where signed-in users can request to join.
- **Integrations.** Slack announcements on publish/update, Mailchimp subscriber
  sync, and HMAC-signed outgoing webhooks.
- **Passwordless auth.** Login is an email magic link — no passwords are stored.
  Optional multi-user mode with roles (admin / editor / author / viewer),
  invite / domain-restricted / open registration, and an audit log.
- **Visibility modes.** Keep the whole site public, or restrict it to
  registered users, or to admins only.
- **Editorial chrome.** A homepage epigraph, a built-in About page, a site-wide
  announcement banner, and a footer colophon — all authored in the dashboard.
- **Import & export.** Import from JSON; export everything as Markdown files
  with front-matter, or as a single JSON document.
- **Themes.** Five built-in color themes, a dark/light toggle with a default
  mode, custom CSS, and custom head/footer HTML.

## Quick start (local)

Requires Python 3.11+.

```bash
git clone <this-repo> indexcards && cd indexcards
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python run.py
```

Open <http://localhost:5000> — the first visit runs a setup wizard that creates
the admin account. In dev mode, emails (login links, invites, digests) print to
the console until you configure SMTP.

Optionally seed demo content from **Dashboard → Data → Add test data**.

> `run.py` runs the test suite once before launching the dev server (the app
> still starts even if tests fail). Set `SKIP_TESTS=1` to skip it.

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite (`tests/`) runs against an in-memory SQLite database and covers
entries, publishing, links and backlinks, hierarchy, search, auth, access
control, groups, feeds, integrations, import/export, locks, and the CLI.

## Deploying to a server

A complete single-server setup for Ubuntu/Debian lives in [`deploy/`](deploy/).
Get the code onto the server, then run the setup script as root from inside the
checkout:

```bash
sudo bash deploy/setup.sh
```

`setup.sh` installs nginx, gunicorn, and certbot, creates a service user, writes
an `.env` with a random `SECRET_KEY`, installs the systemd service and the
weekly digest timer, configures nginx, and obtains a TLS certificate. See
[`deploy/README.md`](deploy/README.md) for details and
[`deploy/upgrade.sh`](deploy/upgrade.sh) for updates.

## Configuration

Environment variables (see [`env.example`](env.example)):

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Flask session/CSRF key — **required in production** | dev-only fallback |
| `SITE_URL` | Public base URL, used in emails and feeds | `http://localhost:5000` |
| `DATABASE_URL` | SQLAlchemy database URL (SQLite in practice) | `sqlite:///instance/indexcards.db` |
| `FLASK_DEBUG` | Enable dev mode (console emails, no SECRET_KEY check) | off |
| `SMTP_*` | Optional SMTP settings; when `SMTP_HOST` is set they override the dashboard's SMTP fields | unset |

The app refuses to boot in production if `SECRET_KEY` is left at the dev
default. Everything else — site title, themes, SMTP, registration policy,
visibility, groups, integrations, digest schedule — is configured in the admin
dashboard and stored in the database.

## CLI

```bash
flask send-digest [--force]   # email the weekly digest (timer-driven in deploy)
flask rebuild-fts             # rebuild the full-text search index
```

`send-digest` only sends on the configured digest day unless `--force` is given.

## License

See [LICENSE](LICENSE).

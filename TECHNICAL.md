# Index Cards — Technical Documentation

This document covers architecture, data model, routes, and deployment
topology for developers. For a product overview and quick start, see
[README.md](README.md).

## 1. Tech stack

| Layer | Choice |
|---|---|
| Web framework | Flask 3.1 (app factory pattern, `app/__init__.py`) |
| ORM | Flask-SQLAlchemy 3.1 |
| Auth | Flask-Login, passwordless (email magic links) |
| CSRF | Flask-WTF |
| Rate limiting | Flask-Limiter (in-memory storage, per-process) |
| Database | SQLite (file-based, `instance/indexcards.db`) + SQLite FTS5 for search |
| Markdown | `mistune` for rendering, `bleach` for HTML sanitization |
| Frontend | Server-rendered Jinja2 + vanilla JS, no SPA framework |
| Rich text editor | ProseMirror, vendored/bundled via `scripts/vendor-prosemirror.sh` (esbuild) |
| Email | stdlib `smtplib`; prints to console if SMTP isn't configured |
| WSGI server | gunicorn |
| Deployment | systemd + nginx + certbot on a single Ubuntu/Debian host |

## 2. Application structure

Routes (`app/views/`) are kept thin — each view module imports its business
logic from a same-named or feature-named module at the top of `app/`.
Standalone logic modules don't import Flask blueprints and are shared across
views (e.g. `revisions.py` serves both entry and page history).

```
app/
  __init__.py       app factory: extension init, blueprint registration,
                     before_request guards (first-run setup, private-site gate),
                     startup DB bootstrap (see §5), template filters/context
                     processors (timeago, entry_url, cache-busted static_url)
  models.py          SQLAlchemy models (§3) + the entry_url() URL helper
  views/                   routes only — thin, delegate to the logic modules below
    auth.py                 public auth blueprint — login, signup, setup wizard
    account.py                /account — user profile (own blueprint)
    main.py                     public site blueprint — entries, notes timeline,
                                 search, feeds, uploads, subscribe
    admin.py                     /dashboard blueprint shell: admin_bp +
                                  admin_required / writer_required / editor_required
    admin_entries.py               entry CRUD, publish, bulk actions, history
    admin_pages.py                  page CRUD, publish, history
    admin_notes.py                   note CRUD, publish (gated on notes_enabled)
    admin_users.py                    users, roles, registrations, audit logs
    admin_settings.py                  site settings, themes, integrations config
    admin_import_export.py              markdown/JSON export, JSON/WordPress import,
                                         test data
  entries.py           entry save/validate, alias & backlink sync, cycle guard,
                        JSON import, RESERVED_SLUGS
  notes.py              note save + note→entry backlink sync
  pages.py              page save/validate logic
  revisions.py           diff/history-building helpers shared by entries and pages
  locks.py                soft edit-locking (EditLock) — acquire/release/active_locks
  registration.py           invite/signup role resolution (VALID_ROLES, create_registration)
  feeds.py                 RSS/Atom/JSON feed data assembly, used by main.py
  wordpress_import.py       WordPress export XML → Entry import (HTML→markdown parser)
  api.py               /api blueprint — JSON endpoints, per-endpoint auth (§4)
  markdown.py          mistune render → footnote processing → bleach sanitize →
                        heading IDs; internal-link extraction & missing-link marking
  search.py            SQLite FTS5 index maintenance and querying
  digest.py            `flask send-digest` / `flask rebuild-fts` CLI commands
  mail.py              SMTP sending via per-site settings, email template rendering
  integrations.py      Slack webhook, Mailchimp subscribe, HMAC-signed webhook
  icons.py             inline Bootstrap Icons SVG lookup
  migrate_db.py         hand-rolled schema migration runner (see §5)
  testdata.py / testdata_content.py   admin-triggered demo content seed/clear
  templates/           Jinja2 templates (public, admin/, email/, errors/)
  static/              CSS, JS, vendored ProseMirror bundle, Bootstrap Icons font
```

`admin_bp` is defined once in `app/views/admin.py`; the six `admin_*`
sibling modules import it and attach their own `@admin_bp.route(...)`
handlers. All are imported explicitly in `create_app()` — importing
`admin.py` alone does not wire up the full `/dashboard` route table.

There is no `tests/` directory or automated test suite in this repository.

## 3. Data model

All models live in `app/models.py`.

- **Entry** — the core wiki/blog unit. `slug` (unique), `title`, `summary`,
  `body_markdown` / `body_html`, `is_draft`, `is_stub`, `published_at`,
  `created_at` / `updated_at`, `created_by` (FK → User), `sort_title`
  (derived — strips leading "the/a/an"), `parent_id` (self-referential FK;
  hierarchy is capped at two levels — an entry that has a parent cannot
  itself be a parent). Cascade-deletes its `aliases`, `edit_logs`, and
  backlinks in both directions. Indexed on `parent_id` and `created_by`.
- **`entry_url(obj)`** — canonical URL helper: `/<slug>/` for top-level
  entries, `/<parent-slug>/<slug>/` for children. Used everywhere URLs are
  built (templates via a context processor, feeds, API, integrations).
- **Alias** — alternate titles/slugs that 301-redirect to an Entry.
- **EditLog** — per-entry revision history: `changelog`, `body_snapshot`
  (nullable; only stored when content changed, pruned to 50 per entry),
  `is_import` (marks rows created by importers so they're excluded from
  digests/timelines), `edited_at`, `user_id`. Indexed on `entry_id`.
- **Backlink** — directed edge `source_entry_id → target_entry_id`, fully
  rebuilt on every save by scanning the rendered markdown for internal
  links. Indexed on both columns.
- **Note / NoteBacklink** — optional short-form posts (no title/slug; URL is
  `/notes/<id>/`), with their own backlinks *to* entries.
- **EditLock** — soft lock for concurrent editing. Unique on
  `(content_type, content_id)`, 60-second TTL, refreshed by a 30s JS
  heartbeat via `/api/lock/...`; insert races are absorbed by catching the
  unique-constraint violation.
- **User** (`UserMixin`) — `email` (unique), `display_name`, `role`
  (`admin` / `editor` / `author` / `viewer`), `bio`, `link`, `subscribed`,
  `unsubscribe_token`, `login_token` + `login_token_expires` (15-minute
  magic link). Role helpers: `is_admin`, `can_write`, `can_modify(obj)` —
  admin modifies anything; editor anything not authored by an admin; author
  only their own; viewer nothing. `can_modify` is used for entries and
  notes alike.
- **Registration** — pending invite/signup: `email`, `token` (unique),
  `invited_by`, `role`, `accepted`. No expiry (see issues.md).
- **AuditLog** — generic action log written via `log_audit()`.
- **Page** — static content (e.g. "About") outside the wiki graph: same
  shape as Entry minus aliases/backlinks/parent, plus `show_in_nav` /
  `nav_position`. Revisions via **PageRevision**.
- **SiteSettings** — singleton row (`id=1`). Site title/footer/theme/custom
  CSS + head/footer HTML, feature toggles (search, subscribe, feeds, notes,
  history, authors, alpha jump, subpage display), multi-user and
  registration configuration (`invite` / `domain` / `open`, `default_role`,
  `registration_domain`), `site_visibility` (`public` / `registered`),
  digest config, SMTP credentials (cleartext at rest), and
  Mailchimp/Slack/outgoing-webhook credentials including the webhook HMAC
  secret.

## 4. Routes

### `auth_bp` (no prefix) — `app/views/auth.py`

| Route | Methods | Notes |
|---|---|---|
| `/login` | GET, POST | rate-limited 10/min; anti-enumeration flash |
| `/login/<token>` | GET | consumes a magic-link token |
| `/logout` | GET | requires login |
| `/setup` | GET, POST | only usable while zero users exist |
| `/signup` | GET, POST | gated on multi-user + non-invite registration; 10/min |
| `/signup/<token>` | GET, POST | consumes an invite token |

### `account_bp` (no prefix) — `/account` (GET, POST) — profile fields.

### `main_bp` (no prefix) — `app/views/main.py`

| Route | Methods | Notes |
|---|---|---|
| `/` | GET | A–Z index (entries + aliases, optional nesting), edit heatmap |
| `/<slug>/` | GET | resolver: Entry → Alias (301) → Page → (writers) create prompt → 404; child entries 301 to their nested URL |
| `/<parent_slug>/<slug>/` | GET | canonical URL for child entries |
| `/notes/`, `/notes/<id>/` | GET | timeline + single note; 404 unless `notes_enabled` |
| `/search` | GET | FTS search |
| `/random` | GET | random published entry |
| `/healthz` | GET | DB liveness check |
| `/subscribe` | POST | rate-limited 5/min; double-opt-in via email |
| `/confirm/<token>`, `/unsubscribe/<token>` | GET | |
| `/feed.xml`, `/feed.json` | GET | gated on `site_visibility=public` + `feeds_enabled` |
| `/favicon.svg`, `/site-image` | GET | |
| `/uploads/<filename>` | GET | filename validated against `^[0-9a-f]{32}\.[a-z]{2,4}$` |

A global `before_request` gate redirects anonymous users to `/login` when
`site_visibility='registered'`, with an endpoint allowlist for auth/health/
confirmation routes. The `api` blueprint is excluded and enforces its own
visibility per endpoint (JSON 401 instead of HTML redirect).

### `admin_bp` (`/dashboard`) — routes attached across six modules

Three decorators (defined in `app/views/admin.py`): `writer_required`
(admin/editor/author), `editor_required` (admin/editor), `admin_required`.
Entry and note mutations additionally check `User.can_modify()` per object.

- `admin_entries.py` — dashboard list (sortable, paginated, shows locks);
  entry new/edit/delete (writer + `can_modify`); publish + preview (login +
  `can_modify`); bulk publish/unpublish/delete (admin, still per-entry
  `can_modify`); history + restore.
- `admin_pages.py` — page CRUD (editor), delete (admin), history/restore.
- `admin_notes.py` — note CRUD/publish (writer + `can_modify`); all routes
  bounce to settings if notes are disabled.
- `admin_users.py` — invites, role changes (last-admin protection), user
  deletion (references nulled), pending registrations, subscribers, audit
  log (admin).
- `admin_settings.py` — settings, theme picker, site image upload,
  integrations config (admin).
- `admin_import_export.py` — markdown zip export, JSON export/import
  (import is atomic — a failure rolls back the whole batch), WordPress XML
  import, test-data seed/clear (admin).

### `api_bp` (`/api`) — `app/api.py`

| Route | Methods | Notes |
|---|---|---|
| `/api/v1/entries`, `/api/v1/entries/<slug>` | GET | public read API, 120/min, respects `site_visibility`; alias slugs resolve |
| `/api/entries/search` | GET | autocomplete (title + alias match, `for_parent` filter) |
| `/api/entries/quick-create` | POST | create a draft entry by title (writer); used by the parent picker |
| `/api/entry/<slug>/preview` | GET | hover-card data |
| `/api/upload-image` | POST | writer; extension allowlist, random hex filename |
| `/api/lock/<type>/<id>`, `.../release` | POST | lock heartbeat/release |
| `/api/preview` | POST | markdown → sanitized HTML |

## 5. Database & migrations

There is no Alembic migration history, even though `Flask-Migrate` is
installed. Schema evolution is handled by `app/migrate_db.py`, an
imperative script that inspects `PRAGMA table_info` / `sqlite_master` and
issues `ALTER TABLE` / `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX` as
needed. It runs unconditionally on every boot inside `create_app()`,
alongside `db.create_all()` (idempotent) and FTS table creation.

Consequences to be aware of:

- The DDL is raw SQLite — `DATABASE_URL` accepts other backends but only
  SQLite actually works.
- Multiple gunicorn workers each run the migration at boot; there is no
  cross-process guard (see issues.md).
- A `sort_title` recompute pass runs over all entries on every boot.

## 6. Markdown, sanitization, and search

- **Rendering** (`app/markdown.py`): `mistune` (no plugins) renders with
  `escape=False`; custom footnote pre/post-processing turns `[^1]` syntax
  into hover-able references and an end-of-page section (fenced code blocks
  are excluded from footnote processing); then `bleach.clean()` with an
  explicit tag/attribute allowlist; then heading-ID injection for the TOC.
- **Internal links**: `INTERNAL_LINK_RE` matches `href="/slug/"` in the
  rendered HTML. `extract_internal_links()` feeds backlink sync;
  `mark_missing_links()` styles links to nonexistent entries as red links
  at render time. Note it only matches single-segment URLs — nested child
  URLs are not recognized (see issues.md).
- **Search** (`app/search.py`): an FTS5 virtual table (`entry_fts`) indexes
  title, aliases, and body (markdown stripped to plain text). Kept in sync
  on save/delete; `update_fts_entry(commit=False)` lets importers stay
  atomic. Queries are prefix-match, ranked, parameterized, and return
  `snippet()` excerpts from whichever column matched.

## 7. Email, digest, and integrations

- **`app/mail.py`** renders `templates/email/<name>.{txt,html}` and sends
  via SMTP using `SiteSettings` credentials. Without SMTP configured, the
  email is printed to the console and reported as sent — convenient in dev,
  a footgun in production (login links land in the journal).
- **`app/digest.py`** — `flask send-digest` emails subscribers a roundup of
  entries published (and optionally edited) in the last 7 days; it no-ops
  unless today matches `SiteSettings.digest_day` (`--force` overrides).
  Import-created EditLog rows (`is_import`) are excluded. Scheduled daily
  by `deploy/indexcards-digest.timer`.
- **`app/integrations.py`** — synchronous, best-effort outbound HTTP (5s
  timeout, failures logged) via stdlib `urllib`: Mailchimp list subscribe on
  confirmed subscription, Slack announcements on publish/update, and a
  generic outgoing webhook signed with HMAC-SHA256 over the canonical JSON
  body (`X-Webhook-Signature: sha256=<hex>`, keyed on
  `outgoing_webhook_secret`). Webhooks fire only for public sites;
  integrations fire from `save_entry()` (note: not from the standalone
  Publish action — see issues.md).

## 8. Frontend

- Server-rendered Jinja2 with a small set of vanilla-JS modules in
  `app/static/js/`: `base.js` (toasts, theme toggle, confirms), `entry.js`
  (hover previews, bio popups, copy-link), `editor.js` (the bundled
  ProseMirror editor + markdown textarea sync, word count, localStorage
  autosave every 10s), `editor-page.js` (slug generation, parent picker
  with quick-create, lock heartbeat + `sendBeacon` release), `heatmap.js`,
  `dashboard.js`, `settings.js`.
- Theme system: five palettes set via `data-site-theme` on `<html>`, a
  dark/light toggle persisted in `localStorage`, and a site-wide default
  color mode. Admin-provided custom CSS/head/footer HTML are injected
  unsanitized (admin-trust boundary, by design).
- Public pages emit microformats (`h-entry`, `h-card`, `u-url`) and OG/
  Twitter meta tags.

## 9. Security model

- **Trust boundaries**: admins are fully trusted (custom HTML injection is a
  feature). Editors/authors are semi-trusted content authors — their
  markdown is sanitized with bleach. Viewers/anonymous users are untrusted.
- **Auth**: magic links only, 15-minute expiry, tokens cleared on use.
  No passwords stored. Sessions via Flask-Login with `SECRET_KEY` (boot
  fails in production if it's the dev default).
- **CSRF**: global Flask-WTF protection; the API blueprint is CSRF-exempt
  only on the public read endpoints, and state-changing API endpoints
  require the `X-CSRFToken` header.
- **Rate limits**: login/signup 10/min, subscribe 5/min, public API
  120/min — in-memory per process (multiply by worker count).
- **Uploads**: extension allowlist, random 32-hex filenames, served with a
  strict filename regex (but note the nginx `/uploads/` alias bypasses the
  private-site gate — see issues.md).
- Known gaps are tracked in [issues.md](issues.md) — notably the
  search-page XSS, unvalidated profile link URLs, and unvalidated settings
  enums.

## 10. Deployment architecture

Single-server Ubuntu/Debian target under `deploy/`:

- **`setup.sh`** (run as root from inside the checkout) installs nginx,
  gunicorn, certbot, and Python; creates a system user `indexcards`; sets
  up a venv; writes `.env` with a random `SECRET_KEY`; installs the systemd
  service and digest timer; configures nginx; obtains a Let's Encrypt
  certificate. Both scripts derive the app root from their own location, so
  any install path works (`/srv/indexcards` is the documented example).
- **`indexcards.service`** — gunicorn, 3 workers, Unix socket at
  `/run/indexcards/indexcards.sock`.
- **`indexcards-digest.service` / `.timer`** — daily `flask send-digest`;
  the command itself checks `digest_day` and no-ops on other days.
- **`nginx.conf`** — TLS termination, direct static and `/uploads/`
  serving, proxy to gunicorn, `client_max_body_size 3M` (app-level cap is
  2 MB).
- **`upgrade.sh`** — `git pull` + `pip install` + `chown` + restart.

Backups: the entire site state is `instance/indexcards.db` plus
`instance/uploads/`. Copy those two and you have everything.

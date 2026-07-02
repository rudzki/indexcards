# Index Cards — Technical Documentation

This document covers architecture, data model, routes, deployment topology,
and known issues. For a product overview and quick start, see [README.md](README.md).

## 1. Tech stack

| Layer | Choice |
|---|---|
| Web framework | Flask 3.1 (app factory pattern, `app/__init__.py`) |
| ORM | Flask-SQLAlchemy 3.1 |
| Auth | Flask-Login, passwordless (email magic links) |
| CSRF | Flask-WTF |
| Rate limiting | Flask-Limiter (in-memory storage — see [Accepted limitations](#9-accepted-limitations-not-fixed)) |
| Database | SQLite (file-based, `instance/indexcards.db`) + SQLite FTS5 for search |
| Markdown | `mistune` for rendering, `bleach` for HTML sanitization |
| Frontend | Server-rendered Jinja2 + vanilla JS, no SPA framework |
| Rich text editor | ProseMirror, vendored/bundled via `scripts/vendor-prosemirror.sh` (esbuild) |
| Email | stdlib `smtplib`; prints to console if SMTP isn't configured |
| WSGI server | gunicorn |
| Deployment | systemd + nginx + certbot on a single Ubuntu/Debian host |

## 2. Application structure

```
app/
  __init__.py       app factory: extension init, blueprint registration,
                     before_request guards (first-run setup, private-site gate),
                     startup DB bootstrap (see §5)
  models.py          SQLAlchemy models (§3)
  views/
    auth.py          public auth blueprint — login, signup, setup wizard
    main.py           public site blueprint — entries, pages, search, feeds, uploads
    admin.py           /dashboard blueprint — the CMS (entries, pages, users, settings)
  api.py              /api blueprint — JSON endpoints, CSRF-exempt as a whole
  markdown.py         mistune render → footnote processing → bleach sanitize → heading IDs
  search.py           SQLite FTS5 index maintenance and querying
  digest.py           `flask send-digest` / `flask rebuild-fts` CLI commands
  mail.py             SMTP sending via per-site settings, template rendering
  integrations.py     Slack webhook, Mailchimp subscribe, generic signed webhook
  icons.py            inline Bootstrap Icons SVG lookup
  migrate_db.py        hand-rolled schema migration runner (see §5)
  testdata.py / testdata_content.py   admin-triggered demo content seed/clear
  templates/          Jinja2 templates (public, admin/, email/, errors/)
  static/             CSS, JS, vendored ProseMirror bundle, Bootstrap Icons font
```

There is no `tests/` directory or automated test suite in this repository.

## 3. Data model

All models live in `app/models.py`.

- **Entry** — the core wiki/blog unit. `slug` (unique), `title`, `summary`,
  `body_markdown` / `body_html`, `is_draft`, `published_at`, `created_at` /
  `updated_at`, `created_by` (FK → User), `sort_title` (derived — strips
  leading "the/a/an" for alphabetical sorting), `parent_id` (self-referential
  FK for hierarchy). Cascade-deletes its `aliases`, `edit_logs`,
  `outgoing_links` / `incoming_links` (backlinks in both directions).
- **Alias** — alternate titles/slugs that redirect to an Entry. Unique `slug`.
- **EditLog** — per-entry revision history: `changelog`, `body_snapshot`
  (nullable; older snapshots are pruned, capped at 50 per entry, and only
  stored when content actually changed), `edited_at`, `user_id`.
- **Backlink** — directed edge `source_entry_id → target_entry_id`, fully
  rebuilt on every save by scanning rendered markdown for internal links.
- **EditLock** — soft optimistic lock for concurrent editing. Unique on
  `(content_type, content_id)`, 60-second TTL, refreshed via `/api/lock/...`.
- **User** (`UserMixin`) — `email` (unique), `display_name`, `role`
  (`admin` / `editor` / `author` / `viewer`), `bio`, `link`, `subscribed`,
  `unsubscribe_token`, `login_token` + `login_token_expires` (15-minute magic
  link). Role helpers: `is_admin`, `can_write`, `can_modify(entry)` — admin
  can modify anything, editor can modify any entry not authored by an admin,
  author can only modify their own entries, viewer can modify nothing.
- **Registration** — pending invite/signup: `email`, `token` (unique),
  `invited_by` (FK → User), `role`, `accepted`.
- **AuditLog** — generic action log (`action`, `detail`, `user_id`,
  `created_at`), written via a `log_audit()` helper.
- **Page** — static content (e.g. "About") outside the wiki graph: same shape
  as Entry minus aliases/backlinks/parent, plus `show_in_nav` / `nav_position`.
  Has its own revision history via **PageRevision**.
- **SiteSettings** — singleton row (`id=1`). Site title/footer/theme/custom
  CSS/head/footer HTML, search/subscribe/feeds toggles, multi-user and
  registration configuration (`invite` / `domain` / `open` methods,
  `default_role`, `registration_domain`), `site_visibility`
  (`public` / `registered`), SMTP credentials, and Mailchimp/Slack/outgoing
  webhook credentials including a webhook HMAC secret. **SMTP password and
  integration secrets are stored in cleartext** — see
  [Accepted limitations](#9-accepted-limitations-not-fixed).

## 4. Routes

### `auth_bp` (no prefix) — `app/views/auth.py`

| Route | Methods | Notes |
|---|---|---|
| `/login` | GET, POST | rate-limited 10/min |
| `/login/<token>` | GET | consumes a magic-link token |
| `/logout` | GET | requires login |
| `/setup` | GET, POST | only usable while zero users exist |
| `/signup` | GET, POST | gated on multi-user + open registration; rate-limited 10/min |
| `/signup/<token>` | GET, POST | consumes an invite token |
| `/account` | GET, POST | requires login |

### `main_bp` (no prefix) — `app/views/main.py`

| Route | Methods | Notes |
|---|---|---|
| `/` | GET | index — entries, aliases, last-year edit heatmap |
| `/<slug>/` | GET | entry / alias / page resolver |
| `/search` | GET | FTS search |
| `/random` | GET | random entry |
| `/healthz` | GET | health check |
| `/subscribe` | POST | rate-limited 5/min |
| `/confirm/<token>` | GET | subscription confirmation |
| `/unsubscribe/<token>` | GET | |
| `/favicon.svg`, `/site-image` | GET | |
| `/feed.xml`, `/feed.json` | GET | gated on `site_visibility=public` and `feeds_enabled` |
| `/uploads/<filename>` | GET | filename validated against a regex |

### `admin_bp` (`/dashboard`) — `app/views/admin.py`

Gated by three decorators: `writer_required` (admin/editor/author),
`editor_required` (admin/editor), `admin_required` (admin only). Entry and
page mutations additionally check `User.can_modify()` per-object.

- `/` — dashboard (writer)
- `/entry/new/`, `/entry/<id>/edit/`, `/entry/<id>/delete/` — writer + `can_modify`
- `/entries/<id>/publish/`, `/preview/<id>/` — login required + `can_modify`
- `/entry/<id>/history/`, `.../history/<log_id>/restore/` — writer + `can_modify`
- `/entries/bulk/` — admin; publish/unpublish/delete, each still checked per-entry via `can_modify`
- `/pages/`, `/pages/new/` — editor
- `/pages/<id>/edit/`, `/pages/<id>/publish/` — editor
- `/pages/<id>/delete/` — admin
- `/pages/<id>/history/`, `.../history/<rev_id>/restore/` — editor
- `/settings/`, `/settings/upload-image/`, `/settings/remove-image/` — admin
- `/users/`, `/users/<id>/role/`, `/users/<id>/delete/`, `/users/registration/<id>/resend|revoke/` — admin
- `/export/markdown/`, `/export/json/`, `/import/json/`, `/import/wordpress/` — admin
- `/test-data/add|remove/`, `/data/` — admin
- `/subscribers/`, `/logs/`, `/integrations/` — admin

### `api_bp` (`/api`) — `app/api.py`

Excluded from the global `require_login_for_private_site` gate — each
endpoint enforces its own visibility/auth (see §9).

| Route | Methods | Notes |
|---|---|---|
| `/api/v1/entries`, `/api/v1/entries/<slug>` | GET | public read API, rate-limited 120/min, `@csrf.exempt`, respects `site_visibility` |
| `/api/entries/search` | GET | internal autocomplete, respects `site_visibility` |
| `/api/entry/<slug>/preview` | GET | hover-card data, respects `site_visibility` |
| `/api/upload-image` | POST | login required + `can_write`, CSRF-protected |
| `/api/lock/<type>/<id>`, `.../release` | POST | login required, CSRF-protected |
| `/api/preview` | POST | login required — markdown→HTML preview, CSRF-protected |

## 5. Database & migrations

There is no Alembic migration history in this repo, even though
`Flask-Migrate` is installed and `migrate.init_app(app, db)` runs. Schema
evolution is handled entirely by `app/migrate_db.py`, an imperative script
that inspects `PRAGMA table_info` / `sqlite_master` and issues
`ALTER TABLE` / `CREATE TABLE IF NOT EXISTS` statements as needed. It runs
unconditionally on every app boot, inside `create_app()`.

Table creation on a **brand-new** database runs via two mechanisms:

- `db.create_all()` — runs unconditionally on every boot (`app/__init__.py`);
  idempotent, so it's a no-op once tables exist
- `migrate_db.py` — has explicit `CREATE TABLE IF NOT EXISTS` fallbacks for
  three tables it also needs to backfill data into: `page`, `edit_lock`,
  `page_revision`

(`db.create_all()` used to be gated behind `FLASK_DEBUG`, which meant a
fresh production database never got most of its tables — see
[Known issues fixed in this pass](#9-known-issues--fixed-in-this-pass).)

Because the migration logic is raw SQLite DDL, it is not portable to any
other `DATABASE_URL` backend (Postgres, MySQL) — `DATABASE_URL` is
configurable in `config.py`, but only SQLite is actually supported in practice.

## 6. Markdown, sanitization, and search

- **Rendering** (`app/markdown.py`): `mistune` renders with `escape=False`,
  followed by custom footnote pre/post-processing, then `bleach.clean()`
  with an explicit tag/attribute allowlist, then heading-ID injection for
  the table of contents. `extract_internal_links()` / `mark_missing_links()`
  detect wiki-style links (`href="/slug/"`); `strip_markdown()` produces the
  plain-text body used for FTS indexing.
- **Search** (`app/search.py`): a SQLite FTS5 virtual table (`entry_fts`)
  indexes title, aliases, and body. `update_fts_entry` / `delete_fts_entry`
  keep it in sync on every save/delete; `search_entries()` builds a
  prefix-match FTS query and returns ranked results with `snippet()`-based
  highlighted excerpts. All queries are parameterized.

## 7. Email, digest, and integrations

- **`app/mail.py`** renders `templates/email/<name>.{txt,html}` and sends via
  SMTP using per-site `SiteSettings` credentials. If SMTP isn't configured,
  it prints the email to the console instead of raising errors, making it convenient for
  dev.
- **`app/digest.py`** exposes `flask send-digest` (emails `subscribed` users
  a weekly roundup of entries published/edited in the last 7 days, only on
  the day of week configured in `SiteSettings.digest_day`; pass `--force` to
  send regardless of the day) and `flask rebuild-fts`. Scheduled daily via
  `deploy/indexcards-digest.timer` (see §8).
- **`app/integrations.py`** does best-effort, fire-and-forget outbound HTTP
  (5s timeout, failures only logged) via stdlib `urllib`: Mailchimp
  subscribe, Slack webhook announcements, and a generic outgoing webhook
  signed with HMAC-SHA256 (`X-Webhook-Signature`, keyed on
  `outgoing_webhook_secret`).

## 8. Deployment architecture

Single-server Ubuntu/Debian target under `deploy/`, path-agnostic — both
scripts derive the app root from their own on-disk location, so the app can
be deployed anywhere, not just `/srv/indexcards` (that path is only used as
the example in the docs below):

- **`setup.sh`** (run as root, from inside the checkout) installs nginx,
  gunicorn, certbot, and Python; creates a system user `indexcards`; sets up
  a venv; writes `.env` with a randomly generated `SECRET_KEY`; installs the
  systemd service and the weekly digest timer; configures nginx; and obtains
  a Let's Encrypt certificate via `certbot --nginx`.
- **`indexcards.service`** — gunicorn, 3 workers, bound to a Unix socket at
  `/run/indexcards/indexcards.sock`.
- **`indexcards-digest.service`** / **`indexcards-digest.timer`** — a
  systemd timer that runs `flask send-digest` daily; the command itself
  checks `SiteSettings.digest_day` and no-ops on any other day of the week.
- **`nginx.conf`** — TLS termination via certbot, static asset and
  `/uploads/` aliasing, proxies everything else to gunicorn.
- **`upgrade.sh`** — `git pull` + `pip install` + `chown` + `systemctl restart`,
  run from inside the deployed checkout.

## 9. Accepted limitations

- **In-memory rate limiter isn't multi-worker-safe.**
  `Limiter(storage_uri="memory://")` keeps counters per-process, and
  `indexcards.service` runs gunicorn with 3 workers, so effective limits on
  `/login`, `/signup`, `/subscribe`, and the public API are roughly 3x the
  configured value and reset on worker restart.

- **SMTP password and integration secrets are stored in cleartext** in
  `SiteSettings`, with no encryption at rest. A leaked database backup or
  the admin-only `/dashboard/export/json/` endpoint would expose SMTP
  credentials, Mailchimp keys, and the webhook HMAC secret in plaintext.

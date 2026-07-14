# Index Cards — Technical Documentation

Architecture, data model, routes, and deployment topology for developers.
For a product overview and quick start, see [README.md](README.md).

## 1. Tech stack

| Layer | Choice |
|---|---|
| Web framework | Flask 3.1 (app-factory pattern, `app/__init__.py`) |
| ORM | Flask-SQLAlchemy 3.1 |
| Auth | Flask-Login, passwordless (email magic links) |
| CSRF | Flask-WTF (global; public read API is exempt) |
| Rate limiting | Flask-Limiter (in-memory storage, per process) |
| Database | SQLite (file-based, `instance/indexcards.db`) + SQLite FTS5 for search |
| Markdown | `mistune` for rendering, `bleach` for HTML sanitization |
| Frontend | Server-rendered Jinja2 + vanilla JS, no SPA framework |
| Rich-text editor | ProseMirror, vendored/bundled via `scripts/vendor-prosemirror.sh` (esbuild) |
| Email | stdlib `smtplib`; prints to console when SMTP isn't configured |
| Tests | `pytest` / `unittest`, against in-memory SQLite (`tests/`) |
| WSGI server | gunicorn |
| Deployment | systemd + nginx + certbot on a single Ubuntu/Debian host |

## 2. Application structure

Routes (`app/views/`) are kept thin — each view module imports its business
logic from a same-named or feature-named module at the top of `app/`.
Standalone logic modules don't import Flask blueprints, so they're freely
shared across views.

```
app/
  __init__.py       app factory: extension init, blueprint registration,
                     before_request guards (first-run setup, private-site gate),
                     startup DB bootstrap (see §5), template filters/context
                     processors (timeago, entry_url, cache-busted static_url)
  models.py          SQLAlchemy models (§3) + entry_url()/set_published() helpers
  views/                   routes only — thin, delegate to the logic modules below
    auth.py                 public auth blueprint — login, signup, setup wizard
    account.py                /account — user profile (own blueprint)
    main.py                     public site blueprint — entries, search, feeds,
                                 uploads, subscribe (+ homepage edit heatmap)
    admin.py                     /dashboard blueprint shell: admin_bp +
                                  admin_required / writer_required / editor_required
    admin_entries.py               entry CRUD, publish, bulk actions, history
    admin_pages.py                  page CRUD, publish
    admin_users.py                    users, roles, registrations, audit logs
    admin_settings.py                  site settings, themes, integrations config
    admin_import_export.py              markdown/JSON export, JSON import, test data
  entries.py           entry save/validate, backlink sync, cycle guard,
                        integration dispatch, JSON import, RESERVED_SLUGS
  pages.py              page save/validate logic
  locks.py               soft edit-locking (EditLock) — acquire/release/active_locks
  registration.py         invite/signup role resolution (VALID_ROLES, create_registration)
  feeds.py                RSS/Atom/JSON feed data assembly, used by main.py
  api.py               /api blueprint — JSON endpoints, per-endpoint auth (§4)
  markdown.py          mistune render → footnote processing → bleach sanitize →
                        heading IDs; internal-link extraction & link-state marking
  search.py            SQLite FTS5 index maintenance and querying
  digest.py            `flask send-digest` / `flask rebuild-fts` CLI commands
  mail.py              SMTP sending via per-site settings, email template rendering
  integrations.py      Slack webhook, Mailchimp subscribe, HMAC-signed webhook
  icons.py             inline Bootstrap Icons SVG lookup (header site icon)
  migrate_db.py        hand-rolled schema migration runner (see §5)
  testdata.py / testdata_content.py   admin-triggered demo content seed/clear
  templates/           Jinja2 templates (public, admin/, email/, errors/)
  static/              CSS, JS, vendored ProseMirror bundle, Bootstrap Icons font
```

`admin_bp` is defined once in `app/views/admin.py`; the five `admin_*`
sibling modules import it and attach their own `@admin_bp.route(...)`
handlers. All are imported explicitly in `create_app()` — importing
`admin.py` alone does not wire up the full `/dashboard` route table.

Tests live in `tests/` (one `test_*.py` per feature area) and share a
`BaseTest` fixture (`tests/base.py`) that builds the app against an in-memory
SQLite database with CSRF disabled.

## 3. Data model

All models live in `app/models.py`.

- **Entry** — the core wiki/blog unit. `slug` (unique), `title`, `summary`,
  `body_markdown` / `body_html`, `is_draft`, `is_stub`, `published_at`,
  `created_at` / `updated_at`, `created_by` (FK → User), `sort_title`
  (derived — strips a leading "the/a/an"), `parent_id` (self-referential FK;
  hierarchy is capped at two levels — an entry that has a parent cannot
  itself be a parent). Cascade-deletes its `edit_logs` and backlinks in both
  directions. Indexed on `parent_id` and `created_by`.
- **`entry_url(obj)`** — canonical URL helper: `/<slug>/` for top-level
  entries, `/<parent-slug>/<slug>/` for children. Used everywhere URLs are
  built (templates via a context processor, feeds, API, integrations).
- **`set_published(obj, published)`** — the single draft/publish transition
  for Entry *and* Page: stamps `published_at` once, on the first publish, and
  never clears it. Returns `True` on that first publish, which callers use as
  the "new entry" signal for integrations.
- **Drafts vs. stubs.** Two independent flags. `is_draft` means unpublished —
  invisible on every public surface (index, entry page, search, feeds, API).
  `is_stub` means published-but-skeletal — visible and linkable, shows a
  "still being written" banner, but deliberately withheld from feeds, the
  digest, and integration announcements. The `[[`-link **Create new entry**
  action produces a published stub (see §4, §6).
- **EditLog** — per-entry changelog: `changelog` message, `is_import` (marks
  rows created by importers so they're excluded from digests), `edited_at`,
  `user_id`. Indexed on `entry_id`. The history view is a plain audit list of
  these rows — there are no full-text snapshots, diffs, or restore.
- **Backlink** — directed edge `source_entry_id → target_entry_id`, fully
  rebuilt on every save by scanning the rendered markdown for internal links.
  Indexed on both columns.
- **EditLock** — soft lock for concurrent editing. Unique on
  `(content_type, content_id)`, 60-second TTL, refreshed by a 30s JS
  heartbeat via `/api/lock/...`; insert races are absorbed by catching the
  unique-constraint violation.
- **User** (`UserMixin`) — `email` (unique), `display_name`, `role`
  (`admin` / `editor` / `author` / `viewer`), `bio`, `link`, `subscribed`,
  `unsubscribe_token`, `login_token` + `login_token_expires` (15-minute magic
  link). Role helpers: `is_admin`, `can_write`, `can_modify(obj)` — admin
  modifies anything; editor anything not authored by an admin; author only
  their own; viewer nothing. `can_modify` covers both entries and pages.
- **Registration** — pending invite/signup: `email`, `token` (unique),
  `invited_by`, `role`, `accepted`. Expires `REGISTRATION_TTL` (14 days)
  after creation via the `is_expired` property.
- **AuditLog** — generic action log written via `log_audit()`.
- **Page** — static content (e.g. "About") outside the wiki graph: same shape
  as Entry minus backlinks/parent, plus `show_in_nav` / `nav_position`. Shares
  the `/<slug>/` namespace with entries and the same draft/stub semantics.
- **SiteSettings** — singleton row (`id=1`). Site title/footer/theme/custom
  CSS + head/footer HTML, feature toggles (search, subscribe, feeds, history,
  authors, alpha jump, subpage display), multi-user and registration config
  (`invite` / `domain` / `open`, `default_role`, `registration_domain`),
  `site_visibility` (`public` / `registered` / `admin`), digest config, SMTP
  credentials (cleartext at rest), and Mailchimp/Slack/outgoing-webhook
  credentials including the webhook HMAC secret.

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
| `/` | GET | A–Z index (entries, optional nesting), edit heatmap |
| `/<slug>/` | GET | resolver: Entry → Page → (writers) create prompt → 404; child entries 301 to their nested URL |
| `/<parent_slug>/<slug>/` | GET | canonical URL for child entries |
| `/search` | GET | FTS search |
| `/random` | GET | random published entry |
| `/healthz` | GET | DB liveness check |
| `/subscribe` | POST | rate-limited 5/min; double-opt-in via email |
| `/confirm/<token>`, `/unsubscribe/<token>` | GET | |
| `/feed.xml`, `/feed.json` | GET | gated on `site_visibility=public` + `feeds_enabled` |
| `/favicon.svg`, `/site-image` | GET | |
| `/uploads/<filename>` | GET | filename validated against `^[0-9a-f]{32}\.[a-z]{2,4}$` |

A global `before_request` gate redirects anonymous users to `/login` when the
site is private (`site_visibility` is `registered` or `admin`), with an
endpoint allowlist for auth/health/confirmation routes. In `admin` mode a
logged-in non-admin is still denied. The `api` blueprint is excluded and
enforces its own visibility per endpoint (JSON 401/403 instead of an HTML
redirect).

### `admin_bp` (`/dashboard`) — routes attached across five modules

Three decorators (defined in `app/views/admin.py`): `writer_required`
(admin/editor/author), `editor_required` (admin/editor), `admin_required`.
Entry and page mutations additionally check `User.can_modify()` per object.

- `admin_entries.py` — dashboard list (sortable, paginated, shows locks);
  entry new/edit/delete (writer + `can_modify`); publish + preview (login +
  `can_modify`); bulk publish/unpublish/delete (admin, still per-entry
  `can_modify`); history (changelog list).
- `admin_pages.py` — page CRUD (editor), delete (admin).
- `admin_users.py` — invites, role changes (last-admin protection), user
  deletion (references nulled), pending registrations, subscribers, audit log
  (admin).
- `admin_settings.py` — settings, theme picker, site image upload,
  integrations config (admin).
- `admin_import_export.py` — markdown zip export, JSON export/import (import
  is atomic — a failure rolls back the whole batch), test-data seed/clear
  (admin).

### `api_bp` (`/api`) — `app/api.py`

| Route | Methods | Notes |
|---|---|---|
| `/api/v1/entries`, `/api/v1/entries/<slug>` | GET | public read API, 120/min, CSRF-exempt, respects `site_visibility` |
| `/api/entries/search` | GET | autocomplete (title match, `for_parent` filter) |
| `/api/entries/quick-create` | POST | create a **published stub** by title (writer); used by the `[[` link autocomplete and the parent picker |
| `/api/entry/<slug>/preview` | GET | hover-card data |
| `/api/upload-image` | POST | writer; extension allowlist, random hex filename |
| `/api/lock/<type>/<id>`, `.../release` | POST | lock heartbeat/release |
| `/api/preview` | POST | markdown → sanitized HTML |

State-changing API endpoints require the `X-CSRFToken` header; only the two
public `/api/v1/` read endpoints are CSRF-exempt.

## 5. Database & migrations

There is no Alembic migration history, even though `Flask-Migrate` is
installed. Schema evolution is handled by `app/migrate_db.py`, an imperative
script that inspects `PRAGMA table_info` / `sqlite_master` and issues
`ALTER TABLE` / `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX` as needed. It
runs unconditionally on every boot inside `create_app()`, alongside
`db.create_all()` (idempotent) and FTS table creation.

Consequences to be aware of:

- The DDL is raw SQLite — `DATABASE_URL` accepts other backends, but only
  SQLite actually works.
- Multiple gunicorn workers each run the migration at boot; there is no
  cross-process guard.
- A `sort_title` recompute pass runs over all entries on every boot.

## 6. Markdown, sanitization, and search

- **Rendering** (`app/markdown.py`): `mistune` (table + strikethrough
  plugins) renders with `escape=False`; custom footnote pre/post-processing
  turns `[^1]` syntax into hover-able references and an end-of-page section
  (fenced code blocks are excluded); then `bleach.clean()` with an explicit
  tag/attribute allowlist; then heading-ID injection for the TOC.
- **Internal links**: `INTERNAL_LINK_RE` matches `href="/slug/"` in the
  rendered HTML, capturing the final path segment so both flat (`/slug/`) and
  nested child (`/parent/child/`) URLs are recognized.
  `extract_internal_links()` feeds backlink sync. `mark_missing_links()`
  classifies each internal link at render time into three states: **missing**
  (target doesn't exist) → `entry-link-missing` ("not yet written", red);
  **stub** (target is a published stub) → `entry-link-stub` ("still being
  written", amber); **normal** (published entry) → left untouched. The public
  renderer counts only publicly-viewable entries as existing, so a link to a
  draft correctly renders as missing.
- **Search** (`app/search.py`): an FTS5 virtual table (`entry_fts`) indexes
  title and body (markdown stripped to plain text). Kept in sync on
  save/delete; `update_fts_entry(commit=False)` lets importers stay atomic.
  Queries are prefix-match, ranked, parameterized, and return `snippet()`
  excerpts from whichever column matched. (Older databases carried a 3-column
  index that included aliases; the alias feature has been removed and the
  index is rebuilt to two columns.)

## 7. Email, digest, and integrations

- **`app/mail.py`** renders `templates/email/<name>.{txt,html}` and sends via
  SMTP using `SiteSettings` credentials. Without SMTP configured, the email is
  printed to the console and reported as sent — convenient in dev, a footgun
  in production (login links land in the journal).
- **`app/digest.py`** — `flask send-digest` emails subscribers a roundup of
  entries published (and optionally edited) in the last 7 days; it no-ops
  unless today matches `SiteSettings.digest_day` (`--force` overrides). Drafts
  and stubs are excluded, as are import-created EditLog rows (`is_import`).
  Scheduled daily by `deploy/indexcards-digest.timer`.
- **`app/integrations.py`** — synchronous, best-effort outbound HTTP (5s
  timeout, failures logged) via stdlib `urllib`: Mailchimp list subscribe on
  confirmed subscription, Slack announcements on publish/update, and a generic
  outgoing webhook signed with HMAC-SHA256 over the canonical JSON body
  (`X-Webhook-Signature: sha256=<hex>`, keyed on `outgoing_webhook_secret`).
  Webhooks fire only for public sites. Announcements fire from the entry save
  path and the standalone Publish action, and are suppressed for drafts and
  stubs — an entry announces on its first *full* publish, not when it is first
  created as a stub.

## 8. Frontend

- Server-rendered Jinja2 with a small set of vanilla-JS modules in
  `app/static/js/`: `base.js` (toasts, theme toggle, confirms), `entry.js`
  (hover previews, bio popups, copy-link), `editor.js` (the bundled
  ProseMirror editor + markdown textarea sync, word count, localStorage
  autosave, and the `[[` wiki-link autocomplete with inline create-stub),
  `editor-page.js` (slug generation, parent picker with quick-create, lock
  heartbeat + `sendBeacon` release), `heatmap.js`, `dashboard.js`,
  `settings.js`.
- Theme system: color palettes set via `data-site-theme` on `<html>`, a
  dark/light toggle persisted in `localStorage`, and a site-wide default color
  mode. Admin-provided custom CSS/head/footer HTML are injected unsanitized
  (admin-trust boundary, by design).
- Public pages emit microformats (`h-entry`, `h-card`, `u-url`) and OG/Twitter
  meta tags.

## 9. Security model

- **Trust boundaries**: admins are fully trusted (custom HTML injection is a
  feature). Editors/authors are semi-trusted content authors — their markdown
  is sanitized with bleach. Viewers/anonymous users are untrusted.
- **Auth**: magic links only, 15-minute expiry, tokens cleared on use. No
  passwords stored. Invite/signup tokens expire after 14 days. Sessions via
  Flask-Login with `SECRET_KEY` (boot fails in production if it's the dev
  default).
- **CSRF**: global Flask-WTF protection; the API blueprint is CSRF-exempt only
  on the public read endpoints, and state-changing API endpoints require the
  `X-CSRFToken` header.
- **Rate limits**: login/signup 10/min, subscribe 5/min, public API 120/min —
  in-memory per process (multiply by worker count).
- **Uploads**: extension allowlist, random 32-hex filenames, served through a
  strict filename regex; app-level body cap 2 MB.

## 10. Deployment architecture

Single-server Ubuntu/Debian target under `deploy/`:

- **`setup.sh`** (run as root from inside the checkout) installs nginx,
  gunicorn, certbot, and Python; creates a system user `indexcards`; sets up a
  venv; writes `.env` with a random `SECRET_KEY`; installs the systemd service
  and digest timer; configures nginx; obtains a Let's Encrypt certificate.
  Both scripts derive the app root from their own location, so any install
  path works (`/srv/indexcards` is the documented example).
- **`indexcards.service`** — gunicorn, 3 workers, Unix socket at
  `/run/indexcards/indexcards.sock`.
- **`indexcards-digest.service` / `.timer`** — daily `flask send-digest`; the
  command itself checks `digest_day` and no-ops on other days.
- **`nginx.conf`** — TLS termination, direct static and `/uploads/` serving,
  proxy to gunicorn, `client_max_body_size 3M` (app-level cap is 2 MB).
- **`upgrade.sh`** — `git pull` + `pip install` + `chown` + restart.

Backups: the entire site state is `instance/indexcards.db` plus
`instance/uploads/`. Copy those two and you have everything.

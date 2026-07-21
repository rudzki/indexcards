# Index Cards — Technical Documentation

Architecture, data model, routes, and deployment topology for developers. For a
product overview and quick start, see [README.md](README.md); for a field-level
schema reference, see [models.md](models.md).

## 1. Tech stack

| Layer | Choice |
|---|---|
| Web framework | Flask (app-factory pattern, `app/__init__.py`) |
| ORM | Flask-SQLAlchemy |
| Auth | Flask-Login, passwordless (email magic links) |
| CSRF | Flask-WTF (global; the public read API is exempt) |
| Rate limiting | Flask-Limiter (in-memory storage, per process) |
| Database | SQLite (file-based, `instance/indexcards.db`) + FTS5 for search |
| Markdown | `mistune` for rendering, `bleach` for HTML sanitization |
| Frontend | Server-rendered Jinja2 + vanilla JS, no SPA framework |
| Rich-text editor | ProseMirror, bundled into `app/static/js/vendor/` |
| Email | stdlib `smtplib`; prints to the console in dev when SMTP is unset |
| Tests | `pytest`, against in-memory SQLite (`tests/`) |
| WSGI server | gunicorn |
| Deployment | systemd + nginx + certbot on a single Ubuntu/Debian host |

## 2. Application structure

Route modules under `app/views/` stay thin and delegate to standalone logic
modules at the top of `app/`. Those logic modules don't import Flask
blueprints, so they're freely shared across views.

```
app/
  __init__.py       app factory: extension init, blueprint registration,
                     before_request guards (first-run setup, private-site gate),
                     startup DB bootstrap (§5), template filters/context
                     processors (timeago, entry_url, cache-busted static_url,
                     nav items, site settings)
  models.py         SQLAlchemy models (§3) plus URL/publish/access helpers
  views/            routes only — thin, delegate to the logic modules below
    auth.py           public auth: login, signup, setup wizard
    account.py        /account — the signed-in user's own profile
    main.py           public site: index, cards, search, feeds, uploads,
                       subscribe, the public /about and /groups pages
    admin.py          /dashboard blueprint shell + writer/editor/admin decorators
    admin_entries.py  dashboard list, entry CRUD, publish, bulk actions, history
    admin_users.py    users, roles, invites/registrations, subscribers, audit log
    admin_settings.py site settings, themes, nav, site image, editorial content,
                       integrations config
    admin_groups.py   group CRUD, membership, join-request decisions, all-access
    admin_import_export.py  Markdown/JSON export, JSON import, test-data seed/clear
    _helpers.py       shared view helpers (list sorting, upload extension check)
  entries.py        card save/validate, backlink sync, cycle guard, group
                     assignment, integration dispatch, JSON import, RESERVED_SLUGS
  locks.py          soft edit-locking (EditLock): acquire/release/active_locks
  registration.py   invite/signup role resolution (VALID_ROLES, create_registration)
  feeds.py          Atom/JSON feed data assembly, used by main.py
  api.py            /api blueprint — JSON endpoints, per-endpoint auth (§4)
  markdown.py       mistune render → footnotes → bleach sanitize → heading IDs;
                     internal-link extraction and link-state marking
  search.py         SQLite FTS5 index maintenance and querying
  digest.py         `flask send-digest` / `flask rebuild-fts` CLI commands
  mail.py           SMTP sending (env or site settings), email template rendering
  integrations.py   Slack webhook, Mailchimp subscribe, HMAC-signed webhook
  icons.py          inline Bootstrap Icons SVG lookup (header/site icon, favicon)
  migrate_db.py     hand-rolled schema migration runner (§5)
  testdata.py / testdata_content.py   admin-triggered demo content seed/clear
  templates/        Jinja2 templates (public, admin/, email/, errors/)
  static/           CSS, JS, bundled ProseMirror, Bootstrap Icons font
```

`admin_bp` is defined once in `app/views/admin.py`; the sibling `admin_*`
modules import it and attach their own `@admin_bp.route(...)` handlers. Each is
imported explicitly in `create_app()`, so importing `admin.py` alone does not
wire up the full `/dashboard` route table.

Tests live in `tests/` (one `test_*.py` per feature area) and share a `BaseTest`
fixture (`tests/base.py`) that builds the app against an in-memory SQLite
database with CSRF disabled.

## 3. Data model

All models live in `app/models.py`. Field-level detail is in
[models.md](models.md); this section covers the behavior that isn't obvious from
the columns.

- **One card model.** Wiki entries, blog posts, and standalone pages are all
  `Entry` rows — there is no separate page type, and every card goes through one
  save path (`entries.save_content`).
- **Timestamps.** `utcnow()` is the single convention: naive UTC at the storage
  boundary, so in-memory objects match reloaded rows. `iso_utc()` serializes
  those to ISO-8601 with a literal `Z`, shared by feeds, the API, and the
  `timeago` template filter.
- **`entry_url(obj)`** — canonical URL helper: `/<slug>/` for a top-level card,
  `/<parent-slug>/<slug>/` for a child. Used everywhere URLs are built
  (templates via a context processor, feeds, API, integrations).
- **`set_published(obj, published)`** — the single draft/publish transition. It
  stamps `published_at` once, on the first publish, and never clears it. It
  returns `True` on that first publish, which callers use as the "new card"
  signal for integrations.
- **Drafts vs. stubs.** Two independent flags. `is_draft` means unpublished —
  invisible on every public surface (index, card page, search, feeds, API).
  `is_stub` means published-but-skeletal — visible and linkable, shows a "still
  being written" banner, but withheld from feeds, the digest, and integration
  announcements. The `[[`-link **Create new entry** action produces a published
  stub.
- **Hierarchy** is a self-referential adjacency list capped at two levels: a
  card that has a parent cannot itself be a parent. The cap is enforced both in
  the parent picker (client-side) and in `save_content` (server-side), with a
  `_creates_cycle` guard as a backstop.
- **Backlink** — a directed edge `source → target`, fully rebuilt on every save
  by scanning the rendered body for internal links.
- **EditLog** — a per-card changelog row (message, author, timestamp). Rows
  created by an importer carry `is_import=True` so they're excluded from digests
  and the activity heatmap. The history view is a plain audit list — no
  snapshots, diffs, or restore.
- **EditLock** — a soft lock keyed on `(content_type, content_id)` with a
  60-second TTL, refreshed by a 30-second JS heartbeat via `/api/lock/...`.
  Insert races are absorbed by catching the unique-constraint violation.
- **User** — roles are `admin` / `editor` / `author` / `viewer`. `can_write`
  covers the first three; `can_modify(entry)` grants admins and editors every
  card, authors only their own, viewers none. `all_groups` grants read access to
  every group-restricted card without explicit membership.
- **Groups** (`Group`, `GroupJoinRequest`, and the `entry_groups` /
  `group_members` join tables) — see §7.
- **NavItem** — a curated navigation slot pointing at a published card. Any
  published card can be added; slots are ordered by `position` (nulls last) and
  filtered by group access before rendering.
- **SiteSettings** — a singleton row (`id=1`) holding all site configuration:
  identity/theme/custom HTML, editorial prose (epigraph, About body,
  announcement banner, footer colophon), feature toggles, multi-user and
  registration policy, `site_visibility`, digest config, SMTP credentials, and
  integration credentials. `SiteSettings.get()` is the one accessor for row 1.

## 4. Routes

### `auth_bp` (no prefix) — `app/views/auth.py`

| Route | Methods | Notes |
|---|---|---|
| `/login` | GET, POST | rate-limited 10/min; uniform anti-enumeration response |
| `/login/<token>` | GET | consumes a 15-minute magic-link token |
| `/logout` | GET | requires login |
| `/setup` | GET, POST | only usable while zero users exist |
| `/signup` | GET, POST | gated on multi-user + non-invite registration; 10/min |
| `/signup/<token>` | GET, POST | consumes an invite/signup token |

### `account_bp` (no prefix) — `/account` (GET, POST) — the user's own profile.

### `main_bp` (no prefix) — `app/views/main.py`

| Route | Methods | Notes |
|---|---|---|
| `/` | GET | A–Z index (optional nesting), edit heatmap |
| `/about` | GET | built-in About page; 404s when its body is empty |
| `/<slug>/` | GET | resolver: card → (writers) create prompt → 404; child cards 301 to their nested URL |
| `/<parent_slug>/<slug>/` | GET | canonical URL for child cards |
| `/search` | GET | FTS search (404 when search is disabled) |
| `/random` | GET | redirect to a random readable card |
| `/groups` | GET | public group discovery (404 when the feature is off) |
| `/groups/<id>/request` | POST | request to join a group (login required) |
| `/healthz` | GET | DB liveness check |
| `/subscribe` | POST | rate-limited 5/min; double-opt-in via email |
| `/confirm/<token>`, `/unsubscribe/<token>` | GET | subscription confirm/opt-out |
| `/feed.xml`, `/feed.json` | GET | gated on `site_visibility=public` + `feeds_enabled` |
| `/favicon.svg`, `/site-image` | GET | site icon and social image |
| `/uploads/<filename>` | GET | validated against `^[0-9a-f]{32}\.[a-z]{2,4}$` |

A global `before_request` gate redirects anonymous users to `/login` when the
site is private (`site_visibility` is `registered` or `admin`), with an
allowlist for auth/health/confirmation routes. In `admin` mode a logged-in
non-admin is still denied. The `api` blueprint is excluded from this gate and
enforces its own visibility per endpoint (JSON 401/403 instead of an HTML
redirect). A second `before_request` guard redirects everything to `/setup`
until the first user exists.

### `admin_bp` (`/dashboard`) — routes attached across the `admin_*` modules

Three decorators (in `app/views/admin.py`): `writer_required`
(admin/editor/author), `editor_required` (admin/editor), and `admin_required`.
Entry mutations additionally check `User.can_modify()` per card. Group routes
use `groups_admin_required` (admin-only, 404 when the feature is off).

- `admin_entries.py` — dashboard list (sortable, paginated, filterable by
  publish status and by stub, shows active locks, standing stub count); entry
  new/edit/delete (writer + `can_modify`); publish (login + `can_modify`); bulk
  publish/unpublish/delete (writer, still per-card `can_modify`); history.
- `admin_users.py` — invites, role changes (last-admin protection), user
  deletion (references nulled), pending registrations, subscribers, audit log
  (all admin; the section 404s to Settings when multi-user is off).
- `admin_settings.py` — settings, theme picker, site-icon and site-image
  upload, curated navigation (add/remove/reorder), the Site Content editor
  (epigraph, About body, announcement banner, footer colophon), integrations
  config (all admin).
- `admin_groups.py` — group CRUD, member add/remove, all-access grant, and
  approve/deny of join requests (admin).
- `admin_import_export.py` — the Data page: Markdown-zip export, JSON
  export/import (import is atomic — a failure rolls back the whole batch),
  test-data seed/clear (admin).

### `api_bp` (`/api`) — `app/api.py`

| Route | Methods | Notes |
|---|---|---|
| `/api/v1/entries`, `/api/v1/entries/<slug>` | GET | public read API, 120/min, CSRF-exempt, paginated, respects visibility + groups |
| `/api/entries/search` | GET | autocomplete (title match, `for_parent` filter) |
| `/api/entries/quick-create` | POST | create a published **stub** by title (writer); used by the `[[` autocomplete and parent picker |
| `/api/entry/<slug>/preview` | GET | hover-card data |
| `/api/upload-image` | POST | writer; extension allowlist, random hex filename |
| `/api/lock/<type>/<id>`, `.../release` | POST | edit-lock heartbeat/release |

State-changing API endpoints require the `X-CSRFToken` header; only the two
public `/api/v1/` read endpoints are CSRF-exempt. Read endpoints run every query
through the group-access filter (§7) so a restricted card never leaks.

## 5. Database & migrations

Schema evolution is handled by `app/migrate_db.py`, an imperative script that
inspects `PRAGMA table_info` / `sqlite_master` and issues `ALTER TABLE` /
`CREATE TABLE IF NOT EXISTS` / `CREATE INDEX` as needed. On every boot,
`create_app()` runs `db.create_all()` (idempotent), then the migration runner,
then FTS table creation, then seeds the `SiteSettings` singleton if absent.

- The migration runner takes an exclusive `flock` on a lock file beside the
  database, so when gunicorn starts several workers at once only one migrates
  and the rest wait — no "duplicate column" races.
- The DDL is raw SQLite; `DATABASE_URL` accepts other backends, but only SQLite
  is actually supported.
- A `sort_title` recompute pass runs over all cards inside the same lock.

## 6. Markdown, sanitization, and search

- **Rendering** (`app/markdown.py`): `mistune` (strikethrough plugin plus a
  custom `:::details` block rule) renders with `escape=False`; custom footnote
  pre/post-processing turns `[^1]` syntax into hover-able references and an
  end-of-page section (fenced code blocks are left untouched); loose-list `<p>`
  wrappers from the editor are tightened; then `bleach.clean()` with an explicit
  tag/attribute allowlist; then heading-ID injection for the table of contents.
  A separate
  `render_inline_markdown` renders short one-off strings (footer, announcement
  banner) with inline formatting only. **Tables are deliberately unsupported**:
  the editor's ProseMirror schema has no table nodes, so a table authored in
  markdown would be destroyed on the next save. Anything added to the renderer
  needs a matching schema node *and* serializer rule in `editor.js`, or it will
  not survive a round-trip.
- **Internal links**: `INTERNAL_LINK_RE` matches `href="/slug/"` in the rendered
  HTML, capturing the final path segment so both flat (`/slug/`) and nested
  (`/parent/child/`) URLs are recognized. `extract_internal_links()` feeds
  backlink sync. `mark_missing_links()` classifies each internal link at render
  time: **missing** (target doesn't exist) → red "not yet written"; **stub**
  (target is a published stub) → amber "still being written"; **normal** →
  untouched. Only cards the current viewer can actually read count as existing,
  so links to drafts or inaccessible grouped cards render as missing.
- **Search** (`app/search.py`): an FTS5 virtual table (`entry_fts`) indexes
  title and body (markdown stripped to plain text, HTML-escaped before
  indexing). It's kept in sync on save/delete, and `update_fts_entry(commit=
  False)` lets importers stay atomic. Queries are prefix-match, ranked,
  parameterized, and return `snippet()` excerpts. The search view further
  filters results through publish state and group access.

## 7. Access groups

Groups let an admin restrict individual cards to named audiences. The feature is
gated by **both** `multiuser_enabled` and `groups_enabled`
(`groups_feature_enabled()`); with it off, groups are ignored entirely and
grouped cards fall back to normal visibility.

- **Data**: an `Entry` carries a many-to-many `groups`. Empty means public
  (subject to the usual draft/visibility gates). Non-empty means readable only
  by members of one of those groups, plus admins and `all_groups` users.
- **Enforcement**: `user_can_read_entry(user, entry)` is the single-card
  decision (used for the 404 so a restricted card's existence never leaks);
  `accessible_entries_filter(user)` is the matching SQLAlchemy clause applied to
  every list/query (index, search, feeds, backlinks, nav, heatmap, API). Both
  return a permissive no-op when the feature is off.
- **Assignment**: a writer may only tag a card with groups they can already read
  (`assignable_groups`), unioned with the groups already on the card, so no one
  can lock themselves out of their own card.
- **Discovery**: `/groups` lists every group with a state-aware join button;
  a signed-in non-member can file a `GroupJoinRequest`, which an admin approves
  or denies. Admins can also add/remove members directly and grant all-access.
- **Broadcast surfaces**: a grouped card is treated as private — it is excluded
  from feeds, the digest, and Slack/webhook announcements.

## 8. Email, digest, and integrations

- **`app/mail.py`** renders `templates/email/<name>.{txt,html}` and sends via
  SMTP. Config comes from environment variables when `SMTP_HOST` is set
  (overriding the dashboard fields), otherwise from `SiteSettings`. With SMTP
  unconfigured, dev mode prints the email to the console and reports success;
  production refuses and logs an error rather than silently dropping login
  tokens into the journal.
- **`app/digest.py`** — `flask send-digest` emails subscribers a roundup of
  cards published (and optionally edited) in the last 7 days. It no-ops unless
  today matches `SiteSettings.digest_day` (`--force` overrides). Drafts, stubs,
  grouped cards, and import-created log rows are excluded. Scheduled daily by
  `deploy/indexcards-digest.timer`; the command itself checks the day.
- **`app/integrations.py`** — outbound HTTP via stdlib `urllib`, dispatched on a
  daemon thread (fire-and-forget, 5s timeout, failures logged) so a slow
  endpoint never stalls Save. Three integrations: Mailchimp list subscribe on
  confirmed subscription; Slack announcements on publish/update; and a generic
  outgoing webhook signed with HMAC-SHA256 over the canonical JSON body
  (`X-Webhook-Signature: sha256=<hex>`). Webhooks fire only for public sites.
  Announcements fire from both the save path and the standalone Publish action,
  are suppressed for drafts, stubs, and grouped cards, and treat the first full
  publish as "new".

## 9. Frontend

- Server-rendered Jinja2 with a small set of vanilla-JS modules in
  `app/static/js/`: `base.js` (toasts, theme toggle, confirms), `entry.js`
  (hover previews, bio popups, copy-link), `editor.js` (the bundled ProseMirror
  editor + markdown textarea sync, word count, localStorage autosave, and the
  `[[` wiki-link autocomplete with inline create-stub), `editor-page.js` (slug
  generation, parent picker with quick-create, lock heartbeat + `sendBeacon`
  release), `heatmap.js`, `dashboard.js`, `settings.js`, `integrations.js`.
- Theme system: color palettes selected via `data-site-theme` on `<html>`, a
  dark/light toggle persisted in `localStorage`, and a site-wide default color
  mode (auto/light/dark). Five themes ship: default, forest, sepia, midnight,
  stone. Admin-provided custom CSS and head/footer HTML are injected
  unsanitized, by design (admin trust boundary — see §10).
- Public pages emit microformats (`h-entry`, `h-card`, `u-url`) and OG/Twitter
  meta tags.

## 10. Security model

- **Trust boundaries**: admins are fully trusted — custom HTML injection is a
  feature. Editors and authors are semi-trusted content authors; their markdown
  is sanitized with bleach. Viewers and anonymous users are untrusted.
- **Auth**: magic links only, 15-minute expiry, tokens cleared on use. No
  passwords stored. Invite/signup tokens expire after 14 days. Sessions via
  Flask-Login with `SECRET_KEY`; boot fails in production if it's the dev
  default.
- **CSRF**: global Flask-WTF protection; only the two public `/api/v1/` read
  endpoints are exempt, and every state-changing API endpoint requires the
  `X-CSRFToken` header.
- **Rate limits**: login/signup 10/min, subscribe 5/min, public API 120/min —
  in-memory per process (multiply by worker count).
- **Uploads**: extension allowlist, random 32-hex filenames, served through a
  strict filename regex; app-level request-body cap of 2 MB.
- **Injection defense**: rendered bodies, FTS-indexed text, and search snippets
  are all HTML-escaped/sanitized before they reach a page; group badge colors
  and author website links are validated before use.

## 11. Deployment architecture

Single-server Ubuntu/Debian target under `deploy/`:

- **`setup.sh`** (run as root from inside the checkout) installs nginx,
  gunicorn, certbot, and Python; creates the `indexcards` system user; sets up a
  venv; writes `.env` with a random `SECRET_KEY`; installs the systemd service
  and digest timer; configures nginx; and obtains a Let's Encrypt certificate.
  The scripts derive the app root from their own location, so any install path
  works.
- **`indexcards.service`** — gunicorn (3 workers by default) on a Unix socket at
  `/run/indexcards/indexcards.sock`.
- **`indexcards-digest.service` / `.timer`** — daily `flask send-digest`; the
  command no-ops on non-digest days.
- **`nginx.conf`** — TLS termination, direct static and `/uploads/` serving,
  proxy to gunicorn, `client_max_body_size 3M` (the app-level cap is 2 MB).
- **`upgrade.sh`** — `git pull` + `pip install` + `chown` + restart.

Backups: the entire site state is `instance/indexcards.db` plus
`instance/uploads/`. Copy those two and you have everything.

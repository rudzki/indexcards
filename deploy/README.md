# Deploying Index Cards

Standard deployment on Ubuntu/Debian using nginx + gunicorn + systemd.

## Requirements

- Ubuntu 22.04 or Debian 12 (or similar)
- A domain name pointed at the server
- Root access

---

## First deployment

Get the code onto the server first — clone the repo or copy your local
checkout to wherever you want it to live (e.g. `/srv/indexcards`, `/opt/indexcards`,
your home directory — any path works). Then run the setup script as root
from inside that checkout:

```bash
sudo bash deploy/setup.sh
```

The app is installed in place, at whatever path you cloned/copied it to —
the script detects its own location and configures the systemd service and
nginx to match. It will ask two questions — your domain name and an email
address for SSL renewal notices — then handle everything automatically:

- Installs nginx, gunicorn, certbot, and Python 3
- Creates the `indexcards` system user
- Creates the virtualenv and installs dependencies
- Generates a `.env` with a random `SECRET_KEY`
- Installs and starts the systemd service and the weekly digest timer
- Configures nginx and obtains an SSL certificate via Let's Encrypt

When it finishes, open the URL in your browser. The first page is the account setup wizard — create your admin account there.

The examples below use `/srv/indexcards` as the app root — substitute
whatever path you actually deployed to.

---

## Upgrading

```bash
bash /srv/indexcards/deploy/upgrade.sh
```

Pulls latest code, updates dependencies, fixes ownership, and restarts the
service. Run it from inside the deployed checkout (or point the path at
wherever you installed it) — it derives the app root from its own location,
the same way `setup.sh` does.

---

## Useful commands

| Task | Command |
|------|---------|
| View live logs | `journalctl -u indexcards -f` |
| Restart the app | `systemctl restart indexcards` |
| Reload nginx | `systemctl reload nginx` |
| Check nginx config | `nginx -t` |
| Renew SSL certificate | `certbot renew` (runs automatically via cron) |
| Backup the database | `cp /srv/indexcards/instance/indexcards.db ~/backup-$(date +%F).db` |

---

## File locations

| Path | Purpose |
|------|---------|
| `/srv/indexcards/` | App root |
| `/srv/indexcards/.env` | Environment variables (secret — not in git) |
| `/srv/indexcards/instance/indexcards.db` | SQLite database |
| `/srv/indexcards/instance/uploads/` | Uploaded images |
| `/var/log/indexcards/` | Gunicorn access and error logs |
| `/run/indexcards/indexcards.sock` | Gunicorn Unix socket |

---

## Gunicorn worker count

The service defaults to 3 workers, which is suitable for most servers. A common formula is `(2 × CPU cores) + 1`. Edit `/etc/systemd/system/indexcards.service` and run `systemctl daemon-reload && systemctl restart indexcards` to apply.

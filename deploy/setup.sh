#!/usr/bin/env bash
# Full production setup for Index Cards on Ubuntu/Debian.
# Run as root: bash deploy/setup.sh
set -euo pipefail

APP_DIR=/srv/indexcards
APP_USER=indexcards
LOG_DIR=/var/log/indexcards
SERVICE_NAME=indexcards

# ── helpers ──────────────────────────────────────────────────────────────────

bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
step()  { echo; printf '\033[1;34m==> %s\033[0m\n' "$*"; }
ok()    { printf '\033[0;32m    ✓ %s\033[0m\n' "$*"; }
ask()   {
    # ask <var> <prompt> [default]
    local var="$1" prompt="$2" default="${3:-}"
    if [[ -n "$default" ]]; then
        read -rp "    $prompt [$default]: " "$var"
        [[ -z "${!var}" ]] && printf -v "$var" '%s' "$default"
    else
        while [[ -z "${!var:-}" ]]; do
            read -rp "    $prompt: " "$var"
        done
    fi
}
confirm() {
    # confirm <prompt> — returns 0 for yes, 1 for no
    local reply
    read -rp "    $1 [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]]
}

# ── preflight ─────────────────────────────────────────────────────────────────

if [[ $EUID -ne 0 ]]; then
    echo "Run this script as root (sudo bash deploy/setup.sh)." >&2
    exit 1
fi

clear
bold "Index Cards — production setup"
echo
echo "This script will install and configure Index Cards on this server."
echo "It will install: nginx, gunicorn, certbot, and Python 3."
echo

# ── questions ─────────────────────────────────────────────────────────────────

ask DOMAIN      "Domain name (e.g. notes.example.com)"
ask CERT_EMAIL  "Email address for SSL certificate renewal notices"

echo
if confirm "Clone from a git repository?"; then
    ask GIT_URL "Repository URL"
    DO_GIT=1
else
    DO_GIT=0
    echo "    Code will be installed from the current directory."
fi

echo

# ── packages ──────────────────────────────────────────────────────────────────

step "Installing system packages"
apt-get update -q
apt-get install -y -q python3 python3-venv python3-pip nginx certbot python3-certbot-nginx git
ok "Packages installed"

# ── user + directories ────────────────────────────────────────────────────────

step "Creating app user and directories"
id "$APP_USER" &>/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR" "$LOG_DIR" "$APP_DIR/instance/uploads"
ok "User '$APP_USER' ready"

# ── app code ──────────────────────────────────────────────────────────────────

step "Installing app code"
if [[ "$DO_GIT" -eq 1 ]]; then
    if [[ -d "$APP_DIR/.git" ]]; then
        git -C "$APP_DIR" pull
        ok "Repository updated"
    else
        git clone "$GIT_URL" "$APP_DIR"
        ok "Repository cloned"
    fi
else
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    rsync -a --exclude='.env' --exclude='instance/' --exclude='venv/' \
        "$SCRIPT_DIR/../" "$APP_DIR/"
    ok "Files copied from $(dirname "$SCRIPT_DIR")"
fi

# ── virtualenv ────────────────────────────────────────────────────────────────

step "Setting up Python virtualenv"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
ok "Dependencies installed"

# ── environment file ──────────────────────────────────────────────────────────

step "Creating .env"
if [[ -f "$APP_DIR/.env" ]]; then
    ok ".env already exists — skipping (delete it to regenerate)"
else
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    cat > "$APP_DIR/.env" <<EOF
SECRET_KEY=${SECRET_KEY}
DATABASE_URL=sqlite:////srv/indexcards/instance/indexcards.db
SITE_URL=https://${DOMAIN}
EOF
    chmod 640 "$APP_DIR/.env"
    ok ".env written with generated secret key"
fi

# ── ownership ─────────────────────────────────────────────────────────────────

chown -R "$APP_USER:$APP_USER" "$APP_DIR" "$LOG_DIR"

# ── systemd service ───────────────────────────────────────────────────────────

step "Installing systemd service"
cp "$APP_DIR/deploy/indexcards.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
ok "Service enabled and started"

# ── nginx ─────────────────────────────────────────────────────────────────────

step "Configuring nginx"
sed "s/example.com/${DOMAIN}/g" "$APP_DIR/deploy/nginx.conf" \
    > /etc/nginx/sites-available/indexcards

# Remove default site if it's still there
rm -f /etc/nginx/sites-enabled/default

if [[ ! -L /etc/nginx/sites-enabled/indexcards ]]; then
    ln -s /etc/nginx/sites-available/indexcards /etc/nginx/sites-enabled/indexcards
fi

# Temporarily strip the SSL block so nginx starts on plain HTTP for certbot
# (certbot --nginx will add SSL config itself)
nginx -t
systemctl reload nginx
ok "nginx configured for ${DOMAIN}"

# ── SSL certificate ───────────────────────────────────────────────────────────

step "Obtaining SSL certificate via Let's Encrypt"
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$CERT_EMAIL" --redirect
ok "SSL certificate installed and auto-renewal configured"

# ── done ──────────────────────────────────────────────────────────────────────

step "Done"
echo
bold "Index Cards is running at https://${DOMAIN}"
echo
echo "  The first time you visit the site you'll see the account setup wizard."
echo "  Create your admin account there."
echo
echo "  Useful commands:"
echo "    View logs:      journalctl -u indexcards -f"
echo "    Restart app:    systemctl restart indexcards"
echo "    Upgrade:        bash $APP_DIR/deploy/upgrade.sh"
echo "    Backup DB:      cp $APP_DIR/instance/indexcards.db ~/backup-\$(date +%F).db"
echo

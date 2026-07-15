import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app, render_template


def render_email(template_name, **context):
    """Render email/template_name.{txt,html} and return (text, html)."""
    text = render_template(f'email/{template_name}.txt', **context).strip()
    html = render_template(f'email/{template_name}.html', **context)
    return text, html


def smtp_env_configured():
    """True when SMTP is supplied via environment (.env / config).

    When set, the environment config fully overrides the SMTP fields stored in
    Site Settings, so the admin UI notes that its fields are being ignored.
    """
    return bool(current_app.config.get('SMTP_HOST'))


def resolve_smtp(settings):
    """Return the effective SMTP config as a dict, or None if unconfigured.

    Environment config (.env) wins over Site Settings when present.
    """
    if smtp_env_configured():
        cfg = current_app.config
        return {
            'host': cfg.get('SMTP_HOST'),
            'port': cfg.get('SMTP_PORT') or 587,
            'username': cfg.get('SMTP_USERNAME'),
            'password': cfg.get('SMTP_PASSWORD'),
            'use_tls': cfg.get('SMTP_USE_TLS', True),
            'from_address': cfg.get('SMTP_FROM_ADDRESS'),
        }
    if settings and settings.smtp_configured:
        return {
            'host': settings.smtp_host,
            'port': settings.smtp_port or 587,
            'username': settings.smtp_username,
            'password': settings.smtp_password,
            'use_tls': settings.smtp_use_tls,
            'from_address': settings.smtp_from_address,
        }
    return None


def send_email(to, subject, body_text, body_html=None):
    from app import db
    from app.models import SiteSettings
    settings = db.session.get(SiteSettings, 1)
    smtp = resolve_smtp(settings)

    if not smtp or not smtp['from_address']:
        # In debug, print to console — handy for grabbing magic links locally.
        # In production, refuse: silently "succeeding" here would drop working
        # login tokens into the server log while telling the user mail was sent.
        if current_app.debug:
            print(
                f'\n[CONSOLE EMAIL] To: {to}\n'
                f'Subject: {subject}\n'
                f'---\n{body_text}\n---'
            )
            return True
        current_app.logger.error(
            'SMTP is not configured; cannot send email to %s (subject: %r)', to, subject)
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = smtp['from_address']
    msg['To'] = to

    msg.attach(MIMEText(body_text, 'plain'))
    if body_html:
        msg.attach(MIMEText(body_html, 'html'))

    try:
        server = smtplib.SMTP(smtp['host'], smtp['port'])
        if smtp['use_tls']:
            server.starttls()

        if smtp['username']:
            server.login(smtp['username'], smtp['password'] or '')

        server.sendmail(smtp['from_address'], to, msg.as_string())
        server.quit()
    except Exception as e:
        current_app.logger.error(f'Failed to send email to {to}: {e}')
        return False

    return True

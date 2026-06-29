import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app, render_template


def render_email(template_name, **context):
    """Render email/template_name.{txt,html} and return (text, html)."""
    text = render_template(f'email/{template_name}.txt', **context).strip()
    html = render_template(f'email/{template_name}.html', **context)
    return text, html


def send_email(to, subject, body_text, body_html=None):
    from app.models import SiteSettings
    settings = SiteSettings.query.get(1)

    if not settings or not settings.smtp_configured:
        print(
            f'\n[CONSOLE EMAIL] To: {to}\n'
            f'Subject: {subject}\n'
            f'---\n{body_text}\n---'
        )
        return True

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = settings.smtp_from_address
    msg['To'] = to

    msg.attach(MIMEText(body_text, 'plain'))
    if body_html:
        msg.attach(MIMEText(body_html, 'html'))

    port = settings.smtp_port or 587
    try:
        if settings.smtp_use_tls:
            server = smtplib.SMTP(settings.smtp_host, port)
            server.starttls()
        else:
            server = smtplib.SMTP(settings.smtp_host, port)

        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password or '')

        server.sendmail(settings.smtp_from_address, to, msg.as_string())
        server.quit()
    except Exception as e:
        current_app.logger.error(f'Failed to send email to {to}: {e}')
        return False

    return True

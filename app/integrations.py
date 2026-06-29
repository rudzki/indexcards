import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request
from base64 import b64encode
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _post_json(url, payload, headers=None):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        logger.warning('Integration HTTP error: %s', e)
        return None, None


def notify_mailchimp_subscribe(email, settings):
    """Add a new subscriber to the configured Mailchimp list."""
    if not settings.mailchimp_configured:
        return
    url = (
        f'https://{settings.mailchimp_server_prefix}.api.mailchimp.com'
        f'/3.0/lists/{settings.mailchimp_list_id}/members'
    )
    creds = b64encode(f'anystring:{settings.mailchimp_api_key}'.encode()).decode()
    status, body = _post_json(
        url,
        {'email_address': email, 'status': 'subscribed'},
        headers={'Authorization': f'Basic {creds}'},
    )
    if status and status not in (200, 400):  # 400 = already subscribed, which is fine
        logger.warning('Mailchimp returned %s for %s: %s', status, email, body)


def notify_slack_entry(entry, is_new, changelog, settings, base_url=''):
    """Post a new or updated entry announcement to the configured Slack webhook."""
    if not settings.slack_configured:
        return
    if is_new and not settings.slack_announce_new:
        return
    if not is_new and not settings.slack_announce_updates:
        return

    if is_new:
        action = 'New entry'
    else:
        action = 'Updated entry'

    entry_url = f'{base_url.rstrip("/")}/entry/{entry.slug}' if base_url else f'/entry/{entry.slug}'
    text = f'{action}: <{entry_url}|{entry.title}>'
    if entry.summary:
        text += f'\n{entry.summary}'
    if not is_new and changelog:
        text += f'\n_{changelog}_'

    _post_json(settings.slack_webhook_url, {'text': text})


def fire_outgoing_webhook(entry, event, changelog, settings, base_url=''):
    """POST entry data to the configured outgoing webhook URL."""
    if not settings.outgoing_webhook_url:
        return

    entry_url = f'{base_url.rstrip("/")}/entry/{entry.slug}' if base_url else f'/entry/{entry.slug}'
    payload = {
        'event': event,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'entry': {
            'title': entry.title,
            'slug': entry.slug,
            'url': entry_url,
            'summary': entry.summary or '',
            'changelog': changelog or '',
        },
    }
    headers = {}
    if settings.outgoing_webhook_secret:
        sig = hmac.new(
            settings.outgoing_webhook_secret.encode(),
            json.dumps(payload, sort_keys=True, separators=(',', ':')).encode(),
            hashlib.sha256,
        ).hexdigest()
        headers['X-Webhook-Signature'] = f'sha256={sig}'

    _post_json(settings.outgoing_webhook_url, payload, headers=headers)

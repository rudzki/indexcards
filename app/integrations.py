import hashlib
import hmac
import json
import logging
import threading
import urllib.error
import urllib.request
from base64 import b64encode
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _dispatch(fn):
    """Run a fire-and-forget integration call off the request thread.

    The payload (including any _external URLs, which need request context) is
    built by the caller *before* dispatch; only the blocking HTTP POST runs
    here. This keeps a slow or unreachable endpoint from stalling Save, which
    could previously hang for ~10s when both Slack and a webhook were fired."""
    def _run():
        try:
            fn()
        except Exception as e:  # never let a background integration crash silently-loudly
            logger.warning('Integration dispatch error: %s', e)
    threading.Thread(target=_run, daemon=True).start()


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
    headers = {'Authorization': f'Basic {creds}'}
    payload = {'email_address': email, 'status': 'subscribed'}

    def _do():
        status, body = _post_json(url, payload, headers=headers)
        if status == 200:
            return
        # A 400 is only benign when it means the address is already a member;
        # invalid emails, deleted lists and bad merge fields also return 400
        # and must not be swallowed.
        if status == 400 and _mailchimp_error_title(body) == 'Member Exists':
            return
        if status:
            logger.warning('Mailchimp returned %s for %s: %s', status, email, body)

    _dispatch(_do)


def _mailchimp_error_title(body):
    try:
        return json.loads(body).get('title')
    except (ValueError, TypeError, AttributeError):
        return None


def notify_slack_entry(entry, is_new, changelog, settings):
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

    from app.models import entry_url
    text = f'{action}: <{entry_url(entry, external=True)}|{entry.title}>'
    if entry.summary:
        text += f'\n{entry.summary}'
    if not is_new and changelog:
        text += f'\n_{changelog}_'

    webhook_url = settings.slack_webhook_url
    _dispatch(lambda: _post_json(webhook_url, {'text': text}))


def fire_outgoing_webhook(entry, event, changelog, settings):
    """POST entry data to the configured outgoing webhook URL."""
    if not settings.outgoing_webhook_url:
        return

    from app.models import entry_url
    payload = {
        'event': event,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'entry': {
            'title': entry.title,
            'slug': entry.slug,
            'url': entry_url(entry, external=True),
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

    webhook_url = settings.outgoing_webhook_url
    _dispatch(lambda: _post_json(webhook_url, payload, headers=headers))

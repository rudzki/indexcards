"""P2 — Slack / webhook / Mailchimp dispatch, with the network mocked out."""

import hashlib
import hmac
import json
import unittest
from contextlib import contextmanager
from unittest import mock

from tests.base import BaseTest

from app import db, integrations
from app.models import SiteSettings


@contextmanager
def mocked_http():
    """Run integration dispatch inline (no daemon thread) and capture the HTTP
    call, so assertions don't race the real fire-and-forget thread."""
    with mock.patch('app.integrations._dispatch', side_effect=lambda fn: fn()), \
         mock.patch('app.integrations._post_json', return_value=(200, b'')) as post:
        yield post


class SlackTests(BaseTest):
    def _settings(self, **kw):
        s = db.session.get(SiteSettings, 1)
        s.slack_webhook_url = 'https://hooks.slack.test/x'
        for k, v in kw.items():
            setattr(s, k, v)
        return s

    def test_new_fires_when_announce_new(self):
        entry = self._add_entry('Fresh', slug='fresh', summary='hi')
        settings = self._settings(slack_announce_new=True)
        with self.app.test_request_context(), mocked_http() as post:
            integrations.notify_slack_entry(entry, is_new=True, changelog=None, settings=settings)
        post.assert_called_once()
        self.assertIn('New entry', post.call_args.args[1]['text'])

    def test_new_suppressed_when_toggle_off(self):
        entry = self._add_entry('Fresh', slug='fresh')
        settings = self._settings(slack_announce_new=False)
        with self.app.test_request_context(), mocked_http() as post:
            integrations.notify_slack_entry(entry, is_new=True, changelog=None, settings=settings)
        post.assert_not_called()

    def test_update_fires_only_when_announce_updates(self):
        entry = self._add_entry('Fresh', slug='fresh')
        off = self._settings(slack_announce_updates=False)
        with self.app.test_request_context(), mocked_http() as post:
            integrations.notify_slack_entry(entry, is_new=False, changelog='fix', settings=off)
        post.assert_not_called()

        on = self._settings(slack_announce_updates=True)
        with self.app.test_request_context(), mocked_http() as post:
            integrations.notify_slack_entry(entry, is_new=False, changelog='fix', settings=on)
        post.assert_called_once()
        self.assertIn('Updated entry', post.call_args.args[1]['text'])

    def test_unconfigured_never_posts(self):
        entry = self._add_entry('Fresh', slug='fresh')
        settings = db.session.get(SiteSettings, 1)  # no webhook url
        with self.app.test_request_context(), mocked_http() as post:
            integrations.notify_slack_entry(entry, is_new=True, changelog=None, settings=settings)
        post.assert_not_called()


class OutgoingWebhookTests(BaseTest):
    def test_hmac_signature_over_canonical_payload(self):
        entry = self._add_entry('Signed', slug='signed', summary='s')
        settings = db.session.get(SiteSettings, 1)
        settings.outgoing_webhook_url = 'https://hook.test/x'
        settings.outgoing_webhook_secret = 'topsecret'

        with self.app.test_request_context(), mocked_http() as post:
            integrations.fire_outgoing_webhook(entry, event='entry.published',
                                               changelog=None, settings=settings)

        post.assert_called_once()
        _, payload = post.call_args.args
        headers = post.call_args.kwargs['headers']
        expected = hmac.new(
            b'topsecret',
            json.dumps(payload, sort_keys=True, separators=(',', ':')).encode(),
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(headers['X-Webhook-Signature'], f'sha256={expected}')

    def test_no_url_does_not_post(self):
        entry = self._add_entry('X', slug='x')
        settings = db.session.get(SiteSettings, 1)  # no outgoing_webhook_url
        with self.app.test_request_context(), mocked_http() as post:
            integrations.fire_outgoing_webhook(entry, event='entry.updated',
                                               changelog=None, settings=settings)
        post.assert_not_called()


class MailchimpTests(BaseTest):
    def _settings(self):
        s = db.session.get(SiteSettings, 1)
        s.mailchimp_api_key = 'key'
        s.mailchimp_server_prefix = 'us1'
        s.mailchimp_list_id = 'list'
        return s

    def test_member_exists_400_is_swallowed(self):
        settings = self._settings()
        body = json.dumps({'title': 'Member Exists'}).encode()
        with mock.patch('app.integrations._dispatch', side_effect=lambda fn: fn()), \
             mock.patch('app.integrations._post_json', return_value=(400, body)), \
             mock.patch.object(integrations.logger, 'warning') as warn:
            integrations.notify_mailchimp_subscribe('a@b.com', settings)
        warn.assert_not_called()

    def test_other_400_is_logged(self):
        settings = self._settings()
        body = json.dumps({'title': 'Invalid Resource'}).encode()
        with mock.patch('app.integrations._dispatch', side_effect=lambda fn: fn()), \
             mock.patch('app.integrations._post_json', return_value=(400, body)), \
             mock.patch.object(integrations.logger, 'warning') as warn:
            integrations.notify_mailchimp_subscribe('a@b.com', settings)
        warn.assert_called_once()


class FireAndForgetTests(BaseTest):
    def test_failing_endpoint_never_raises(self):
        entry = self._add_entry('X', slug='x')
        settings = db.session.get(SiteSettings, 1)
        settings.slack_webhook_url = 'https://hooks.slack.test/x'
        settings.slack_announce_new = True
        # Real _dispatch (threaded, swallows) + a _post_json that blows up: the
        # request-thread call must still return cleanly.
        with self.app.test_request_context(), \
             mock.patch('app.integrations._post_json', side_effect=RuntimeError('down')):
            integrations.notify_slack_entry(entry, is_new=True, changelog=None, settings=settings)
        # Reaching here without an exception is the assertion.


if __name__ == '__main__':
    unittest.main()

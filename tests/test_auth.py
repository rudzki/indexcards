"""P0/P2 — first-run setup, login, subscribe, registration, and the digest CLI."""

import unittest
from datetime import timedelta
from unittest import mock

from tests.base import BaseTest

from app import db
from app.mail import send_email
from app.models import User, Registration, SiteSettings, utcnow
from app.registration import resolve_role


class SetupTests(BaseTest):
    def setUp(self):
        super().setUp()
        # Undo BaseTest's setup-gate bypass so the first-run redirect is live.
        self.app.config['_SETUP_DONE'] = False

    def test_no_users_redirects_to_setup(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/setup', resp.headers['Location'])

    def test_setup_creates_admin(self):
        self.client.post('/setup', data={'email': 'boss@example.com',
                                         'display_name': 'Boss',
                                         'site_title': 'My Wiki'})
        user = User.query.filter_by(email='boss@example.com').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, 'admin')

    def test_second_setup_short_circuits(self):
        self._make_user('admin', email='first@example.com')
        resp = self.client.get('/setup')
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('/setup', resp.headers['Location'])


class LoginFlowTests(BaseTest):
    def test_unknown_email_shows_neutral_message(self):
        resp = self.client.post('/login', data={'email': 'nobody@example.com'})
        self.assertIn(b'If that email is registered', resp.data)
        # No token minted for a non-existent user (there is none to mint on).
        self.assertEqual(User.query.count(), 0)

    def test_known_email_mints_token_same_message(self):
        user = self._make_user('author', email='known@example.com')
        with mock.patch('app.views.auth.send_email', return_value=True):
            resp = self.client.post('/login', data={'email': 'known@example.com'})
        self.assertIn(b'If that email is registered', resp.data)
        self.assertIsNotNone(db.session.get(User, user.id).login_token)

    def test_valid_token_logs_in_and_is_single_use(self):
        user = self._make_user('author', email='u@example.com')
        with self._acting_as(user):
            token = user.generate_login_token()
        db.session.commit()
        resp = self.client.get(f'/login/{token}')
        self.assertEqual(resp.status_code, 302)
        # Token cleared after use.
        self.assertIsNone(db.session.get(User, user.id).login_token)
        # Re-using the same token now fails.
        again = self.client.get(f'/login/{token}', follow_redirects=True)
        self.assertIn(b'Invalid or expired', again.data)

    def test_expired_token_rejected(self):
        user = self._make_user('author', email='u@example.com')
        user.login_token = 'stale'
        user.login_token_expires = utcnow() - timedelta(minutes=1)
        db.session.commit()
        resp = self.client.get('/login/stale', follow_redirects=True)
        self.assertIn(b'Invalid or expired', resp.data)


class SubscribeFlowTests(BaseTest):
    def test_generic_message_regardless_of_account(self):
        msg = b'Check your email to confirm your subscription.'
        with mock.patch('app.views.main.send_email', return_value=True):
            unknown = self.client.post('/subscribe', data={'email': 'new@example.com'},
                                       follow_redirects=True)
        self.assertIn(msg, unknown.data)

        self._make_user('viewer', email='sub@example.com', subscribed=True)
        already = self.client.post('/subscribe', data={'email': 'sub@example.com'},
                                   follow_redirects=True)
        self.assertIn(msg, already.data)

    def test_confirm_subscribes_and_clears_token(self):
        user = self._make_user('viewer', email='c@example.com')
        token = user.generate_login_token()
        db.session.commit()
        self.client.get(f'/confirm/{token}')
        refreshed = db.session.get(User, user.id)
        self.assertTrue(refreshed.subscribed)
        self.assertIsNone(refreshed.login_token)

    def test_unsubscribe_flips_flag(self):
        user = self._make_user('viewer', email='u@example.com', subscribed=True)
        self.client.get(f'/unsubscribe/{user.unsubscribe_token}')
        self.assertFalse(db.session.get(User, user.id).subscribed)


class RegistrationTests(BaseTest):
    def test_is_expired(self):
        fresh = Registration(email='a@b.com')
        fresh.created_at = utcnow()
        self.assertFalse(fresh.is_expired)

        accepted = Registration(email='a@b.com', accepted=True)
        accepted.created_at = utcnow()
        self.assertTrue(accepted.is_expired)

        old = Registration(email='a@b.com')
        old.created_at = utcnow() - timedelta(days=15)
        self.assertTrue(old.is_expired)

    def test_resolve_role(self):
        settings = db.session.get(SiteSettings, 1)
        settings.default_role = 'author'
        self.assertEqual(resolve_role(Registration(email='x', role='editor'), settings), 'editor')
        self.assertEqual(resolve_role(Registration(email='x', role=None), settings), 'author')
        # A nonsensical default falls back to author, never an escalation.
        settings.default_role = 'admin'
        self.assertEqual(resolve_role(Registration(email='x', role=None), settings), 'author')

    def test_domain_restricted_signup_rejects_other_domains(self):
        self._set_setting(multiuser_enabled=True, registration_method='domain',
                          registration_domain='example.com')
        self.client.post('/signup', data={'email': 'user@other.com'})
        self.assertEqual(Registration.query.count(), 0)

        self.client.post('/signup', data={'email': 'user@example.com'})
        self.assertEqual(Registration.query.filter_by(email='user@example.com').count(), 1)


class SendEmailTests(BaseTest):
    def test_returns_false_in_prod_when_unconfigured(self):
        self.assertFalse(self.app.debug)  # not debug in tests
        self.assertFalse(send_email('x@y.com', 'Subj', 'body'))

    def test_prints_in_debug_when_unconfigured(self):
        self.app.debug = True
        try:
            with mock.patch('builtins.print') as p:
                self.assertTrue(send_email('x@y.com', 'Subj', 'body'))
            p.assert_called()
        finally:
            self.app.debug = False


class DigestCliTests(BaseTest):
    def _run(self, *args):
        return self.app.test_cli_runner().invoke(args=['send-digest', *args])

    def test_respects_digest_day_unless_forced(self):
        # Configure a day that isn't today so the unforced run skips.
        today = utcnow().weekday()
        self._set_setting(digest_day=(today + 1) % 7)
        out = self._run().output
        self.assertIn('Not the configured digest day', out)

    def test_no_subscribers_is_noop(self):
        self._add_entry('Fresh', slug='fresh')  # published now, within window
        out = self._run('--force').output
        self.assertIn('No subscribers', out)

    def test_nothing_new_is_noop(self):
        self._make_user('viewer', subscribed=True)
        out = self._run('--force').output
        self.assertIn('Nothing new', out)

    def test_sends_to_subscribers(self):
        self._add_entry('Fresh', slug='fresh')
        self._make_user('viewer', email='sub@example.com', subscribed=True)
        with mock.patch('app.digest.send_email', return_value=True):
            out = self._run('--force').output
        self.assertIn('Digest sent to 1/1', out)

    def test_stub_is_excluded(self):
        # A published stub has a fresh published_at but is skeletal — it must not
        # be surfaced to subscribers.
        stub = self._add_entry('Stub', slug='stub')
        stub.is_stub = True
        db.session.commit()
        self._make_user('viewer', subscribed=True)
        out = self._run('--force').output
        self.assertIn('Nothing new', out)


if __name__ == '__main__':
    unittest.main()

"""P3 — settings enum validation, feed gating/shape, healthz failure."""

import unittest
from unittest import mock

from tests.base import BaseTest

from app import db
from app.feeds import feeds_available
from app.models import Entry, SiteSettings


class SettingsValidationTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin')
        self._login(self.admin)

    def _post(self, **overrides):
        form = {'site_title': 'T'}
        form.update(overrides)
        self.client.post('/dashboard/settings/', data=form)
        return db.session.get(SiteSettings, 1)

    def test_unknown_enums_fall_back_to_safe_defaults(self):
        s = self._post(site_visibility='bogus', registration_method='bogus',
                       default_role='bogus', site_theme='bogus',
                       default_color_mode='bogus', subpage_display='bogus',
                       digest_day='99')
        self.assertEqual(s.site_visibility, 'public')
        self.assertEqual(s.registration_method, 'invite')
        self.assertEqual(s.default_role, 'viewer')
        self.assertEqual(s.site_theme, 'default')
        self.assertEqual(s.default_color_mode, 'dark')
        self.assertEqual(s.subpage_display, 'both')
        self.assertEqual(s.digest_day, 0)

    def test_blank_smtp_password_preserves_stored(self):
        settings = db.session.get(SiteSettings, 1)
        settings.smtp_password = 'kept-secret'
        db.session.commit()
        self._post(smtp_password='')
        self.assertEqual(db.session.get(SiteSettings, 1).smtp_password, 'kept-secret')


class FeedGatingTests(BaseTest):
    def test_404_when_feeds_disabled(self):
        self._set_setting(site_visibility='public', feeds_enabled=False)
        self.assertEqual(self.client.get('/feed.xml').status_code, 404)
        self.assertEqual(self.client.get('/feed.json').status_code, 404)

    def test_unavailable_when_site_private(self):
        # On a private site the request-level login gate intercepts first, but
        # feeds_available itself must also report False regardless.
        private = self._set_setting(site_visibility='registered', feeds_enabled=True)
        self.assertFalse(feeds_available(private))
        # And the endpoint does not serve the feed to an anonymous visitor.
        self.assertNotEqual(self.client.get('/feed.xml').status_code, 200)

    def test_only_entries_with_published_at_appear(self):
        self._set_setting(site_visibility='public', feeds_enabled=True)
        self._add_entry('Published', slug='pub')
        # A non-draft row that somehow lacks a published_at must not surface.
        ghost = Entry(title='Ghost', slug='ghost', is_draft=False, published_at=None)
        ghost.update_sort_title()
        db.session.add(ghost)
        db.session.commit()

        xml = self.client.get('/feed.xml').data
        self.assertIn(b'Published', xml)
        self.assertNotIn(b'Ghost', xml)

    def test_json_feed_shape(self):
        self._set_setting(site_visibility='public', feeds_enabled=True)
        self._add_entry('Published', slug='pub', summary='s')
        feed = self.client.get('/feed.json').get_json()
        self.assertEqual(feed['version'], 'https://jsonfeed.org/version/1.1')
        self.assertEqual(len(feed['items']), 1)
        self.assertIn('content_html', feed['items'][0])
        self.assertIn('date_published', feed['items'][0])


class HealthzTests(BaseTest):
    def test_ok(self):
        resp = self.client.get('/healthz')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'ok', resp.data)

    def test_503_when_db_check_fails(self):
        with mock.patch.object(db.session, 'execute', side_effect=Exception('db down')):
            resp = self.client.get('/healthz')
        self.assertEqual(resp.status_code, 503)


if __name__ == '__main__':
    unittest.main()

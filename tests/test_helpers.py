"""P3 — supporting utilities: make_slug, sort_key, site_requires_login, timeago."""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from tests.base import BaseTest

from app import db
from app.models import make_slug, sort_key, site_requires_login, SiteSettings


class MakeSlugTests(BaseTest):
    def test_basic_normalization(self):
        self.assertEqual(make_slug('Hello, World!'), 'hello-world')
        self.assertEqual(make_slug('  Multiple   Spaces  '), 'multiple-spaces')
        self.assertEqual(make_slug('Under_score'), 'under-score')

    def test_collapses_and_trims_dashes(self):
        self.assertEqual(make_slug('a -- b'), 'a-b')
        self.assertEqual(make_slug('--edge--'), 'edge')


class SortKeyTests(BaseTest):
    def test_drops_only_leading_stop_word(self):
        self.assertEqual(sort_key('The Apple'), 'apple')
        self.assertEqual(sort_key('A Banana'), 'banana')
        self.assertEqual(sort_key('An Orange'), 'orange')
        # A stop word that isn't leading stays put.
        self.assertEqual(sort_key('Cats and Dogs'), 'cats and dogs')

    def test_strips_leading_punctuation(self):
        self.assertEqual(sort_key('!Bang'), 'bang')


class SiteRequiresLoginTests(BaseTest):
    def test_visibility_matrix(self):
        settings = db.session.get(SiteSettings, 1)
        settings.site_visibility = 'public'
        self.assertFalse(site_requires_login(settings))
        settings.site_visibility = 'registered'
        self.assertTrue(site_requires_login(settings))
        self.assertFalse(site_requires_login(None))


class TimeagoTests(BaseTest):
    def _render(self, dt):
        filt = self.app.jinja_env.filters['timeago']
        return str(filt(dt))

    def test_boundaries(self):
        now = datetime(2026, 7, 11, 12, 0, 0)
        with mock.patch('app.models.utcnow', return_value=now):
            self.assertIn('just now', self._render(now - timedelta(seconds=5)))
            self.assertIn('5m ago', self._render(now - timedelta(minutes=5)))
            self.assertIn('3h ago', self._render(now - timedelta(hours=3)))
            self.assertIn('2d ago', self._render(now - timedelta(days=2)))
            self.assertIn('2mo ago', self._render(now - timedelta(days=70)))
            self.assertIn('1y ago', self._render(now - timedelta(days=400)))

    def test_emits_iso_utc_and_title(self):
        now = datetime(2026, 7, 11, 15, 30, 0)
        with mock.patch('app.models.utcnow', return_value=now):
            html = self._render(now - timedelta(minutes=1))
        self.assertIn('datetime="2026-07-11T15:29:00Z"', html)
        self.assertIn('title="', html)
        self.assertIn('<time', html)

    def test_none_is_empty(self):
        self.assertEqual(self._render(None), '')


if __name__ == '__main__':
    unittest.main()

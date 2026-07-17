"""P0 — the single /<slug>/ namespace: collisions, reserved slugs, resolver.

Entry and Page merged into one card model, so slug uniqueness is now a single
UNIQUE(slug) on `entry`.
"""

import unittest

from tests.base import BaseTest

from app.models import Entry


class SaveEntryCollisionTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin')
        self._login(self.admin)

    def test_new_entry_rejected_on_existing_card_slug(self):
        # An existing card owns slug foo; a new card can't take it.
        self._add_entry('Foo', slug='foo')
        resp = self.client.post('/dashboard/entry/new/',
                                data={'title': 'Foo', 'body_markdown': ''})
        self.assertEqual(resp.status_code, 200)  # re-rendered form, not a redirect
        self.assertEqual(Entry.query.filter_by(slug='foo').count(), 1)

    def test_reserved_slug_rejected(self):
        self.client.post('/dashboard/entry/new/',
                         data={'title': 'Admin Page', 'slug': 'admin'})
        self.assertIsNone(Entry.query.filter_by(slug='admin').first())

    def test_card_created_via_editor(self):
        self.client.post('/dashboard/entry/new/',
                         data={'title': 'News', 'body_markdown': 'hi'})
        news = Entry.query.filter_by(slug='news').first()
        self.assertIsNotNone(news)


class ResolverTests(BaseTest):
    def test_card_reachable_by_url(self):
        self._add_entry('Standalone', slug='standalone', body='standalone body')
        resp = self.client.get('/standalone/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Standalone', resp.data)

    def test_child_flat_url_301s_to_nested(self):
        parent = self._add_entry('Parent', slug='parent')
        self._add_entry('Child', slug='child', parent=parent)
        resp = self.client.get('/child/')
        self.assertEqual(resp.status_code, 301)
        self.assertIn('/parent/child/', resp.headers['Location'])


if __name__ == '__main__':
    unittest.main()

"""P0 — the single /<slug>/ namespace: collisions, reserved slugs, resolver.

Entry and Page merged into one card model, so slug uniqueness is now a single
UNIQUE(slug) on `entry`; listed vs unlisted is just the is_listed flag.
"""

import unittest

from tests.base import BaseTest

from app.models import Entry


class SaveEntryCollisionTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin')
        self._login(self.admin)

    def test_new_entry_rejected_on_unlisted_card_slug(self):
        # An unlisted card ("page") owns slug foo; a new listed card can't take it.
        self._add_page('Foo', slug='foo')
        resp = self.client.post('/dashboard/entry/new/',
                                data={'title': 'Foo', 'body_markdown': ''})
        self.assertEqual(resp.status_code, 200)  # re-rendered form, not a redirect
        cards = Entry.query.filter_by(slug='foo').all()
        self.assertEqual(len(cards), 1)  # still just the original unlisted card
        self.assertFalse(cards[0].is_listed)

    def test_new_entry_rejected_on_existing_entry_slug(self):
        self._add_entry('Foo', slug='foo')
        self.client.post('/dashboard/entry/new/',
                         data={'title': 'Foo', 'body_markdown': ''})
        self.assertEqual(Entry.query.filter_by(slug='foo').count(), 1)

    def test_reserved_slug_rejected(self):
        self.client.post('/dashboard/entry/new/',
                         data={'title': 'Admin Page', 'slug': 'admin'})
        self.assertIsNone(Entry.query.filter_by(slug='admin').first())

    def test_unlisted_card_created_via_editor(self):
        # Leaving "Show in index & feeds" unchecked makes an unlisted card.
        self.client.post('/dashboard/entry/new/',
                         data={'title': 'About', 'body_markdown': 'hi'})
        about = Entry.query.filter_by(slug='about').first()
        self.assertIsNotNone(about)
        self.assertFalse(about.is_listed)

    def test_listed_card_created_via_editor(self):
        self.client.post('/dashboard/entry/new/',
                         data={'title': 'News', 'body_markdown': 'hi', 'is_listed': 'on'})
        news = Entry.query.filter_by(slug='news').first()
        self.assertIsNotNone(news)
        self.assertTrue(news.is_listed)


class ResolverTests(BaseTest):
    def test_unlisted_card_reachable_by_url(self):
        self._add_page('About', slug='about', body='about us')
        resp = self.client.get('/about/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'About', resp.data)

    def test_child_flat_url_301s_to_nested(self):
        parent = self._add_entry('Parent', slug='parent')
        self._add_entry('Child', slug='child', parent=parent)
        resp = self.client.get('/child/')
        self.assertEqual(resp.status_code, 301)
        self.assertIn('/parent/child/', resp.headers['Location'])


if __name__ == '__main__':
    unittest.main()

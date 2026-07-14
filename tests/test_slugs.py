"""P0 — the shared /<slug>/ namespace: collisions, reserved slugs, resolver."""

import unittest

from tests.base import BaseTest

from app import db
from app.models import Entry, Page


class SaveEntryCollisionTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin')
        self._login(self.admin)

    def test_new_entry_rejected_on_page_slug(self):
        self._add_page('Foo', slug='foo')
        resp = self.client.post('/dashboard/entry/new/',
                                data={'title': 'Foo', 'body_markdown': ''})
        self.assertEqual(resp.status_code, 200)  # re-rendered form, not a redirect
        self.assertIsNone(Entry.query.filter_by(slug='foo').first())

    def test_new_entry_rejected_on_existing_entry_slug(self):
        self._add_entry('Foo', slug='foo')
        self.client.post('/dashboard/entry/new/',
                         data={'title': 'Foo', 'body_markdown': ''})
        self.assertEqual(Entry.query.filter_by(slug='foo').count(), 1)

    def test_reserved_slug_rejected(self):
        self.client.post('/dashboard/entry/new/',
                         data={'title': 'Admin Page', 'slug': 'admin'})
        self.assertIsNone(Entry.query.filter_by(slug='admin').first())


class SavePageCollisionTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin')
        self._login(self.admin)

    def test_page_rejected_on_entry_slug(self):
        self._add_entry('Foo', slug='foo')
        resp = self.client.post('/dashboard/pages/new/',
                                data={'title': 'Foo', 'body_markdown': ''})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(Page.query.filter_by(slug='foo').first())

    def test_reserved_slug_rejected(self):
        self.client.post('/dashboard/pages/new/',
                         data={'title': 'API', 'slug': 'api'})
        self.assertIsNone(Page.query.filter_by(slug='api').first())


class ResolverPrecedenceTests(BaseTest):
    def test_entry_wins_over_page_on_same_slug(self):
        # The collision guards normally prevent this, but if both exist the
        # resolver must deterministically prefer the entry.
        self._add_entry('Entry Title', slug='dup', body='entry body')
        page = Page(title='Page Title', slug='dup', body_html='<p>page body</p>')
        page.update_sort_title()
        db.session.add(page)
        db.session.commit()
        resp = self.client.get('/dup/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Entry Title', resp.data)

    def test_child_flat_url_301s_to_nested(self):
        parent = self._add_entry('Parent', slug='parent')
        self._add_entry('Child', slug='child', parent=parent)
        resp = self.client.get('/child/')
        self.assertEqual(resp.status_code, 301)
        self.assertIn('/parent/child/', resp.headers['Location'])


if __name__ == '__main__':
    unittest.main()

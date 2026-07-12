"""P2 — public read-only JSON API shape and visibility gating."""

import unittest

from tests.base import BaseTest

from app import db
from app.models import Alias


class PublicListTests(BaseTest):
    def test_lists_only_published_with_summary_shape(self):
        self._add_entry('Live', slug='live', summary='s', body='b')
        self._add_entry('Draft', slug='draft', is_draft=True)
        data = self.client.get('/api/v1/entries').get_json()

        self.assertEqual(data['total'], 1)
        self.assertEqual(len(data['entries']), 1)
        item = data['entries'][0]
        self.assertEqual(set(item), {'slug', 'title', 'summary', 'published_at',
                                     'updated_at', 'url'})
        self.assertEqual(item['slug'], 'live')
        # Draft never appears.
        self.assertNotIn('draft', [e['slug'] for e in data['entries']])

    def test_pagination_envelope(self):
        for i in range(3):
            self._add_entry(f'E{i}', slug=f'e{i}')
        data = self.client.get('/api/v1/entries?per_page=2').get_json()
        self.assertEqual(data['per_page'], 2)
        self.assertEqual(data['total'], 3)
        self.assertEqual(data['pages'], 2)


class PublicEntryTests(BaseTest):
    def test_published_entry_returns_full_body(self):
        self._add_entry('Full', slug='full', body='hello', summary='s')
        data = self.client.get('/api/v1/entries/full').get_json()
        self.assertEqual(data['slug'], 'full')
        self.assertIn('body_html', data)
        self.assertIn('aliases', data)

    def test_draft_slug_404s(self):
        self._add_entry('Secret', slug='secret', is_draft=True)
        self.assertEqual(self.client.get('/api/v1/entries/secret').status_code, 404)

    def test_unknown_slug_404s(self):
        self.assertEqual(self.client.get('/api/v1/entries/nope').status_code, 404)

    def test_alias_resolves_to_entry(self):
        entry = self._add_entry('Real', slug='real')
        db.session.add(Alias(entry_id=entry.id, title='Nick', slug='nick'))
        db.session.commit()
        data = self.client.get('/api/v1/entries/nick').get_json()
        self.assertEqual(data['slug'], 'real')


class ApiVisibilityTests(BaseTest):
    def test_private_site_returns_json_401(self):
        self._set_setting(site_visibility='registered')
        self._add_entry('X', slug='x')
        for path in ('/api/v1/entries', '/api/v1/entries/x'):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 401)
            self.assertEqual(resp.get_json()['error'], 'Authentication required')

    def test_public_site_returns_200(self):
        self._set_setting(site_visibility='public')
        self._add_entry('X', slug='x')
        self.assertEqual(self.client.get('/api/v1/entries').status_code, 200)


if __name__ == '__main__':
    unittest.main()

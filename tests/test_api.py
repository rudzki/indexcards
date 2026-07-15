"""P2 — public read-only JSON API shape and visibility gating."""

import unittest

from app.models import Entry
from tests.base import BaseTest


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

    def test_draft_slug_404s(self):
        self._add_entry('Secret', slug='secret', is_draft=True)
        self.assertEqual(self.client.get('/api/v1/entries/secret').status_code, 404)

    def test_unknown_slug_404s(self):
        self.assertEqual(self.client.get('/api/v1/entries/nope').status_code, 404)


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


class QuickCreateTests(BaseTest):
    def _post(self, **payload):
        return self.client.post('/api/entries/quick-create', json=payload)

    def test_creates_published_stub_reachable_by_readers(self):
        self._login(self._make_user(role='author'))
        resp = self._post(title='Photosynthesis')
        self.assertEqual(resp.status_code, 201)
        slug = resp.get_json()['slug']

        entry = Entry.query.filter_by(slug=slug).first()
        # A stub, not a hidden draft, so the link resolves for readers.
        self.assertTrue(entry.is_stub)
        self.assertFalse(entry.is_draft)
        self.assertIsNotNone(entry.published_at)
        self.assertEqual(self.client.get(f'/{slug}/').status_code, 200)

    def test_stub_page_shows_banner(self):
        self._login(self._make_user(role='author'))
        slug = self._post(title='Skeletal').get_json()['slug']
        body = self.client.get(f'/{slug}/').get_data(as_text=True)
        self.assertIn('stub-banner', body)

    def test_returns_existing_entry_without_duplicating(self):
        self._login(self._make_user(role='author'))
        existing = self._add_entry('Already Here', slug='already-here')
        resp = self._post(title='Already Here')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['id'], existing.id)

    def test_requires_write_permission(self):
        self._login(self._make_user(role='viewer'))
        self.assertEqual(self._post(title='Nope').status_code, 403)

    def test_returns_existing_unlisted_card(self):
        # After the merge an unlisted card ("page") shares the one namespace, so
        # quick-create over its slug returns that card rather than colliding.
        self._login(self._make_user(role='author'))
        about = self._add_page('About', slug='about')
        resp = self._post(title='About')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['id'], about.id)


class StubLinkRenderTests(BaseTest):
    def _add_home_linking_to(self, target_slug):
        from app import db
        from app.markdown import render_markdown
        home = self._add_entry('Home', slug='home',
                               body=f'See [X](/{target_slug}/).')
        home.body_html = render_markdown(home.body_markdown)
        db.session.commit()
        return home

    def test_link_to_stub_gets_stub_class(self):
        from app import db
        stub = self._add_entry('Stubby', slug='stubby')
        stub.is_stub = True
        db.session.commit()
        self._add_home_linking_to('stubby')
        html = self.client.get('/home/').get_data(as_text=True)
        self.assertIn('entry-link-stub', html)

    def test_link_to_draft_renders_as_missing(self):
        self._add_entry('Hidden', slug='hidden', is_draft=True)
        self._add_home_linking_to('hidden')
        html = self.client.get('/home/').get_data(as_text=True)
        # A draft target isn't publicly reachable, so it must not read as a
        # live link — it's marked missing.
        self.assertIn('entry-link-missing', html)


if __name__ == '__main__':
    unittest.main()

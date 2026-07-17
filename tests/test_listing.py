"""Listing + nav regressions after the Entry/Page merge. There is no more
Listed/Unlisted distinction: every published, non-stub card appears in the
stream surfaces (index, feeds, digest, API). Stubs are still held back from
feeds. Plus NavItem curation, ordering, and cleanup.
"""

import unittest
from unittest import mock

from tests.base import BaseTest

from app import db
from app.models import NavItem


class ListingTests(BaseTest):
    def setUp(self):
        super().setUp()
        self._set_setting(site_visibility='public', feeds_enabled=True,
                          search_enabled=True)
        # A plain entry and a former "page" — both are now ordinary listed cards.
        self.one = self._add_entry('Card One', slug='card-one', body='one body')
        self.two = self._add_entry('Card Two', slug='card-two', body='two body')

    def test_both_in_index(self):
        data = self.client.get('/').data
        self.assertIn(b'Card One', data)
        self.assertIn(b'Card Two', data)

    def test_both_in_feeds(self):
        xml = self.client.get('/feed.xml').data
        self.assertIn(b'Card One', xml)
        self.assertIn(b'Card Two', xml)
        titles = [i['title'] for i in self.client.get('/feed.json').get_json()['items']]
        self.assertIn('Card One', titles)
        self.assertIn('Card Two', titles)

    def test_both_in_api(self):
        listing = self.client.get('/api/v1/entries').get_json()
        slugs = [e['slug'] for e in listing['entries']]
        self.assertIn('card-one', slugs)
        self.assertIn('card-two', slugs)
        self.assertEqual(self.client.get('/api/v1/entries/card-two').status_code, 200)

    def test_present_in_search_and_url(self):
        resp = self.client.get('/search?q=two')
        self.assertIn(b'card-two', resp.data)
        self.assertEqual(self.client.get('/card-two/').status_code, 200)

    def test_both_in_digest_selection(self):
        self._set_setting(digest_include_edits=False)
        self._make_user('viewer', email='sub@example.com', subscribed=True)
        captured = {}

        def fake_render(_template, **kwargs):
            captured['new_entries'] = kwargs.get('new_entries', [])
            return ('text', '<p>html</p>')

        with mock.patch('app.digest.render_email', side_effect=fake_render), \
                mock.patch('app.digest.send_email', return_value=True):
            self.app.test_cli_runner().invoke(args=['send-digest', '--force'])

        titles = [e.title for e in captured.get('new_entries', [])]
        self.assertIn('Card One', titles)
        self.assertIn('Card Two', titles)

    def test_stub_still_held_back_from_feeds(self):
        stub = self._add_entry('Stub Card', slug='stub-card', body='stub')
        stub.is_stub = True
        db.session.commit()
        xml = self.client.get('/feed.xml').data
        self.assertNotIn(b'Stub Card', xml)
        # ...but the stub is still in the index.
        self.assertIn(b'Stub Card', self.client.get('/').data)


class LinkTargetTests(BaseTest):
    def test_any_card_is_a_valid_backlink_target(self):
        from app.entries import sync_backlinks
        self._add_entry('Target', slug='target')
        source = self._add_entry('Source', slug='source',
                                 body='See [Target](/target/).')
        sync_backlinks(source)
        db.session.commit()
        resp = self.client.get('/target/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Source', resp.data)


class ParentPickerTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin')
        self._login(self.admin)

    def test_parent_picker_lists_top_level_cards(self):
        self._add_entry('Parent A', slug='pa')
        self._add_entry('Parent B', slug='pb')
        results = self.client.get('/api/entries/search?for_parent=1').get_json()
        slugs = [r['slug'] for r in results]
        self.assertIn('pa', slugs)
        self.assertIn('pb', slugs)

    def test_plain_search_finds_card(self):
        self._add_entry('Searchable', slug='searchable')
        results = self.client.get('/api/entries/search?q=searchable').get_json()
        slugs = [r['slug'] for r in results]
        self.assertIn('searchable', slugs)


class NavCurationTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin')
        self._login(self.admin)

    def _nav(self, entry, position):
        item = NavItem(entry_id=entry.id, position=position)
        db.session.add(item)
        db.session.commit()
        return item

    def test_nav_renders_in_position_order(self):
        a = self._add_entry('Alpha Nav', slug='alpha-nav')
        b = self._add_entry('Beta Nav', slug='beta-nav')
        self._nav(b, 1)
        self._nav(a, 2)
        body = self.client.get('/').get_data(as_text=True)
        self.assertIn('Beta Nav', body)
        self.assertIn('Alpha Nav', body)
        # ...in position order: Beta (pos 1) before Alpha (pos 2).
        self.assertLess(body.index('Beta Nav'), body.index('Alpha Nav'))

    def test_draft_nav_item_hidden(self):
        d = self._add_entry('Draft Nav', slug='draft-nav', is_draft=True)
        self._nav(d, 1)
        body = self.client.get('/').get_data(as_text=True)
        # A draft in the nav simply doesn't render.
        self.assertNotIn('Draft Nav', body)

    def test_delete_removes_nav_slot(self):
        e = self._add_entry('Doomed', slug='doomed')
        self._nav(e, 1)
        self.client.post(f'/dashboard/entry/{e.id}/delete/')
        self.assertEqual(NavItem.query.filter_by(entry_id=e.id).count(), 0)

    def test_nav_add_move_remove_endpoints(self):
        a = self._add_entry('One', slug='one')
        b = self._add_entry('Two', slug='two')
        self.client.post('/dashboard/nav/add/', data={'entry_id': a.id})
        self.client.post('/dashboard/nav/add/', data={'entry_id': b.id})
        self.assertEqual(NavItem.query.count(), 2)
        # Adding the same card again is rejected (no duplicate slot).
        self.client.post('/dashboard/nav/add/', data={'entry_id': a.id})
        self.assertEqual(NavItem.query.count(), 2)
        # Move the second item up; it should now sort before the first.
        second = NavItem.query.filter_by(entry_id=b.id).first()
        self.client.post(f'/dashboard/nav/{second.id}/move/', data={'direction': 'up'})
        ordered = (NavItem.query
                   .order_by(NavItem.position.asc(), NavItem.id.asc()).all())
        self.assertEqual(ordered[0].entry_id, b.id)
        # Remove it.
        self.client.post(f'/dashboard/nav/{second.id}/remove/')
        self.assertEqual(NavItem.query.count(), 1)


if __name__ == '__main__':
    unittest.main()

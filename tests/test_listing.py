"""Regressions for the Entry/Page merge: an unlisted card (is_listed=False)
stays out of every stream surface (index, feeds, digest, API) but remains
reachable by URL/link/search/nav; plus NavItem curation, ordering, and cleanup.
"""

import unittest
from unittest import mock

from tests.base import BaseTest

from app import db
from app.models import NavItem


class UnlistedExclusionTests(BaseTest):
    def setUp(self):
        super().setUp()
        self._set_setting(site_visibility='public', feeds_enabled=True,
                          search_enabled=True)
        self.listed = self._add_entry('Listed One', slug='listed-one',
                                      body='listed body')
        self.unlisted = self._add_entry('Unlisted One', slug='unlisted-one',
                                        body='unlisted body', is_listed=False)

    def test_absent_from_index(self):
        data = self.client.get('/').data
        self.assertIn(b'Listed One', data)
        self.assertNotIn(b'Unlisted One', data)

    def test_absent_from_feeds(self):
        xml = self.client.get('/feed.xml').data
        self.assertIn(b'Listed One', xml)
        self.assertNotIn(b'Unlisted One', xml)
        items = self.client.get('/feed.json').get_json()['items']
        titles = [i['title'] for i in items]
        self.assertIn('Listed One', titles)
        self.assertNotIn('Unlisted One', titles)

    def test_absent_from_api(self):
        listing = self.client.get('/api/v1/entries').get_json()
        slugs = [e['slug'] for e in listing['entries']]
        self.assertIn('listed-one', slugs)
        self.assertNotIn('unlisted-one', slugs)
        # Single fetch of an unlisted card 404s through the public API.
        self.assertEqual(self.client.get('/api/v1/entries/unlisted-one').status_code, 404)
        self.assertEqual(self.client.get('/api/v1/entries/listed-one').status_code, 200)

    def test_absent_from_random(self):
        # Only the unlisted card would be a candidate if the filter were missing;
        # with it, /random has nothing listed here besides `listed`.
        for _ in range(5):
            loc = self.client.get('/random').headers.get('Location', '')
            self.assertNotIn('/unlisted-one/', loc)

    def test_present_in_search_and_url(self):
        # Unlisted cards are still searchable and directly reachable. (The
        # visible title gets <mark> highlighting, so match on the result link.)
        resp = self.client.get('/search?q=unlisted')
        self.assertIn(b'unlisted-one', resp.data)
        self.assertEqual(self.client.get('/unlisted-one/').status_code, 200)

    def test_excluded_from_digest_selection(self):
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
        self.assertIn('Listed One', titles)
        self.assertNotIn('Unlisted One', titles)


class UnlistedLinkTargetTests(BaseTest):
    def test_unlisted_card_is_valid_backlink_target(self):
        from app.entries import sync_backlinks
        self._add_entry('Target', slug='target', is_listed=False)
        source = self._add_entry('Source', slug='source',
                                 body='See [Target](/target/).')
        sync_backlinks(source)
        db.session.commit()
        # The unlisted card's page lists the linking card as a backlink.
        resp = self.client.get('/target/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Source', resp.data)


class ParentPickerTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin')
        self._login(self.admin)

    def test_parent_picker_excludes_unlisted(self):
        self._add_entry('Listed Parent', slug='lp')
        self._add_entry('Unlisted Parent', slug='up', is_listed=False)
        results = self.client.get('/api/entries/search?for_parent=1').get_json()
        slugs = [r['slug'] for r in results]
        self.assertIn('lp', slugs)
        self.assertNotIn('up', slugs)

    def test_plain_search_includes_unlisted(self):
        self._add_entry('Unlisted Searchable', slug='us', is_listed=False)
        results = self.client.get('/api/entries/search?q=unlisted').get_json()
        slugs = [r['slug'] for r in results]
        self.assertIn('us', slugs)


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
        b = self._add_entry('Beta Nav', slug='beta-nav', is_listed=False)
        self._nav(b, 1)   # unlisted card, first
        self._nav(a, 2)
        body = self.client.get('/').get_data(as_text=True)
        # Both appear (unlisted cards may still be nav items)...
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

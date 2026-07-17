"""P0 — publishing state machine, integration firing, draft visibility."""

import unittest

from tests.base import BaseTest, capture_integrations

from app import db
from app.models import Entry, set_published


class SetPublishedTests(BaseTest):
    def test_first_publish_stamps_and_signals(self):
        entry = Entry(title='X', slug='x')
        first = set_published(entry, True)
        self.assertTrue(first)
        self.assertFalse(entry.is_draft)
        self.assertIsNotNone(entry.published_at)

    def test_republish_does_not_restamp(self):
        entry = Entry(title='X', slug='x')
        set_published(entry, True)
        original = entry.published_at
        second = set_published(entry, False)
        self.assertFalse(second)
        self.assertTrue(entry.is_draft)
        self.assertEqual(entry.published_at, original)
        third = set_published(entry, True)
        self.assertFalse(third)
        self.assertEqual(entry.published_at, original)


class SaveEntryIntegrationTests(BaseTest):
    """The content_changed / first_publish gate that decides whether a save
    announces to Slack/webhooks — and as 'new' vs 'updated'."""

    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin')
        self._login(self.admin)

    def _new(self, **form):
        form.setdefault('title', 'Thing')
        form.setdefault('body_markdown', 'Body one')
        return self.client.post('/dashboard/entry/new/', data=form,
                                follow_redirects=False)

    def test_new_nondraft_fires_as_new(self):
        with capture_integrations() as fire:
            self._new()
        fire.assert_called_once()
        self.assertTrue(fire.call_args.kwargs['is_new'])

    def test_new_draft_fires_nothing(self):
        with capture_integrations() as fire:
            self._new(is_draft='on')
        fire.assert_not_called()

    def test_new_stub_fires_nothing(self):
        # A stub is a published "still being written" placeholder; it should no
        # more announce a "new entry" than a draft does.
        with capture_integrations() as fire:
            self._new(is_stub='on')
        fire.assert_not_called()

    def test_body_edit_of_published_fires_as_updated(self):
        self._new()  # publishes
        entry = Entry.query.filter_by(slug='thing').first()
        with capture_integrations() as fire:
            self.client.post(f'/dashboard/entry/{entry.id}/edit/',
                             data={'title': 'Thing', 'body_markdown': 'Body two'})
        fire.assert_called_once()
        self.assertFalse(fire.call_args.kwargs['is_new'])

    def test_metadata_only_save_fires_nothing(self):
        self._new()
        entry = Entry.query.filter_by(slug='thing').first()
        with capture_integrations() as fire:
            # Same body, only the summary differs -> no content change.
            self.client.post(f'/dashboard/entry/{entry.id}/edit/',
                             data={'title': 'Thing', 'body_markdown': 'Body one',
                                   'summary': 'new summary'})
        fire.assert_not_called()


class PublishRouteTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin')
        self._login(self.admin)

    def test_draft_publish_fires_once_as_first_publish(self):
        entry = self._add_entry('Draft', is_draft=True)
        self.assertIsNone(entry.published_at)
        with capture_integrations() as fire:
            self.client.post(f'/dashboard/entries/{entry.id}/publish/')
        fire.assert_called_once()
        self.assertTrue(fire.call_args.kwargs['is_new'])
        self.assertIsNotNone(db.session.get(Entry, entry.id).published_at)

    def test_republish_does_not_reannounce(self):
        entry = self._add_entry('Live')  # already published
        with capture_integrations() as fire:
            self.client.post(f'/dashboard/entries/{entry.id}/publish/')
        fire.assert_not_called()


class BulkEntryTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin')
        self._login(self.admin)

    def test_bulk_publish_stamps_only_new_rows(self):
        draft = self._add_entry('Draft', is_draft=True)
        live = self._add_entry('Live')
        live_stamp = live.published_at
        with capture_integrations() as fire:
            self.client.post('/dashboard/entries/bulk/',
                             data={'entry_ids': [draft.id, live.id],
                                   'bulk_action': 'publish'})
        # Only the formerly-draft row is announced.
        self.assertEqual(fire.call_count, 1)
        self.assertIsNotNone(db.session.get(Entry, draft.id).published_at)
        # The already-published row keeps its original stamp.
        self.assertEqual(db.session.get(Entry, live.id).published_at, live_stamp)

    def test_bulk_unpublish_preserves_published_at(self):
        live = self._add_entry('Live')
        stamp = live.published_at
        self.client.post('/dashboard/entries/bulk/',
                         data={'entry_ids': [live.id], 'bulk_action': 'unpublish'})
        row = db.session.get(Entry, live.id)
        self.assertTrue(row.is_draft)
        self.assertEqual(row.published_at, stamp)

    def test_bulk_delete_removes_row_fts_and_children(self):
        parent = self._add_entry('Parent')
        child = self._add_entry('Child', parent=parent)

        self.client.post('/dashboard/entries/bulk/',
                         data={'entry_ids': [parent.id], 'bulk_action': 'delete'})

        self.assertIsNone(db.session.get(Entry, parent.id))
        # Child is detached, not deleted.
        self.assertIsNone(db.session.get(Entry, child.id).parent_id)
        # FTS row removed.
        rows = db.session.execute(
            db.text('SELECT rowid FROM entry_fts WHERE rowid = :id'),
            {'id': parent.id}).fetchall()
        self.assertEqual(rows, [])


class DraftVisibilityTests(BaseTest):
    """A draft must not leak through any public read surface."""

    def setUp(self):
        super().setUp()
        self._set_setting(site_visibility='public', feeds_enabled=True,
                          search_enabled=True)
        self.draft = self._add_entry('Secret Draft', slug='secret',
                                     is_draft=True, body='hidden content')

    def test_absent_from_index(self):
        resp = self.client.get('/')
        self.assertNotIn(b'Secret Draft', resp.data)

    def test_entry_page_404(self):
        # No writer logged in -> a draft slug is a plain 404.
        self.assertEqual(self.client.get('/secret/').status_code, 404)

    def test_absent_from_api_list_and_single_404(self):
        listing = self.client.get('/api/v1/entries').get_json()
        self.assertEqual(listing['entries'], [])
        self.assertEqual(self.client.get('/api/v1/entries/secret').status_code, 404)

    def test_absent_from_search_even_though_in_fts(self):
        # The draft is in the FTS index (indexed on save) but filtered out.
        resp = self.client.get('/search?q=hidden')
        self.assertNotIn(b'Secret Draft', resp.data)

    def test_absent_from_feeds(self):
        self.assertNotIn(b'Secret Draft', self.client.get('/feed.xml').data)
        items = self.client.get('/feed.json').get_json()['items']
        self.assertEqual(items, [])

    def test_random_never_redirects_to_draft(self):
        # Only a draft exists, so /random has nothing to send you to.
        resp = self.client.get('/random')
        self.assertNotIn('/secret/', resp.headers.get('Location', ''))


if __name__ == '__main__':
    unittest.main()

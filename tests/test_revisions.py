"""P1 — entry revision history list (changelog audit trail).

Diffs, snapshots, and restore were removed; the history view is now a plain
list of changelog entries.
"""

import unittest

from tests.base import BaseTest

from app.models import Entry, EditLog


class HistoryLoggingTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin')
        self._login(self.admin)

    def _save_new(self, body, changelog=''):
        self.client.post('/dashboard/entry/new/',
                         data={'title': 'Doc', 'body_markdown': body,
                               'changelog': changelog})
        return Entry.query.filter_by(slug='doc').first()

    def test_each_save_records_a_changelog_entry(self):
        entry = self._save_new('v1', changelog='first')
        self.client.post(f'/dashboard/entry/{entry.id}/edit/',
                         data={'title': 'Doc', 'body_markdown': 'v2',
                               'changelog': 'second'})
        logs = (EditLog.query.filter_by(entry_id=entry.id)
                .order_by(EditLog.edited_at.asc()).all())
        self.assertEqual([log.changelog for log in logs], ['first', 'second'])

    def test_history_page_renders(self):
        entry = self._save_new('body', changelog='wrote it')
        resp = self.client.get(f'/dashboard/entry/{entry.id}/history/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'wrote it', resp.data)


if __name__ == '__main__':
    unittest.main()

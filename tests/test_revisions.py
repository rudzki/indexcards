"""P1 — revision snapshots, diff, and restore."""

import unittest
from types import SimpleNamespace
from datetime import datetime

from tests.base import BaseTest

from app import db
from app.models import Entry, EditLog
from app.revisions import compute_diff, build_revisions


def _row(snapshot, i, changelog=None):
    return SimpleNamespace(id=i, body_snapshot=snapshot, changelog=changelog,
                           edited_at=datetime(2026, 1, i + 1), user=None)


class ComputeDiffTests(BaseTest):
    def test_opcodes(self):
        diff = compute_diff('a\nb\nc', 'a\nx\nc')
        self.assertEqual(diff, [('=', 'a'), ('-', 'b'), ('+', 'x'), ('=', 'c')])

    def test_pure_insert_and_delete(self):
        self.assertEqual(compute_diff('', 'new'), [('+', 'new')])
        self.assertEqual(compute_diff('old', ''), [('-', 'old')])


class BuildRevisionsTests(BaseTest):
    def test_metadata_only_carries_last_snapshot_forward(self):
        # items are newest-first: a metadata-only edit (None) over a real body.
        items = [_row(None, 0, 'retitle'), _row('hello world', 1, 'write')]
        revs = build_revisions(items)
        # The metadata-only revision shows the carried-forward body, not empty,
        # so it doesn't render as a full-body deletion.
        self.assertEqual(revs[0]['snapshot'], 'hello world')
        self.assertEqual(revs[0]['char_delta'], 0)
        self.assertEqual(revs[1]['snapshot'], 'hello world')


class SnapshotStorageTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin')
        self._login(self.admin)

    def _save_new(self, body):
        self.client.post('/dashboard/entry/new/',
                         data={'title': 'Doc', 'body_markdown': body})
        return Entry.query.filter_by(slug='doc').first()

    def _edit(self, entry, **form):
        form.setdefault('title', 'Doc')
        self.client.post(f'/dashboard/entry/{entry.id}/edit/', data=form)

    def test_snapshot_only_stored_on_body_change(self):
        entry = self._save_new('v1')
        self._edit(entry, body_markdown='v1', summary='meta change')  # no body change
        self._edit(entry, body_markdown='v2')  # body change

        logs = (EditLog.query.filter_by(entry_id=entry.id)
                .order_by(EditLog.edited_at.asc()).all())
        snapshots = [log.body_snapshot for log in logs]
        self.assertEqual(snapshots[0], 'v1')     # initial save
        self.assertIsNone(snapshots[1])          # metadata-only save
        self.assertEqual(snapshots[2], 'v2')     # real body change

    def test_snapshots_capped_at_50(self):
        entry = self._save_new('body-0')
        for i in range(1, 55):
            self._edit(entry, body_markdown=f'body-{i}')
        kept = (EditLog.query
                .filter(EditLog.entry_id == entry.id,
                        EditLog.body_snapshot.isnot(None))
                .count())
        self.assertEqual(kept, 50)

    def test_restore_writes_new_revision_and_rerenders(self):
        entry = self._save_new('original body')
        first_log = EditLog.query.filter_by(entry_id=entry.id).first()
        self._edit(entry, body_markdown='changed body')

        self.client.post(
            f'/dashboard/entry/{entry.id}/history/{first_log.id}/restore/')
        entry = db.session.get(Entry, entry.id)
        self.assertEqual(entry.body_markdown, 'original body')
        self.assertIn('original body', entry.body_html)
        # A restore is itself a new revision.
        restore_logs = EditLog.query.filter(
            EditLog.entry_id == entry.id,
            EditLog.changelog.like('Restored%')).count()
        self.assertEqual(restore_logs, 1)


if __name__ == '__main__':
    unittest.main()

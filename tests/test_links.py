"""P1 — aliases, entry backlinks, note backlinks."""

import unittest

from tests.base import BaseTest

from app import db
from app.models import Entry, Alias, Backlink, Note, NoteBacklink
from app.entries import sync_aliases, sync_backlinks
from app.notes import sync_note_backlinks


class SyncAliasesTests(BaseTest):
    def _slugs(self, entry):
        return {a.slug for a in entry.aliases}

    def test_add_remove_and_skip_self_and_dupes(self):
        entry = self._add_entry('Main', slug='main')
        sync_aliases(entry, 'One, Two')
        db.session.commit()
        self.assertEqual(self._slugs(entry), {'one', 'two'})

        # Dropping "Two", adding "Three"; a repeat of "One" and the entry's own
        # slug must not create duplicates or a self-alias.
        sync_aliases(entry, 'One, One, Three, Main')
        db.session.commit()
        self.assertEqual(self._slugs(entry), {'one', 'three'})


class BacklinkTests(BaseTest):
    def test_sync_backlinks_rebuilds_and_excludes_self(self):
        target = self._add_entry('Target', slug='target')
        source = self._add_entry('Source', slug='source',
                                 body='See [Target](/target/) and [me](/source/).')
        sync_backlinks(source)
        db.session.commit()
        links = Backlink.query.filter_by(source_entry_id=source.id).all()
        target_ids = {b.target_entry_id for b in links}
        self.assertIn(target.id, target_ids)
        self.assertNotIn(source.id, target_ids)  # self-link excluded

    def test_entry_page_shows_only_nondraft_backlinks(self):
        target = self._add_entry('Target', slug='target')
        live = self._add_entry('Live Source', slug='live',
                               body='[Target](/target/)')
        draft = self._add_entry('Draft Source', slug='draft', is_draft=True,
                                body='[Target](/target/)')
        for e in (live, draft):
            sync_backlinks(e)
        db.session.commit()
        resp = self.client.get('/target/')
        self.assertIn(b'Live Source', resp.data)
        self.assertNotIn(b'Draft Source', resp.data)


class NoteBacklinkTests(BaseTest):
    def test_sync_note_backlinks_rebuilds_from_body(self):
        target = self._add_entry('Target', slug='target')
        note = self._add_note(body='linking [Target](/target/)')
        sync_note_backlinks(note)
        db.session.commit()
        self.assertEqual(
            NoteBacklink.query.filter_by(note_id=note.id,
                                         target_entry_id=target.id).count(), 1)

    def test_deleting_entry_clears_inbound_note_backlinks(self):
        self._make_user('admin')  # for the delete route audit log
        admin = self._make_user('admin')
        self._login(admin)
        target = self._add_entry('Target', slug='target')
        note = self._add_note(body='[Target](/target/)')
        db.session.add(NoteBacklink(note_id=note.id, target_entry_id=target.id))
        db.session.commit()
        self.client.post(f'/dashboard/entry/{target.id}/delete/')
        self.assertEqual(NoteBacklink.query.filter_by(target_entry_id=target.id).count(), 0)

    def test_note_page_shows_only_nondraft_note_backlinks(self):
        self._set_setting(notes_enabled=True)
        target = self._add_entry('Target', slug='target')
        live = self._add_note(body='[Target](/target/)')
        draft = self._add_note(body='[Target](/target/)', is_draft=True)
        for n in (live, draft):
            sync_note_backlinks(n)
        db.session.commit()
        # Only the published note is joined into the entry page's note backlinks.
        note_backlink_rows = (Note.query
                              .join(Note.outgoing_links)
                              .filter(Note.outgoing_links.any(target_entry_id=target.id),
                                      Note.is_draft == False)  # noqa: E712
                              .all())
        self.assertIn(live.id, {n.id for n in note_backlink_rows})
        self.assertNotIn(draft.id, {n.id for n in note_backlink_rows})


if __name__ == '__main__':
    unittest.main()

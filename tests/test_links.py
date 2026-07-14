"""P1 — entry backlinks."""

import unittest

from tests.base import BaseTest

from app import db
from app.models import Backlink
from app.entries import sync_backlinks


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
        self._add_entry('Target', slug='target')
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


if __name__ == '__main__':
    unittest.main()

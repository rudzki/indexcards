"""P1 — FTS index lifecycle and query behavior."""

import unittest

from tests.base import BaseTest

from app import db
from app.search import (
    search_entries, update_fts_entry, delete_fts_entry, rebuild_fts,
)


def _ids(results):
    return {r[0] for r in results}


class FtsLifecycleTests(BaseTest):
    def test_insert_update_delete_round_trip(self):
        entry = self._add_entry('Alpha Beta', slug='ab', body='some content')
        self.assertIn(entry.id, _ids(search_entries('alpha')))

        # Update: retitle and reindex; the old term stops matching.
        entry.title = 'Gamma'
        db.session.commit()
        update_fts_entry(entry)
        self.assertNotIn(entry.id, _ids(search_entries('alpha')))
        self.assertIn(entry.id, _ids(search_entries('gamma')))

        delete_fts_entry(entry.id)
        self.assertEqual(search_entries('gamma'), [])

    def test_rebuild_reindexes_all(self):
        e1 = self._add_entry('Foo One', slug='foo-one')
        e2 = self._add_entry('Bar Two', slug='bar-two')
        db.session.execute(db.text('DELETE FROM entry_fts'))
        db.session.commit()
        self.assertEqual(search_entries('foo'), [])
        rebuild_fts()
        self.assertIn(e1.id, _ids(search_entries('foo')))
        self.assertIn(e2.id, _ids(search_entries('bar')))


class SearchQueryTests(BaseTest):
    def test_prefix_match(self):
        entry = self._add_entry('Testing Ground', slug='tg')
        # A partial term matches via the trailing '*' prefix operator.
        self.assertIn(entry.id, _ids(search_entries('test')))

    def test_quotes_do_not_crash(self):
        self._add_entry('Quote Land', slug='ql')
        # An embedded double-quote must be escaped, not raise a syntax error.
        self.assertEqual(search_entries('say "hi"'), [])

    def test_empty_query_returns_nothing(self):
        self._add_entry('Anything', slug='any')
        self.assertEqual(search_entries(''), [])
        self.assertEqual(search_entries('   '), [])


class SearchViewFiltersDraftsTests(BaseTest):
    def test_draft_in_fts_is_filtered_from_view(self):
        self._set_setting(search_enabled=True)
        draft = self._add_entry('Hidden Term', slug='hidden', is_draft=True,
                                body='findme')
        # It is present in the FTS index...
        self.assertIn(draft.id, _ids(search_entries('findme')))
        # ...but the search page filters drafts out of the rendered results.
        resp = self.client.get('/search?q=findme')
        self.assertNotIn(b'Hidden Term', resp.data)


if __name__ == '__main__':
    unittest.main()

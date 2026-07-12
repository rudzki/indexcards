"""P1 — two-level entry hierarchy: URLs, reparent rules, delete/detach, index nesting."""

import unittest

from tests.base import BaseTest

from app import db
from app.models import Entry, entry_url


class EntryUrlTests(BaseTest):
    def test_child_url_nested_parent_url_flat(self):
        parent = self._add_entry('Parent', slug='parent')
        child = self._add_entry('Child', slug='child', parent=parent)
        with self.app.test_request_context():
            self.assertEqual(entry_url(parent), '/parent/')
            self.assertEqual(entry_url(child), '/parent/child/')


class ReparentRuleTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin')
        self._login(self.admin)

    def _edit(self, entry, parent_id):
        self.client.post(f'/dashboard/entry/{entry.id}/edit/',
                         data={'title': entry.title, 'body_markdown': entry.body_markdown or '',
                               'parent_id': str(parent_id)})
        return db.session.get(Entry, entry.id)

    def test_parent_must_be_top_level(self):
        parent = self._add_entry('P', slug='p')
        child = self._add_entry('C', slug='c', parent=parent)
        loner = self._add_entry('N', slug='n')
        # Adopting a non-top-level entry as parent is refused.
        self.assertIsNone(self._edit(loner, child.id).parent_id)

    def test_entry_with_children_cannot_become_child(self):
        x = self._add_entry('X', slug='x')
        self._add_entry('Y', slug='y', parent=x)
        z = self._add_entry('Z', slug='z')
        self.assertIsNone(self._edit(x, z.id).parent_id)

    def test_self_parent_rejected(self):
        e = self._add_entry('E', slug='e')
        self.assertIsNone(self._edit(e, e.id).parent_id)


class DeleteDetachTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin')
        self._login(self.admin)

    def test_deleting_parent_detaches_children(self):
        parent = self._add_entry('Parent', slug='parent')
        child = self._add_entry('Child', slug='child', parent=parent)
        self.client.post(f'/dashboard/entry/{parent.id}/delete/')
        detached = db.session.get(Entry, child.id)
        self.assertIsNotNone(detached)
        self.assertIsNone(detached.parent_id)
        # The now-top-level child is reachable at its flat URL, not a 500.
        self.assertEqual(self.client.get('/child/').status_code, 200)


class IndexNestingTests(BaseTest):
    def setUp(self):
        super().setUp()
        # Disable the activity heatmap, which would otherwise also render the
        # child's URL and skew the raw occurrence count.
        self._set_setting(show_history=False)
        self.parent = self._add_entry('Parent', slug='parent')
        self.child = self._add_entry('Child', slug='child', parent=self.parent)

    def _index(self):
        return self.client.get('/').data

    def test_both_shows_child_twice(self):
        self._set_setting(subpage_display='both')
        self.assertEqual(self._index().count(b'/parent/child/'), 2)

    def test_nested_shows_child_only_nested(self):
        self._set_setting(subpage_display='nested')
        data = self._index()
        self.assertEqual(data.count(b'/parent/child/'), 1)
        self.assertIn(b'index-children', data)

    def test_separate_shows_child_only_top_level(self):
        self._set_setting(subpage_display='separate')
        data = self._index()
        self.assertEqual(data.count(b'/parent/child/'), 1)
        self.assertNotIn(b'index-children', data)


class NavigationTests(BaseTest):
    def test_prev_next_with_duplicate_sort_title(self):
        """Regression: two entries normalizing to the same sort_title must still
        be reachable via prev/next (the old strict `<` comparison skipped one)."""
        e1 = self._add_entry('Apple', slug='apple')
        e2 = self._add_entry('The Apple', slug='the-apple')
        self.assertEqual(e1.sort_title, e2.sort_title)
        resp = self.client.get('/apple/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'/the-apple/', resp.data)


if __name__ == '__main__':
    unittest.main()

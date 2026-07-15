"""P0 — can_modify matrix, route authorization guards, private-site gate."""

import unittest

from tests.base import BaseTest

from app import db
from app.models import User, Entry


class CanModifyMatrixTests(BaseTest):
    """Pure-function authorization table."""

    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin')
        self.editor = self._make_user('editor')
        self.author = self._make_user('author')
        self.other_author = self._make_user('author')
        self.viewer = self._make_user('viewer')
        self.by_admin = self._add_entry('A', created_by=self.admin.id)
        self.by_author = self._add_entry('B', slug='b', created_by=self.author.id)
        self.orphan = self._add_entry('C', slug='c', created_by=None)

    def test_admin_modifies_everything(self):
        for e in (self.by_admin, self.by_author, self.orphan):
            self.assertTrue(self.admin.can_modify(e))

    def test_editor_modifies_everything(self):
        # Editors are trusted with all content, including admin-authored.
        for e in (self.by_admin, self.by_author, self.orphan):
            self.assertTrue(self.editor.can_modify(e))

    def test_author_own_only(self):
        self.assertTrue(self.author.can_modify(self.by_author))
        self.assertFalse(self.author.can_modify(self.by_admin))
        self.assertFalse(self.other_author.can_modify(self.by_author))

    def test_viewer_none(self):
        for e in (self.by_admin, self.by_author, self.orphan):
            self.assertFalse(self.viewer.can_modify(e))


class RouteGuardTests(BaseTest):
    def test_author_cannot_edit_another_users_entry(self):
        author = self._make_user('author')
        other = self._make_user('author')
        entry = self._add_entry('Theirs', created_by=other.id)
        self._login(author)
        resp = self.client.get(f'/dashboard/entry/{entry.id}/edit/')
        self.assertEqual(resp.status_code, 403)

    def test_non_admin_blocked_from_admin_routes(self):
        editor = self._make_user('editor')
        self._login(editor)
        self.assertEqual(self.client.get('/dashboard/settings/').status_code, 403)
        self.assertEqual(self.client.get('/dashboard/export/json/').status_code, 403)

    def test_editor_can_bulk_delete_admin_content(self):
        admin = self._make_user('admin')
        editor = self._make_user('editor')
        entry = self._add_entry('Admin card', created_by=admin.id)
        self._login(editor)
        self.client.post('/dashboard/entries/bulk/',
                         data={'entry_ids': [entry.id], 'bulk_action': 'delete'})
        self.assertIsNone(db.session.get(Entry, entry.id))

    def test_author_bulk_delete_only_affects_own(self):
        author = self._make_user('author')
        other = self._make_user('author')
        mine = self._add_entry('Mine', slug='mine', created_by=author.id)
        theirs = self._add_entry('Theirs', slug='theirs', created_by=other.id)
        self._login(author)
        self.client.post('/dashboard/entries/bulk/',
                         data={'entry_ids': [mine.id, theirs.id], 'bulk_action': 'delete'})
        self.assertIsNone(db.session.get(Entry, mine.id))
        self.assertIsNotNone(db.session.get(Entry, theirs.id))

class LastAdminAndSelfProtectionTests(BaseTest):
    def setUp(self):
        super().setUp()
        self._set_setting(multiuser_enabled=True)
        self.admin = self._make_user('admin')
        self._login(self.admin)

    def test_cannot_change_own_role(self):
        self.client.post(f'/dashboard/users/{self.admin.id}/role/',
                         data={'role': 'viewer'}, follow_redirects=True)
        self.assertEqual(db.session.get(User, self.admin.id).role, 'admin')

    def test_cannot_delete_own_account(self):
        self.client.post(f'/dashboard/users/{self.admin.id}/delete/',
                         follow_redirects=True)
        self.assertIsNotNone(db.session.get(User, self.admin.id))

    def test_can_demote_another_admin_when_more_than_one(self):
        other = self._make_user('admin')
        self.client.post(f'/dashboard/users/{other.id}/role/',
                         data={'role': 'editor'}, follow_redirects=True)
        self.assertEqual(db.session.get(User, other.id).role, 'editor')


class PrivateSiteTests(BaseTest):
    def setUp(self):
        super().setUp()
        self._set_setting(site_visibility='registered')

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers['Location'])

    def test_allowlisted_endpoints_reachable(self):
        self.assertEqual(self.client.get('/login').status_code, 200)
        self.assertEqual(self.client.get('/healthz').status_code, 200)
        self.assertEqual(self.client.get('/favicon.svg').status_code, 200)

    def test_api_returns_json_401_not_html_redirect(self):
        resp = self.client.get('/api/v1/entries')
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.get_json()['error'], 'Authentication required')

    def test_authenticated_user_can_view(self):
        self._login(self._make_user('viewer'))
        self.assertEqual(self.client.get('/').status_code, 200)


class AdminOnlySiteTests(BaseTest):
    def setUp(self):
        super().setUp()
        self._set_setting(site_visibility='admin')

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers['Location'])

    def test_authenticated_non_admin_forbidden(self):
        self._login(self._make_user('editor'))
        self.assertEqual(self.client.get('/').status_code, 403)

    def test_admin_can_view(self):
        self._login(self._make_user('admin'))
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_non_admin_blocked_from_admin_panel(self):
        # A writer (editor) can normally reach the admin panel, but admin-only
        # visibility locks it down along with the rest of the site.
        self._login(self._make_user('editor'))
        self.assertEqual(self.client.get('/dashboard/').status_code, 403)
        self.assertEqual(self.client.get('/dashboard/settings/').status_code, 403)

    def test_non_admin_can_still_log_out(self):
        self._login(self._make_user('viewer'))
        self.assertEqual(self.client.get('/logout').status_code, 302)

    def test_api_non_admin_returns_json_403(self):
        self._login(self._make_user('viewer'))
        resp = self.client.get('/api/v1/entries')
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json()['error'], 'Administrator access required')

    def test_api_anonymous_returns_json_401(self):
        resp = self.client.get('/api/v1/entries')
        self.assertEqual(resp.status_code, 401)


if __name__ == '__main__':
    unittest.main()

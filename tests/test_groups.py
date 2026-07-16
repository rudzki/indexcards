"""Groups feature: access predicate, read-surface filtering, feature flag,
admin management, and the public request-to-join flow."""

from tests.base import BaseTest

from app import db
from app.models import (Group, GroupJoinRequest, Entry,
                        user_can_read_entry, accessible_entries_filter,
                        groups_feature_enabled, assignable_groups)


class GroupsTestBase(BaseTest):
    def setUp(self):
        super().setUp()
        # Groups only work with multi-user + groups on.
        self._set_setting(multiuser_enabled=True, groups_enabled=True)
        self.admin = self._make_user('admin')
        self.member = self._make_user('viewer')
        self.outsider = self._make_user('viewer')
        self.all_access = self._make_user('viewer')
        self.all_access.all_groups = True
        db.session.commit()
        self.group = Group(name='Staff', slug='staff', description='Internal stuff')
        db.session.add(self.group)
        db.session.commit()
        self.group.members.append(self.member)
        db.session.commit()
        self.public_entry = self._add_entry('Public', slug='public')
        self.grouped_entry = self._add_entry('Secret', slug='secret')
        self.grouped_entry.groups.append(self.group)
        db.session.commit()

    def _login(self, user):
        # BaseTest keeps one app context open for the whole test, and Flask-Login
        # caches the resolved user on that context's `g`. When a single test
        # switches identities, clear the cache so the next request re-resolves
        # from the freshly-set session cookie.
        super()._login(user)
        import flask
        flask.g.pop('_login_user', None)


class AccessPredicateTests(GroupsTestBase):
    def test_public_entry_readable_by_all(self):
        for u in (self.admin, self.member, self.outsider, self.all_access):
            self.assertTrue(user_can_read_entry(u, self.public_entry))

    def test_grouped_entry_member_and_privileged_only(self):
        self.assertTrue(user_can_read_entry(self.member, self.grouped_entry))
        self.assertTrue(user_can_read_entry(self.admin, self.grouped_entry))
        self.assertTrue(user_can_read_entry(self.all_access, self.grouped_entry))
        self.assertFalse(user_can_read_entry(self.outsider, self.grouped_entry))

    def test_anonymous_cannot_read_grouped(self):
        from flask_login import AnonymousUserMixin
        self.assertFalse(user_can_read_entry(AnonymousUserMixin(), self.grouped_entry))
        self.assertTrue(user_can_read_entry(AnonymousUserMixin(), self.public_entry))

    def test_filter_matches_predicate(self):
        def visible_ids(user):
            return {e.id for e in Entry.query.filter(accessible_entries_filter(user)).all()}
        self.assertEqual(visible_ids(self.member), {self.public_entry.id, self.grouped_entry.id})
        self.assertEqual(visible_ids(self.outsider), {self.public_entry.id})
        self.assertEqual(visible_ids(self.admin), {self.public_entry.id, self.grouped_entry.id})
        self.assertEqual(visible_ids(self.all_access), {self.public_entry.id, self.grouped_entry.id})


class FeatureFlagTests(GroupsTestBase):
    def test_flag_off_ignores_groups(self):
        # Turning the feature off re-exposes grouped entries (option A).
        self._set_setting(groups_enabled=False)
        self.assertFalse(groups_feature_enabled(self._set_setting()))
        self.assertTrue(user_can_read_entry(self.outsider, self.grouped_entry))
        ids = {e.id for e in Entry.query.filter(accessible_entries_filter(self.outsider)).all()}
        self.assertIn(self.grouped_entry.id, ids)

    def test_multiuser_off_disables_groups(self):
        self._set_setting(multiuser_enabled=False)
        self.assertTrue(user_can_read_entry(self.outsider, self.grouped_entry))

    def test_public_groups_page_404_when_off(self):
        self._set_setting(groups_enabled=False)
        self.assertEqual(self.client.get('/groups').status_code, 404)


class ReadSurfaceTests(GroupsTestBase):
    def test_index_hides_grouped_from_outsider(self):
        self._login(self.outsider)
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('Public', html)
        self.assertNotIn('Secret', html)

    def test_index_shows_grouped_to_member(self):
        self._login(self.member)
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('Secret', html)

    def test_entry_page_404_for_outsider(self):
        self._login(self.outsider)
        self.assertEqual(self.client.get('/secret/').status_code, 404)

    def test_entry_page_200_for_member(self):
        self._login(self.member)
        self.assertEqual(self.client.get('/secret/').status_code, 200)

    def test_entry_page_404_for_anonymous(self):
        self.assertEqual(self.client.get('/secret/').status_code, 404)

    def test_search_filters_grouped(self):
        self._login(self.outsider)
        html = self.client.get('/search?q=Secret').get_data(as_text=True)
        self.assertNotIn('/secret/', html)
        self._login(self.member)
        html = self.client.get('/search?q=Secret').get_data(as_text=True)
        self.assertIn('/secret/', html)

    def test_api_list_filters_grouped(self):
        self._login(self.outsider)
        slugs = {e['slug'] for e in self.client.get('/api/v1/entries').get_json()['entries']}
        self.assertNotIn('secret', slugs)
        self._login(self.member)
        slugs = {e['slug'] for e in self.client.get('/api/v1/entries').get_json()['entries']}
        self.assertIn('secret', slugs)

    def test_api_single_404_for_outsider(self):
        self._login(self.outsider)
        self.assertEqual(self.client.get('/api/v1/entries/secret').status_code, 404)

    def test_feed_excludes_grouped(self):
        xml = self.client.get('/feed.xml').get_data(as_text=True)
        self.assertIn('Public', xml)
        self.assertNotIn('Secret', xml)


class IntegrationSuppressionTests(GroupsTestBase):
    def test_grouped_entry_does_not_fire_integrations(self):
        from app.entries import _fire_integrations
        from unittest import mock
        with mock.patch('app.integrations.notify_slack_entry') as slack:
            _fire_integrations(self.grouped_entry, is_new=True, changelog=None)
            slack.assert_not_called()
        with mock.patch('app.integrations.notify_slack_entry') as slack:
            self._set_setting(slack_webhook_url='http://x')
            _fire_integrations(self.public_entry, is_new=True, changelog=None)
            slack.assert_called()


class AssignableGroupsTests(GroupsTestBase):
    def test_admin_can_assign_any(self):
        with self._acting_as(self.admin):
            ids = {g.id for g in assignable_groups(self.admin)}
        self.assertIn(self.group.id, ids)

    def test_member_can_only_assign_own(self):
        other = Group(name='Other', slug='other')
        db.session.add(other)
        db.session.commit()
        with self._acting_as(self.member):
            ids = {g.id for g in assignable_groups(self.member)}
        self.assertEqual(ids, {self.group.id})

    def test_save_entry_rejects_unassignable_group(self):
        secret2 = Group(name='Ultra', slug='ultra')
        db.session.add(secret2)
        db.session.commit()
        author = self._make_user('author')
        self.group.members.append(author)
        db.session.commit()
        self._login(author)
        # author is in self.group but not secret2 — only self.group should stick
        self.client.post('/dashboard/entry/new/', data={
            'title': 'Mine', 'body_markdown': 'x', 'is_listed': 'on',
            'group_ids': [self.group.id, secret2.id],
        })
        entry = Entry.query.filter_by(slug='mine').first()
        self.assertEqual({g.id for g in entry.groups}, {self.group.id})


class AdminManagementTests(GroupsTestBase):
    def test_create_and_delete_group(self):
        self._login(self.admin)
        self.client.post('/dashboard/groups/', data={'name': 'Beta', 'color': '#00ff00'})
        g = Group.query.filter_by(slug='beta').first()
        self.assertIsNotNone(g)
        self.assertEqual(g.color, '#00ff00')
        # delete makes its entries public again
        g.entries.append(self.public_entry)
        db.session.commit()
        self.client.post(f'/dashboard/groups/{g.id}/delete/')
        self.assertIsNone(Group.query.filter_by(slug='beta').first())

    def test_invalid_color_falls_back(self):
        self._login(self.admin)
        self.client.post('/dashboard/groups/', data={'name': 'Gamma', 'color': 'red;evil'})
        g = Group.query.filter_by(slug='gamma').first()
        self.assertEqual(g.color, '#6b7785')

    def test_non_admin_cannot_access_group_admin(self):
        self._login(self.member)
        self.assertEqual(self.client.get('/dashboard/groups/').status_code, 403)


class JoinRequestTests(GroupsTestBase):
    def test_request_and_approve_grants_access(self):
        self._login(self.outsider)
        self.client.post(f'/groups/{self.group.id}/request')
        req = GroupJoinRequest.query.filter_by(user_id=self.outsider.id).first()
        self.assertEqual(req.status, 'pending')
        # admin approves
        self._login(self.admin)
        self.client.post(f'/dashboard/groups/requests/{req.id}/approve/')
        db.session.refresh(req)
        self.assertEqual(req.status, 'approved')
        self.assertIn(self.outsider, self.group.members)
        self.assertTrue(user_can_read_entry(self.outsider, self.grouped_entry))

    def test_deny_does_not_grant(self):
        self._login(self.outsider)
        self.client.post(f'/groups/{self.group.id}/request')
        req = GroupJoinRequest.query.filter_by(user_id=self.outsider.id).first()
        self._login(self.admin)
        self.client.post(f'/dashboard/groups/requests/{req.id}/deny/')
        db.session.refresh(req)
        self.assertEqual(req.status, 'denied')
        self.assertNotIn(self.outsider, self.group.members)

    def test_no_duplicate_pending(self):
        self._login(self.outsider)
        self.client.post(f'/groups/{self.group.id}/request')
        self.client.post(f'/groups/{self.group.id}/request')
        self.assertEqual(GroupJoinRequest.query.filter_by(
            user_id=self.outsider.id, status='pending').count(), 1)

    def test_member_request_is_noop(self):
        self._login(self.member)
        self.client.post(f'/groups/{self.group.id}/request')
        self.assertEqual(GroupJoinRequest.query.filter_by(user_id=self.member.id).count(), 0)

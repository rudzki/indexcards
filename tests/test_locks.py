"""P2 — edit-lock acquire / refresh / steal / blocker / release."""

import unittest
from datetime import timedelta

from tests.base import BaseTest

from app import db, locks
from app.models import EditLock, utcnow


class LockTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.a = self._make_user('editor')
        self.b = self._make_user('editor')

    def _lock_row(self):
        return EditLock.query.filter_by(content_type='entry', content_id=1).first()

    def test_fresh_acquire_returns_none(self):
        with self._acting_as(self.a):
            self.assertIsNone(locks.acquire_lock('entry', 1))
        self.assertEqual(self._lock_row().user_id, self.a.id)

    def test_owner_refresh_returns_none(self):
        with self._acting_as(self.a):
            locks.acquire_lock('entry', 1)
            first_expiry = self._lock_row().expires_at
            self.assertIsNone(locks.acquire_lock('entry', 1))
            self.assertGreaterEqual(self._lock_row().expires_at, first_expiry)

    def test_live_lock_blocks_other_user(self):
        with self._acting_as(self.a):
            locks.acquire_lock('entry', 1)
        with self._acting_as(self.b):
            blocker = locks.acquire_lock('entry', 1)
        self.assertEqual(blocker, self.a.display_name)
        # The lock still belongs to A.
        self.assertEqual(self._lock_row().user_id, self.a.id)

    def test_expired_lock_is_stolen(self):
        db.session.add(EditLock(content_type='entry', content_id=1,
                                user_id=self.b.id,
                                expires_at=utcnow() - timedelta(seconds=1)))
        db.session.commit()
        with self._acting_as(self.a):
            self.assertIsNone(locks.acquire_lock('entry', 1))
        self.assertEqual(self._lock_row().user_id, self.a.id)

    def test_release_only_removes_own_lock(self):
        with self._acting_as(self.a):
            locks.acquire_lock('entry', 1)
        # B's release is a no-op against A's lock.
        with self._acting_as(self.b):
            locks.release_lock('entry', 1)
        self.assertIsNotNone(self._lock_row())
        # A can release its own.
        with self._acting_as(self.a):
            locks.release_lock('entry', 1)
        self.assertIsNone(self._lock_row())

    def test_active_locks_reports_live_only(self):
        db.session.add(EditLock(content_type='entry', content_id=2,
                                user_id=self.a.id,
                                expires_at=utcnow() - timedelta(seconds=1)))
        with self._acting_as(self.a):
            locks.acquire_lock('entry', 1)
        active = locks.active_locks('entry')
        self.assertIn(1, active)
        self.assertNotIn(2, active)  # expired lock excluded


if __name__ == '__main__':
    unittest.main()

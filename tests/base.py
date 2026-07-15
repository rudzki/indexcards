"""Shared test harness for the index-cards suite.

Importing this module has the side effect of pointing config.Config at an
isolated temp SQLite database *before* create_app() reads it, so no test ever
touches the real instance DB. Every test module builds on `BaseTest` here
rather than repeating the bootstrap.
"""

import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

import config

_TMP = tempfile.mkdtemp(prefix='indexcards-tests-')
config.Config.SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(_TMP, 'test.db')
config.Config.SECRET_KEY = 'test-secret'
config.Config.WTF_CSRF_ENABLED = False
config.Config.UPLOAD_DIR = os.path.join(_TMP, 'uploads')

from flask_login import login_user  # noqa: E402

from app import create_app, db  # noqa: E402
from app.models import (  # noqa: E402
    Entry, SiteSettings, User, make_slug, set_published,
)


class BaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()

    def setUp(self):
        self.ctx = self.app.app_context()
        self.ctx.push()
        self._reset_db()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    # --- fixtures -------------------------------------------------------

    def _reset_db(self):
        from app.search import create_fts_table
        db.session.remove()
        db.drop_all()
        db.session.execute(db.text('DROP TABLE IF EXISTS entry_fts'))
        db.session.commit()
        db.create_all()
        create_fts_table()
        self.settings = SiteSettings(id=1, site_title='Test')
        db.session.add(self.settings)
        db.session.commit()
        # Skip the first-run setup redirect gate for client tests.
        self.app.config['_SETUP_DONE'] = True

    def _set_setting(self, **kwargs):
        settings = db.session.get(SiteSettings, 1)
        for key, value in kwargs.items():
            setattr(settings, key, value)
        db.session.commit()
        return settings

    _user_seq = 0

    def _make_user(self, role='admin', email=None, display_name=None,
                   subscribed=False):
        BaseTest._user_seq += 1
        email = email or f'{role}{BaseTest._user_seq}@example.com'
        user = User(email=email, display_name=display_name or role.title(),
                    role=role, subscribed=subscribed)
        db.session.add(user)
        db.session.commit()
        return user

    def _login(self, user):
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

    def _add_entry(self, title, slug=None, is_draft=False, body='', summary='',
                   parent=None, created_by=None, is_listed=True):
        entry = Entry(title=title, slug=slug or make_slug(title),
                      body_markdown=body, summary=summary, created_by=created_by,
                      is_listed=is_listed)
        if parent is not None:
            entry.parent_id = parent.id
        entry.update_sort_title()
        set_published(entry, not is_draft)
        db.session.add(entry)
        db.session.commit()
        from app.search import update_fts_entry
        update_fts_entry(entry)
        return entry

    def _add_page(self, title, slug=None, is_draft=False, body=''):
        """A 'page' is now just an unlisted card (is_listed=False) — kept out of
        the index/feeds but reachable by URL, link, and nav."""
        return self._add_entry(title, slug=slug, is_draft=is_draft, body=body,
                               is_listed=False)

    @contextmanager
    def _acting_as(self, user):
        """Run a block inside a request context with `user` logged in, so code
        that reaches for current_user (save_entry, import_entry, …) works."""
        with self.app.test_request_context():
            login_user(user)
            yield


@contextmanager
def capture_integrations():
    """Patch app.entries._fire_integrations and yield the mock so tests can
    assert whether an entry save/publish announced, and with which flag."""
    with mock.patch('app.entries._fire_integrations') as fire:
        yield fire

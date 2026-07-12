"""P2 — JSON round-trip, WordPress import, and import stamping rules."""

import io
import unittest
from unittest import mock

from tests.base import BaseTest

from app import db
from app.models import Entry
from app.entries import import_entry
from app.wordpress_import import import_wordpress_export, InvalidWordPressFile


class ImportStampingTests(BaseTest):
    def test_published_import_without_date_gets_stamped(self):
        user = self._make_user()
        with self._acting_as(user):
            entry = import_entry('Imported', 'imported', 'body',
                                 is_draft=False, published_at=None)
            db.session.commit()
            self.assertIsNotNone(entry.published_at)

    def test_draft_import_stays_unpublished(self):
        user = self._make_user()
        with self._acting_as(user):
            entry = import_entry('Draft', 'draft', 'body',
                                 is_draft=True, published_at=None)
            db.session.commit()
            self.assertTrue(entry.is_draft)
            self.assertIsNone(entry.published_at)

    def test_duplicate_slug_skipped(self):
        user = self._make_user()
        with self._acting_as(user):
            self.assertIsNotNone(import_entry('One', 'dup', 'a'))
            self.assertIsNone(import_entry('Two', 'dup', 'b'))
            db.session.commit()
        self.assertEqual(Entry.query.filter_by(slug='dup').count(), 1)


class JsonRoundTripTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin')
        self._login(self.admin)

    def test_export_then_import_preserves_fields(self):
        entry = self._add_entry('Alpha', slug='alpha', body='hello',
                                summary='sum', is_draft=False)
        from app.models import Alias
        db.session.add(Alias(entry_id=entry.id, title='Al', slug='al'))
        db.session.commit()
        stamp = entry.published_at

        exported = self.client.get('/dashboard/export/json/').data

        # Wipe entries, then re-import the exported payload.
        Alias.query.delete()
        Entry.query.delete()
        db.session.commit()

        self.client.post('/dashboard/import/json/',
                         data={'file': (io.BytesIO(exported), 'entries.json')},
                         content_type='multipart/form-data')

        restored = Entry.query.filter_by(slug='alpha').first()
        self.assertIsNotNone(restored)
        self.assertEqual(restored.title, 'Alpha')
        self.assertFalse(restored.is_draft)
        self.assertEqual({a.title for a in restored.aliases}, {'Al'})
        self.assertEqual(restored.published_at, stamp)

    def test_malformed_json_rejected(self):
        self.client.post('/dashboard/import/json/',
                         data={'file': (io.BytesIO(b'{not json'), 'x.json')},
                         content_type='multipart/form-data')
        self.assertEqual(Entry.query.count(), 0)

    def test_non_array_rejected(self):
        self.client.post('/dashboard/import/json/',
                         data={'file': (io.BytesIO(b'{"title": "x"}'), 'x.json')},
                         content_type='multipart/form-data')
        self.assertEqual(Entry.query.count(), 0)

    def test_partial_failure_rolls_back(self):
        payload = b'[{"title": "A", "slug": "a"}, {"title": "B", "slug": "b"}]'
        calls = {'n': 0}
        real = import_entry

        def flaky(*args, **kwargs):
            calls['n'] += 1
            if calls['n'] == 1:
                return real(*args, **kwargs)
            raise RuntimeError('boom')

        with mock.patch('app.views.admin_import_export.import_entry', side_effect=flaky):
            self.client.post('/dashboard/import/json/',
                             data={'file': (io.BytesIO(payload), 'x.json')},
                             content_type='multipart/form-data')
        # The first insert must be rolled back — no partial import.
        self.assertEqual(Entry.query.count(), 0)


WXR = b"""<?xml version="1.0"?>
<rss xmlns:wp="http://wordpress.org/export/1.2/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
 <item>
  <title>Hello Post</title>
  <wp:post_name>hello-post</wp:post_name>
  <wp:post_type>post</wp:post_type>
  <wp:status>publish</wp:status>
  <wp:post_date>2020-01-02 03:04:05</wp:post_date>
  <content:encoded>&lt;p&gt;Body text&lt;/p&gt;</content:encoded>
 </item>
 <item>
  <title>Draft Page</title>
  <wp:post_name>draft-page</wp:post_name>
  <wp:post_type>page</wp:post_type>
  <wp:status>draft</wp:status>
 </item>
 <item>
  <title>No Slug Here</title>
  <wp:post_type>post</wp:post_type>
  <wp:status>publish</wp:status>
 </item>
 <item>
  <title>An Attachment</title>
  <wp:post_type>attachment</wp:post_type>
 </item>
</channel>
</rss>"""


class WordPressImportTests(BaseTest):
    def test_parses_posts_and_pages(self):
        user = self._make_user()
        with self._acting_as(user):
            count = import_wordpress_export(io.BytesIO(WXR))
            db.session.commit()

        # post + page + no-slug post = 3; the attachment is skipped.
        self.assertEqual(count, 3)

        post = Entry.query.filter_by(slug='hello-post').first()
        self.assertFalse(post.is_draft)
        self.assertEqual(post.published_at.year, 2020)
        self.assertEqual(post.published_at.month, 1)

        page = Entry.query.filter_by(slug='draft-page').first()
        self.assertTrue(page.is_draft)

        # No <wp:post_name> -> slug falls back to make_slug(title).
        self.assertIsNotNone(Entry.query.filter_by(slug='no-slug-here').first())

    def test_invalid_xml_raises(self):
        with self.assertRaises(InvalidWordPressFile):
            import_wordpress_export(io.BytesIO(b'this is not xml <<<'))


if __name__ == '__main__':
    unittest.main()

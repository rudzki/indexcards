"""Site Content page: epigraph, About page, and the (renamed) colophon.

The site's editorial prose lives in Dashboard → Site Content, separate from
operational Settings. Epigraph shows atop the homepage; About is served at
/about with a conditional menu link; the colophon is the footer text.
"""

import unittest

from tests.base import BaseTest

from app.models import SiteSettings, Entry


class SiteContentPageTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin')

    def test_requires_admin(self):
        # Anonymous / non-admin can't reach the page.
        author = self._make_user('author')
        self._login(author)
        self.assertEqual(self.client.get('/dashboard/content/').status_code, 403)

    def test_get_renders_for_admin(self):
        self._login(self.admin)
        resp = self.client.get('/dashboard/content/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Epigraph', resp.data)
        self.assertIn(b'Colophon', resp.data)

    def test_post_saves_all_three_fields(self):
        self._login(self.admin)
        self.client.post('/dashboard/content/', data={
            'epigraph': 'A wiki of *ideas*.',
            'about_markdown': '# About\n\nHello.',
            'footer_text': 'Built with **care**.',
        })
        s = SiteSettings.get()
        self.assertEqual(s.epigraph, 'A wiki of *ideas*.')
        self.assertEqual(s.about_markdown, '# About\n\nHello.')
        self.assertEqual(s.footer_text, 'Built with **care**.')

    def test_colophon_moved_out_of_settings(self):
        # The footer field no longer lives on the Settings page.
        self._login(self.admin)
        settings_html = self.client.get('/dashboard/settings/').data
        self.assertNotIn(b'name="footer_text"', settings_html)
        # ...it's on Site Content instead.
        content_html = self.client.get('/dashboard/content/').data
        self.assertIn(b'name="footer_text"', content_html)


class EpigraphTests(BaseTest):
    def test_epigraph_renders_on_homepage(self):
        self._set_setting(epigraph='A wiki of *ideas*.')
        data = self.client.get('/').data
        self.assertIn(b'site-epigraph', data)
        # Markdown is rendered (the * becomes <em>).
        self.assertIn(b'<em>ideas</em>', data)

    def test_epigraph_absent_when_blank(self):
        self._set_setting(epigraph='')
        self.assertNotIn(b'site-epigraph', self.client.get('/').data)


class AboutPageTests(BaseTest):
    def test_about_200_with_body_when_set(self):
        self._set_setting(about_markdown='# About us\n\nThe *story*.')
        resp = self.client.get('/about')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'About us', resp.data)
        self.assertIn(b'<em>story</em>', resp.data)

    def test_about_404_when_blank(self):
        self._set_setting(about_markdown='')
        self.assertEqual(self.client.get('/about').status_code, 404)
        # Whitespace-only is treated as empty too.
        self._set_setting(about_markdown='   \n  ')
        self.assertEqual(self.client.get('/about').status_code, 404)

    def test_menu_link_only_when_set(self):
        self._set_setting(about_markdown='')
        self.assertNotIn(b'href="/about"', self.client.get('/').data)
        self._set_setting(about_markdown='About text')
        self.assertIn(b'href="/about"', self.client.get('/').data)

    def test_about_respects_private_site(self):
        # On a registered-only site, an anonymous visitor is redirected to login
        # rather than shown the page.
        self._set_setting(about_markdown='Secret about', site_visibility='registered')
        resp = self.client.get('/about')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers['Location'])


class AboutSlugReservedTests(BaseTest):
    def test_about_slug_rejected_in_editor(self):
        admin = self._make_user('admin')
        self._login(admin)
        self.client.post('/dashboard/entry/new/',
                         data={'title': 'About', 'slug': 'about', 'body_markdown': 'x'})
        self.assertIsNone(Entry.query.filter_by(slug='about').first())


if __name__ == '__main__':
    unittest.main()

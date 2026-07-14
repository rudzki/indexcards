"""P0/P1 — markdown rendering, sanitization, links, headings, strip."""

import unittest

from tests.base import BaseTest

from app.markdown import (
    render_markdown, extract_internal_links, mark_missing_links,
    add_heading_ids, extract_toc, strip_markdown,
)


class RenderTests(BaseTest):
    def test_script_is_sanitized(self):
        html = render_markdown('<script>alert(1)</script>')
        self.assertNotIn('<script>', html)

    def test_footnotes_rendered(self):
        html = render_markdown('Hello[^1]\n\n[^1]: A note')
        self.assertIn('footnote-ref', html)
        self.assertIn('Footnotes', html)

    def test_loose_list_items_tightened(self):
        html = render_markdown('- a\n\n- b')
        self.assertIn('<li>a', html)
        self.assertNotIn('<li><p>', html)

    def test_footnote_ref_in_code_fence_left_literal(self):
        html = render_markdown('```\nsee[^1]\n```\n\n[^1]: note')
        # The ref inside the fence must not become a live footnote link.
        self.assertIn('see[^1]', html)


class SanitizeTests(BaseTest):
    def test_allowed_markup_kept(self):
        html = render_markdown('[link](https://example.com)')
        self.assertIn('href="https://example.com"', html)

        img = render_markdown('![alt](https://example.com/i.png)')
        self.assertIn('<img', img)
        self.assertIn('src="https://example.com/i.png"', img)

        table = render_markdown('| a | b |\n| - | - |\n| 1 | 2 |')
        self.assertIn('<table>', table)

    def test_disallowed_tag_stripped_text_kept(self):
        html = render_markdown('<div class="x">hi</div>')
        self.assertNotIn('<div', html)
        self.assertIn('hi', html)

    def test_dangerous_href_schemes_neutralized(self):
        for scheme in ('javascript:alert(1)', 'data:text/html;base64,x'):
            html = render_markdown(f'[x]({scheme})')
            self.assertNotIn('javascript:', html)
            self.assertNotIn('data:text/html', html)


class InternalLinkTests(BaseTest):
    def test_extract_flat_and_nested(self):
        md = 'See [a](/foo/) and [b](/parent/child/).'
        self.assertEqual(extract_internal_links(md), {'foo', 'child'})

    def test_extract_empty(self):
        self.assertEqual(extract_internal_links(''), set())

    def test_mark_missing_only_unknown(self):
        html = '<a href="/known/">k</a> <a href="/unknown/">u</a>'
        marked = mark_missing_links(html, {'known'})
        self.assertEqual(marked.count('entry-link-missing'), 1)
        # The missing class attaches to the unknown link, not the known one.
        self.assertIn('entry-link-missing" title="Unknown', marked)

    def test_mark_stub_links(self):
        html = ('<a href="/known/">k</a> <a href="/stubby/">s</a> '
                '<a href="/gone/">g</a>')
        marked = mark_missing_links(html, {'known', 'stubby'}, {'stubby'})
        # Existing non-stub link is untouched; stub link is tagged; missing link
        # is tagged as missing, not stub.
        self.assertNotIn('entry-link-stub" title="Stub — still being written" href="/known/"',
                         marked)
        self.assertIn('entry-link-stub" title="Stub — still being written" href="/stubby/"',
                      marked)
        self.assertIn('entry-link-missing" title="Gone — not yet written" href="/gone/"',
                      marked)


class HeadingTocTests(BaseTest):
    def test_duplicate_headings_get_unique_ids(self):
        html = add_heading_ids('<h2>Dup</h2><h2>Dup</h2>')
        self.assertIn('<h2 id="dup">', html)
        self.assertIn('<h2 id="dup-1">', html)

    def test_extract_toc_shape(self):
        html = add_heading_ids('<h2>Hello World</h2><h3>Sub</h3>')
        toc = extract_toc(html)
        self.assertEqual(toc, [
            {'level': 2, 'text': 'Hello World', 'id': 'hello-world'},
            {'level': 3, 'text': 'Sub', 'id': 'sub'},
        ])


class StripMarkdownTests(BaseTest):
    def test_strips_syntax_and_footnotes(self):
        out = strip_markdown('# Title\n\nHello[^1] **bold**\n\n[^1]: the def')
        self.assertIn('Title', out)
        self.assertIn('bold', out)
        self.assertNotIn('#', out)
        self.assertNotIn('*', out)
        self.assertNotIn('[^1]', out)
        # The footnote *definition* text is dropped for the summary/index.
        self.assertNotIn('the def', out)

    def test_empty(self):
        self.assertEqual(strip_markdown(''), '')


if __name__ == '__main__':
    unittest.main()

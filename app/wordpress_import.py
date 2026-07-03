import html as html_lib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser

from app.entries import import_entry
from app.models import make_slug

WP_NS = {
    'wp': 'http://wordpress.org/export/1.2/',
    'content': 'http://purl.org/rss/1.0/modules/content/',
    'dc': 'http://purl.org/dc/elements/1.1/',
}
WP_ALT_NS = {
    'wp': 'http://wordpress.org/export/1.1/',
}


class HTMLToMarkdown(HTMLParser):
    def __init__(self):
        super().__init__()
        self._out_stack = [[]]
        self._stack = []
        self._li_count = []
        self._href = None
        self._pre = False

    @property
    def _out(self):
        return self._out_stack[-1]

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self._stack.append(tag)
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            level = int(tag[1])
            self._out.append('\n\n' + '#' * level + ' ')
        elif tag == 'p':
            self._out.append('\n\n')
        elif tag == 'br':
            self._out.append('\n')
        elif tag == 'strong' or tag == 'b':
            self._out.append('**')
        elif tag == 'em' or tag == 'i':
            self._out.append('*')
        elif tag == 'cite' or tag == 'q':
            self._out.append(f'<{tag}>')
        elif tag == 'abbr':
            title = attrs.get('title', '')
            if title:
                self._out.append(f'<abbr title="{html_lib.escape(title, quote=True)}">')
            else:
                self._out.append('<abbr>')
        elif tag == 'a':
            self._href = attrs.get('href', '')
            self._out.append('[')
        elif tag == 'img':
            alt = attrs.get('alt', '')
            src = attrs.get('src', '')
            self._out.append(f'![{alt}]({src})')
        elif tag == 'ul':
            self._out.append('\n')
            self._li_count.append(None)
        elif tag == 'ol':
            self._out.append('\n')
            self._li_count.append(0)
        elif tag == 'li':
            if self._li_count and self._li_count[-1] is not None:
                self._li_count[-1] += 1
                self._out.append(f'{self._li_count[-1]}. ')
            else:
                self._out.append('- ')
        elif tag == 'blockquote':
            self._out.append('\n\n')
            self._out_stack.append([])
        elif tag == 'pre':
            self._pre = True
            self._out.append('\n\n```\n')
        elif tag == 'code' and not self._pre:
            self._out.append('`')
        elif tag == 'hr':
            self._out.append('\n\n---\n\n')

    def handle_endtag(self, tag):
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._out.append('\n')
        elif tag in ('strong', 'b'):
            self._out.append('**')
        elif tag in ('em', 'i'):
            self._out.append('*')
        elif tag in ('cite', 'q', 'abbr'):
            self._out.append(f'</{tag}>')
        elif tag == 'a':
            self._out.append(f']({self._href})')
            self._href = None
        elif tag in ('ul', 'ol'):
            if self._li_count:
                self._li_count.pop()
            self._out.append('\n')
        elif tag == 'li':
            self._out.append('\n')
        elif tag == 'blockquote':
            buf = self._out_stack.pop()
            text = re.sub(r'\n{3,}', '\n\n', ''.join(buf)).strip('\n')
            quoted = '\n'.join(('> ' + line if line else '>') for line in text.split('\n'))
            self._out.append('\n\n' + quoted + '\n\n')
        elif tag == 'pre':
            self._pre = False
            self._out.append('\n```\n')
        elif tag == 'code' and not self._pre:
            self._out.append('`')

    def handle_data(self, data):
        self._out.append(unescape_fully(data))

    def get_markdown(self):
        text = ''.join(self._out).strip()
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text


def unescape_fully(text):
    # WordPress exports sometimes double-encode entities (e.g. "&amp;amp;"
    # for a literal "&"). Unescape repeatedly until stable to avoid leaving
    # literal "&amp;" in the text.
    while True:
        unescaped = html_lib.unescape(text)
        if unescaped == text:
            return text
        text = unescaped


def html_to_markdown(html):
    parser = HTMLToMarkdown()
    parser.feed(html)
    return parser.get_markdown()


class InvalidWordPressFile(Exception):
    pass


def import_wordpress_export(f):
    """Parse a WordPress export file and create entries via app.entries.import_entry.

    Returns the number of entries imported. Raises InvalidWordPressFile if the
    file isn't parseable XML or doesn't look like a WordPress export.
    """
    try:
        tree = ET.parse(f)
    except ET.ParseError:
        raise InvalidWordPressFile('Invalid XML file.')

    root = tree.getroot()
    channel = root.find('channel')
    if channel is None:
        raise InvalidWordPressFile('Invalid WordPress export file.')

    count = 0
    for item in channel.findall('item'):
        post_type = item.find('wp:post_type', WP_NS)
        if post_type is None:
            post_type = item.find('wp:post_type', WP_ALT_NS)
        if post_type is not None and post_type.text not in ('post', 'page'):
            continue

        title_el = item.find('title')
        title = unescape_fully((title_el.text or '').strip()) if title_el is not None else ''
        if not title:
            continue

        slug_el = item.find('wp:post_name', WP_NS)
        if slug_el is None:
            slug_el = item.find('wp:post_name', WP_ALT_NS)
        slug = (slug_el.text or '').strip() if slug_el is not None else ''
        if not slug:
            slug = make_slug(title)

        content_el = item.find('content:encoded', WP_NS)
        html_content = (content_el.text or '') if content_el is not None else ''
        body_markdown = html_to_markdown(html_content) if html_content else ''

        status_el = item.find('wp:status', WP_NS)
        if status_el is None:
            status_el = item.find('wp:status', WP_ALT_NS)
        status = (status_el.text or '') if status_el is not None else ''
        is_draft = status != 'publish'

        published_at = None
        date_el = item.find('wp:post_date', WP_NS)
        if date_el is None:
            date_el = item.find('wp:post_date', WP_ALT_NS)
        if date_el is not None and date_el.text:
            try:
                published_at = datetime.strptime(date_el.text, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        if import_entry(title, slug, body_markdown, is_draft=is_draft, published_at=published_at):
            count += 1

    return count

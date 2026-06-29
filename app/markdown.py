import re

import bleach
import mistune

ALLOWED_TAGS = [
    'p', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'strong', 'em', 'a', 'ul', 'ol', 'li', 'blockquote',
    'pre', 'code', 'hr', 'sup', 'section', 'img',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
]
ALLOWED_ATTRS = {
    'a': ['href', 'title', 'class'],
    'img': ['src', 'alt', 'title'],
    'sup': ['class', 'id'],
    'section': ['class'],
    '*': ['id'],
}

INTERNAL_LINK_RE = re.compile(r'href=["\']/([\w-]+)/["\']')
FOOTNOTE_DEF_RE = re.compile(r'^\[\^(\w+)\]:\s*(.+)$', re.MULTILINE)
FOOTNOTE_REF_RE = re.compile(r'\[\^(\w+)\](?!:)')


def render_markdown(text):
    if not text:
        return ''

    body_lines = []
    footnotes = {}
    for line in text.split('\n'):
        m = FOOTNOTE_DEF_RE.match(line)
        if m:
            footnotes[m.group(1)] = m.group(2)
        else:
            body_lines.append(line)

    body_text = '\n'.join(body_lines)

    md = mistune.create_markdown(escape=False)
    html = md(body_text)

    def replace_ref(m):
        key = m.group(1)
        if key in footnotes:
            content = footnotes[key]
            return (
                f'<sup class="footnote-ref" id="fnref-{key}">'
                f'<a href="#fn-{key}" data-footnote="{bleach.clean(content)}">{key}</a>'
                f'</sup>'
            )
        return m.group(0)

    html = FOOTNOTE_REF_RE.sub(replace_ref, html)

    if footnotes:
        html += '\n<section class="entry-footnotes"><h2>Footnotes</h2><ol>'
        for key, content in footnotes.items():
            fn_html = md(content).strip()
            html += (
                f'<li id="fn-{key}">'
                f'{fn_html} '
                f'<a href="#fnref-{key}" class="footnote-backref">↩</a>'
                f'</li>'
            )
        html += '</ol></section>'

    html = bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS)
    html = add_heading_ids(html)
    return html


def extract_internal_links(markdown_text):
    if not markdown_text:
        return set()
    md = mistune.create_markdown(escape=False)
    html = md(markdown_text)
    return set(INTERNAL_LINK_RE.findall(html))


def mark_missing_links(html, existing_slugs):
    def replacer(m):
        slug = m.group(1)
        full_match = m.group(0)
        if slug not in existing_slugs:
            title = slug.replace('-', ' ').title()
            return full_match.replace(
                'href=',
                f'class="entry-link-missing" title="{title} — not yet written" href='
            )
        return full_match

    return INTERNAL_LINK_RE.sub(replacer, html)


HEADING_BARE_RE = re.compile(r'<(h[2-4])>(.*?)</\1>', re.DOTALL)
HEADING_WITH_ATTRS_RE = re.compile(r'<(h[2-4])(\s[^>]*)?(>)(.*?)</\1>', re.DOTALL)


def add_heading_ids(html):
    seen = {}

    def replacer(m):
        tag = m.group(1)
        text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        slug = re.sub(r'[^\w\s-]', '', text.lower())
        slug = re.sub(r'[\s]+', '-', slug).strip('-')
        if slug in seen:
            seen[slug] += 1
            slug = f'{slug}-{seen[slug]}'
        else:
            seen[slug] = 0
        return f'<{tag} id="{slug}">{m.group(2)}</{tag}>'

    return HEADING_BARE_RE.sub(replacer, html)


def extract_toc(html):
    headings = []
    for m in HEADING_WITH_ATTRS_RE.finditer(html):
        tag = m.group(1)
        level = int(tag[1])
        attrs = m.group(2) or ''
        text = re.sub(r'<[^>]+>', '', m.group(4)).strip()
        id_match = re.search(r'id="([^"]+)"', attrs)
        if id_match:
            headings.append({'level': level, 'text': text, 'id': id_match.group(1)})
    return headings


def strip_markdown(text):
    if not text:
        return ''
    text = FOOTNOTE_DEF_RE.sub('', text)
    text = FOOTNOTE_REF_RE.sub('', text)
    text = re.sub(r'[#*_`\[\]()>~]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

import html as html_lib
import re

import bleach
import mistune

ALLOWED_TAGS = [
    'p', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'strong', 'em', 'del', 'a', 'ul', 'ol', 'li', 'blockquote',
    'pre', 'code', 'hr', 'sup', 'section', 'img',
    'details', 'summary',
    'cite', 'q', 'abbr',
]
ALLOWED_ATTRS = {
    'a': ['href', 'title', 'class', 'data-footnote'],
    'img': ['src', 'alt', 'title'],
    'sup': ['class', 'id'],
    'section': ['class'],
    'abbr': ['title'],
    '*': ['id'],
}

# The final path segment is the entry slug, so both flat (/slug/) and
# canonical child (/parent/child/) URLs are recognized as internal links.
INTERNAL_LINK_RE = re.compile(r'href=["\']/(?:[\w-]+/)?([\w-]+)/["\']')
FOOTNOTE_DEF_RE = re.compile(r'^\[\^(\w+)\]:\s*(.+)$', re.MULTILINE)
FOOTNOTE_REF_RE = re.compile(r'\[\^(\w+)\](?!:)')
FENCE_LINE_RE = re.compile(r'^\s*```')
PRE_BLOCK_RE = re.compile(r'(<pre>.*?</pre>)', re.DOTALL)

# CommonMark renders a "loose" list (one with blank lines between items) by
# wrapping each item's text in <p>. The ProseMirror editor emits loose markdown
# for any list built with its toolbar/shortcuts, so entries pick up stray <p>
# tags inside <li>. Unwrap the leading paragraph of an item, but only when it is
# the item's sole paragraph — i.e. the </p> is followed by the item's end or a
# nested list, not another <p> (which would be a genuine multi-paragraph item).
LOOSE_LI_RE = re.compile(
    r'<li>(\s*)<p>((?:(?!</p>)[\s\S])*)</p>(?=\s*(?:</li>|<[uo]l\b))'
)


def tighten_list_items(html):
    return LOOSE_LI_RE.sub(lambda m: f'<li>{m.group(1)}{m.group(2)}', html)

# A collapsible block, authored as:
#
#     :::details Summary line
#     Any block markdown here.
#     :::
#
# mistune's own FencedDirective is not used: it insists on the MyST brace form
# (`:::{details} title`), which is noisier to type and to read in the raw body.
# An unterminated block falls through to a literal paragraph rather than
# swallowing the rest of the entry.
DETAILS_PATTERN = (
    r'^:::details[ \t]*(?P<details_title>[^\n]*)\n'
    r'(?P<details_text>(?:[^\n]*\n)*?)'
    r':::[ \t]*(?:\n|$)'
)


def parse_details(block, m, state):
    child = state.child_state(m.group('details_text'))
    block.parse(child)
    state.append_token({
        'type': 'details',
        'children': child.tokens,
        'attrs': {'title': m.group('details_title').strip() or 'Details'},
    })
    return m.end()


def render_details(renderer, text, **attrs):
    title = html_lib.escape(attrs.get('title') or 'Details')
    return f'<details><summary>{title}</summary>\n{text}</details>\n'


def details_plugin(md):
    md.block.register('details', DETAILS_PATTERN, parse_details, before='fenced_code')
    if md.renderer and md.renderer.NAME == 'html':
        md.renderer.register('details', render_details)


MISTUNE_PLUGINS = ['strikethrough', details_plugin]


def _new_markdown():
    return mistune.create_markdown(escape=False, plugins=MISTUNE_PLUGINS)


def render_markdown(text):
    if not text:
        return ''

    body_lines = []
    footnotes = {}
    in_fence = False
    for line in text.split('\n'):
        if FENCE_LINE_RE.match(line):
            in_fence = not in_fence
            body_lines.append(line)
            continue
        m = None if in_fence else FOOTNOTE_DEF_RE.match(line)
        if m:
            footnotes[m.group(1)] = m.group(2)
        else:
            body_lines.append(line)

    body_text = '\n'.join(body_lines)

    md = _new_markdown()
    html = md(body_text)
    html = tighten_list_items(html)

    def replace_ref(m):
        key = m.group(1)
        if key in footnotes:
            content = footnotes[key]
            # Strip any markup and escape for safe embedding inside a quoted
            # HTML attribute — bleach.clean() alone does not escape quotes.
            plain = html_lib.unescape(bleach.clean(content, tags=[], strip=True))
            safe_content = html_lib.escape(plain, quote=True)
            return (
                f'<sup class="footnote-ref" id="fnref-{key}">'
                f'<a href="#fn-{key}" data-footnote="{safe_content}">{key}</a>'
                f'</sup>'
            )
        return m.group(0)

    def replace_refs_outside_code(html_text):
        # Leave anything inside a rendered <pre>...</pre> (fenced code) block
        # untouched, so a code sample that documents footnote syntax isn't
        # turned into a live footnote link.
        parts = PRE_BLOCK_RE.split(html_text)
        return ''.join(
            part if PRE_BLOCK_RE.match(part) else FOOTNOTE_REF_RE.sub(replace_ref, part)
            for part in parts
        )

    html = replace_refs_outside_code(html)

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


INLINE_ALLOWED_TAGS = ['strong', 'em', 'del', 'a', 'code', 'br', 'abbr', 'q', 'cite']
INLINE_ALLOWED_ATTRS = {'a': ['href', 'title', 'class'], 'abbr': ['title']}


def render_inline_markdown(text):
    """Render a short one-off string (footer text, announcement banner) with
    inline markdown only — bold, italic, links, code, strikethrough — with no
    block wrappers. Paragraph breaks collapse to <br> so the result drops into
    a single element."""
    if not text:
        return ''
    md = _new_markdown()
    html = md(text.strip())
    # Collapse mistune's block wrappers: paragraph breaks become line breaks.
    html = re.sub(r'</p>\s*<p>', '<br>', html)
    html = re.sub(r'</?p>', '', html).strip()
    return bleach.clean(html, tags=INLINE_ALLOWED_TAGS, attributes=INLINE_ALLOWED_ATTRS)


def extract_internal_links(markdown_text):
    if not markdown_text:
        return set()
    md = _new_markdown()
    html = md(markdown_text)
    return set(INTERNAL_LINK_RE.findall(html))


def mark_missing_links(html, existing_slugs, stub_slugs=None):
    """Tag internal links by the state of their target entry:

    - target doesn't exist (not in existing_slugs) → `entry-link-missing`
      ("not yet written"), a red dead-end link.
    - target is a published stub (in stub_slugs) → `entry-link-stub`
      ("still being written"), a live link styled to signal it's skeletal.
    - target is a normal published entry → left untouched.
    """
    stub_slugs = stub_slugs or set()

    def replacer(m):
        slug = m.group(1)
        full_match = m.group(0)
        if slug not in existing_slugs:
            title = slug.replace('-', ' ').title()
            return full_match.replace(
                'href=',
                f'class="entry-link-missing" title="{title} — not yet written" href='
            )
        if slug in stub_slugs:
            return full_match.replace(
                'href=',
                'class="entry-link-stub" title="Stub — still being written" href='
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


def extract_toc(html_content):
    headings = []
    for m in HEADING_WITH_ATTRS_RE.finditer(html_content):
        tag = m.group(1)
        level = int(tag[1])
        attrs = m.group(2) or ''
        text = html_lib.unescape(re.sub(r'<[^>]+>', '', m.group(4)).strip())
        id_match = re.search(r'id="([^"]+)"', attrs)
        if id_match:
            headings.append({'level': level, 'text': text, 'id': id_match.group(1)})
    return headings


def strip_markdown(text):
    if not text:
        return ''
    text = FOOTNOTE_DEF_RE.sub('', text)
    text = FOOTNOTE_REF_RE.sub('', text)
    # Drop the details fences but keep the summary line, which reads as prose.
    text = re.sub(r'^:::details[ \t]*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^:::[ \t]*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'[#*_`\[\]()>~]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

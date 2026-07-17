import re
from tests.base import BaseTest
from app import db
from app.models import Entry, set_published


class Drive(BaseTest):
    def runTest(self):
        admin = self._make_user('admin')
        self._login(admin)
        self._add_entry('Aldous Huxley', slug='aldous-huxley')
        for t in ('Vedanta', 'Gerald Heard'):
            e = Entry(title=t, slug=t.lower().replace(' ', '-'), is_stub=True)
            e.update_sort_title()
            set_published(e, True)
            db.session.add(e)
        db.session.commit()

        r = self.client.get('/dashboard/?status=draft&listed=unlisted')
        html = r.get_data(as_text=True)
        print('status', r.status_code)
        block = re.search(r'<div class="admin-filters">.*?</div>\s*</div>', html, re.S)
        # normalize whitespace for readability
        out = re.sub(r'\n\s*', '\n', block.group(0))
        print(out)
        print('--- active pills:', re.findall(r'class="active">([^<]+)', html))
        print('--- labels present:', re.findall(r'admin-filter-label">([^<]+)', html))
        print('--- stub count chip:', re.search(r'subnav-count">(\d+)', html).group(1))

import difflib


def compute_diff(old_text, new_text):
    old_lines = (old_text or '').splitlines()
    new_lines = (new_text or '').splitlines()
    result = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_lines, new_lines).get_opcodes():
        if op == 'equal':
            for line in old_lines[i1:i2]:
                result.append(('=', line))
        elif op == 'insert':
            for line in new_lines[j1:j2]:
                result.append(('+', line))
        elif op == 'delete':
            for line in old_lines[i1:i2]:
                result.append(('-', line))
        elif op == 'replace':
            for line in old_lines[i1:i2]:
                result.append(('-', line))
            for line in new_lines[j1:j2]:
                result.append(('+', line))
    return result


def build_revisions(items):
    """Build revision display dicts from a list of EditLog/PageRevision rows,
    ordered most-recent-first."""
    revisions = []
    for i, item in enumerate(items):
        prev_snapshot = items[i + 1].body_snapshot if i + 1 < len(items) else ''
        curr_snapshot = item.body_snapshot or ''
        revisions.append({
            'id': item.id,
            'snapshot': curr_snapshot,
            'changelog': item.changelog,
            'edited_at': item.edited_at,
            'user': item.user,
            'diff_lines': compute_diff(prev_snapshot or '', curr_snapshot),
            'char_delta': len(curr_snapshot) - len(prev_snapshot or ''),
        })
    return revisions

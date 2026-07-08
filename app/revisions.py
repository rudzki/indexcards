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
    ordered most-recent-first.

    A row's body_snapshot is None when that save didn't change the body (only
    the title/aliases/changelog did) — snapshots are stored only on content
    changes. Such a row's *effective* content is therefore the nearest older
    real snapshot, not empty. Resolving that here keeps a metadata-only edit
    from rendering as a full-body deletion (and its neighbour as a full
    re-addition)."""
    n = len(items)

    # items are newest-first, so an older revision sits at a higher index.
    # Walk oldest→newest carrying the last real snapshot forward.
    effective = [''] * n
    last_real = ''
    for i in range(n - 1, -1, -1):
        if items[i].body_snapshot is not None:
            last_real = items[i].body_snapshot
        effective[i] = last_real

    revisions = []
    for i, item in enumerate(items):
        curr_snapshot = effective[i]
        prev_snapshot = effective[i + 1] if i + 1 < n else ''
        revisions.append({
            'id': item.id,
            'snapshot': curr_snapshot,
            'changelog': item.changelog,
            'edited_at': item.edited_at,
            'user': item.user,
            'diff_lines': compute_diff(prev_snapshot, curr_snapshot),
            'char_delta': len(curr_snapshot) - len(prev_snapshot),
        })
    return revisions

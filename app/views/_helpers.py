"""Small shared helpers for the views (list sorting, upload validation)."""


def validated_image_ext(file, allowed):
    """Return the lowercased extension of an uploaded image when it's in the
    `allowed` set, else None. Shared by the image-upload endpoints so the
    extension allowlist check lives in one place. Callers do their own
    empty-file check first (they flash different messages)."""
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    return ext if ext in allowed else None


def apply_sort(query, request, column_map, default_key, default_order='desc'):
    """Read ?sort/?order, map the sort key to a column, and apply the ordering.

    column_map maps each sort key to either a column, or a (column, join_arg)
    pair when that sort needs a join applied first (e.g. the logs view joins
    User to sort by editor email). An unknown sort/order falls back to the
    defaults. `default_order` sets the direction used when ?order is absent,
    letting a caller land on ascending (e.g. oldest-first) by default. Returns
    (query, sort, order) so the caller can echo the resolved values back to the
    template.
    """
    sort = request.args.get('sort', default_key)
    if sort not in column_map:
        sort = default_key
    order = request.args.get('order', default_order)
    if order not in ('asc', 'desc'):
        order = default_order

    spec = column_map[sort]
    if isinstance(spec, tuple):
        col, join_arg = spec
        if join_arg is not None:
            query = query.outerjoin(join_arg)
    else:
        col = spec

    query = query.order_by(col.asc() if order == 'asc' else col.desc())
    return query, sort, order

from app import db
from app.models import Registration

VALID_ROLES = ('viewer', 'author', 'editor', 'admin')


def resolve_role(reg, settings):
    if reg.role and reg.role in VALID_ROLES:
        return reg.role
    default_role = (settings.default_role if settings else 'author') or 'author'
    if default_role not in ('viewer', 'author', 'editor'):
        default_role = 'author'
    return default_role


def create_registration(email, invited_by=None, role=None):
    reg = Registration(email=email, invited_by=invited_by, role=role)
    db.session.add(reg)
    return reg

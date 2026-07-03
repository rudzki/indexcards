from functools import wraps

from flask import Blueprint, abort
from flask_login import login_required, current_user

admin_bp = Blueprint('admin', __name__, url_prefix='/dashboard')


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def writer_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.can_write:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def editor_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not (current_user.is_admin or current_user.is_editor):
            abort(403)
        return f(*args, **kwargs)
    return decorated

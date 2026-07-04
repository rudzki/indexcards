from datetime import datetime, timedelta, timezone

from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import EditLock

LOCK_TTL = 60


def acquire_lock(content_type, content_id):
    """Acquire or refresh a lock. Returns the display name of the blocking user, or None on success."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires = now + timedelta(seconds=LOCK_TTL)

    EditLock.query.filter(EditLock.expires_at < now).delete()

    existing = EditLock.query.filter_by(content_type=content_type, content_id=content_id).first()
    if existing and existing.user_id != current_user.id:
        exp = existing.expires_at.replace(tzinfo=None) if existing.expires_at.tzinfo else existing.expires_at
        if exp > now:
            return existing.user.display_name if existing.user else 'Someone'
        existing.user_id = current_user.id
        existing.expires_at = expires
        db.session.commit()
        return None
    elif existing:
        existing.expires_at = expires
        db.session.commit()
        return None

    # No lock row existed at the check above — but a concurrent request could
    # have inserted one in between, so guard the insert itself rather than
    # trusting the earlier SELECT (avoids a 500 on the unique constraint).
    db.session.add(EditLock(content_type=content_type, content_id=content_id,
                            user_id=current_user.id, expires_at=expires))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = EditLock.query.filter_by(content_type=content_type, content_id=content_id).first()
        if existing and existing.user_id != current_user.id:
            return existing.user.display_name if existing.user else 'Someone'
        return None
    return None


def release_lock(content_type, content_id):
    EditLock.query.filter_by(
        content_type=content_type, content_id=content_id, user_id=current_user.id
    ).delete()
    db.session.commit()


def active_locks(content_type):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    locks = EditLock.query.filter_by(content_type=content_type).filter(EditLock.expires_at > now).all()
    return {lock.content_id: lock.user.display_name if lock.user else 'Someone' for lock in locks}

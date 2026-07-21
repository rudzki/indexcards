import os
import secrets

from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_required, current_user

from app import db
from app.views._helpers import validated_image_ext

account_bp = Blueprint('account', __name__)

ALLOWED_AVATAR_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}


def _remove_avatar_file(filename):
    """Delete an avatar file from the uploads dir, ignoring a missing file."""
    if not filename:
        return
    path = os.path.join(current_app.config['UPLOAD_DIR'], filename)
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


@account_bp.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    if request.method == 'POST':
        display_name = request.form.get('display_name', '').strip()
        bio = request.form.get('bio', '').strip()
        link = request.form.get('link', '').strip()
        subscribed = 'subscribed' in request.form

        if not display_name:
            flash('Display name is required.', 'error')
            return render_template('account.html')

        # Only allow http(s) website links — a javascript:/data: URL here would
        # become a clickable link on every entry the user authored.
        if link and not link.lower().startswith(('http://', 'https://')):
            flash('Website link must start with http:// or https://.', 'error')
            return render_template('account.html')

        # Avatar: an uploaded file replaces the current one; a "remove" checkbox
        # clears it. Validate the upload before touching anything so a bad file
        # doesn't wipe the existing avatar. Both paths delete the old file so the
        # uploads dir doesn't accumulate orphans.
        avatar_file = request.files.get('avatar')
        remove_avatar = 'remove_avatar' in request.form
        new_avatar_filename = None
        if avatar_file and avatar_file.filename:
            ext = validated_image_ext(avatar_file, ALLOWED_AVATAR_EXTENSIONS)
            if not ext:
                flash('Avatar must be a PNG, JPEG, WebP, or GIF image.', 'error')
                return render_template('account.html')
            new_avatar_filename = secrets.token_hex(16) + '.' + ext

        current_user.display_name = display_name
        current_user.bio = bio
        current_user.link = link
        current_user.subscribed = subscribed

        if new_avatar_filename:
            avatar_file.save(os.path.join(current_app.config['UPLOAD_DIR'], new_avatar_filename))
            _remove_avatar_file(current_user.avatar)
            current_user.avatar = new_avatar_filename
        elif remove_avatar and current_user.avatar:
            _remove_avatar_file(current_user.avatar)
            current_user.avatar = ''

        db.session.commit()
        flash('Account updated.', 'success')
        return redirect(url_for('account.account'))

    return render_template('account.html')

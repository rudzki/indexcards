from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user

from app import db

account_bp = Blueprint('account', __name__)


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

        current_user.display_name = display_name
        current_user.bio = bio
        current_user.link = link
        current_user.subscribed = subscribed
        db.session.commit()
        flash('Account updated.', 'success')
        return redirect(url_for('account.account'))

    return render_template('account.html')

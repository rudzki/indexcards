from flask import render_template, redirect, url_for, request, flash
from flask_login import current_user

from app import db
from app.models import (User, Registration, SiteSettings, DEFAULT_SITE_TITLE, EditLog,
                        Entry, AuditLog, EditLock, log_audit)
from app.mail import send_email, render_email
from app.registration import VALID_ROLES, create_registration
from app.views.admin import admin_bp, admin_required
from app.views._helpers import apply_sort


@admin_bp.route('/users/', methods=['GET', 'POST'])
@admin_required
def users():
    site_settings = SiteSettings.get()
    if not site_settings or not site_settings.multiuser_enabled:
        return redirect(url_for('admin.settings'))

    if request.method == 'POST' and site_settings.registration_method == 'invite':
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('Email is required.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('A user with this email already exists.', 'error')
        elif Registration.query.filter_by(email=email, accepted=False).first():
            flash('An invitation for this email is already pending.', 'error')
        else:
            invited_role = request.form.get('role', '').strip()
            if invited_role not in VALID_ROLES:
                invited_role = None
            reg = create_registration(email, invited_by=current_user.id, role=invited_role)
            db.session.commit()
            log_audit('invite_sent', detail=email, user_id=current_user.id)

            signup_url = url_for('auth.signup_token', token=reg.token, _external=True)
            site_title = site_settings.display_title if site_settings else DEFAULT_SITE_TITLE
            text, html = render_email('invite', site_title=site_title, signup_url=signup_url,
                                      invited_by=current_user.display_name)
            if send_email(to=email, subject=f'You\'ve been invited to {site_title}',
                          body_text=text, body_html=html):
                flash(f'Invite sent to {email}.', 'success')
            else:
                flash(f'Invite created but the email to {email} could not be sent.', 'error')

        return redirect(url_for('admin.users'))

    q, sort, order = apply_sort(User.query, request, {
        'name': User.display_name, 'email': User.email,
        'role': User.role, 'joined': User.created_at,
    }, 'joined')
    all_users = q.all()
    pending = Registration.query.filter_by(accepted=False).order_by(Registration.created_at.desc()).all()
    admin_count = User.query.filter_by(role='admin').count()
    return render_template('admin/users.html', users=all_users, pending=pending,
                           settings=site_settings, admin_count=admin_count, sort=sort, order=order)


@admin_bp.route('/users/<int:user_id>/role/', methods=['POST'])
@admin_required
def change_role(user_id):
    user = db.get_or_404(User, user_id)
    new_role = request.form.get('role', '')
    if new_role not in VALID_ROLES:
        flash('Invalid role.', 'error')
        return redirect(url_for('admin.users'))

    if user.id == current_user.id:
        flash('You cannot change your own role.', 'error')
        return redirect(url_for('admin.users'))

    if user.is_admin and User.query.filter_by(role='admin').count() <= 1:
        flash('Cannot demote the last admin.', 'error')
        return redirect(url_for('admin.users'))

    old_role = user.role
    user.role = new_role
    db.session.commit()
    log_audit('role_changed', detail=f'{user.display_name}: {old_role} -> {new_role}', user_id=current_user.id)
    flash(f'{user.display_name} is now {new_role}.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/delete/', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = db.get_or_404(User, user_id)

    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin.users'))

    if user.is_admin and User.query.filter_by(role='admin').count() <= 1:
        flash('Cannot delete the last admin.', 'error')
        return redirect(url_for('admin.users'))

    user_name = user.display_name
    EditLog.query.filter_by(user_id=user.id).update({'user_id': None})
    Entry.query.filter_by(created_by=user.id).update({'created_by': None})
    Registration.query.filter_by(invited_by=user.id).update({'invited_by': None})
    AuditLog.query.filter_by(user_id=user.id).update({'user_id': None})
    # EditLock also references user.id; leaving it would create rows pointing at a
    # nonexistent user once FK enforcement (or a Postgres port) arrives.
    EditLock.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    log_audit('user_deleted', detail=user_name, user_id=current_user.id)
    flash(f'{user_name} has been removed.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/registration/<int:reg_id>/resend/', methods=['POST'])
@admin_required
def resend_invite(reg_id):
    reg = db.get_or_404(Registration, reg_id)
    if reg.accepted:
        flash('This registration has already been accepted.', 'info')
        return redirect(url_for('admin.users'))

    signup_url = url_for('auth.signup_token', token=reg.token, _external=True)
    site_settings = SiteSettings.get()
    site_title = site_settings.display_title if site_settings else DEFAULT_SITE_TITLE
    inviter = db.session.get(User, reg.invited_by) if reg.invited_by else None
    invited_by_name = inviter.display_name if inviter else site_title
    text, html = render_email('invite', site_title=site_title, signup_url=signup_url,
                              invited_by=invited_by_name)
    if send_email(to=reg.email, subject=f'You\'ve been invited to {site_title}',
                  body_text=text, body_html=html):
        flash(f'Invite resent to {reg.email}.', 'success')
    else:
        flash(f'Could not send email to {reg.email}.', 'error')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/registration/<int:reg_id>/revoke/', methods=['POST'])
@admin_required
def revoke_invite(reg_id):
    reg = db.get_or_404(Registration, reg_id)
    db.session.delete(reg)
    db.session.commit()
    flash(f'Invitation for {reg.email} revoked.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/subscribers/')
@admin_required
def subscribers():
    all_subscribers = User.query.filter_by(subscribed=True).order_by(User.created_at.desc()).all()
    return render_template('admin/subscribers.html', subscribers=all_subscribers)


@admin_bp.route('/logs/')
@admin_required
def logs():
    q, sort, order = apply_sort(AuditLog.query, request, {
        'time': AuditLog.created_at,
        'action': AuditLog.action,
        'user': (User.email, AuditLog.user),  # join User to sort by editor email
    }, 'time')
    entries = q.limit(200).all()
    return render_template('admin/logs.html', logs=entries, sort=sort, order=order)

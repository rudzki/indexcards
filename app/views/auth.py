from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_user, logout_user, login_required

from app import db, limiter
from app.models import User, Registration, SiteSettings, log_audit
from app.mail import send_email, render_email
from app.registration import resolve_role, create_registration

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        settings = db.session.get(SiteSettings, 1)
        site_title = (settings.site_title if settings else None) or 'Index Cards'
        user = User.query.filter_by(email=email).first()
        if user:
            token = user.generate_login_token()
            db.session.commit()

            login_url = url_for('auth.verify_login', token=token, _external=True)
            text, html = render_email('login', site_title=site_title, login_url=login_url)
            send_email(to=email, subject='Your login link', body_text=text, body_html=html)
        elif (settings and settings.multiuser_enabled
                and settings.registration_method == 'domain'):
            # No account yet, but domain-based registration is open. If the
            # email is in the allowed domain, start the signup flow (emailed
            # token) so a legitimate user isn't stranded at the login box.
            # We never create a User here — typing an address only sends a
            # signup link; the account is created when that link is clicked.
            allowed_domain = (settings.registration_domain or '').strip().lower()
            if allowed_domain and email.endswith(f'@{allowed_domain}'):
                existing_reg = Registration.query.filter_by(
                    email=email, accepted=False).first()
                if not (existing_reg and not existing_reg.is_expired):
                    reg = create_registration(email, invited_by=None)
                    db.session.commit()
                    log_audit('user_registered', detail=email)

                    signup_url = url_for(
                        'auth.signup_token', token=reg.token, _external=True)
                    text, html = render_email(
                        'signup', site_title=site_title, signup_url=signup_url)
                    send_email(to=email, subject='Complete your signup',
                               body_text=text, body_html=html)
        # Uniform response whether we sent a login link, a signup link, or
        # nothing — so the login box can't be used to enumerate accounts.
        flash('If that email is registered or eligible to join, a link has '
              'been sent. Check your inbox.', 'success')
        return render_template('login.html', sent=True)
    return render_template('login.html', sent=False)


@auth_bp.route('/login/<token>')
def verify_login(token):
    user = User.query.filter_by(login_token=token).first()
    if user and user.token_valid:
        user.clear_login_token()
        db.session.commit()
        login_user(user)
        return redirect(url_for('main.index'))
    flash('Invalid or expired login link. Please request a new one.', 'error')
    return redirect(url_for('auth.login'))


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))


@auth_bp.route('/setup', methods=['GET', 'POST'])
def setup():
    if User.query.count() > 0:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        display_name = request.form.get('display_name', '').strip()
        site_title = request.form.get('site_title', '').strip()

        if not email or not display_name:
            flash('Email and name are required.', 'error')
            return render_template('setup.html')

        user = User(email=email, display_name=display_name, role='admin')
        db.session.add(user)
        db.session.flush()

        # Guard against two concurrent /setup POSTs both creating an admin:
        # if another user slipped in between the count check and here, bail out.
        if User.query.count() > 1:
            db.session.rollback()
            flash('Setup has already been completed.', 'info')
            return redirect(url_for('auth.login'))

        if site_title:
            settings = db.session.get(SiteSettings, 1)
            if settings:
                settings.site_title = site_title

        db.session.commit()
        login_user(user)
        return redirect(url_for('main.index'))

    return render_template('setup.html')


@auth_bp.route('/signup', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def signup_form():
    settings = db.session.get(SiteSettings, 1)
    if not settings or not settings.multiuser_enabled or settings.registration_method == 'invite':
        abort(404)

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('Email is required.', 'error')
            return render_template('signup_form.html', settings=settings)

        if settings.registration_method == 'domain':
            allowed_domain = (settings.registration_domain or '').strip().lower()
            if not email.endswith(f'@{allowed_domain}'):
                flash(f'Registration is limited to @{allowed_domain} email addresses.', 'error')
                return render_template('signup_form.html', settings=settings)

        existing_user = User.query.filter_by(email=email).first()
        if existing_user and existing_user.role != 'viewer':
            flash('An account with this email already exists. Try logging in.', 'info')
            return redirect(url_for('auth.login'))

        existing_reg = Registration.query.filter_by(email=email, accepted=False).first()
        if existing_reg and not existing_reg.is_expired:
            flash('A signup link has already been sent to this email. Check your inbox.', 'info')
            return render_template('signup_form.html', settings=settings)

        reg = create_registration(email, invited_by=None)
        db.session.commit()
        log_audit('user_registered', detail=email)

        signup_url = url_for('auth.signup_token', token=reg.token, _external=True)
        site_title = (settings.site_title if settings else None) or 'Index Cards'
        text, html = render_email('signup', site_title=site_title, signup_url=signup_url)
        send_email(to=email, subject='Complete your signup', body_text=text, body_html=html)

        flash('Check your email to complete signup.', 'success')
        return render_template('signup_form.html', settings=settings, sent=True)

    return render_template('signup_form.html', settings=settings)


@auth_bp.route('/signup/<token>', methods=['GET', 'POST'])
def signup_token(token):
    reg = Registration.query.filter_by(token=token, accepted=False).first_or_404()
    if reg.is_expired:
        flash('This signup link has expired. Please request a new invitation.', 'error')
        return redirect(url_for('auth.login'))
    settings = db.session.get(SiteSettings, 1)

    if request.method == 'POST':
        display_name = request.form.get('display_name', '').strip()

        if not display_name:
            flash('Display name is required.', 'error')
            return render_template('signup.html', invite=reg)

        default_role = resolve_role(reg, settings)

        user = User.query.filter_by(email=reg.email).first()
        if user:
            user.display_name = display_name
            if user.role == 'viewer':
                user.role = default_role
        else:
            user = User(email=reg.email, display_name=display_name, role=default_role)
            db.session.add(user)
        reg.accepted = True
        db.session.commit()
        log_audit('user_signed_up', detail=user.email, user_id=user.id)
        login_user(user)
        return redirect(url_for('main.index'))

    return render_template('signup.html', invite=reg)

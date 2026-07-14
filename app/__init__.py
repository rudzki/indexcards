from flask import Flask, redirect, url_for, request, render_template, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")


def create_app():
    app = Flask(__name__)
    app.url_map.strict_slashes = False
    app.config.from_object('config.Config')

    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    import os
    is_dev = os.environ.get('FLASK_DEBUG', '0').lower() in ('1', 'true', 'yes')
    if not is_dev and app.config['SECRET_KEY'] == 'dev-secret-change-me':
        raise RuntimeError('SECRET_KEY must be set in production. Set the SECRET_KEY environment variable.')

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)

    login_manager.login_view = 'auth.login'

    from app.views.auth import auth_bp
    from app.views.account import account_bp
    from app.views.main import main_bp
    from app.views.admin import admin_bp
    from app.views import admin_entries  # noqa: F401 - registers routes on admin_bp
    from app.views import admin_pages  # noqa: F401 - registers routes on admin_bp
    from app.views import admin_users  # noqa: F401 - registers routes on admin_bp
    from app.views import admin_settings  # noqa: F401 - registers routes on admin_bp
    from app.views import admin_import_export  # noqa: F401 - registers routes on admin_bp
    from app.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    from app.digest import register_cli
    register_cli(app)

    @app.before_request
    def require_setup():
        if app.config.get('_SETUP_DONE'):
            return
        from app.models import User
        allowed = ('auth.setup', 'static')
        if request.endpoint and request.endpoint not in allowed:
            if User.query.count() == 0:
                return redirect(url_for('auth.setup'))
            else:
                app.config['_SETUP_DONE'] = True

    @app.before_request
    def require_login_for_private_site():
        # The `api` blueprint enforces its own visibility rules (see
        # app/api.py:_check_visibility) with proper JSON 401 responses
        # instead of an HTML redirect — keep it out of this gate so there's
        # a single source of truth per endpoint instead of two allowlists
        # that can drift out of sync.
        if request.endpoint and request.endpoint.startswith('api.'):
            return
        from flask_login import current_user
        from app.models import SiteSettings, site_requires_login, site_requires_admin
        settings = db.session.get(SiteSettings, 1)
        if not site_requires_login(settings):
            return
        requires_admin = site_requires_admin(settings)
        # Always reachable so users can log in/out even on a locked-down site.
        allowed_endpoints = ('auth.login', 'auth.verify_login', 'auth.setup',
                             'auth.signup_form', 'auth.signup_token', 'auth.logout',
                             'main.healthz', 'main.confirm_subscription', 'main.favicon',
                             'main.site_image', 'main.unsubscribe', 'static')
        if request.endpoint in allowed_endpoints:
            return
        if current_user.is_authenticated:
            if not requires_admin or current_user.is_admin:
                return
            # Logged in, but not an admin on an admin-only site.
            abort(403)
        from flask import flash as _flash
        _flash('This site requires an account to view.', 'info')
        return redirect(url_for('auth.login'))

    import os as _os
    _os.makedirs(app.config.get('UPLOAD_DIR', 'instance/uploads'), exist_ok=True)

    with app.app_context():
        from app import models  # noqa: F401
        db.create_all()
        from app.migrate_db import run_migrations
        run_migrations()
        from app.search import create_fts_table
        create_fts_table()
        from app.models import SiteSettings
        if not db.session.get(SiteSettings, 1):
            db.session.add(SiteSettings(id=1, site_title='Index Cards'))
            db.session.commit()

    @app.template_filter('timeago')
    def timeago_filter(dt):
        from markupsafe import Markup
        from app.models import utcnow
        if dt is None:
            return ''
        now = utcnow()
        diff = now - dt
        seconds = int(diff.total_seconds())
        if seconds < 60:
            relative = 'just now'
        elif seconds < 3600:
            minutes = seconds // 60
            relative = f'{minutes}m ago'
        elif seconds < 86400:
            hours = seconds // 3600
            relative = f'{hours}h ago'
        elif seconds < 2592000:
            days = seconds // 86400
            relative = f'{days}d ago'
        elif seconds < 31536000:
            months = seconds // 2592000
            relative = f'{months}mo ago'
        else:
            years = seconds // 31536000
            relative = f'{years}y ago'
        hour = dt.hour % 12 or 12
        ampm = 'AM' if dt.hour < 12 else 'PM'
        absolute = f'{dt.strftime("%B")} {dt.day}, {dt.year} at {hour}:{dt.strftime("%M")} {ampm}'
        # dt is naive UTC (the storage convention); mark the machine-readable
        # timestamp as UTC so browsers/readers don't treat it as local time.
        iso = dt.isoformat() + 'Z'
        return Markup(f'<time datetime="{iso}" title="{absolute}">{relative}</time>')

    @app.context_processor
    def inject_nav_pages():
        from app.models import Page
        from sqlalchemy import nullslast
        pages = (Page.query
                 .filter_by(show_in_nav=True, is_draft=False)
                 .order_by(nullslast(Page.nav_position.asc()))
                 .all())
        return dict(nav_pages=pages)

    @app.context_processor
    def inject_entry_url():
        from app.models import entry_url
        return dict(entry_url=entry_url)

    @app.context_processor
    def inject_static_url():
        import os as _os2
        def static_url(filename):
            path = _os2.path.join(app.static_folder, filename)
            try:
                mtime = int(_os2.path.getmtime(path))
            except OSError:
                mtime = 0
            return url_for('static', filename=filename) + '?v=' + str(mtime)
        return dict(static_url=static_url)

    @app.context_processor
    def inject_site_settings():
        from app.models import SiteSettings
        from markupsafe import Markup as _Markup
        settings = db.session.get(SiteSettings, 1)
        icon_svg = ''
        if settings and settings.site_icon:
            from app.icons import get_icon_svg
            icon_svg = _Markup(get_icon_svg(settings.site_icon, size=20))
        if settings:
            settings.site_icon_svg = icon_svg
        return dict(site_settings=settings)

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html'), 500

    return app

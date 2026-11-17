"""AZUL - Wallet-based Loyalty Card Platform for Local Businesses."""
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()


def create_app(config=None):
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    app = Flask(__name__, template_folder=os.path.join(here, "templates"),
                static_folder=os.path.join(here, "static"))

    # SECRET_KEY handling - production must have it set via environment
    secret_key = os.environ.get('SECRET_KEY')
    if not secret_key:
        if config and config.get('TESTING'):
            # Only allow a fallback key for testing environments
            secret_key = 'test-secret-key-for-testing-only'
        else:
            raise RuntimeError(
                "SECURITY ERROR: SECRET_KEY environment variable must be set in production. "
                "Set it in .env file or environment before running."
            )
    app.config["SECRET_KEY"] = secret_key

    # Database URI
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        'DATABASE_URL',
        'sqlite:///azul.db'
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Engine options for SQLite timeout
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith('sqlite'):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"timeout": 30}
        }

    # CSRF Protection
    # Disable for API endpoints, enable for forms
    app.config["WTF_CSRF_ENABLED"] = True
    app.config["WTF_CSRF_SECRET_KEY"] = secret_key

    # Rate limiting configuration
    app.config["RATELIMIT_ENABLED"] = True
    app.config["RATELIMIT_DEFAULT"] = "200 per day;50 per hour"

    if config:
        app.config.update(config)
        # Override CSRF setting for testing
        if config.get('TESTING'):
            app.config["WTF_CSRF_ENABLED"] = False

    # Session security for production
    if not config or not config.get('TESTING'):
        app.config["SESSION_COOKIE_SECURE"] = True  # HTTPS only
        app.config["SESSION_COOKIE_HTTPONLY"] = True  # No JS access
        app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # CSRF protection

    db.init_app(app)
    migrate.init_app(app, db)

    # Initialize CSRF protection
    csrf.init_app(app)

    # Register blueprints/modules
    from . import routes  # noqa: F401
    from . import qr  # noqa: F401
    from . import wallet  # noqa: F401
    from . import customer_portal  # noqa: F401
    from . import auth_routes  # noqa: F401

    routes.register(app)
    customer_portal.register_customer_portal(app)
    auth_routes.register_auth_routes(app)

    return app
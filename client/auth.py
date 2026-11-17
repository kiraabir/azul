"""Authentication and Authorization for AZUL."""
import secrets
import hashlib
import os
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import session, redirect, url_for, request, g, flash

from werkzeug.security import generate_password_hash, check_password_hash

from .models import db, Merchant, User, get_current_merchant_id as _model_get_merchant_id


# SQLAlchemy 2.0 compatible helper for session get
def _session_get(model, pk):
    """Get a model instance by primary key using SQLAlchemy 2.0 session pattern."""
    return db.session.get(model, pk)


# =============================================================================
# Password Hashing - Using Werkzeug for production-grade security
# =============================================================================

def hash_password(password):
    """Hash a password using Werkzeug's secure hashing."""
    return generate_password_hash(password, method='scrypt', salt_length=16)


def verify_password(stored_password, provided_password):
    """Verify a password against its hash using Werkzeug's check_password_hash.

    Returns False for None or invalid password hashes to prevent errors.
    """
    if not stored_password or not provided_password:
        return False
    try:
        return check_password_hash(stored_password, provided_password)
    except (ValueError, AttributeError, TypeError):
        return False


# =============================================================================
# Login Rate Limiting
# =============================================================================

_login_attempts = {}  # In production, use Redis or database-backed storage
LOGIN_RATE_LIMIT_WINDOW = 300  # 5 minutes in seconds
MAX_LOGIN_ATTEMPTS = 5


def check_rate_limit(key):
    """Check if a key is rate limited. Returns True if allowed, False if blocked."""
    now = datetime.now(timezone.utc)
    if key in _login_attempts:
        attempts, first_attempt = _login_attempts[key]
        if now - first_attempt > timedelta(seconds=LOGIN_RATE_LIMIT_WINDOW):
            # Reset the window
            del _login_attempts[key]
            return True
        if attempts >= MAX_LOGIN_ATTEMPTS:
            return False
    return True


def record_login_attempt(key, success=False):
    """Record a login attempt for rate limiting."""
    now = datetime.now(timezone.utc)
    if key in _login_attempts:
        attempts, first_attempt = _login_attempts[key]
        if now - first_attempt > timedelta(seconds=LOGIN_RATE_LIMIT_WINDOW):
            if success:
                del _login_attempts[key]
            else:
                _login_attempts[key] = (attempts + 1, first_attempt)
        else:
            _login_attempts[key] = (attempts + 1, first_attempt)
    else:
        _login_attempts[key] = (1, now)
    if success:
        if key in _login_attempts:
            del _login_attempts[key]


# =============================================================================
# Password Reset Tokens
# =============================================================================

_password_reset_tokens = {}  # In production, use database storage


def generate_reset_token():
    """Generate a secure password reset token."""
    return secrets.token_urlsafe(32)


def store_reset_token(token, user_id, expires_in_seconds=3600):
    """Store a password reset token with expiration."""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
    _password_reset_tokens[token] = {
        'user_id': user_id,
        'expires_at': expires_at,
        'used': False
    }


def validate_reset_token(token):
    """Validate a password reset token. Returns user_id if valid, None otherwise."""
    if token not in _password_reset_tokens:
        return None

    token_data = _password_reset_tokens[token]

    # Check if expired
    if datetime.now(timezone.utc) > token_data['expires_at']:
        del _password_reset_tokens[token]
        return None

    # Check if already used (single-use)
    if token_data['used']:
        return None

    return token_data['user_id']


def invalidate_reset_token(token):
    """Invalidate a password reset token (mark as used)."""
    if token in _password_reset_tokens:
        _password_reset_tokens[token]['used'] = True


# =============================================================================
# Session Management
# =============================================================================

def login_user(user_id, merchant_id):
    """Log a user in by setting session data.

    Clears existing session data before setting new values.
    Does NOT store password in session.
    """
    # Clear any existing session data
    session.clear()

    # Set new session values
    session['user_id'] = user_id
    session['merchant_id'] = merchant_id
    session.permanent = True

    # Regenerate session ID for security (Flask handles this via SECRET_KEY)
    session.modified = True


def logout_user():
    """Log out the current user by clearing the entire session."""
    session.clear()


def get_current_user():
    """Get the currently logged in user."""
    if 'user_id' in session:
        return db.session.get(User, session['user_id'])
    return None


def get_current_merchant_id():
    """Get the current merchant ID from session.

    SECURITY: This derives merchant_id from authenticated user,
    not from URL parameters or form data directly.
    """
    # First check if user is logged in
    user_id = session.get('user_id')
    if user_id:
        user = db.session.get(User, user_id)
        if user:
            return user.merchant_id

    # Fall back to session merchant_id (set during login or merchant setup)
    return session.get('merchant_id', 1)


def get_current_merchant():
    """Get the current merchant context."""
    merchant_id = get_current_merchant_id()
    if merchant_id:
        return db.session.get(Merchant, merchant_id)
    return None


# =============================================================================
# Decorators
# =============================================================================

def login_required(f):
    """Decorator to require login for a route.

    Redirects to login page if not authenticated.
    Stores the original URL for redirect after login.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please sign in to access this page.', 'error')
            return redirect(url_for('auth.login', next=request.url))

        user = db.session.get(User, session['user_id'])
        if not user or not user.is_active:
            session.clear()
            flash('Your account is inactive. Please contact support.', 'error')
            return redirect(url_for('auth.login'))

        # Set g.user and g.merchant for request context
        g.user = user
        g.merchant = user.merchant

        return f(*args, **kwargs)
    return decorated_function


def merchant_required(f):
    """Decorator to ensure route is within a valid merchant context.

    This is used for routes that need merchant context but not necessarily
    user authentication (e.g., customer portal accessed via wallet pass).
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        merchant_id = get_current_merchant_id()
        if 'merchant_id' not in session and not merchant_id:
            session['merchant_id'] = 1

        merchant = db.session.get(Merchant, merchant_id or 1)
        if not merchant:
            g.merchant = db.session.get(Merchant, 1)
        else:
            g.merchant = merchant

        if 'merchant_id' not in session:
            session['merchant_id'] = merchant_id or 1

        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    """Decorator for role-based access control.

    Usage: @role_required('owner', 'manager')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please sign in to access this page.', 'error')
                return redirect(url_for('auth.login', next=request.url))

            user = db.session.get(User, session['user_id'])
            if not user or not user.is_active:
                session.clear()
                flash('Your account is inactive.', 'error')
                return redirect(url_for('auth.login'))

            g.user = user
            g.merchant = user.merchant

            if user.role not in roles:
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('index'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """Decorator that requires owner or manager role."""
    return role_required('owner', 'manager')(f)


# =============================================================================
# User Registration
# =============================================================================

def create_merchant_and_user(shop_name, email, phone, business_type, password):
    """Create a new merchant and associated user.

    Returns (merchant, user) tuple on success, (None, None) on failure.
    """
    try:
        # Check if email is already registered as a merchant
        existing_merchant = Merchant.query.filter_by(email=email).first()
        if existing_merchant:
            return None, None  # Prevent user enumeration

        # Create merchant
        merchant = Merchant(
            name=shop_name,
            email=email,
            phone=phone,
            business_type=business_type or 'other',
            is_active=True,
            subscription_tier='starter'
        )
        merchant.password_hash = hash_password(password)

        db.session.add(merchant)
        db.session.commit()

        # Create owner user for the merchant
        user = User(
            merchant_id=merchant.id,
            email=email,
            password_hash=hash_password(password),
            role='owner',
            can_scan=True,
            can_earn=True,
            can_redeem=True,
            can_view_reports=True
        )

        db.session.add(user)
        db.session.commit()

        return merchant, user
    except Exception:
        db.session.rollback()
        return None, None


# =============================================================================
# Admin Setup (for initial database setup)
# =============================================================================

def setup_admin_merchant():
    """Create default admin merchant and user for development.

    This should only be called during initial setup or testing.
    In production, use proper user management via registration flow.
    """
    admin_merchant = db.session.get(Merchant, 1)

    if not admin_merchant:
        admin_merchant = Merchant(
            name='AZUL Demo Shop',
            email='admin@azul.ma',
            phone='+212 5 00 00 00 00',
            business_type='café',
            language='fr',
            subscription_tier='growth'
        )
        # Require ADMIN_PASSWORD to be set in production
        admin_password = os.environ.get('ADMIN_PASSWORD')
        if not admin_password:
            # Only allow fallback for testing
            from flask import current_app
            if not current_app.config.get('TESTING'):
                raise RuntimeError("ADMIN_PASSWORD environment variable must be set for initial setup")
            admin_password = 'changeme'
        admin_merchant.password_hash = hash_password(admin_password)

        db.session.add(admin_merchant)
        db.session.commit()

        admin_user = User(
            merchant_id=admin_merchant.id,
            email='admin@azul.ma',
            password_hash=hash_password(admin_password),
            role='owner',
            can_scan=True,
            can_earn=True,
            can_redeem=True,
            can_view_reports=True
        )

        db.session.add(admin_user)
        db.session.commit()

    return admin_merchant
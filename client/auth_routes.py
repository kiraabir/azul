"""Authentication routes for AZUL - Login, Register, Logout, Password Reset."""
import re
from functools import wraps
from flask import (render_template, redirect, url_for, flash, request,
                   session, g, Blueprint)

from flask_wtf.csrf import CSRFProtect

from . import db
from .models import Merchant, User
from .auth import (
    login_required, login_user, logout_user, get_current_user, get_current_merchant,
    verify_password, create_merchant_and_user, hash_password,
    check_rate_limit, record_login_attempt, generate_reset_token,
    store_reset_token, validate_reset_token, invalidate_reset_token
)


# Create blueprint for auth routes
auth_bp = Blueprint('auth', __name__)


# =============================================================================
# CSRF Token Helper
# =============================================================================

def csrf_token():
    """Generate or get CSRF token for the session."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = generate_reset_token()  # Reuse token generation
    return session['_csrf_token']


@auth_bp.context_processor
def inject_csrf_token():
    """Inject CSRF token into all templates."""
    return dict(csrf_token=csrf_token)


# =============================================================================
# Form Validation
# =============================================================================

def validate_email(email):
    """Basic email validation."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password(password):
    """Validate password meets minimum requirements."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    return True, None


def validate_phone(phone):
    """Validate phone number format (basic validation for Morocco numbers)."""
    if not phone:
        return True  # Phone is optional
    pattern = r'^\+212[56]\d{9}$|^0[56]\d{8}$'
    return re.match(pattern, phone.replace(' ', '')) is not None


# =============================================================================
# Login Route
# =============================================================================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login."""
    # If already logged in, redirect to dashboard
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        next_url = request.args.get('next')

        # Rate limiting check
        ip_key = request.remote_addr
        if not check_rate_limit(ip_key):
            flash('Too many login attempts. Please try again later.', 'error')
            return render_template('login.html'), 429

        # Check if email provided
        if not email or not password:
            record_login_attempt(ip_key, success=False)
            flash('Please enter both email and password.', 'error')
            return render_template('login.html')

        # Find user by email
        user = User.query.filter_by(email=email, is_active=True).first()

        # SECURITY: Use constant-time comparison and same error message
        # to prevent user enumeration
        if user and verify_password(user.password_hash, password):
            # Record successful login
            record_login_attempt(ip_key, success=True)

            # Log the user in
            login_user(user.id, user.merchant_id)

            flash('Welcome back!', 'ok')

            # Redirect to next URL or dashboard
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect(url_for('index'))

        # Record failed login attempt
        record_login_attempt(ip_key, success=False)

        # Generic error message to prevent user enumeration
        flash('Invalid email or password.', 'error')

    return render_template('login.html', email=request.form.get('email', ''))


# =============================================================================
# Logout Route
# =============================================================================

@auth_bp.route('/logout')
def logout():
    """Handle user logout."""
    logout_user()
    flash('You have been logged out.', 'ok')
    return redirect(url_for('auth.login'))


# =============================================================================
# Registration Route
# =============================================================================

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Handle new user registration."""
    if request.method == 'POST':
        shop_name = request.form.get('shop_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        business_type = request.form.get('business_type', 'other')
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        errors = []

        # Validate shop name
        if not shop_name or len(shop_name) < 2:
            errors.append('Shop name must be at least 2 characters.')

        # Validate email
        if not email:
            errors.append('Email is required.')
        elif not validate_email(email):
            errors.append('Please enter a valid email address.')

        # Validate phone (optional but must be valid if provided)
        if phone and not validate_phone(phone):
            errors.append('Please enter a valid phone number (e.g., +212 6 00 00 00 00).')

        # Validate business type
        valid_business_types = ['café', 'restaurant', 'retail', 'beauty', 'auto', 'other']
        if business_type not in valid_business_types:
            business_type = 'other'

        # Validate password
        valid, msg = validate_password(password)
        if not valid:
            errors.append(msg)

        # Check password confirmation
        if password != confirm_password:
            errors.append('Passwords do not match.')

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('register.html',
                                   shop_name=shop_name,
                                   email=email,
                                   phone=phone,
                                   business_type=business_type)

        # Check for existing merchant with this email
        existing = Merchant.query.filter_by(email=email).first()
        if existing:
            flash('An account with this email already exists. Please sign in.', 'error')
            return render_template('register.html',
                                   shop_name=shop_name,
                                   email=email,
                                   phone=phone,
                                   business_type=business_type)

        # Create merchant and user
        merchant, user = create_merchant_and_user(
            shop_name=shop_name,
            email=email,
            phone=phone or None,
            business_type=business_type,
            password=password
        )

        if merchant and user:
            # Auto-login after registration
            login_user(user.id, user.merchant_id)
            flash(f'Welcome, {shop_name}! Your account has been created.', 'ok')
            return redirect(url_for('settings'))
        else:
            flash('An error occurred while creating your account. Please try again.', 'error')

    return render_template('register.html')


# =============================================================================
# Password Reset Routes
# =============================================================================

@auth_bp.route('/password-reset', methods=['GET', 'POST'])
def request_password_reset():
    """Request a password reset link."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        if email:
            # Find user by email
            user = User.query.filter_by(email=email, is_active=True).first()

            if user:
                # Generate reset token
                token = generate_reset_token()
                store_reset_token(token, user.id, expires_in_seconds=3600)  # 1 hour

                # In production, send email with reset link
                # For now, we'll just flash a message
                # The token would be sent via email in production
                reset_url = url_for('auth.password_reset', token=token, _external=True)
                flash(f'Password reset link generated. Check your email for instructions.', 'ok')

                # For development/testing, also show in flash
                # Remove in production
                flash(f'Development: Reset token: {token}', 'info')

        # Always show same message to prevent user enumeration
        flash('If an account exists with that email, a reset link has been sent.', 'ok')

    return render_template('password_reset_request.html')


@auth_bp.route('/password-reset/<token>', methods=['GET', 'POST'])
def password_reset(token):
    """Handle password reset with token."""
    user_id = validate_reset_token(token)

    if not user_id:
        flash('Invalid or expired reset link. Please request a new one.', 'error')
        return redirect(url_for('auth.request_password_reset'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        errors = []

        # Validate password
        valid, msg = validate_password(password)
        if not valid:
            errors.append(msg)

        # Check password confirmation
        if password != confirm_password:
            errors.append('Passwords do not match.')

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('password_reset.html')

        # Update password
        user = User.query.get(user_id)
        if user:
            user.password_hash = hash_password(password)
            db.session.commit()

            # Invalidate the token (single-use)
            invalidate_reset_token(token)

            flash('Your password has been reset. Please sign in.', 'ok')
            return redirect(url_for('auth.login'))
        else:
            flash('User not found.', 'error')
            return redirect(url_for('auth.request_password_reset'))

    return render_template('password_reset.html')


# =============================================================================
# Route Registration
# =============================================================================

def register_auth_routes(app):
    """Register authentication routes with the Flask app."""
    app.register_blueprint(auth_bp)

    # Add csrf_token to app context for templates
    @app.context_processor
    def inject_csrf():
        return dict(csrf_token=csrf_token)


# =============================================================================
# Legacy compatibility routes (for direct function imports)
# =============================================================================

def login_route():
    """Legacy compatibility - redirect to blue route."""
    from flask import redirect
    return redirect(url_for('auth.login'))


def register_route():
    """Legacy compatibility - redirect to blue route."""
    from flask import redirect
    return redirect(url_for('auth.register'))


def logout_route():
    """Legacy compatibility - redirect to blue route."""
    from flask import redirect
    return redirect(url_for('auth.logout'))
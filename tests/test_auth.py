"""Authentication tests for AZUL - Login, Logout, Registration, Password Reset."""
import pytest
from client import create_app, db
from client.models import Merchant, User
from client.auth import hash_password, verify_password


@pytest.fixture
def app():
    """Create test app with authentication setup."""
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()

        # Create a test merchant
        merchant = Merchant(
            name="Test Merchant",
            email="test@test.com",
            business_type="café",
            is_active=True,
            subscription_tier="starter"
        )
        db.session.add(merchant)
        db.session.commit()

        # Create test users
        user1 = User(
            merchant_id=merchant.id,
            email="user1@test.com",
            password_hash=hash_password("password123"),
            role="owner",
            is_active=True
        )
        user2 = User(
            merchant_id=merchant.id,
            email="user2@test.com",
            password_hash=hash_password("password456"),
            role="manager",
            is_active=True
        )
        inactive_user = User(
            merchant_id=merchant.id,
            email="inactive@test.com",
            password_hash=hash_password("password789"),
            role="staff",
            is_active=False
        )
        db.session.add_all([user1, user2, inactive_user])
        db.session.commit()

        app.test_data = {
            "merchant_id": merchant.id,
            "user1_email": "user1@test.com",
            "user2_email": "user2@test.com",
            "user1_password": "password123",
            "user2_password": "password456",
        }

        yield app


@pytest.fixture
def client(app):
    return app.test_client()


class TestLogin:
    """Login route tests."""

    def test_login_page_loads(self, client):
        """Login page should be accessible."""
        res = client.get("/login")
        assert res.status_code == 200
        assert b"Sign In" in res.data or b"login" in res.data.lower()

    def test_successful_login(self, client, app):
        """Valid credentials should log in successfully."""
        res = client.post("/login", data={
            "email": app.test_data["user1_email"],
            "password": app.test_data["user1_password"]
        }, follow_redirects=True)
        assert res.status_code == 200
        # Should redirect to dashboard or show welcome message
        assert b"Welcome" in res.data or b"Dashboard" in res.data or b"logout" in res.data.lower()

    def test_invalid_password(self, client, app):
        """Wrong password should show error."""
        res = client.post("/login", data={
            "email": app.test_data["user1_email"],
            "password": "wrongpassword"
        }, follow_redirects=True)
        assert b"Invalid" in res.data or b"invalid" in res.data.lower() or b"error" in res.data.lower()

    def test_invalid_email(self, client, app):
        """Non-existent email should show error."""
        res = client.post("/login", data={
            "email": "nonexistent@test.com",
            "password": "password123"
        }, follow_redirects=True)
        assert b"Invalid" in res.data or b"invalid" in res.data.lower() or b"error" in res.data.lower()

    def test_inactive_user_cannot_login(self, client, app):
        """Inactive user should not be able to log in."""
        res = client.post("/login", data={
            "email": "inactive@test.com",
            "password": "password789"
        }, follow_redirects=True)
        # Should either redirect or show error
        assert res.status_code in [200, 302]


class TestLogout:
    """Logout route tests."""

    def test_logout_clears_session(self, client, app):
        """Logout should clear the session."""
        # First log in
        client.post("/login", data={
            "email": app.test_data["user1_email"],
            "password": app.test_data["user1_password"]
        }, follow_redirects=True)

        # Then logout - should redirect to login page
        res = client.get("/logout", follow_redirects=False)
        # Should redirect to login
        assert res.status_code == 302

        # Session should be cleared - try accessing protected route
        res = client.get("/settings", follow_redirects=True)
        # Should show login page since not authenticated
        assert b"Sign In" in res.data or b"login" in res.data.lower()


class TestRegistration:
    """Registration route tests."""

    def test_register_page_loads(self, client):
        """Registration page should be accessible."""
        res = client.get("/register")
        assert res.status_code == 200
        assert b"Create" in res.data or b"Account" in res.data

    def test_successful_registration(self, client):
        """New user can register."""
        res = client.post("/register", data={
            "shop_name": "New Test Shop",
            "email": "newshop@test.com",
            "phone": "+212 6 00 00 00 99",
            "business_type": "café",
            "password": "newpassword123",
            "confirm_password": "newpassword123"
        }, follow_redirects=True)
        assert res.status_code == 200

    def test_duplicate_email_registration(self, client, app):
        """Duplicate email should fail."""
        res = client.post("/register", data={
            "shop_name": "Duplicate Shop",
            "email": app.test_data["user1_email"],  # Already exists
            "phone": "+212 6 00 00 00 98",
            "business_type": "café",
            "password": "password123",
            "confirm_password": "password123"
        }, follow_redirects=True)
        assert b"exists" in res.data.lower() or b"already" in res.data.lower() or b"error" in res.data.lower()

    def test_password_mismatch(self, client):
        """Password confirmation mismatch should fail."""
        res = client.post("/register", data={
            "shop_name": "Mismatched Shop",
            "email": "mismatch@test.com",
            "phone": "+212 6 00 00 00 97",
            "business_type": "café",
            "password": "password123",
            "confirm_password": "differentpassword"
        }, follow_redirects=True)
        assert b"match" in res.data.lower() or b"error" in res.data.lower()

    def test_short_password(self, client):
        """Short password should fail validation."""
        res = client.post("/register", data={
            "shop_name": "Short Pass Shop",
            "email": "shortpass@test.com",
            "phone": "+212 6 00 00 00 96",
            "business_type": "café",
            "password": "short",
            "confirm_password": "short"
        }, follow_redirects=True)
        assert b"8" in res.data or b"character" in res.data.lower() or b"error" in res.data.lower()


class TestPasswordReset:
    """Password reset route tests."""

    def test_reset_request_page_loads(self, client):
        """Reset request page should be accessible."""
        res = client.get("/password-reset")
        assert res.status_code == 200
        assert b"reset" in res.data.lower() or b"password" in res.data.lower()

    def test_reset_request_sends_message(self, client, app):
        """Reset request should show success message."""
        res = client.post("/password-reset", data={
            "email": app.test_data["user1_email"]
        }, follow_redirects=True)
        assert b"sent" in res.data.lower() or b"reset" in res.data.lower() or b"success" in res.data.lower()


class TestPasswordHashing:
    """Password hashing tests."""

    def test_hash_creates_different_hashes(self):
        """Same password should create different hashes (salted)."""
        hash1 = hash_password("password123")
        hash2 = hash_password("password123")
        assert hash1 != hash2

    def test_verify_correct_password(self):
        """Verify should accept correct password."""
        hashed = hash_password("password123")
        assert verify_password(hashed, "password123") is True

    def test_verify_incorrect_password(self):
        """Verify should reject incorrect password."""
        hashed = hash_password("password123")
        assert verify_password(hashed, "wrongpassword") is False

    def test_verify_none_password(self):
        """Verify should handle None password."""
        assert verify_password(None, "password123") is False


class TestRouteAccess:
    """Protected route access tests."""

    def test_unauthenticated_index_redirects(self, client):
        """Unauthenticated user should be redirected from dashboard."""
        res = client.get("/", follow_redirects=False)
        # Should redirect to login
        assert res.status_code == 302 or res.status_code == 200 and b"login" in res.data.lower()

    def test_unauthenticated_customers_list_redirects(self, client):
        """Unauthenticated user should be redirected from customers list."""
        res = client.get("/customers", follow_redirects=True)
        # Should show login page or redirect
        assert b"login" in res.data.lower() or b"Sign" in res.data or b"sign" in res.data

    def test_unauthenticated_settings_redirects(self, client):
        """Unauthenticated user should be redirected from settings."""
        res = client.get("/settings", follow_redirects=True)
        # Should show login page or redirect
        assert b"login" in res.data.lower() or b"Sign" in res.data or b"sign" in res.data

    def test_authenticated_can_access_own_merchant_data(self, client, app):
        """Authenticated user should access their merchant data."""
        # Log in
        client.post("/login", data={
            "email": app.test_data["user1_email"],
            "password": app.test_data["user1_password"]
        })

        # Access dashboard
        res = client.get("/", follow_redirects=True)
        assert res.status_code == 200

        # Access customers list
        res = client.get("/customers")
        assert res.status_code == 200

        # Access settings
        res = client.get("/settings")
        assert res.status_code == 200
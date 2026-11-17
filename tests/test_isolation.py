"""Comprehensive cross-merchant isolation and security test suite for AZUL."""
import pytest
from flask import session
from client import create_app, db
from client.models import (Merchant, Customer, LoyaltyCard, Transaction,
                           ShopSetting, RewardTier, Campaign, Notification, Feedback, User)


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()

        # Create Merchant A
        m_a = Merchant(
            id=1,
            name="Cafe Casablanca (Merchant A)",
            email="casa@azul.ma",
            phone="+212500000001",
            business_type="café"
        )
        db.session.add(m_a)

        # Create Merchant B
        m_b = Merchant(
            id=2,
            name="Marrakech Spas (Merchant B)",
            email="spa@azul.ma",
            phone="+212500000002",
            business_type="spa"
        )
        db.session.add(m_b)
        db.session.commit()

        # Create users for testing (login_required checks for user_id)
        user_a = User(
            merchant_id=1,
            email="casa@azul.ma",
            password_hash="test",
            role="owner",
            is_active=True
        )
        user_b = User(
            merchant_id=2,
            email="spa@azul.ma",
            password_hash="test",
            role="owner",
            is_active=True
        )
        db.session.add_all([user_a, user_b])
        db.session.commit()

        # Setup data for Merchant A
        cust_a = Customer(merchant_id=1, name="Ali A", phone="0611111111")
        db.session.add(cust_a)
        db.session.commit()
        card_a = LoyaltyCard(merchant_id=1, customer_id=cust_a.id)
        db.session.add(card_a)

        tier_a = RewardTier(merchant_id=1, threshold_stamps=5, name="Cafe Reward A")
        db.session.add(tier_a)

        # Setup data for Merchant B
        cust_b = Customer(merchant_id=2, name="Fatima B", phone="0622222222")
        db.session.add(cust_b)
        db.session.commit()
        card_b = LoyaltyCard(merchant_id=2, customer_id=cust_b.id)
        db.session.add(card_b)

        tier_b = RewardTier(merchant_id=2, threshold_stamps=5, name="Spa Reward B")
        db.session.add(tier_b)
        db.session.commit()

        # Capture only plain primitives (ints/strings) here. ORM instances are
        # bound to the session that is torn down when this app_context exits,
        # so holding onto them across the `yield` raises DetachedInstanceError
        # the moment they are lazily accessed. Tests must re-query inside their
        # own app_context instead, which is what the session architecture
        # (one session per app_context) expects.
        app.azul_fixture = {
            "customer_a_id": cust_a.id,
            "customer_b_id": cust_b.id,
            "card_a_id": card_a.id,
            "card_b_id": card_b.id,
            "tier_a_id": tier_a.id,
            "tier_b_id": tier_b.id,
            "token_b": card_b.qr_token,
        }

        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _login_as_merchant(client, merchant_id):
    """Helper to set session for testing as a logged-in merchant."""
    with client.session_transaction() as sess:
        sess['merchant_id'] = merchant_id
        # Set a dummy user_id for testing (login_required checks for user_id)
        sess['user_id'] = 1 if merchant_id == 1 else 2


def test_merchant_a_cannot_view_merchant_b_customers(client, app):
    """Scenario 1 & 2: Merchant A cannot view or access Merchant B's customers and cards."""
    f = app.azul_fixture

    with app.app_context():
        cust_b = Customer.query.get(f["customer_b_id"])
        card_b = LoyaltyCard.query.get(f["card_b_id"])

    _login_as_merchant(client, 1)  # Logged in as Merchant A

    # Attempt to view Merchant B's customer detail
    res = client.get(f"/customers/{cust_b.id}")
    assert res.status_code == 404, "Merchant A should get 404 on Merchant B's customer"

    # Attempt to view Merchant B's card detail
    res = client.get(f"/cards/{card_b.id}")
    assert res.status_code == 404, "Merchant A should get 404 on Merchant B's card"


def test_merchant_a_cannot_access_merchant_b_transactions(client, app):
    """Scenario 3: Merchant A cannot view or modify Merchant B's transactions."""
    f = app.azul_fixture

    _login_as_merchant(client, 1)

    # Attempt to earn points on Merchant B's card using Merchant A session
    res = client.post(f"/cards/{f['card_b_id']}/earn",
                      data={"points": "5", "description": "Hacked"},
                      follow_redirects=True)
    assert res.status_code == 404

    with app.app_context():
        card_b_refreshed = LoyaltyCard.query.get(f["card_b_id"])
        assert card_b_refreshed.points_balance == 0, "Points balance must not change across tenants"


def test_merchant_a_cannot_redeem_merchant_b_rewards(client, app):
    """Scenario 4: Merchant A cannot modify or redeem Merchant B's rewards."""
    f = app.azul_fixture

    with app.app_context():
        card_a = LoyaltyCard.query.get(f["card_a_id"])
        card_a.points_balance = 20
        db.session.commit()

    _login_as_merchant(client, 1)

    # Attempt to redeem Merchant B's reward tier using Merchant A's card
    res = client.post(f"/c/{f['card_a_id']}/redeem",
                      data={"reward_tier_id": f["tier_b_id"]},
                      follow_redirects=True)
    assert res.status_code == 404


def test_customer_portal_isolation(client, app):
    """Scenario 10: Customers cannot access another merchant's card or portal."""
    f = app.azul_fixture

    _login_as_merchant(client, 1)  # Merchant A active session

    res = client.get(f"/c/{f['card_b_id']}")
    assert res.status_code == 404, "Merchant A session cannot view Merchant B customer portal"


def test_scan_token_tenant_isolation(client, app):
    """Scenario 8: Token scan is scoped correctly to active merchant."""
    f = app.azul_fixture

    # Merchant A session scanning Merchant B token
    _login_as_merchant(client, 1)

    res = client.get(f"/scan/{f['token_b']}")
    assert res.status_code == 404, "Merchant A cannot scan/resolve Merchant B's card token"


# =============================================================================
# Extended Security Verification Tests
# =============================================================================

def test_no_data_exposure_in_error_responses(client, app):
    """Verify error responses don't leak data about other merchants."""
    f = app.azul_fixture
    _login_as_merchant(client, 1)

    # Try various endpoints with cross-merchant IDs
    endpoints = [
        f"/customers/{f['customer_b_id']}",
        f"/cards/{f['card_b_id']}",
        f"/c/{f['card_b_id']}",
    ]
    for endpoint in endpoints:
        r = client.get(endpoint)
        assert r.status_code == 404
        # Response body should not contain any customer/card data
        assert b"Fatima" not in r.data, f"Response leaked customer name via {endpoint}"
        assert b"Card" not in r.data or b"merchant" not in r.data.lower(), f"Response may leak card data via {endpoint}"


def test_transactions_never_leaked(client, app):
    """Verify transactions cannot be accessed via cross-merchant ID."""
    f = app.azul_fixture
    with app.app_context():
        # Create a transaction for card_b
        card_b = LoyaltyCard.query.get(f["card_b_id"])
        tx = Transaction(card=card_b, merchant_id=2, customer_id=card_b.customer_id,
                        type="earn", points=10, description="Test")
        db.session.add(tx)
        db.session.commit()
        tx_id = tx.id

    _login_as_merchant(client, 1)

    # Merchant A cannot view Merchant B's transactions
    res = client.get(f"/cards/{f['card_b_id']}")
    assert res.status_code == 404


def test_settings_never_leaked_to_other_merchants(client, app):
    """Verify shop settings are always tenant-scoped."""
    from client.models import ShopSetting

    with app.app_context():
        # Set a unique setting for Merchant B
        ShopSetting.set("shop_name", "Marrakech Spas Exclusive Name", merchant_id=2)

    _login_as_merchant(client, 1)

    # Merchant A's settings page should not show Merchant B's shop name
    res = client.get("/settings")
    assert res.status_code == 200
    # Should not contain Merchant B's exclusive name
    assert b"Marrakech Spas Exclusive Name" not in res.data, "Settings page leaked other merchant's data"


def test_rewards_cannot_cross_merchant(client, app):
    """Verify reward redemption is strictly scoped to merchant."""
    f = app.azul_fixture

    # Set up card_a with enough points
    with app.app_context():
        card_a = LoyaltyCard.query.get(f["card_a_id"])
        card_a.points_balance = 50
        db.session.commit()

    _login_as_merchant(client, 1)

    # Attempt to redeem Merchant B's tier with Merchant A's card
    res = client.post(f"/c/{f['card_a_id']}/redeem",
                      data={"reward_tier_id": f["tier_b_id"]},
                      follow_redirects=True)
    assert res.status_code == 404

    # Verify no balance change
    with app.app_context():
        card_a = LoyaltyCard.query.get(f["card_a_id"])
        assert card_a.points_balance == 50, "Points leaked or changed"


def test_customer_query_is_tenant_scoped(client, app):
    """Verify customer search/list is scoped to tenant."""
    f = app.azul_fixture

    _login_as_merchant(client, 1)

    # Search for customer that only exists in Merchant B
    res = client.get("/customers?q=Fatima")
    # Should return empty or just own customers, never Merchant B's data
    assert b"Fatima B" not in res.data, "Search leaked cross-tenant customer"


def test_notification_isolation(client, app):
    """Verify notifications are tenant-isolated."""
    from client.models import Notification

    f = app.azul_fixture
    with app.app_context():
        # Create notification for card_b
        card_b = LoyaltyCard.query.get(f["card_b_id"])
        notif = Notification(
            merchant_id=2, customer_id=card_b.customer_id,
            title="Private B Notification",
            body="This is Merchant B's private data"
        )
        db.session.add(notif)
        db.session.commit()

    _login_as_merchant(client, 1)

    # Merchant A cannot see Merchant B's notifications via card endpoint
    res = client.get(f"/c/{f['card_b_id']}/notifications")
    assert res.status_code == 404

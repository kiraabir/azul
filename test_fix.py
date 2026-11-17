#!/usr/bin/env python3
"""Test script to verify wallet_serial fix."""
import os
import sys
import uuid

# Set secret key
os.environ['SECRET_KEY'] = 'dev-secret-key-change-in-production'

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Clean database for fresh test - use absolute path to ensure correct file
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_azul.db')
TEST_DB_URI = f'sqlite:///{TEST_DB_PATH}'

if os.path.exists(TEST_DB_PATH):
    os.remove(TEST_DB_PATH)

# Create app with test database
from client import create_app, db as azul_db
from client.models import Customer, LoyaltyCard, Merchant, RewardTier

app = create_app({
    "TESTING": True,
    "SQLALCHEMY_DATABASE_URI": TEST_DB_URI,
})

def test_wallet_serial():
    """Test that wallet_serial is unique across multiple cards."""
    with app.app_context():
        # Create all tables first
        azul_db.create_all()

        # Create merchant WITHOUT hardcoding id=1
        # Let SQLAlchemy auto-assign the primary key
        merchant = Merchant(
            name="Test Shop",
            email="test@test.com",
            business_type="café",
            language="fr",
            subscription_tier="growth"
        )
        azul_db.session.add(merchant)
        azul_db.session.commit()

        # Use the auto-generated merchant ID
        merchant_id = merchant.id
        print(f"Created merchant with auto-assigned ID: {merchant_id}")

        # Seed reward tiers
        tier = RewardTier(merchant_id=merchant_id, threshold_stamps=5, name="Free Item",
                         description="Test reward")
        azul_db.session.add(tier)
        azul_db.session.commit()

        # Create first customer and card
        cust1 = Customer(name="Alice", phone="+212 6 00 00 00 01", merchant_id=merchant_id)
        azul_db.session.add(cust1)
        azul_db.session.commit()

        card1 = LoyaltyCard(customer=cust1, merchant_id=merchant_id)
        azul_db.session.add(card1)
        azul_db.session.commit()

        # Create second customer and card
        cust2 = Customer(name="Bob", phone="+212 6 00 00 00 02", merchant_id=merchant_id)
        azul_db.session.add(cust2)
        azul_db.session.commit()

        card2 = LoyaltyCard(customer=cust2, merchant_id=merchant_id)
        azul_db.session.add(card2)
        azul_db.session.commit()

        # Create third card for same customer (edge case)
        card3 = LoyaltyCard(customer=cust1, merchant_id=merchant_id)
        azul_db.session.add(card3)
        azul_db.session.commit()

        # Verify all wallet_serials are unique
        serials = [card1.wallet_serial, card2.wallet_serial, card3.wallet_serial]
        print(f"Card 1: {card1.card_number}, wallet_serial: {card1.wallet_serial}")
        print(f"Card 2: {card2.card_number}, wallet_serial: {card2.wallet_serial}")
        print(f"Card 3: {card3.card_number}, wallet_serial: {card3.wallet_serial}")

        if len(serials) == len(set(serials)):
            print("\n✅ SUCCESS: All wallet_serials are unique!")
            return True
        else:
            print("\n❌ FAILURE: Duplicate wallet_serials detected!")
            return False

if __name__ == '__main__':
    success = test_wallet_serial()
    # Clean up test database - use try/except to handle file locking
    try:
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
    except PermissionError:
        pass  # File may be locked by another process
    sys.exit(0 if success else 1)
"""AZUL - Shop Loyalty Card Tool.

A wallet-based loyalty card platform for local businesses.
Supports Apple Wallet, Google Wallet, SMS engagement, and feedback loops.

Run with:  python -m client.app
"""
import os

# SECRET_KEY is enforced by client.create_app().
# Production must set SECRET_KEY via environment or .env file.
# See PRODUCTION_READINESS_REPORT.md for deployment instructions.

from client import create_app, db
from client.models import (ShopSetting, RewardTier, Customer, LoyaltyCard,
                           Merchant, User, Transaction, Campaign)


app = create_app()


def _bootstrap(app):
    """Initialize database and seed default data."""
    with app.app_context():
        db.create_all()

        # Get or create the default merchant (merchant_id = 1)
        merchant = Merchant.query.get(1)
        if not merchant:
            merchant = Merchant(
                id=1,
                name="AZUL Demo Shop",
                email="admin@azul.ma",
                phone="+212 5 00 00 00 00",
                business_type="café",
                language="fr",
                subscription_tier="growth"
            )
            db.session.add(merchant)
            db.session.commit()

        # Set default shop settings (scoped to merchant 1)
        settings_to_set = [
            ("shop_name", "AZUL"),
            ("points_per_purchase", "1"),
            ("redemption_value", "10"),
            ("feedback_stamp_value", "1"),
            ("reengage_days", "15"),
        ]
        for key, value in settings_to_set:
            row = ShopSetting.query.filter_by(merchant_id=1, key=key).first()
            if not row:
                ShopSetting.set(key, value, merchant_id=1)

        # Seed default reward tiers (scoped to merchant 1)
        existing_tier = RewardTier.query.filter_by(merchant_id=1).first()
        if not existing_tier:
            default_tiers = [
                RewardTier(merchant_id=1, threshold_stamps=5, name="Free Item",
                           description="Any item of equal or lesser value"),
                RewardTier(merchant_id=1, threshold_stamps=10, name="10% Off",
                           description="10% discount on next purchase"),
                RewardTier(merchant_id=1, threshold_stamps=15, name="Free Item + Drink",
                           description="Free item with a drink"),
            ]
            for tier in default_tiers:
                db.session.add(tier)
            db.session.commit()


if __name__ == "__main__":
    _bootstrap(app)
    app.run(debug=True, port=5000)
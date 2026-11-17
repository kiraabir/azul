"""Smoke test for AZUL: full customer -> card -> earn/redeem -> scan flow."""
import io
import os
import sys
import json as json_module

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client import create_app, db as azul_db
from client.models import (Customer, LoyaltyCard, Transaction, ShopSetting, RewardTier,
                           Campaign, Merchant, User)
from client.auth import hash_password

app = create_app({
    "TESTING": True,
    "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
})


def _set_test_merchant():
    """Set up test merchant context in session."""
    from flask import session
    with app.app_context():
        # Create default merchant if not exists
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
            azul_db.session.add(merchant)
            azul_db.session.commit()

        # Create a user for the test merchant (required for login_required decorator)
        user = User.query.filter_by(merchant_id=1, email="admin@azul.ma").first()
        if not user:
            user = User(
                merchant_id=merchant.id,
                email="admin@azul.ma",
                password_hash=hash_password("password123"),
                role="owner",
                is_active=True
            )
            azul_db.session.add(user)
            azul_db.session.commit()
            test_user_id = user.id
        else:
            test_user_id = user.id

        # Seed default reward tiers for merchant 1
        if not RewardTier.query.filter_by(merchant_id=1).first():
            default_tiers = [
                RewardTier(merchant_id=1, threshold_stamps=5, name="Free Item",
                           description="Any item of equal or lesser value"),
                RewardTier(merchant_id=1, threshold_stamps=10, name="10% Off",
                           description="10% discount on next purchase"),
                RewardTier(merchant_id=1, threshold_stamps=15, name="Free Item + Drink",
                           description="Free item with a drink"),
            ]
            for tier in default_tiers:
                azul_db.session.add(tier)
            azul_db.session.commit()

        # Set default shop settings for merchant 1
        for key, value in [
            ("shop_name", "AZUL"),
            ("points_per_purchase", "1"),
            ("redemption_value", "10"),
            ("feedback_stamp_value", "1"),
            ("reengage_days", "15"),
        ]:
            row = ShopSetting.query.filter_by(merchant_id=1, key=key).first()
            if not row:
                ShopSetting.set(key, value, merchant_id=1)

        # Create a test customer for merchant context lookups
        return merchant, test_user_id


with app.app_context():
    azul_db.create_all()
    _merchant, test_user_id = _set_test_merchant()

c = app.test_client()
failures = []


def check(name, cond, detail=""):
    status = "ok" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def with_merchant_session():
    """Context manager to set merchant_id AND user_id in session for requests.

    login_required checks for user_id, so both must be set.
    """
    with c.session_transaction() as sess:
        sess['merchant_id'] = 1
        sess['user_id'] = test_user_id  # Required by login_required decorator


# 1. Dashboard loads
with_merchant_session()
r = c.get("/")
check("dashboard 200", r.status_code == 200, r.status_code)

# 2. Customer creation with name (required) and phone (optional)
with_merchant_session()
r = c.post("/customers/new", data={"name": "Ada Lovelace", "phone": "555-0100"},
           follow_redirects=True)
check("create customer with phone", r.status_code == 200 and b"Ada Lovelace" in r.data,
      r.status_code)

# 2b. Customer creation without phone (phone is optional)
with_merchant_session()
r = c.post("/customers/new", data={"name": "Grace Hopper"},
           follow_redirects=True)
check("create customer without phone", r.status_code == 200 and b"Grace Hopper" in r.data,
      r.status_code)

with app.app_context():
    ada = Customer.query.filter_by(merchant_id=1, name="Ada Lovelace").first()
    grace = Customer.query.filter_by(merchant_id=1, name="Grace Hopper").first()
    check("customer has_phone True when phone provided", ada.has_phone == True, f"Ada has_phone={ada.has_phone}")
    check("customer has_phone False when no phone provided", grace.has_phone == False, f"Grace has_phone={grace.has_phone}")

# 3. Card creation
with_merchant_session()
r = c.post("/cards/new", data={"customer_id": str(ada.id)}, follow_redirects=True)
check("create card", r.status_code == 200 and b"Card" in r.data, r.status_code)

with app.app_context():
    card = LoyaltyCard.query.filter_by(merchant_id=1).first()
check("card has 16-digit number", len(card.card_number) == 16, card.card_number)
check("card has opaque token", len(card.qr_token) == 64, card.qr_token)

# 4. QR PNG renders and decodes back to the token
with_merchant_session()
r = c.get(f"/cards/{card.id}/qr.png")
check("qr png 200", r.status_code == 200, r.status_code)
check("qr png content-type", r.content_type == "image/png", r.content_type)
check("qr png is an image", r.data[:4] == b"\x89PNG", r.data[:4])

import qrcode
from PIL import Image
from pyzbar.pyzbar import decode as decode_qr

img = Image.open(io.BytesIO(r.data))
img.load()
check("qr image dimensions sane", img.size[0] >= 200, str(img.size))

# Verify the produced QR is actually scannable and decodes to the token.
decoded = decode_qr(img)
check("qr decodes", len(decoded) == 1, decoded)
if decoded:
    check("qr decodes to token", decoded[0].data.decode() == card.qr_payload,
          decoded[0].data.decode())

# Verify QR payload uses AZUL prefix
check("qr payload uses azul:card: prefix", card.qr_payload.startswith("azul:card:"),
      card.qr_payload)

# 5. Wallet pass generation (Apple)
with_merchant_session()
r = c.get(f"/wallet/apple/{card.id}")
check("apple wallet pass 200", r.status_code == 200, r.status_code)

# 6. Wallet pass generation (Google)
with_merchant_session()
r = c.get(f"/wallet/google/{card.id}")
check("google wallet pass 200", r.status_code == 200, r.status_code)

# 7. Earn points
with_merchant_session()
r = c.post(f"/cards/{card.id}/earn", data={"points": "5", "description": "Coffee"},
           follow_redirects=True)
check("earn points", r.status_code == 200 and b"5" in r.data, r.status_code)
with app.app_context():
    card = LoyaltyCard.query.get(card.id)
check("balance after earn", card.points_balance == 5, card.points_balance)

# 8. Refund points (redeem)
with_merchant_session()
r = c.post(f"/cards/{card.id}/redeem", data={"points": "2", "description": "Pastry"},
           follow_redirects=True)
check("redeem points", r.status_code == 200, r.status_code)
with app.app_context():
    card = LoyaltyCard.query.get(card.id)
check("balance after redeem", card.points_balance == 3, card.points_balance)

# 9. Over-redemption rejected
with_merchant_session()
r = c.post(f"/cards/{card.id}/redeem", data={"points": "999", "description": "x"},
           follow_redirects=True)
with app.app_context():
    card = LoyaltyCard.query.get(card.id)
check("over-redemption rejected", card.points_balance == 3, card.points_balance)

# 10. Feedback submission earns a stamp
with_merchant_session()
r = c.post(f"/feedback/{card.id}", data={"rating": "5", "comment": "Great service!"},
           follow_redirects=True)
check("submit feedback 200", r.status_code == 200, r.status_code)
with app.app_context():
    card = LoyaltyCard.query.get(card.id)
check("feedback earns stamp", card.points_balance == 4, f"balance={card.points_balance}")

# 11. Reward tiers exist and are seeded
with app.app_context():
    tiers = RewardTier.query.filter_by(merchant_id=1, is_available=True).all()
check("reward tiers exist", len(tiers) >= 3, f"{len(tiers)} tiers found")
with app.app_context():
    free_item = RewardTier.query.filter_by(merchant_id=1, name="Free Item").first()
check("reward tier has threshold", free_item.threshold_stamps == 5, f"threshold={free_item.threshold_stamps}")

# 12. Add a new reward tier
with_merchant_session()
r = c.post("/rewards/new", data={"threshold_stamps": "20", "name": "Special Reward",
                                 "description": "Exclusive offer", "is_available": "on"},
           follow_redirects=True)
check("create new reward tier", r.status_code == 200, r.status_code)
with app.app_context():
    special = RewardTier.query.filter_by(merchant_id=1, name="Special Reward").first()
check("new tier has correct threshold", special.threshold_stamps == 20, f"threshold={special.threshold_stamps}")

# 13. Re-engagement campaign creation
with_merchant_session()
r = c.post("/campaigns/re-engage", data={"content": "We miss you! Come back for a free drink!"},
           follow_redirects=True)
check("re-engagement campaign 200", r.status_code == 200, r.status_code)
with app.app_context():
    campaigns = Campaign.query.filter_by(merchant_id=1, type="re_engage").all()
check("re-engagement campaign exists", len(campaigns) >= 1, f"{len(campaigns)} campaigns")

# 14. Scan endpoint resolves token -> balance
with_merchant_session()
r = c.get(f"/scan/{card.qr_token}")
check("scan returns found", r.status_code == 200, r.status_code)
payload = json_module.loads(r.data)
check("scan payload has balance", payload.get("points_balance") == 4, payload)
check("scan payload has card number", payload.get("card_number") == card.card_number,
      payload)

# 15. Scan with unknown token -> 404
with_merchant_session()
r = c.get("/scan/00" * 32)
check("scan unknown token 404", r.status_code == 404, r.status_code)

# 16. Settings save
with_merchant_session()
r = c.post("/settings", data={"shop_name": "The Daily Grind",
                              "points_per_purchase": "2",
                              "redemption_value": "20"},
           follow_redirects=True)
check("settings save", r.status_code == 200, r.status_code)
with app.app_context():
    check("settings persisted", ShopSetting.get("shop_name") == "The Daily Grind",
          ShopSetting.get("shop_name"))

# 17. Card number is NOT the QR payload (anti-clone)
check("qr payload hides card number", card.qr_payload != card.card_number,
      f"{card.qr_payload} vs {card.card_number}")

# 18. Customer portal loads (security: card belongs to merchant)
with_merchant_session()
r = c.get(f"/c/{card.id}")
check("customer portal 200", r.status_code == 200, r.status_code)

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("ALL CHECKS PASSED")
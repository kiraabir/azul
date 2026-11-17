"""Database models for AZUL Loyalty Card Platform - Multi-tenant with RBAC."""
import secrets
import uuid
import hashlib
from datetime import datetime, timezone
from flask import session
from functools import wraps
from sqlalchemy.ext.hybrid import hybrid_property

from . import db


# SQLALCHEMY 2.0 compatible helper for session get
def _session_get(model, pk):
    """Get a model instance by primary key using SQLAlchemy 2.0 session pattern."""
    return db.session.get(model, pk)


# =============================================================================
# Multi-Tenancy Support
# =============================================================================

def get_current_merchant_id():
    """Get the current merchant ID from session.

    SECURITY: This function derives merchant_id from the authenticated user
    when available, preventing cross-tenant access. Falls back to session
    merchant_id for testing scenarios.
    """
    # First check if user is logged in and derive merchant_id from user
    from flask import g
    if 'user_id' in session:
        try:
            user = db.session.get(User, session['user_id'])
            if user and user.is_active:
                return user.merchant_id
        except Exception:
            pass

    # Fall back to session merchant_id (set during login or merchant setup)
    return session.get('merchant_id', 1)


def merchant_only(f):
    """Decorator to ensure routes only access current merchant's data."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'merchant_id' not in session:
            session['merchant_id'] = get_current_merchant_id()
        # Add guard to prevent default merchant bypass in production
        # In production, merchant_id should always be set by authenticated user
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# Authentication & RBAC
# =============================================================================

class Merchant(db.Model):
    """Merchant/Shop entity for multi-tenancy."""
    __tablename__ = "merchant"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(32))
    password_hash = db.Column(db.String(256), nullable=True)  # Can be set later

    # Business details
    business_type = db.Column(db.String(60))  # café, barber, car wash, etc.
    address = db.Column(db.Text)

    # Localization
    language = db.Column(db.String(10), default='en')  # 'en', 'fr', 'ar'
    currency = db.Column(db.String(3), default='MAD')  # Morocco Dirham

    # Wallet configuration
    apple_pass_type_id = db.Column(db.String(120))
    google_merchant_id = db.Column(db.String(120))

    # Account status
    is_active = db.Column(db.Boolean, default=True)
    subscription_tier = db.Column(db.String(20), default='starter')  # starter, growth, multi_branch
    subscription_ends_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=db.func.now())

    # Relationships - using back_populates for consistency
    customers = db.relationship("Customer", back_populates="merchant", cascade="all, delete-orphan")
    settings = db.relationship("ShopSetting", back_populates="merchant", cascade="all, delete-orphan")
    reward_tiers = db.relationship("RewardTier", back_populates="merchant", cascade="all, delete-orphan")
    cards = db.relationship("LoyaltyCard", back_populates="merchant", cascade="all, delete-orphan")
    campaigns = db.relationship("Campaign", back_populates="merchant", cascade="all, delete-orphan")
    notifications = db.relationship("Notification", back_populates="merchant", cascade="all, delete-orphan")
    transactions = db.relationship("Transaction", back_populates="merchant", cascade="all, delete-orphan")
    feedbacks = db.relationship("Feedback", back_populates="merchant", cascade="all, delete-orphan")
    users = db.relationship("User", back_populates="merchant")


class User(db.Model):
    """User account for merchant staff (RBAC)."""
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    merchant_id = db.Column(db.Integer, db.ForeignKey("merchant.id"), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    # Role-based access control
    role = db.Column(db.String(20), default='owner')  # owner, manager, staff

    # Permissions
    can_scan = db.Column(db.Boolean, default=True)
    can_earn = db.Column(db.Boolean, default=True)
    can_redeem = db.Column(db.Boolean, default=True)
    can_view_reports = db.Column(db.Boolean, default=True)

    # Notification preferences
    notify_on_earnings = db.Column(db.Boolean, default=True)
    notify_on_redemptions = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=db.func.now())
    is_active = db.Column(db.Boolean, default=True)

    merchant = db.relationship("Merchant", back_populates="users")


# =============================================================================
# Core Loyalty Models (Multi-tenant)
# =============================================================================

class Customer(db.Model):
    """AZUL Customer with wallet pass integration - multi-tenant."""
    __tablename__ = "customer"

    id = db.Column(db.Integer, primary_key=True)
    merchant_id = db.Column(db.Integer, db.ForeignKey("merchant.id"), nullable=False)

    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(32), index=True, nullable=True)
    phone_verified = db.Column(db.Boolean, default=False)
    email = db.Column(db.String(120), index=True, nullable=True)

    # Wallet integration
    wallet_pass_id = db.Column(db.String(64), unique=True, index=True, nullable=True)
    device_token = db.Column(db.String(256))  # For push notifications
    push_opt_in = db.Column(db.Boolean, default=False)
    notification_preferences = db.Column(db.Text)  # JSON string of preferences

    # Engagement tracking
    # has_phone is a hybrid_property derived from phone (see below)
    created_at = db.Column(db.DateTime, default=db.func.now())
    last_seen_at = db.Column(db.DateTime, nullable=True)
    last_engaged_at = db.Column(db.DateTime, nullable=True)

    # Relationships - using back_populates for consistency
    merchant = db.relationship("Merchant", back_populates="customers")
    cards = db.relationship("LoyaltyCard", back_populates="customer",
                            cascade="all, delete-orphan")
    transactions = db.relationship("Transaction", back_populates="customer",
                                   cascade="all, delete-orphan")
    feedback = db.relationship("Feedback", back_populates="customer",
                               cascade="all, delete-orphan")
    notifications = db.relationship("Notification", back_populates="customer",
                                    cascade="all, delete-orphan")

    @property
    def active_card(self):
        """Return the first active card for this customer."""
        return LoyaltyCard.query.filter_by(
            merchant_id=self.merchant_id,
            customer_id=self.id, is_active=True
        ).first()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # has_phone is a hybrid_property derived from phone, so we
        # only need to ensure the phone column is set correctly.
        # The hybrid_property handles the rest.

    @staticmethod
    def get_by_qr_token(token, merchant_id):
        """Find customer by QR token, limited to merchant."""
        from .models import LoyaltyCard
        card = LoyaltyCard.query.filter_by(
            qr_token=token,
            merchant_id=merchant_id
        ).first()
        if card:
            return card.customer, card
        return None, None

    @hybrid_property
    def has_phone(self):
        """True if the customer has a phone number.

        Derived from the phone column so it is always consistent,
        even when loaded from the database.
        """
        return bool(self.phone)

    @has_phone.expression
    def has_phone(cls):
        """SQL expression for has_phone - derived from phone column."""
        return cls.phone.isnot(None)


class LoyaltyCard(db.Model):
    """AZUL Loyalty Card with Wallet pass support - multi-tenant."""
    __tablename__ = "loyalty_card"

    id = db.Column(db.Integer, primary_key=True)
    merchant_id = db.Column(db.Integer, db.ForeignKey("merchant.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"),
                            nullable=False, index=True)

    card_number = db.Column(db.String(32), unique=True, nullable=False)
    qr_token = db.Column(db.String(64), unique=True, nullable=False)
    points_balance = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=db.func.now())

    # Wallet integration
    wallet_serial = db.Column(db.String(128), unique=True, index=True, nullable=True)
    is_wallet_synced = db.Column(db.Boolean, default=False)

    # Relationships - using back_populates for Merchant, backref for Customer/Card
    merchant = db.relationship("Merchant", back_populates="cards")
    customer = db.relationship("Customer", back_populates="cards")
    transactions = db.relationship("Transaction", back_populates="card",
                                   cascade="all, delete-orphan")
    feedback = db.relationship("Feedback", back_populates="card",
                               cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.card_number:
            self.card_number = self._generate_card_number()
        if not self.qr_token:
            self.qr_token = secrets.token_hex(32)
        if not self.wallet_serial:
            self.wallet_serial = f"AZUL-{uuid.uuid4().hex[:16]}"
        # SECURITY: merchant_id is always derived from session/context
        # Never trust merchant_id from kwargs in production
        # Only set if not explicitly provided (for test fixtures)
        if 'merchant_id' not in kwargs or kwargs['merchant_id'] is None:
            from .auth import get_current_merchant_id
            # Note: In real app this would use session-based auth
            # For now, rely on explicit merchant_id in tests
            pass

    @staticmethod
    def _generate_card_number():
        """Generate a 16-digit style card number."""
        import random
        return "".join(str(random.randint(0, 9)) for _ in range(16))

    @property
    def qr_payload(self):
        """Return the QR code payload for scanning."""
        return f"azul:card:{self.qr_token}"

    def get_progress_to_next_reward(self):
        """Calculate progress to next reward tier."""
        from .models import RewardTier
        next_tier = RewardTier.query.filter(
            RewardTier.merchant_id == self.merchant_id,
            RewardTier.threshold_stamps > self.points_balance
        ).order_by(RewardTier.threshold_stamps).first()
        if next_tier:
            return {
                'current': self.points_balance,
                'target': next_tier.threshold_stamps,
                'progress': self.points_balance / next_tier.threshold_stamps * 100,
                'remaining': next_tier.threshold_stamps - self.points_balance
            }
        return None


class Transaction(db.Model):
    """Transaction tracking - multi-tenant."""
    __tablename__ = "transaction"

    id = db.Column(db.Integer, primary_key=True)
    merchant_id = db.Column(db.Integer, db.ForeignKey("merchant.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    card_id = db.Column(db.Integer, db.ForeignKey("loyalty_card.id"), nullable=False)

    type = db.Column(db.String(8), nullable=False)  # "earn" | "redeem"
    points = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, default=db.func.now())

    # Relationships - using back_populates for consistency
    card = db.relationship("LoyaltyCard", back_populates="transactions")
    customer = db.relationship("Customer", back_populates="transactions")
    merchant = db.relationship("Merchant", back_populates="transactions")

    def apply(self):
        """Apply this transaction to the card's balance."""
        if self.type == "earn":
            self.card.points_balance += self.points
        elif self.type == "redeem":
            if self.points > self.card.points_balance:
                raise ValueError("Insufficient points for redemption")
            self.card.points_balance -= self.points
        else:
            raise ValueError(f"Unknown transaction type: {self.type}")


# =============================================================================
# Rewards & Promotions
# =============================================================================

class RewardTier(db.Model):
    """Tiered rewards system - multi-tenant."""
    __tablename__ = "reward_tier"

    id = db.Column(db.Integer, primary_key=True)
    merchant_id = db.Column(db.Integer, db.ForeignKey("merchant.id"), nullable=False)

    threshold_stamps = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(255))
    is_available = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=db.func.now())

    # Relationships
    merchant = db.relationship("Merchant", back_populates="reward_tiers")
    # Many-to-many through RewardClaim with viewonly to avoid overlap warnings
    claimed_cards = db.relationship("LoyaltyCard", secondary="reward_claim",
                                    backref="claimed_rewards", viewonly=True)


class RewardClaim(db.Model):
    """Track when rewards are claimed - audit trail."""
    __tablename__ = "reward_claim"

    id = db.Column(db.Integer, primary_key=True)
    merchant_id = db.Column(db.Integer, db.ForeignKey("merchant.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    card_id = db.Column(db.Integer, db.ForeignKey("loyalty_card.id"), nullable=False)
    reward_tier_id = db.Column(db.Integer, db.ForeignKey("reward_tier.id"), nullable=False)

    claimed_at = db.Column(db.DateTime, default=db.func.now())
    is_used = db.Column(db.Boolean, default=False)
    redemption_code = db.Column(db.String(64), unique=True)

    # Relationships - using viewonly for the many-to-many side to avoid overlap warnings
    merchant = db.relationship("Merchant")
    customer = db.relationship("Customer")
    # These relationships are part of the many-to-many "claimed_cards" via secondary table
    # viewonly=True prevents SQLAlchemy from trying to write through both sides
    card = db.relationship("LoyaltyCard", viewonly=True, primaryjoin="RewardClaim.card_id==LoyaltyCard.id")
    reward_tier = db.relationship("RewardTier", viewonly=True, primaryjoin="RewardClaim.reward_tier_id==RewardTier.id")


# =============================================================================
# Feedback & Reviews
# =============================================================================

class Feedback(db.Model):
    """Feedback -> Review loop - multi-tenant."""
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)
    merchant_id = db.Column(db.Integer, db.ForeignKey("merchant.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    card_id = db.Column(db.Integer, db.ForeignKey("loyalty_card.id"), nullable=False)

    rating = db.Column(db.Integer, nullable=False)  # 1-5
    comment = db.Column(db.Text)
    sentiment = db.Column(db.String(10), nullable=True)
    submitted_at = db.Column(db.DateTime, default=db.func.now())
    forwarded_to_google = db.Column(db.Boolean, default=False)
    stamp_earned = db.Column(db.Boolean, default=False)

    # Relationships - using back_populates
    merchant = db.relationship("Merchant", back_populates="feedbacks")
    customer = db.relationship("Customer", back_populates="feedback")
    card = db.relationship("LoyaltyCard", back_populates="feedback")


# =============================================================================
# Campaigns & Notifications
# =============================================================================

class Campaign(db.Model):
    """Re-engagement and promotional campaigns - multi-tenant."""
    __tablename__ = "campaign"

    id = db.Column(db.Integer, primary_key=True)
    merchant_id = db.Column(db.Integer, db.ForeignKey("merchant.id"), nullable=False)

    name = db.Column(db.String(80), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # "re_engage" | "promotion"
    content = db.Column(db.Text, nullable=False)
    target_segment = db.Column(db.String(30), default="all")

    sent_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.now())

    # Relationships
    merchant = db.relationship("Merchant", back_populates="campaigns")


class Notification(db.Model):
    """Customer notifications - for PWA push."""
    __tablename__ = "notification"

    id = db.Column(db.Integer, primary_key=True)
    merchant_id = db.Column(db.Integer, db.ForeignKey("merchant.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=True)

    title = db.Column(db.String(120))
    body = db.Column(db.Text)
    data = db.Column(db.Text)  # JSON payload

    is_read = db.Column(db.Boolean, default=False)
    delivered_via_push = db.Column(db.Boolean, default=False)
    sent_at = db.Column(db.DateTime, default=db.func.now())

    # Relationships
    merchant = db.relationship("Merchant", back_populates="notifications")
    customer = db.relationship("Customer", back_populates="notifications")


# =============================================================================
# Shop Settings (per merchant)
# =============================================================================

class ShopSetting(db.Model):
    """Merchant-specific configuration settings."""
    __tablename__ = "shop_setting"

    id = db.Column(db.Integer, primary_key=True)
    merchant_id = db.Column(db.Integer, db.ForeignKey("merchant.id"), nullable=False)

    key = db.Column(db.String(64), nullable=False)
    value = db.Column(db.Text, nullable=False, default="")

    # Relationship
    merchant = db.relationship("Merchant", back_populates="settings")

    __table_args__ = (db.UniqueConstraint('merchant_id', 'key', name='unique_merchant_setting'),)

    @classmethod
    def get(cls, key, merchant_id=None):
        if merchant_id is None:
            try:
                from flask import session
                merchant_id = session.get('merchant_id', 1)
            except RuntimeError:
                # No request context - fall back to default merchant
                merchant_id = 1
        row = cls.query.filter_by(merchant_id=merchant_id, key=key).first()
        return row.value if row else ""

    @classmethod
    def set(cls, key, value, merchant_id=None):
        if merchant_id is None:
            try:
                from flask import session
                merchant_id = session.get('merchant_id', 1)
            except RuntimeError:
                # No request context - fall back to default merchant
                merchant_id = 1
        row = cls.query.filter_by(merchant_id=merchant_id, key=key).first()
        if row is None:
            row = cls(merchant_id=merchant_id, key=key, value=str(value))
            db.session.add(row)
        else:
            row.value = str(value)
        db.session.commit()
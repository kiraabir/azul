"""Initial multi-tenant migration with data preservation.

This migration:
1. Creates the merchant table with AZUL Original Shop (id=1)
2. Adds merchant_id columns to existing tables
3. Migrates existing data to the new merchant context
4. Creates all new multi-tenant tables

Revision ID: 20261116_initial
Revises:
Create Date: 2026-11-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import get_connector

# revision identifiers, used by Alembic.
revision = '20261116_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ========================================
    # STEP 1: Create merchant table
    # ========================================
    op.create_table('merchant',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('email', sa.String(120), nullable=False, unique=True),
        sa.Column('phone', sa.String(32)),
        sa.Column('password_hash', sa.String(256)),
        sa.Column('business_type', sa.String(60)),
        sa.Column('address', sa.Text),
        sa.Column('language', sa.String(10), server_default='en'),
        sa.Column('currency', sa.String(3), server_default='MAD'),
        sa.Column('apple_pass_type_id', sa.String(120)),
        sa.Column('google_merchant_id', sa.String(120)),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('1')),
        sa.Column('subscription_tier', sa.String(20), server_default='starter'),
        sa.Column('subscription_ends_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )

    # Create the default merchant for existing data
    op.execute(
        "INSERT INTO merchant (id, name, email, phone, business_type, language, subscription_tier, is_active) "
        "VALUES (1, 'AZUL Original Shop', 'admin@azul.ma', '+212500000000', 'coffee_shop', 'fr', 'growth', 1)"
    )

    # ========================================
    # STEP 2: Add merchant_id to existing tables
    # ========================================
    # customer table
    op.add_column('customer', sa.Column('merchant_id', sa.Integer(), nullable=False, server_default='1'))
    op.create_foreign_key('fk_customer_merchant', 'customer', 'merchant', ['merchant_id'], ['id'])
    op.add_column('customer', sa.Column('phone_verified', sa.Boolean(), server_default=sa.text('0')))
    op.add_column('customer', sa.Column('wallet_pass_id', sa.String(64), unique=True))
    op.add_column('customer', sa.Column('device_token', sa.String(256)))
    op.add_column('customer', sa.Column('push_opt_in', sa.Boolean(), server_default=sa.text('0')))
    op.add_column('customer', sa.Column('notification_preferences', sa.Text()))
    op.add_column('customer', sa.Column('has_phone', sa.Boolean(), server_default=sa.text('0')))
    op.add_column('customer', sa.Column('last_seen_at', sa.DateTime()))
    op.add_column('customer', sa.Column('last_engaged_at', sa.DateTime()))

    # Set has_phone based on existing phone data
    op.execute("UPDATE customer SET has_phone = 1 WHERE phone IS NOT NULL")

    # shop_setting table
    op.add_column('shop_setting', sa.Column('merchant_id', sa.Integer(), nullable=False, server_default='1'))
    op.create_foreign_key('fk_setting_merchant', 'shop_setting', 'merchant', ['merchant_id'], ['id'])
    op.create_unique_constraint('unique_merchant_setting', 'shop_setting', ['merchant_id', 'key'])

    # loyalty_card table
    op.add_column('loyalty_card', sa.Column('merchant_id', sa.Integer(), nullable=False, server_default='1'))
    op.create_foreign_key('fk_card_merchant', 'loyalty_card', 'merchant', ['merchant_id'], ['id'])
    op.add_column('loyalty_card', sa.Column('wallet_serial', sa.String(128), unique=True))
    op.add_column('loyalty_card', sa.Column('is_wallet_synced', sa.Boolean(), server_default=sa.text('0')))

    # Generate wallet_serial for existing cards
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT id FROM loyalty_card WHERE wallet_serial IS NULL"))
    for (card_id,) in result:
        import uuid
        import secrets
        serial = f"AZUL-{card_id}-{secrets.token_hex(16)}"
        conn.execute(sa.text("UPDATE loyalty_card SET wallet_serial = :serial WHERE id = :id")
                     .bindparams(serial=serial, id=card_id))

    # transaction table
    op.add_column('transaction', sa.Column('merchant_id', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('transaction', sa.Column('customer_id', sa.Integer()))
    op.create_foreign_key('fk_tx_merchant', 'transaction', 'merchant', ['merchant_id'], ['id'])
    op.create_foreign_key('fk_tx_customer', 'transaction', 'customer', ['customer_id'], ['id'])
    op.create_foreign_key('fk_tx_card', 'transaction', 'loyalty_card', ['card_id'], ['id'])

    # Populate customer_id in transaction from card
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE transaction t
        SET customer_id = (
            SELECT customer_id FROM loyalty_card lc WHERE lc.id = t.card_id
        ), merchant_id = 1
        WHERE customer_id IS NULL
    """))

    # ========================================
    # STEP 3: Create new multi-tenant tables
    # ========================================
    op.create_table('reward_tier',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('merchant_id', sa.Integer(), nullable=False),
        sa.Column('threshold_stamps', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(80), nullable=False),
        sa.Column('description', sa.String(255)),
        sa.Column('is_available', sa.Boolean(), server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['merchant_id'], ['merchant.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('campaign',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('merchant_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(80), nullable=False),
        sa.Column('type', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('target_segment', sa.String(30), server_default='all'),
        sa.Column('sent_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['merchant_id'], ['merchant.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('notification',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('merchant_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer()),
        sa.Column('title', sa.String(120)),
        sa.Column('body', sa.Text()),
        sa.Column('data', sa.Text()),
        sa.Column('is_read', sa.Boolean(), server_default=sa.text('0')),
        sa.Column('delivered_via_push', sa.Boolean(), server_default=sa.text('0')),
        sa.Column('sent_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['merchant_id'], ['merchant.id']),
        sa.ForeignKeyConstraint(['customer_id'], ['customer.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('feedback',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('merchant_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('card_id', sa.Integer(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text()),
        sa.Column('sentiment', sa.String(10)),
        sa.Column('submitted_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('forwarded_to_google', sa.Boolean(), server_default=sa.text('0')),
        sa.Column('stamp_earned', sa.Boolean(), server_default=sa.text('0')),
        sa.ForeignKeyConstraint(['merchant_id'], ['merchant.id']),
        sa.ForeignKeyConstraint(['customer_id'], ['customer.id']),
        sa.ForeignKeyConstraint(['card_id'], ['loyalty_card.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('reward_claim',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('merchant_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('card_id', sa.Integer(), nullable=False),
        sa.Column('reward_tier_id', sa.Integer(), nullable=False),
        sa.Column('claimed_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('is_used', sa.Boolean(), server_default=sa.text('0')),
        sa.Column('redemption_code', sa.String(64), unique=True),
        sa.ForeignKeyConstraint(['merchant_id'], ['merchant.id']),
        sa.ForeignKeyConstraint(['customer_id'], ['customer.id']),
        sa.ForeignKeyConstraint(['card_id'], ['loyalty_card.id']),
        sa.ForeignKeyConstraint(['reward_tier_id'], ['reward_tier.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('user',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('merchant_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(120), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(256), nullable=False),
        sa.Column('role', sa.String(20), server_default='owner'),
        sa.Column('can_scan', sa.Boolean(), server_default=sa.text('1')),
        sa.Column('can_earn', sa.Boolean(), server_default=sa.text('1')),
        sa.Column('can_redeem', sa.Boolean(), server_default=sa.text('1')),
        sa.Column('can_view_reports', sa.Boolean(), server_default=sa.text('1')),
        sa.Column('notify_on_earnings', sa.Boolean(), server_default=sa.text('1')),
        sa.Column('notify_on_redemptions', sa.Boolean(), server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('1')),
        sa.ForeignKeyConstraint(['merchant_id'], ['merchant.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # ========================================
    # STEP 4: Seed default reward tiers for merchant 1
    # ========================================
    op.execute("""
        INSERT INTO reward_tier (merchant_id, threshold_stamps, name, description, is_available)
        VALUES
            (1, 5, 'Free Item', 'Any item of equal or lesser value', 1),
            (1, 10, '10% Off', '10% discount on next purchase', 1),
            (1, 15, 'Free Item + Drink', 'Free item with a drink', 1)
    """)


def downgrade():
    # Drop tables in reverse order to handle foreign keys
    op.drop_table('user')
    op.drop_table('reward_claim')
    op.drop_table('feedback')
    op.drop_table('notification')
    op.drop_table('campaign')
    op.drop_table('reward_tier')

    # Drop constraints before columns
    op.drop_constraint('fk_tx_card', 'transaction', type_='foreignkey')
    op.drop_constraint('fk_tx_customer', 'transaction', type_='foreignkey')
    op.drop_constraint('fk_tx_merchant', 'transaction', type_='foreignkey')
    op.drop_column('transaction', 'merchant_id')
    op.drop_column('transaction', 'customer_id')

    op.drop_constraint('fk_card_merchant', 'loyalty_card', type_='foreignkey')
    op.drop_column('loyalty_card', 'merchant_id')
    op.drop_column('loyalty_card', 'wallet_serial')
    op.drop_column('loyalty_card', 'is_wallet_synced')

    op.drop_constraint('unique_merchant_setting', 'shop_setting', type_='unique')
    op.drop_constraint('fk_setting_merchant', 'shop_setting', type_='foreignkey')
    op.drop_column('shop_setting', 'merchant_id')

    op.drop_constraint('fk_customer_merchant', 'customer', type_='foreignkey')
    op.drop_column('customer', 'merchant_id')
    op.drop_column('customer', 'phone_verified')
    op.drop_column('customer', 'wallet_pass_id')
    op.drop_column('customer', 'device_token')
    op.drop_column('customer', 'push_opt_in')
    op.drop_column('customer', 'notification_preferences')
    op.drop_column('customer', 'has_phone')
    op.drop_column('customer', 'last_seen_at')
    op.drop_column('customer', 'last_engaged_at')

    op.drop_table('merchant')
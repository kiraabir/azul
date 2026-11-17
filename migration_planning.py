#!/usr/bin/env python
"""
Migration Planning Script for AZUL Production Database
Read-only analysis - does NOT modify instance/tappy.db
"""
import sys
import os
import sqlite3

PROJECT_DIR = r"C:\Users\abdo oubir\apology-website"

# Read production schema
PROD_DB = os.path.join(PROJECT_DIR, "instance", "tappy.db")

# Read existing data
print("=" * 60)
print("EXISTING PRODUCTION DATABASE ANALYSIS")
print("=" * 60)

con = sqlite3.connect(PROD_DB)
cur = con.cursor()

# Get all tables and columns
print("\n[1] EXISTING TABLES AND COLUMNS:")
print("-" * 40)
tables = [row[0] for row in cur.execute("select name from sqlite_master where type='table'")]
for t in sorted(tables):
    cols = cur.execute(f'pragma table_info("{t}")').fetchall()
    col_names = [c[1] for c in cols]
    print(f"\n{t}:")
    print(f"  Columns: {col_names}")

# Get sample data
print("\n\n[2] EXISTING DATA SAMPLE:")
print("-" * 40)

print("\n--- customer ---")
for row in cur.execute("select * from customer"):
    print(f"  {row}")

print("\n--- loyalty_card ---")
for row in cur.execute("select * from loyalty_card"):
    print(f"  {row}")

print("\n--- shop_setting ---")
for row in cur.execute("select * from shop_setting"):
    print(f"  {row}")

print("\n--- transaction ---")
for row in cur.execute("select * from \"transaction\""):
    print(f"  {row}")

con.close()

# Compare with model schemas
print("\n\n" + "=" * 60)
print("MODEL SCHEMA COMPARISON")
print("=" * 60)

sys.path.insert(0, PROJECT_DIR)
from client import db
from client.models import (
    Merchant, Customer, LoyaltyCard, Transaction,
    ShopSetting, RewardTier, Campaign, Notification, User, Feedback, RewardClaim
)

def get_model_columns(model):
    """Get column names from a SQLAlchemy model."""
    return [c.name for c in model.__table__.columns]

def get_model_primary_key(model):
    """Get primary key column(s) from a SQLAlchemy model."""
    return [c.name for c in model.__table__.primary_key.columns]

print("\n[3] TABLES IN MODELS (NEW SCHEMA):")
print("-" * 40)

model_tables = {
    'merchant': Merchant,
    'customer': Customer,
    'loyalty_card': LoyaltyCard,
    'transaction': Transaction,
    'shop_setting': ShopSetting,
    'reward_tier': RewardTier,
    'campaign': Campaign,
    'notification': Notification,
    'feedback': Feedback,
    'reward_claim': RewardClaim,
    'user': User,
}

for name, model in model_tables.items():
    cols = get_model_columns(model)
    pk = get_model_primary_key(model)
    print(f"\n{name}:")
    print(f"  PK: {pk}")
    print(f"  Columns: {cols}")

# Show migration differences
print("\n\n" + "=" * 60)
print("MIGRATION DIFF ANALYSIS")
print("=" * 60)

existing_tables = {'customer', 'loyalty_card', 'shop_setting', 'transaction'}
model_table_names = set(model_tables.keys())

print("\n[4] TABLES TO BE ADDED (need migration):")
print("-" * 40)
for t in sorted(model_table_names - existing_tables):
    print(f"  - {t}")

print("\n[5] TABLES EXIST BUT SCHEMA DIFFERS:")
print("-" * 40)
for t in existing_tables:
    print(f"\n  {t}:")
    # Get existing columns
    con = sqlite3.connect(PROD_DB)
    cur_ex = con.cursor()
    existing_cols = set([c[1] for c in cur_ex.execute(f'pragma table_info("{t}")').fetchall()])
    con.close()

    model_cols = set(get_model_columns(model_tables[t]))

    missing = model_cols - existing_cols
    extra = existing_cols - model_cols

    if missing:
        print(f"    NEEDS COLUMN: {sorted(missing)}")
    if extra:
        print(f"    EXTRA COLUMN: {sorted(extra)}")

print("\n[6] FOREIGN KEY RELATIONSHIPS (new schema):")
print("-" * 40)
for name in ['customer', 'loyalty_card', 'transaction', 'shop_setting',
             'reward_tier', 'campaign', 'notification', 'feedback', 'reward_claim', 'user']:
    model = model_tables[name]
    fks = [c.name for c in model.__table__.columns
           if c.foreign_keys]
    if fks:
        print(f"  {name}: FK on {fks}")
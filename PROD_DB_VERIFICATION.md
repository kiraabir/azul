# AZUL Production Database Migration Plan

## Executive Summary

The production database (`instance/tappy.db`) uses an **older single-tenant schema** that predates the multi-tenant architecture. Migration requires careful handling to preserve existing data and establish proper multi-tenancy.

---

## 1. Current Production Database Schema

**Tables Present:** 4
- `customer` (5 columns)
- `loyalty_card` (7 columns)
- `shop_setting` (3 columns)
- `transaction` (6 columns)

**Data Records (read-only inspection):**

| Table | Row Count | Sample Data |
|-------|-----------|-------------|
| customer | 1 | Test Shop (id=1), 555-1234 |
| loyalty_card | 4 | 4 cards with various points balances |
| shop_setting | 3 | shop_name="Tappy", points_per_purchase="1", redemption_value="10" |
| transaction | 1 | id=3, 4 points earned |

**SHA-256:** `5341e9263f752e895125f818e7c8766697f80be17b1b87993a969da1f74140f2`
**MD5:** `72b8672c2a1f1ba2073623e4d05186bc`

---

## 2. Target Schema (Current SQLAlchemy Models)

**Tables to Create:** 11

| Table | Primary Key | Foreign Keys |
|-------|-------------|--------------|
| merchant | id | - |
| customer | id | merchant_id |
| loyalty_card | id | merchant_id, customer_id |
| transaction | id | merchant_id, customer_id, card_id |
| shop_setting | id | merchant_id |
| reward_tier | id | merchant_id |
| campaign | id | merchant_id |
| notification | id | merchant_id, customer_id |
| feedback | id | merchant_id, customer_id, card_id |
| reward_claim | id | merchant_id, customer_id, card_id, reward_tier_id |
| user | id | merchant_id |

---

## 3. Migration Requirements

### 3.1 Tables to Add
```sql
CREATE TABLE merchant (...);
CREATE TABLE reward_tier (...);
CREATE TABLE campaign (...);
CREATE TABLE notification (...);
CREATE TABLE feedback (...);
CREATE TABLE reward_claim (...);
CREATE TABLE "user" (...);
```

### 3.2 Columns to Add to Existing Tables

**customer:**
- `merchant_id` (INT NOT NULL, FK→merchant.id, DEFAULT=1)
- `phone_verified` (BOOLEAN, DEFAULT=0)
- `wallet_pass_id` (VARCHAR(64), UNIQUE)
- `device_token` (TEXT)
- `push_opt_in` (BOOLEAN, DEFAULT=0)
- `notification_preferences` (TEXT)
- `has_phone` (BOOLEAN, DEFAULT=0)
- `last_seen_at` (DATETIME)
- `last_engaged_at` (DATETIME)

**loyalty_card:**
- `merchant_id` (INT NOT NULL, FK→merchant.id, DEFAULT=1)
- `wallet_serial` (VARCHAR(128), UNIQUE)
- `is_wallet_synced` (BOOLEAN, DEFAULT=0)

**transaction:**
- `merchant_id` (INT NOT NULL, FK→merchant.id, DEFAULT=1)
- `customer_id` (INT, FK→customer.id)

**shop_setting:**
- `merchant_id` (INT NOT NULL, FK→merchant.id, DEFAULT=1)

---

## 4. Data Migration Plan

### 4.1 Merchant Assignment Strategy

**Decision Required:** Which merchant ID should own the existing data?

Current data analysis:
- "Test Shop" (customer id 1) appears to be the **customer** with name "Test Shop" and phone "555-1234"
- NOT a merchant record (merchant table doesn't exist)
- Has 4 associated loyalty cards
- 1 transaction (4 points earned)
- Settings from "Tappy" shop

**Recommendation:** Create a single merchant to own this existing data:

```sql
INSERT INTO merchant (id, name, email, phone, business_type, language, subscription_tier, is_active)
VALUES (1, 'Tappy Original Shop', 'admin@tappy.ma', '555-1234', 'unspecified', 'en', 'starter', 1);
```

### 4.2 Customer Data Migration

| Existing Column | Target Column | Transformation |
|-----------------|---------------|----------------|
| id | id | Preserve |
| name | name | Preserve ("Test Shop") |
| phone | phone | Preserve |
| email | email | Preserve (None → NULL) |
| created_at | created_at | Preserve |
| - | merchant_id | Set to 1 |
| - | has_phone | Derive from phone IS NOT NULL |
| - | phone_verified | Default to 0 |
| - | wallet_pass_id | NULL (generate later) |
| - | device_token | NULL |
| - | push_opt_in | 0 |
| - | last_seen_at | NULL |
| - | last_engaged_at | NULL |

**Note:** "Test Shop" is the customer NAME, not a merchant name. This is unusual data - verify with stakeholders.

**Potential Issue:** The existing "Test Shop" customer with phone "555-1234" and 4 loyalty cards suggests this might be test/demo data. Consider:
- Keeping as-is for existing customers
- OR archiving before migration
- OR manual verification required

### 4.3 Loyalty Card Data Migration

| Existing Column | Target Column | Transformation |
|-----------------|---------------|----------------|
| id | id | Preserve |
| customer_id | customer_id | Preserve |
| card_number | card_number | Preserve |
| qr_token | qr_token | Preserve |
| points_balance | points_balance | Preserve |
| is_active | is_active | Preserve |
| created_at | created_at | Preserve |
| - | merchant_id | Set to 1 |
| - | wallet_serial | Generate from existing pattern or new |
| - | is_wallet_synced | 0 |

### 4.4 Transaction Data Migration

| Existing Column | Target Column | Transformation |
|-----------------|---------------|----------------|
| id | id | Preserve |
| card_id | card_id | Preserve |
| type | type | Preserve |
| points | points | Preserve |
| description | description | Preserve |
| created_at | created_at | Preserve |
| - | merchant_id | Derive from card.merchant_id |
| - | customer_id | Derive from card.customer_id |

### 4.5 Shop Setting Data Migration

| Existing Key | Existing Value | Action |
|--------------|----------------|--------|
| shop_name | Tappy | Add new row with merchant_id=1 |
| points_per_purchase | 1 | Add new row with merchant_id=1 |
| redemption_value | 10 | Add new row with merchant_id=1 |

**Note:** New columns needed: `id`, `merchant_id`, `key`, `value`
- Preserve existing key/value pairs
- Add merchant_id = 1

---

## 5. Production Security Configuration

### 5.1 SECRET_KEY Requirement

**Current Issue:** `client/__init__.py` has a development fallback:
```python
app.config["SECRET_KEY"] = "dev-secret-change-me-in-production"
```

**Required Fix:** Fail in production if not set:
```python
app.config["SECRET_KEY"] = os.environ.get('SECRET_KEY')
if not app.config["SECRET_KEY"]:
    if app.config.get('TESTING'):
        app.config["SECRET_KEY"] = "test-secret-key"
    else:
        raise RuntimeError("SECRET_KEY environment variable must be set in production")
```

### 5.2 Session Security

Add to `client/__init__.py`:
```python
app.config["SESSION_COOKIE_SECURE"] = True  # HTTPS only
app.config["SESSION_COOKIE_HTTPONLY"] = True  # No JS access
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # CSRF protection
```

### 5.3 Environment Variables Checklist

```bash
# Required in production
export SECRET_KEY="your-256-bit-secret-key-here"
export FLASK_ENV="production"

# Optional
export DATABASE_URL="sqlite:///prod.db"  # or PostgreSQL URI
```

---

## 6. Step-by-Step Migration Procedure

### Step 1: Backup
```bash
# Create backup BEFORE any migration
cp instance/tappy.db instance/tappy.db.backup.$(date +%Y%m%d_%H%M%S)
sha256sum instance/tappy.db  # Record hash
```

### Step 2: Create Migration Script
Use Flask-Migrate/Alembic or execute raw SQL:

```python
# migration_script.py (RUN ONCE)
import os, sys, sqlite3
sys.path.insert(0, os.getcwd())

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/tappy.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Models defined inline to match current version...
```

### Step 3: Execute Migration
```bash
# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate  # Windows

# Run migration
python migration_script.py
```

### Step 4: Verify
```bash
# Verify counts
python -c "from client import db; from client.models import Merchant; print(Merchant.query.count())"
python prod_hash_check.py  # Verify hash changed appropriately
```

### Step 5: Test
```bash
# Run E2E tests against migrated DB
SECRET_KEY="test-key" python e2e_verification.py
```

---

## 7. Rollback Procedure

If migration fails:

```bash
# Stop any running Flask processes
# Restore from backup
rm instance/tappy.db
cp instance/tappy.db.backup.20261116_HHMMSS instance/tappy.db

# Verify
python -c "import sqlite3; print(sqlite3.connect('instance/tappy.db').execute('select count(*) from customer').fetchone())"
# Should show (1,) - original data restored
```

---

## 8. Post-Migration Verification Checklist

- [ ] All 4 original tables have `merchant_id` column
- [ ] All 7 new tables created successfully
- [ ] Customer "Test Shop" retained with merchant_id=1
- [ ] All 4 loyalty cards accessible under merchant 1
- [ ] All existing transactions preserved
- [ ] Shop settings migrated correctly
- [ ] Reward tiers seeded for merchant 1
- [ ] `app.run()` starts without errors
- [ ] All E2E tests pass

---

## 9. Risks and Mitigations

| Risk | Mitigation | Owner Approval Required |
|------|------------|------------------------|
| Data loss during migration | Full backup before migration | ✅ |
| Duplicate merchant_id conflicts | Use explicit merchant_id=1 | ✅ |
| Foreign key constraint violations | Add merchant_id after FK setup | ⚠️ |
| "Test Shop" naming confusion | Manual verification before migration | ✅ |
| Session signing breaks | Preserve SECRET_KEY or migrate users | ✅ |

---

## 10. Running E2E Verification

The E2E test script is always available at `e2e_verification.py`:

```bash
# From project root
python e2e_verification.py

# Or with explicit database path
SECRET_KEY=test-key python e2e_verification.py
```

This test:
- Creates an isolated test database (`tests_e2e_test.db`)
- NEVER modifies `instance/tappy.db`
- Tests all workflows and tenant isolation
- Reports detailed results

---

## AWAITING YOUR APPROVAL

Before executing:
1. **Review data ownership decision** - Should "Test Shop" become merchant 1?
2. **Confirm migration approach** - Raw SQL vs. Alembic
3. **Verify rollback procedure** - Backup location and naming
4. **Approve execution** - Type "PROCEED" to begin migration

**DO NOT EXECUTE** until you confirm:
- [ ] Data ownership assigned
- [ ] Backup strategy approved
- [ ] Migration script reviewed
- [ ] Rollback plan verified
- [ ] SECRET_KEY strategy confirmed
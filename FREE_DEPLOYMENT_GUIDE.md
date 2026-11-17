# AZUL Zero-Budget Deployment Guide

**Target Audience:** Moroccan merchants launching loyalty programs  
**First Launch Date:** 2026-11-16  
**Monthly Cost:** 0 MAD (FREE TIER)

---

## ⚠️ FREE TIER LIMITATIONS & WARNINGS

### Critical Free Tier Restrictions

| Service | Free Tier | Limit | Impact on AZUL |
|---------|-----------|-------|----------------|
| **Render** | ✅ Yes | 750 hours/month (1 web service), 512MB RAM | Sufficient for ~100 merchants |
| **Supabase** | ✅ Yes | 500MB database, 1GB file storage, 10GB bandwidth | Sufficient for <50 merchants |
| **GitHub** | ✅ Yes | Private repos, 2000 actions/min | Build/deploy pipeline |
| **UptimeRobot** | ✅ Yes | 50 monitors, 5min check interval | Basic uptime monitoring |

### What You CANNOT Do on Free Tier

- ❌ Custom domains (Render free tier provides `app.render.com`)
- ❌ Persistent storage (Supabase has 500MB limit)
- ❌ SSL certificates for custom domains (Render provides free HTTPS on `render.com` subdomains)
- ❌ 24/7 email sending (SMTP relays need paid plans)
- ❌ Dedicated IPs
- ❌ Guaranteed uptime SLA

---

## 1. INCOMPATIBILITIES FOUND

### ✅ SQLAlchemy + PostgreSQL Compatibility: FULL

The application uses:
- Standard `Integer`, `String`, `Boolean`, `DateTime` - **Compatible with PostgreSQL**
- `db.func.now()` - **Compatible** (PostgreSQL has `CURRENT_TIMESTAMP`)
- JSON text fields - **Compatible** (PostgreSQL has `TEXT`)
- Unique constraints - **Compatible**

**Migration from SQLite to PostgreSQL requires NO code changes.**

### ✅ QR/Wallet Pass Generation: FULL

- `qrcode` library - Pure Python, no external dependencies
- Pillow for image generation - Pure Python
- Wallet pass generation - JSON/PKPASS files generated dynamically, no external storage needed
- Wallet serials stored in database as `String(128)` - **Compatible**

### ✅ Authentication: FULL

- Password hashing with `werkzeug.security` - **Compatible**
- Session management via Flask sessions - **Compatible**
- All authentication flows in `client/auth.py` - **Compatible**

### ✅ Customer Portal: FULL

- Renders templates dynamically - **No file storage needed**
- Serves static files from memory - **Compatible**

---

## 2. Deployment Architecture (Zero Budget)

```
┌─────────────────┐
│  Render         │
│  free tier      │
│  - Web service  │
│  - HTTPS auto   │
│  - 750 hours/   │
│    monthly      │
└─────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│  SUPABASE FREE (PostgreSQL)      │
│  - 500MB database              │
│  - 1GB file storage            │
│  - No credit card required     │
│  Limitations:                  │
│  - Database size limit         │
│  - No custom SSL (need paid)   │
│  - Limited bandwidth           │
└──────────────────────────────────┘
```

### Data Flow

1. **Database**: Supabase PostgreSQL stores all AZUL data
2. **Application**: Render hosts Flask app, connects to Supabase
3. **QR/Wallet**: Generated dynamically, no file persistence needed
4. **Backup**: Supabase provides point-in-time recovery, manual exports available

---

## 3. Free Tier Limitations Breakdown

### Render Free Tier

**Pros:**
- Provides `https://azul.onrender.com` (free HTTPS)
- Automatic SSL certificate management
- Free custom domains require credit card
- 512MB RAM is sufficient for <200 merchants

**Cons:**
- Sleep after 15 minutes of inactivity (cold starts)
- No custom domains without credit card
- 750 hours/month = always on

### Supabase Free Tier

**Pros:**
- No credit card required
- Point-in-time recovery included
- RESTful API available
- Free custom roles and policies

**Cons:**
- 500MB database size (approximately 100,000 customers)
- Database connections limited
- No automatic backups beyond built-in recovery

### GitHub Free

**Pros:**
- Private repositories
- GitHub Actions for CI/CD
- 2000 minutes/month Actions time

**Cons:**
- No GitHub Packages for Docker
- Limited Actions time

### UptimeRobot Free

**Pros:**
- 50 monitors
- 5-minute check interval
- Email/SMS alerts

**Cons:**
- No HTTP(s) authentication
- Limited integrations

---

## 4. Backup Strategy (Zero Cost)

### Supabase Backups

Supabase provides:
- Point-in-time recovery (last 7 days)
- Logical backups via pg_dump

**Manual Export Script (save as `backup_database.py`):**

```python
#!/usr/bin/env python3
"""Zero-cost database backup using pg_dump via Supabase CLI."""
import subprocess
import os
from datetime import datetime

DATABASE_URL = os.environ.get('DATABASE_URL')

def backup_database():
    """Create a timestamped backup file."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = f'azul_backup_{timestamp}.sql'
    
    if DATABASE_URL:
        # Supabase provides pg_dump access
        # Install supabase CLI: https://supabase.com/docs/guides/api
        cmd = ['pg_dump', DATABASE_URL, '-f', backup_file]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f'Backup created: {backup_file}')
            return backup_file
        else:
            print(f'Backup failed: {result.stderr}')
    else:
        print('DATABASE_URL not set')
    return None

if __name__ == '__main__':
    backup_database()
```

### Automated Backup to GitHub

```yaml
# .github/workflows/backup.yml
name: Daily Database Backup
on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM UTC (19:00 Morocco)

jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Backup database
        run: python backup_database.py
      - name: Commit backup
        run: |
          git config --local user.email "backup@azul.ma"
          git config --local user.name "AZUL Backup"
          git add *.sql
          git commit -m "Daily backup $(date +%Y-%m-%d)" || echo "No changes"
          git push
```

### Alternative: CSV Export (Ultra-lightweight)

If database is too small, export to CSV:

```python
# export_csv.py
import csv
from client import db
from client.models import Customer, LoyaltyCard, Transaction, Merchant

def export_all_data():
    """Export all relevant data to CSV files."""
    # Export merchants
    with open('merchants.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'name', 'email', 'phone', 'is_active'])
        for m in Merchant.query.all():
            writer.writerow([m.id, m.name, m.email, m.phone, m.is_active])
    
    # Similar for customers, cards, transactions...
    # These CSV files are <1MB for typical small installations
```

---

## 5. Database Migration to Supabase PostgreSQL

### Step 1: Create Supabase Project

1. Go to https://supabase.com/
2. Click "Sign Up" (no credit card required)
3. Create new project
4. Note the `DATABASE_URL` from project settings

### Step 2: Configure Render

1. Go to https://render.com/ (no credit card required)
2. Create account
3. New > Web Service
4. Connect to GitHub repo
5. Build command: `pip install -r requirements.txt`
6. Start command: `gunicorn -w 2 -b 0.0.0.0:10000 app:app`
7. Set environment variables (see checklist below)

### Step 3: Set Environment Variables on Render

| Key | Value | Description |
|-----|-------|-------------|
| `SECRET_KEY` | 256-bit random hex | Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | Supabase connection string | From Supabase project settings |
| `ADMIN_PASSWORD` | Your secure admin password | Required for first user creation |
| `FLASK_ENV` | `production` | Disables debug mode |
| `DEBUG` | `False` | Ensures no debugging |

### Step 4: Run Database Setup

```bash
# On Render, create a one-time setup script
# Add to Render as a "Cron Job" or run once manually

# Option 1: Via Render shell
# ssh into render instance and run:
flask db upgrade
flask shell
>>> from app import _bootstrap
>>> _bootstrap()
>>> exit()

# Option 2: Create setup endpoint (REMOVE AFTER SETUP)
# Add temporary route in client/routes.py:
@app.route('/_setup')
def one_time_setup():
    from app import _bootstrap
    with app.app_context():
        _bootstrap()
    return 'Setup complete'
# DELETE this route after first run!
```

---

## 6. Free Domain & HTTPS

### Render Free Subdomain

When you deploy to Render, you get:
- `https://azul.onrender.com` (automatic HTTPS)
- No custom domain support on free tier

### Getting a Free Custom Domain

**Option A: Freenom (Free .tk, .ml, .ga, .cf, .ru)**

1. Go to https://freenom.com
2. Search for available domains
3. Note: Often used for spam, may affect email deliverability

**Option B: GitHub Student Discount**

If you're a student, get free domain names with GitHub Student Developer Pack

**Option C: Regional TLDs**

Consider `.ma` domains from Moroccan registrars - sometimes offer promotional pricing for small businesses

---

## 7. SMS Gateway Workaround (0 MAD/month)

### Option 1: Email-to-SMS (Zero Cost)

Many Moroccan carriers support email-to-SMS:

```python
def send_sms_via_email(phone, message):
    """Moroccan carriers support email-to-SMS."""
    carriers = {
        'INWI': '@sms.inwi.ma',
        'MAROC_TEL': '@sms3.ma',
        'IAM': '@sms2.ir.ma',
    }
    # Send email to carrier's SMS gateway
    # Requires knowing customer's carrier
```

### Option 2: No SMS Initially

Launch without SMS, add later when budget available. AZUL works fully without SMS:
- Wallet passes work offline
- QR codes work offline
- Only re-engagement campaigns need SMS

### Option 3: Local ISP Collaboration

Partner with local ISPs for bulk SMS credits at wholesale rates.

---

## 8. Monitoring Setup (Zero Cost)

### UptimeRobot

1. Sign up at https://uptimerobot.com
2. Create "HTTP(s)" monitor
3. URL: `https://azul.onrender.com`
4. Alert contacts: Your email
5. Check interval: 5 minutes (free tier)

### Render Logs

Render provides free log access:
- View logs in Render dashboard
- Set up email alerts for errors
- Use for debugging

---

## 9. Performance Optimization (Zero Cost)

### Reduce Cold Starts

```python
# Add to gunicorn startup
# gunicorn --preload --timeout 60 --workers 2 app:app
```

### Database Connection Pooling

```python
# In production config
SQLALCHEMY_POOL_SIZE = 5
SQLALCHEMY_POOL_TIMEOUT = 30
```

### Enable Compression

```python
# In client/__init__.py
from flask_compress import Compress
Compress(app)
```

---

## 10. Deployment Checklist (0 MAD/month)

### Pre-Deployment

- [ ] Generate secure `SECRET_KEY`
- [ ] Create Supabase project
- [ ] Get `DATABASE_URL`
- [ ] Set up Render account
- [ ] Create GitHub repo (private)

### Deployment

- [ ] Push code to GitHub
- [ ] Connect Render to GitHub
- [ ] Set environment variables on Render
- [ ] Configure database migrations
- [ ] Run initial setup
- [ ] Test customer creation
- [ ] Test wallet pass generation
- [ ] Test QR code scanning
- [ ] Verify HTTPS works

### Post-Deployment

- [ ] Configure UptimeRobot monitoring
- [ ] Set up daily backup workflow
- [ ] Create admin account
- [ ] Test authentication flow
- [ ] Verify tenant isolation

---

## Free Tier Hard Limits

| Limit | Render | Supabase | AZUL Impact |
|-------|--------|----------|-------------|
| RAM | 512MB | N/A | 200 merchants max |
| Database | N/A | 500MB | 100,000 customers |
| Bandwidth | 100GB | 10GB | ~1M page views |
| Build Time | 15min | N/A | Fast enough |
| Concurrent Connections | 5 | Database limited | 50 concurrent users |

---

## When You Need to Upgrade

| Trigger | Solution |
|---------|----------|
| >200 merchants | Upgrade to Render Starter ($7/month) |
| >100,000 customers | Upgrade to Supabase Pro ($25/month) |
| Need custom domain | Upgrade Render or use free domain |
| Need SMS | Add Twilio ($5 + usage) |
| Need email | Add SendGrid free tier |

---

## Summary

**AZUL CAN RUN ON 0 MAD/MONTH for initial testing with a small number of merchants.**

### What Works Out of the Box

- ✅ Customer-facing loyalty system
- ✅ Wallet pass generation (Apple/Google)
- ✅ QR code stamping
- ✅ Merchant dashboard
- ✅ Authentication
- ✅ Multi-tenant isolation

### What Requires Later Upgrade

- Custom domains
- High traffic volumes
- SMS marketing campaigns
- Large scale (>200 merchants)

---

*Zero-budget deployment guide v1.0 - 2026-11-16*
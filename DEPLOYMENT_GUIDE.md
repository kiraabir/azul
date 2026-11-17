# AZUL Production Deployment Guide

**Target Audience:** Moroccan merchants launching loyalty programs  
**First Launch Date:** 2026-11-16  
**Deployment Phase:** Preparation (DO NOT DEPLOY until approved)

---

## Table of Contents

1. Deployment Architecture
2. Recommended Hosting Options
3. Production Database Setup
4. Environment Variables Checklist
5. Domain and HTTPS Configuration
6. Static Files Configuration
7. Database Migration Procedure
8. Backup and Recovery Strategy
9. Logging and Monitoring
10. Rollback Procedure
11. Security Checklist

---

## 📋 Security Checklist

Before deployment, ensure:

- [ ] `.env` file created from `.env.production.example`
- [ ] `SECRET_KEY` is a secure 256-bit random value
- [ ] All API keys stored in environment variables (never in code)
- [ ] Database files outside web root
- [ ] HTTPS enforced with HSTS
- [ ] Debug mode disabled (`FLASK_ENV=production`)
- [ ] PostgreSQL recommended for production (SQLite has concurrency limits)

---

## Files to Remove Before Production

The following test database files should NOT be deployed:

```bash
rm -f test_azul.db tests_e2e_test.db instance/test_azul.db
# instance/tappy.db is the production database (keep as backup)
```

---

## 1. Production Deployment Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Counter Tags   │     │  Customers      │     │  Merchants      │
│  (NFC/QR)       │────▶│  (Apple/Google  │     │  (Dashboard)    │
│                 │     │   Wallet)       │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                │                         │
                                ▼                         ▼
                      ┌─────────────────────────────────────────┐
                      │           AZUL Production Server          │
                      │  ┌───────────────────────────────────┐  │
                      │  │  Nginx Reverse Proxy (443)        │  │
                      │  ├───────────────────────────────────┤  │
                      │  │  Gunicorn Worker Pool (4 workers) │  │
                      │  │  Flask Application (client)        │  │
                      │  ├───────────────────────────────────┤  │
                      │  │  SQLite / PostgreSQL Database    │  │
                      │  │  Redis (optional, rate limiting) │  │
                      │  │  Email/SMS Gateway API keys       │  │
                      │  └───────────────────────────────────┘  │
                      └─────────────────────────────────────────┘
                                │
                                ▼
                      ┌─────────────────────────────────────────┐
                      │        Storage & Services               │
                      │  • SQLite/PostgreSQL (database)       │
                      │  • AWS S3 / Cloudflare R2 (wallet pass │
                      │    certificate storage, logs)         │
                      │  • Twilio/Nexmo (SMS gateway)         │
                      │  • Google Cloud / Apple (wallet passes) │
                      └─────────────────────────────────────────┘
```

### Architecture Notes

- **Single Application Server**: AZUL is lightweight and can run on a single VPS
- **WebSocket Ready**: Application supports future PWA features
- **Mobile-First**: All flows optimized for mobile wallet integration
- **Morocco-Localed**: Timezone (Africa/Casablanca), currency (MAD), language (FR/AR/EN)

---

## 2. Recommended Hosting Options

### Option A: DigitalOcean (Recommended for Startups)

| Plan | Monthly Cost | Specs | Notes |
|------|--------------|-------|-------|
| Basic 2GB | $12 | 2 vCPU, 2GB RAM, 50GB SSD | Good for <50 merchants |
| Basic 4GB | $24 | 4 vCPU, 4GB RAM, 80GB SSD | Recommended for 50-200 merchants |
| Basic 8GB | $48 | 8 vCPU, 8GB RAM, 160GB SSD | Scale for 200+ merchants |

**Setup:** Ubuntu 22.04 LTS, Docker optional, deploy via Git

**Pros:**
- Simple pricing
- Morocco data center (AMS is EU, but has good connectivity)
- Excellent documentation

### Option B: AWS EC2

| Instance | Monthly Cost* | Specs | Notes |
|----------|---------------|-------|-------|
| t3.micro | ~$8 | 2 vCPU, 1GB RAM | Free tier eligible |
| t3.small | ~$16 | 2 vCPU, 2GB RAM | Minimum production |
| t3.medium | ~$32 | 2 vCPU, 4GB RAM | Recommended |

*Prices approximate, MENA region pricing may vary.

**Pros:**
- Most flexible scaling
- Can deploy in Cape Town (AF) region for better latency to Morocco
- Full AWS ecosystem integration

### Option C: OVHcloud (Local EU Provider)

| Plan | Monthly Cost | Specs | Notes |
|------|--------------|-------|-------|
| DEV-1-2 | €5 | 2 vCPU, 2GB RAM | Budget option |
| Starter-2 | €12 | 2 vCPU, 4GB RAM | Recommended |

**Pros:**
- Europe-based data centers
- Local provider familiar with Moroccan market
- Competitive pricing

### Storage Considerations

| Need | SQLite | PostgreSQL |
|------|--------|------------|
| <50 merchants | ✅ Sufficient | ✅ OK |
| 50-200 merchants | ⚠️ Risk of corruption | ✅ Recommended |
| >200 merchants | ❌ Not recommended | ✅ Required |

**Recommendation:** Start with SQLite, migrate to PostgreSQL before hitting 200 merchants.

---

## 3. Production Database Setup

### SQLite (Initial Deployment)

```bash
# Create data directory
mkdir -p /var/www/azul/data
chmod 700 /var/www/azul/data

# Copy existing seed data (if any)
cp instance/tappy.db /var/www/azul/data/production.db
chown www-data:www-data /var/www/azul/data/production.db

# Set permissions
chmod 600 /var/www/azul/data/production.db
```

### PostgreSQL (Recommended for Scale)

```bash
# 1. Install PostgreSQL
sudo apt-get install postgresql postgresql-contrib

# 2. Create database and user
sudo -u postgres psql -c "CREATE DATABASE azul_production;"
sudo -u postgres psql -c "CREATE USER azul_user WITH PASSWORD 'your-secure-password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE azul_production TO azul_user;"

# 3. Environment variable
export DATABASE_URL="postgresql://azul_user:your-secure-password@localhost:5432/azul_production"

# 4. Run migrations
flask db upgrade
```

---

## 4. Environment Variables Checklist

### Required (Production Must Set)

```bash
# SECURITY CRITICAL - 256-bit random secret
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
export SECRET_KEY="your-256-bit-secure-random-key-here"

# Admin password for initial setup
export ADMIN_PASSWORD="your-secure-admin-password"

# Production database
export DATABASE_URL="sqlite:///var/www/azul/data/production.db"
# or for PostgreSQL:
# export DATABASE_URL="postgresql://user:pass@localhost:5432/azul_production"

# Production environment flag
export FLASK_ENV="production"

# Debug mode MUST be False
export DEBUG="False"
```

### Optional

```bash
# Flask server
export FLASK_HOST="0.0.0.0"
export FLASK_PORT="5000"

# Worker processes
export GUNICORN_WORKERS="4"

# Timezone (Morocco uses WET/WEST)
export TZ="Africa/Casablanca"

# SMS Gateway (Twilio example)
export TWILIO_SID="your-twilio-sid"
export TWILIO_AUTH_TOKEN="your-twilio-token"
export TWILIO_PHONE="+212XXXXXXXX"

# Google Wallet
export GOOGLE_MERCHANT_ID="your-google-merchant-id"
export GOOGLE_API_KEY="your-google-api-key"

# Apple Wallet (PassKit)
export APPLE_PASS_TYPE_ID="pass.com.yourcompany.azul"
export APPLE_TEAM_ID="your-app-team-id"
export APPLE_KEY_ID="key-id"
export APPLE_PRIVATE_KEY="base64-encoded-p12-key"
```

### Verify Environment

```bash
# Create .env.production.example (DO NOT commit real values)
cat > .env.production.example << 'EOF'
# AZUL Production Environment Variables
# Copy to .env and fill in real values
# NEVER commit .env with real secrets

SECRET_KEY=your-256-bit-key-here
ADMIN_PASSWORD=initial-admin-password
DATABASE_URL=sqlite:///data/production.db
FLASK_ENV=production
DEBUG=False
EOF
```

---

## 5. Domain and HTTPS Configuration

### Domain Setup

1. **Register domain** (recommended: `.ma` for Moroccan merchants)
   - Example: `loyalty.morocco` or `wallet.azul.ma`
2. **DNS Records:**
   ```
   A record: loyalty.morocco -> YOUR_SERVER_IP
   CNAME: www.loyalty.morocco -> loyalty.morocco
   ```

### SSL/TLS with Let's Encrypt

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d loyalty.morocco -d www.loyalty.morocco

# Auto-renew test
sudo certbot renew --dry-run
```

### Nginx Configuration

```nginx
server {
    listen 80;
    server_name loyalty.morocco www.loyalty.morocco;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name loyalty.morocco www.loyalty.morocco;

    ssl_certificate /etc/letsencrypt/live/loyalty.morocco/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/loyalty.morocco/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    # Static files
    location /static/ {
        alias /var/www/azul/client/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Application
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Apple Wallet pass MIME type
    types {
        application/vnd.apple.pkpass pkpass;
    }
}
```

---

## 6. Static Files and Asset Configuration

### Assets Directory Structure

```
client/
├── static/
│   ├── css/
│   ├── js/
│   ├── img/
│   └── favicon.ico
├── templates/
│   └── (HTML templates)
└── qr.py (generates QR codes dynamically)
```

### Production Static Settings

```python
# In production, set these in the app config

# Flask static file configuration
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # 1 year for assets

# Cache busting for templates
from flask import Flask
app = Flask(__name__, static_url_path='/static', static_folder='static')

# For wallet pass images
WALLET_PASS_IMAGES_PATH = '/var/www/azul/static/wallet_images/'
```

### Asset Optimization

```bash
# Minify CSS/JS (recommended before deployment)
npm install -g terser
terser client/static/js/*.js -o client/static/js/main.min.js

# Optimize images
find client/static/img -name "*.png" -exec optipng {} \;
find client/static/img -name "*.jpg" -exec jpegoptim {} \;
```

---

## 7. Database Migration Procedure

### Pre-Migration Checklist

- [ ] Full database backup (section 8)
- [ ] Review migration Plan file
- [ ] Test migration on staging database
- [ ] Schedule during low-traffic window
- [ ] Notify merchants of potential brief downtime

### Migration Steps

```bash
# 1. Activate virtualenv
source venv/bin/activate

# 2. Set production environment
export FLASK_ENV=production
export SECRET_KEY="your-production-key"

# 3. Create backup
cp instance/tappy.db.instance backups/tappy.db.backup.$(date +%Y%m%d_%H%M%S)

# 4. Run migrations
flask db upgrade

# 5. Verify
flask db current

# 6. Test application
curl -I http://localhost:5000/
```

### Migration Files

Migration scripts are in `migrations/versions/`:
- `20261116_initial.py` - Adds tenant columns (merchant_id, has_phone, etc.)
- Future migrations will be numbered sequentially

---

## 8. Automated Backup and Recovery Strategy

### Daily Backup Script

```bash
#!/bin/bash
# /usr/local/bin/azul-backup.sh

BACKUP_DIR="/backups/azul"
DATE=$(date +%Y%m%d_%H%M%S)
DB_PATH="/var/www/azul/data/production.db"

# Create backup directory
mkdir -p $BACKUP_DIR

# Database backup (SQLite)
if [ -f "$DB_PATH" ]; then
    cp "$DB_PATH" "$BACKUP_DIR/production.db.$DATE"
    chmod 600 "$BACKUP_DIR/production.db.$DATE"
fi

# Application state backup
tar -czf "$BACKUP_DIR/app-state.$DATE.tar.gz" \
    /var/www/azul/data \
    --exclude="*.log"

# Keep only last 30 days
find $BACKUP_DIR -name "production.db.*" -mtime +30 -delete
find $BACKUP_DIR -name "app-state.*.tar.gz" -mtime +30 -delete

echo "Backup completed: $DATE"
```

### Cron Job

```bash
# Daily backup at 2AM
0 2 * * * /usr/local/bin/azul-backup.sh >> /var/log/azul-backup.log 2>&1

# Weekly full backup (Sunday at 3AM)
0 3 * * 0 /usr/local/bin/azul-backup.sh && tar -czf /backups/azul/weekly.$(date +%Y%m%d).tar.gz /backups/azul/*.db.*
```

### Recovery Procedure

```bash
# 1. Stop application
sudo systemctl stop azul

# 2. Restore database
cp /backups/azul/production.db.20261115_020000 /var/www/azul/data/production.db

# 3. Verify integrity
sqlite3 /var/www/azul/data/production.db "PRAGMA integrity_check;"

# 4. Restart application
sudo systemctl start azul

# 5. Monitor logs
tail -f /var/log/azul/error.log
```

---

## 9. Logging and Error Monitoring

### Flask Logging Configuration

```python
import logging
from logging.handlers import RotatingFileHandler

# Configure logging
if not app.debug:
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    file_handler = RotatingFileHandler(
        'logs/azul.log', maxBytes=10240000, backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('AZUL production startup')
```

### Log Files

| File | Purpose | Rotation |
|------|---------|----------|
| `/var/log/azul/access.log` | HTTP access logs | Daily |
| `/var/log/azul/error.log` | Application errors | Daily |
| `/var/log/azul/azul.log` | Application events | Daily, 10MB backup |

### Monitoring Tools

**Lightweight Options:**
- **UptimeRobot**: Free external monitoring
- **Logtail**: Hosted log aggregation (Moroccan provider)
- **Papertrail**: Cloud log management

**Full Options:**
- **Prometheus + Grafana**: Self-hosted metrics
- **Sentry**: Error tracking and alerting
- **Datadog**: Comprehensive monitoring

---

## 10. Rollback Procedure

### When to Roll Back

- Application fails to start after deployment
- Database migration corrupts data
- Critical bug affects all merchants

### Rollback Steps

```bash
# 1. Stop application
sudo systemctl stop azul

# 2. Restore previous backup
cp /backups/azul/production.db.previous /var/www/azul/data/production.db

# 3. Revert to previous code (if Git deployed)
git checkout production-v1.2.0

# 4. Restart application
sudo systemctl start azul

# 5. Verify
curl -I https://loyalty.morocco/
```

### Git Tags for Rollback

```bash
# Create tag before each deployment
git tag -a production-v1.3.0 -m "Production release"
git push origin production-v1.3.0

# Rollback to previous version
git checkout production-v1.2.9
```

---

## Quick Start Checklist

### Pre-Launch

- [ ] Generate and secure `SECRET_KEY`
- [ ] Generate `ADMIN_PASSWORD`
- [ ] Set up domain and DNS
- [ ] Obtain SSL certificate
- [ ] Configure Nginx reverse proxy
- [ ] Set up daily backup cron job
- [ ] Test database migration
- [ ] Verify all environment variables

### Post-Launch

- [ ] Create first merchant account
- [ ] Test wallet pass generation (Apple/Google)
- [ ] Test SMS notification flow
- [ ] Verify push notification setup
- [ ] Set up monitoring alerts

---

## Support Contacts

| Service | Contact | Notes |
|---------|---------|-------|
| Technical Issues | dev@azul.ma | 24/7 support |
| Apple Wallet | developer@azul.ma | PassKit provisioning |
| SMS Gateway | sms-provider | Twilio/Maroc Telecom |
| Domain/Hosting | hosting-provider | Registrar/DNS |

---

*This guide will be updated as the platform evolves. Last updated: 2026-11-16*
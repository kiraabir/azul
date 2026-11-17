# AZUL - Wallet-Based Loyalty Card Platform

AZUL is a digital loyalty card platform for local businesses in Morocco. Unlike monthly subscription models, AZUL offers a one-time purchase solution that drops loyalty cards directly into customers' Apple Wallet or Google Wallet.

## Key Features

### 1. Wallet-Based Loyalty Cards
- Customers tap a counter tag (NFC/QR) and the card drops into their wallet
- No app installation required
- Personalized pass with customer's name

### 2. Customer Data Capture
- Name **required**, phone **optional**
- Phone enables SMS promotions and re-engagement
- Customers without phone still get full wallet experience

### 3. 100m Radar
- Wallet pass surfaces automatically when customer is within ~100m of shop
- Uses pass relevance date for proximity alerts

### 4. Stamps & Gifts
- Digital stamping on purchases
- Tiered rewards (5/10/15 stamps = different rewards)

### 5. Automatic Re-engagement
- System messages customers who haven't visited in X days (configurable, default 15)
- Via both wallet push and SMS

### 6. Promotions
- Merchants send offers directly to customers' wallets
- SMS campaigns to customers with phone numbers

### 7. Feedback → Review Loop
- Negative feedback goes privately to business inbox first
- Positive feedback gently nudges to Google review
- Feedback submission earns +1 free stamp

### 8. Merchant Dashboard
- Manage card design, stamps, credits
- View customer list with names + phones
- Basic analytics and stats

## Technical Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Counter Tag    │     │  Customer       │     │  Merchant       │
│  (NFC/QR)       │────▶│  Device         │     │  Dashboard      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                │                         │
                                ▼                         ▼
                      ┌─────────────────┐     ┌─────────────────┐
                      │   AZUL Backend  │◀────│   Web Portal    │
                      │                 │     │                 │
                      │ - Wallet Pass   │     │ - Card Design   │
                      │   Generation    │     │ - Stamps        │
                      │ - SMS Gateway   │     │ - Customers     │
                      │ - Push Engine   │     │ - Analytics     │
                      └─────────────────┘     └─────────────────┘
```

## Database Models

- **Customer** - name (required), phone (optional), wallet_pass_id
- **LoyaltyCard** - card_number, qr_token, points_balance, wallet_serial
- **Transaction** - earn/redeem records
- **RewardTier** - threshold_stamps, name, description
- **Feedback** - rating, comment, sentiment
- **Campaign** - SMS/push campaigns

## API Endpoints

```
POST   /api/v1/tags/tap              # Customer taps tag
GET    /api/v1/passes/{id}.pkpass    # Apple Wallet pass download
GET    /api/v1/passes/{id}/android   # Google Wallet pass
POST   /api/v1/stamps                  # In-store stamping
POST   /api/v1/feedback              # Feedback submission
POST   /api/v1/campaigns/send        # SMS campaign
GET    /api/v1/rewards               # List reward tiers
POST   /api/v1/rewards/redeem      # Redeem stamps
```

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
python -c "from app import app, _bootstrap; app.app_context(); _bootstrap(app)"

# Run development server
python -m client.app
```

## Deploying to Production

1. Generate Apple PassKit signing certificates
2. Register Google Pay Merchant account
3. Configure SMS gateway (Twilio, Maroc Telecom API, etc.)
4. Set SECRET_KEY environment variable
5. Run with Gunicorn: `gunicorn -w 4 -b 0.0.0.0:5000 app:app`

## Morocco Localization

- Pricing in MAD (dirhams)
- Arabic/French interfaces
- Local SMS providers: Maroc Telecom, Inwi, Orange

## Commercial Model

- **Starter Tier** - One-time purchase (e.g. 500 DH)
- **Growth Tier** - One-time purchase (e.g. 1500 DH)
- **Multi-Branch Tier** - One-time purchase (e.g. 3000 DH)
- **Annual Support** - Add-on after year one

---

Built for local Moroccan businesses by AZUL.
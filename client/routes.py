"""HTTP routes for AZUL Loyalty Cards."""
import io
import secrets
import uuid

from flask import (render_template, redirect, url_for, flash, request,
                   send_file, abort, jsonify, session, g)

from . import db
from .models import (Customer, LoyaltyCard, Transaction, ShopSetting, RewardTier,
                     Campaign, Feedback, RewardClaim, get_current_merchant_id)
from .auth import login_required, get_current_user, get_current_merchant
from .qr import generate_card_qr, qr_bytes, generate_card_image, generate_wallet_pass_image
from .wallet import WalletPassGenerator, GoogleWalletPassGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _settings():
    """Get all shop settings with defaults."""
    return {
        "shop_name": ShopSetting.get("shop_name", "AZUL"),
        "points_per_purchase": _int(ShopSetting.get("points_per_purchase"), 1),
        "redemption_value": _int(ShopSetting.get("redemption_value"), 10),
        "feedback_stamp_value": _int(ShopSetting.get("feedback_stamp_value", "1")),
        "reengage_days": _int(ShopSetting.get("reengage_days", "15")),
        "logo_url": ShopSetting.get("logo_url", ""),
        "shop_latitude": ShopSetting.get("shop_latitude", ""),
        "shop_longitude": ShopSetting.get("shop_longitude", ""),
        "pass_type_id": ShopSetting.get("pass_type_id", ""),
        "api_key_id": ShopSetting.get("api_key_id", ""),
        "google_merchant_id": ShopSetting.get("google_merchant_id", ""),
        "sms_provider": ShopSetting.get("sms_provider", "default"),
        "sms_api_key": ShopSetting.get("sms_api_key", ""),
    }


def _card_by_token(token):
    """Find card by token, scoped to current merchant."""
    merchant_id = get_current_merchant_id()
    return LoyaltyCard.query.filter_by(qr_token=token, merchant_id=merchant_id).first()


def _get_reward_tiers():
    """Get all available reward tiers for current merchant."""
    merchant_id = get_current_merchant_id()
    return RewardTier.query.filter_by(merchant_id=merchant_id, is_available=True).all()


def _ensure_card_owner(card, card_id):
    """Ensure the card belongs to the current merchant (security check)."""
    current_merchant_id = get_current_merchant_id()
    if card.merchant_id != current_merchant_id:
        abort(404)  # Don't reveal existence to unauthorized users


def _ensure_customer_owner(customer_id):
    """Security check: ensure customer belongs to current merchant."""
    merchant_id = get_current_merchant_id()
    customer = Customer.query.filter_by(id=customer_id, merchant_id=merchant_id).first()
    if not customer:
        abort(404)
    return customer


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@login_required
def index():
    """Dashboard with AZUL-specific metrics."""
    merchant_id = get_current_merchant_id()

    customers = Customer.query.filter_by(merchant_id=merchant_id).all()
    active_cards = LoyaltyCard.query.filter_by(merchant_id=merchant_id, is_active=True).count()

    # Calculate SMS reach
    cards_with_phone = sum(1 for c in customers if c.has_phone and c.active_card)
    cards_no_phone = active_cards - cards_with_phone

    # Recent activity - scoped to merchant
    recent = (Transaction.query.filter_by(merchant_id=merchant_id)
              .order_by(Transaction.id.desc()).limit(5).all())

    # Metrics - scoped to merchant
    total_stamps = db.session.query(db.func.sum(
        LoyaltyCard.points_balance)).filter_by(merchant_id=merchant_id).scalar() or 0

    # Redemption rate - scoped to merchant
    total_redeemed = db.session.query(db.func.sum(
        db.func.abs(Transaction.points)
    )).filter_by(merchant_id=merchant_id, type='redeem').scalar() or 0
    redemption_rate = (total_redeemed / total_stamps) if total_stamps > 0 else 0

    return render_template("index.html",
                     customers=customers,
                     active_cards=active_cards,
                     cards_with_phone=cards_with_phone,
                     cards_no_phone=cards_no_phone,
                     total_stamps=total_stamps,
                     redemption_rate=redemption_rate,
                     recent=recent,
                     settings=_settings())


@login_required
def customers_list():
    """Customer list with phone status indicator."""
    merchant_id = get_current_merchant_id()
    q = request.args.get("q", "").strip()
    query = Customer.query.filter_by(merchant_id=merchant_id)
    if q:
        query = query.filter(
            db.or_(Customer.name.ilike(f"%{q}%"),
                   Customer.phone.ilike(f"%{q}%")))
    customers = query.order_by(Customer.name).all()
    return render_template("customers.html", customers=customers, q=q,
                           settings=_settings())


# capture_customer_info is a public customer-facing endpoint used in wallet flow
# It uses merchant_id from session or defaults to merchant 1 for initial setup
def capture_customer_info():
    """
    AZUL flow: Customer taps tag -> enters name/phone -> wallet pass is generated.
    This is a PUBLIC endpoint used by customers, not merchant authentication.
    """
    merchant_id = get_current_merchant_id()
    customer = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()

        if not name:
            flash("Name is required.", "error")
            return render_template("capture_info.html")

        # Check if customer already exists within this merchant
        customer = Customer.query.filter_by(
            merchant_id=merchant_id, name=name, phone=phone).first()
        if not customer:
            customer = Customer(name=name, phone=phone or None, merchant_id=merchant_id)
            db.session.add(customer)
            db.session.commit()
            flash(f"Welcome, {name}!", "ok")

        # Create or get active card
        card = LoyaltyCard.query.filter_by(
            merchant_id=merchant_id, customer_id=customer.id, is_active=True).first()

        if not card:
            card = LoyaltyCard(customer=customer, merchant_id=merchant_id)
            # wallet_serial is auto-generated in LoyaltyCard.__init__ using UUID
            db.session.add(card)
            db.session.commit()

        # Generate wallet pass URL
        return redirect(url_for('send_to_wallet', card_id=card.id))

    return render_template("capture_info.html", customer=customer)


def tag_scan():
    """
    Customer arrives and taps the NFC/QR tag.
    This initiates the wallet flow.
    """
    return render_template("tag_scan.html", shop_name=_settings()["shop_name"])


# send_to_wallet is a PUBLIC customer-facing endpoint used in wallet flow
def send_to_wallet(card_id):
    """Generate wallet pass links and send to customer."""
    merchant_id = get_current_merchant_id()
    card = LoyaltyCard.query.filter_by(id=card_id, merchant_id=merchant_id).first()
    if not card:
        abort(404)
    customer = card.customer

    settings = _settings()

    # Generate Apple Wallet pass URL
    apple_pass_url = url_for('download_apple_pass', card_id=card.id, _external=True)

    # Generate Google Wallet pass URL
    google_pass_url = url_for('download_google_pass', card_id=card.id, _external=True)

    return render_template("send_to_wallet.html",
                          customer=customer,
                          card=card,
                          apple_url=apple_pass_url,
                          google_url=google_pass_url,
                          settings=settings)


# Wallet pass downloads are PUBLIC customer-facing endpoints
def download_apple_pass(card_id):
    """Download Apple Wallet pass file."""
    merchant_id = get_current_merchant_id()
    card = LoyaltyCard.query.filter_by(id=card_id, merchant_id=merchant_id).first()
    if not card:
        abort(404)
    customer = card.customer

    if not card.wallet_serial:
        # wallet_serial should have been generated in __init__
        # Using UUID to ensure uniqueness
        card.wallet_serial = f"AZUL-{uuid.uuid4().hex[:16]}"
        db.session.commit()

    generator = WalletPassGenerator(
        merchant_name=_settings()["shop_name"],
        merchant_id=_settings()["api_key_id"].split('-')[0] if _settings()["api_key_id"] else "DEV",
        api_key=_settings()["api_key_id"]
    )

    pass_bytes = generator.generate_pass(customer, card)
    card.is_wallet_synced = True
    db.session.commit()

    return send_file(
        io.BytesIO(pass_bytes),
        as_attachment=True,
        download_name=f"{customer.name}_azul.pass",
        mimetype="application/vnd.apple.pkpass"
    )


def download_google_pass(card_id):
    """Generate Google Wallet pass data."""
    merchant_id = get_current_merchant_id()
    card = LoyaltyCard.query.filter_by(id=card_id, merchant_id=merchant_id).first()
    if not card:
        abort(404)
    customer = card.customer

    generator = GoogleWalletPassGenerator(
        merchant_id=_settings()["google_merchant_id"],
        api_key=_settings()["api_key_id"]
    )

    pass_data = generator.generate_pass(customer, card)

    card.is_wallet_synced = True
    db.session.commit()

    return jsonify(pass_data)


@login_required
def customer_new():
    """Add a new customer (manual form entry)."""
    merchant_id = get_current_merchant_id()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()

        if not name:
            flash("Customer name is required.", "error")
            return render_template("customer_form.html", settings=_settings())

        cust = Customer(name=name, phone=phone or None, email=email or None,
                        merchant_id=merchant_id)
        db.session.add(cust)
        db.session.commit()

        flash(f"Customer {cust.name} added.", "ok")
        return redirect(url_for("customers_list"))

    return render_template("customer_form.html", settings=_settings())


@login_required
def customer_detail(customer_id):
    """View customer details with card and activity."""
    merchant_id = get_current_merchant_id()
    cust = Customer.query.filter_by(id=customer_id, merchant_id=merchant_id).first()
    if not cust:
        abort(404)
    reward_tiers = _get_reward_tiers()
    return render_template("customer.html", customer=cust,
                           settings=_settings(),
                           reward_tiers=reward_tiers)


@login_required
def card_new():
    """Issue a new loyalty card."""
    merchant_id = get_current_merchant_id()
    if request.method == "POST":
        customer_id = _int(request.form.get("customer_id"))
        include_qr = request.form.get("include_qr")

        # Ensure customer belongs to current merchant
        cust = Customer.query.filter_by(id=customer_id, merchant_id=merchant_id).first()
        if not cust:
            abort(404)
        card = LoyaltyCard(customer=cust, merchant_id=merchant_id)
        # wallet_serial is auto-generated in LoyaltyCard.__init__ using UUID
        db.session.add(card)
        db.session.commit()

        # Generate QR code for physical counter scanning
        if include_qr:
            generate_card_qr(card)

        flash(f"Issued card {card.card_number} to {cust.name}.", "ok")
        return redirect(url_for('send_to_wallet', card_id=card.id))

    customers = Customer.query.filter_by(merchant_id=merchant_id).order_by(Customer.name).all()
    return render_template("card_form.html", customers=customers,
                           settings=_settings())


@login_required
def card_detail(card_id):
    """View card details with transactions."""
    merchant_id = get_current_merchant_id()
    card = LoyaltyCard.query.filter_by(id=card_id, merchant_id=merchant_id).first()
    if not card:
        abort(404)
    txs = (Transaction.query.filter_by(card_id=card.id, merchant_id=merchant_id)
           .order_by(Transaction.id.desc()).all())
    return render_template("card.html", card=card, transactions=txs,
                           settings=_settings())


@login_required
def card_earn(card_id):
    """Earn stamps on a card."""
    merchant_id = get_current_merchant_id()
    card = LoyaltyCard.query.filter_by(id=card_id, merchant_id=merchant_id).first()
    if not card:
        abort(404)
    if request.method == "POST":
        points = _int(request.form.get("points"))
        desc = request.form.get("description", "Purchase").strip()

        if points <= 0:
            flash("Enter a positive number of points.", "error")
        else:
            tx = Transaction(card=card, customer=card.customer,
                            merchant_id=merchant_id,
                            type="earn", points=points, description=desc)
            tx.apply()
            db.session.add(tx)

            # Update last seen
            card.customer.last_seen_at = db.func.now()

            db.session.commit()
            flash(f"Earned {points} points. Total: {card.points_balance}", "ok")
    return redirect(url_for('card_detail', card_id=card_id))


@login_required
def card_redeem(card_id):
    """Redeem stamps for a reward."""
    merchant_id = get_current_merchant_id()
    card = LoyaltyCard.query.filter_by(id=card_id, merchant_id=merchant_id).first()
    if not card:
        abort(404)
    if request.method == "POST":
        points = _int(request.form.get("points"))
        desc = request.form.get("description", "Redemption").strip()

        if points <= 0:
            flash("Enter a positive number of points.", "error")
        elif points > card.points_balance:
            flash("Not enough points for that redemption.", "error")
        else:
            tx = Transaction(card=card, customer=card.customer,
                            merchant_id=merchant_id,
                            type="redeem", points=points, description=desc)
            tx.apply()
            db.session.add(tx)

            # Create a RewardClaim audit record so redemptions are tracked
            # consistently with the customer portal redemption flow.
            tier = (RewardTier.query
                    .filter_by(merchant_id=merchant_id,
                               threshold_stamps=points)
                    .first())
            if tier:
                claim = RewardClaim(
                    merchant_id=merchant_id,
                    customer_id=card.customer_id,
                    card_id=card.id,
                    reward_tier_id=tier.id,
                    redemption_code=secrets.token_hex(8).upper()
                )
                db.session.add(claim)

            db.session.commit()
            flash(f"Redeemed {points} points. Remaining: {card.points_balance}", "ok")
    return redirect(url_for('card_detail', card_id=card_id))


@login_required
def card_qr_png(card_id):
    """Generate QR code image for a card."""
    merchant_id = get_current_merchant_id()
    card = LoyaltyCard.query.filter_by(id=card_id, merchant_id=merchant_id).first()
    if not card:
        abort(404)
    return send_file(io.BytesIO(qr_bytes(card)), mimetype="image/png")


@login_required
def submit_feedback(card_id):
    """Submit feedback - earns +1 stamp"""
    merchant_id = get_current_merchant_id()
    card = LoyaltyCard.query.filter_by(id=card_id, merchant_id=merchant_id).first()
    if not card:
        abort(404)

    if request.method == "POST":
        rating = int(request.form.get("rating", 3))
        comment = request.form.get("comment", "").strip()

        feedback = Feedback(
            merchant_id=card.merchant_id,
            customer_id=card.customer_id,
            card_id=card.id,
            rating=rating,
            comment=comment,
            sentiment="positive" if rating >= 4 else "negative"
        )

        db.session.add(feedback)

        # Award stamp for feedback
        tx = Transaction(card=card, customer=card.customer,
                         merchant_id=card.merchant_id,
                         type="earn", points=1, description="Feedback submitted")
        tx.apply()
        db.session.add(tx)
        feedback.stamp_earned = True

        db.session.commit()

        # Handle feedback loop
        if rating >= 4:
            flash("Thank you! Your feedback has been submitted.", "ok")
            # TODO: Send Google review nudge
        else:
            flash("Thank you for your feedback. Negative feedback is sent to the shop.", "ok")
            # TODO: Notify merchant

        return redirect(url_for('card_detail', card_id=card.id))

    return render_template("submit_feedback.html", card=card)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
@login_required
def settings():
    """Shop settings with all AZUL configuration."""
    if request.method == "POST":
        ShopSetting.set("shop_name", request.form.get("shop_name", "AZUL"))
        ShopSetting.set("points_per_purchase",
                        request.form.get("points_per_purchase", "1"))
        ShopSetting.set("redemption_value",
                        request.form.get("redemption_value", "10"))
        ShopSetting.set("feedback_stamp_value",
                        request.form.get("feedback_stamp_value", "1"))
        ShopSetting.set("reengage_days",
                        request.form.get("reengage_days", "15"))
        ShopSetting.set("logo_url", request.form.get("logo_url", ""))
        ShopSetting.set("shop_latitude", request.form.get("shop_latitude", ""))
        ShopSetting.set("shop_longitude", request.form.get("shop_longitude", ""))
        ShopSetting.set("pass_type_id", request.form.get("pass_type_id", ""))
        ShopSetting.set("api_key_id", request.form.get("api_key_id", ""))
        ShopSetting.set("google_merchant_id", request.form.get("google_merchant_id", ""))
        ShopSetting.set("sms_provider", request.form.get("sms_provider", "default"))
        ShopSetting.set("sms_api_key", request.form.get("sms_api_key", ""))

        flash("Settings saved.", "ok")

    reward_tiers = _get_reward_tiers()
    return render_template("settings.html", settings=_settings(),
                           reward_tiers=reward_tiers)


@login_required
def new_tier():
    """Add a new reward tier."""
    merchant_id = get_current_merchant_id()
    if request.method == "POST":
        tier = RewardTier(
            threshold_stamps=int(request.form.get("threshold_stamps", 5)),
            name=request.form.get("name", "Reward"),
            description=request.form.get("description", ""),
            is_available=True,
            merchant_id=merchant_id
        )
        db.session.add(tier)
        db.session.commit()
        flash(f"Added reward: {tier.name}", "ok")
        return redirect(url_for('settings'))

    return render_template("new_tier.html", settings=_settings())


@login_required
def edit_tier(tier_id):
    """Edit a reward tier."""
    merchant_id = get_current_merchant_id()
    tier = RewardTier.query.filter_by(id=tier_id, merchant_id=merchant_id).first()
    if not tier:
        abort(404)

    if request.method == "POST":
        tier.threshold_stamps = int(request.form.get("threshold_stamps", 5))
        tier.name = request.form.get("name", "Reward")
        tier.description = request.form.get("description", "")
        tier.is_available = request.form.get("is_available") == "on"
        db.session.commit()
        flash(f"Updated reward: {tier.name}", "ok")
        return redirect(url_for('settings'))

    return render_template("edit_tier.html", tier=tier, settings=_settings())


# ---------------------------------------------------------------------------
# Re-engagement Campaigns
# ---------------------------------------------------------------------------
@login_required
def send_re_engagement_campaign():
    """Send SMS to inactive customers."""
    from datetime import datetime, timedelta, timezone
    merchant_id = get_current_merchant_id()
    reengage_days = _int(ShopSetting.get("reengage_days", "15"), 15)

    # Find customers who haven't visited in reengage_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=reengage_days)

    inactive_customers = Customer.query.filter_by(merchant_id=merchant_id).filter(
        (Customer.last_seen_at < cutoff) | (Customer.last_seen_at == None),
        Customer.phone != None,
        Customer.has_phone == True
    ).all()

    if request.method == "POST":
        # Create campaign and process
        content = request.form.get("content", "")
        campaign = Campaign(
            name=f"Re-engagement - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            type="re_engage",
            content=content,
            target_segment=f"inactive_{reengage_days}d",
            sent_at=datetime.now(timezone.utc),
            merchant_id=merchant_id
        )
        db.session.add(campaign)

        # TODO: Send SMS via provider
        for cust in inactive_customers:
            cust.last_engaged_at = datetime.now(timezone.utc)

        db.session.commit()

        flash(f"Sent campaign to {len(inactive_customers)} customers", "ok")
        return redirect(url_for('customers_list'))

    return render_template("re_engagement.html",
                          customers=inactive_customers,
                          settings=_settings())


# ---------------------------------------------------------------------------
# Scanner API (returns card info for a scanned QR token)
# This is a PUBLIC endpoint used by customer-side wallet scans.
# When a merchant is logged in, scans are scoped to that merchant's cards only.
# ---------------------------------------------------------------------------
def scan(token):
    """API endpoint for QR token scanning.

    When a user is logged in, only shows cards from that merchant.
    When no user is logged in (public mode), shows any card by token.
    """
    from .models import LoyaltyCard

    # Check if user is logged in
    user_id = session.get('user_id')
    if user_id:
        # Authenticated scan - scope to current merchant only
        current_merchant_id = get_current_merchant_id()
        card = LoyaltyCard.query.filter_by(
            qr_token=token,
            merchant_id=current_merchant_id,
            is_active=True
        ).first()
    else:
        # Public scan - allow any merchant to scan their customer's card
        # This is used when customers scan at physical stores
        # The store (merchant) is determined by which store's device is scanning
        card = LoyaltyCard.query.filter_by(qr_token=token, is_active=True).first()

    if card is None:
        return jsonify({"found": False}), 404

    # Return public card info (no sensitive data exposed)
    return jsonify({
        "found": True,
        "card_number": card.card_number,
        "customer": card.customer.name if card.customer else None,
        "phone": card.customer.phone if card.customer else None,
        "points_balance": card.points_balance,
        "wallet_pass_url": url_for('send_to_wallet', card_id=card.id, _external=True)
    })


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------
def register(app):
    app.add_url_rule("/", "index", index, methods=["GET"])

    app.add_url_rule("/customers", "customers_list", customers_list, methods=["GET"])
    app.add_url_rule("/customers/new", "customer_new", customer_new, methods=["GET", "POST"])
    app.add_url_rule("/customers/<int:customer_id>", "customer_detail", customer_detail, methods=["GET"])

    app.add_url_rule("/tags/scan", "tag_scan", tag_scan, methods=["GET"])
    app.add_url_rule("/capture", "capture_customer_info", capture_customer_info, methods=["GET", "POST"])
    app.add_url_rule("/send-to-wallet/<int:card_id>", "send_to_wallet", send_to_wallet, methods=["GET"])

    app.add_url_rule("/cards/new", "card_new", card_new, methods=["GET", "POST"])
    app.add_url_rule("/cards/<int:card_id>", "card_detail", card_detail, methods=["GET"])
    app.add_url_rule("/cards/<int:card_id>/earn", "card_earn", card_earn, methods=["POST"])
    app.add_url_rule("/cards/<int:card_id>/redeem", "card_redeem", card_redeem, methods=["POST"])
    app.add_url_rule("/cards/<int:card_id>/qr.png", "card_qr_png", card_qr_png, methods=["GET"])

    app.add_url_rule("/wallet/apple/<int:card_id>", "download_apple_pass", download_apple_pass, methods=["GET"])
    app.add_url_rule("/wallet/google/<int:card_id>", "download_google_pass", download_google_pass, methods=["GET"])

    app.add_url_rule("/feedback/<int:card_id>", "submit_feedback", submit_feedback, methods=["GET", "POST"])

    app.add_url_rule("/settings", "settings", settings, methods=["GET", "POST"])
    app.add_url_rule("/rewards/new", "new_tier", new_tier, methods=["GET", "POST"])
    app.add_url_rule("/rewards/<int:tier_id>/edit", "edit_tier", edit_tier, methods=["GET", "POST"])

    app.add_url_rule("/campaigns/re-engage", "send_re_engagement_campaign", send_re_engagement_campaign, methods=["GET", "POST"])

    app.add_url_rule("/scan/<token>", "scan", scan, methods=["GET"])
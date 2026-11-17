"""Customer Portal routes for AZUL - Customer-facing wallet endpoints."""
import json
import secrets
from flask import render_template, redirect, url_for, flash, request, jsonify, g, abort, session
from functools import wraps

from . import db
from .models import Customer, LoyaltyCard, Transaction, RewardTier, Notification, Feedback, RewardClaim
from .auth import get_current_merchant_id


def customer_portal(card_id):
    """Customer portal - view their loyalty card.

    This is a PUBLIC endpoint accessed via wallet pass links.
    The merchant context is derived from the card itself.
    """
    card = LoyaltyCard.query.get_or_404(card_id)
    if not card.is_active:
        abort(404)

    # Security check: if a user is logged in, verify they own this card's merchant
    if 'user_id' in session:
        current_merchant_id = get_current_merchant_id()
        if card.merchant_id != current_merchant_id:
            abort(404)

    customer = card.customer
    merchant = card.merchant

    # Get reward tiers for this merchant
    reward_tiers = RewardTier.query.filter_by(
        merchant_id=merchant.id, is_available=True
    ).order_by(RewardTier.threshold_stamps).all()

    # Get notifications for this customer
    notifications = Notification.query.filter_by(
        customer_id=customer.id, is_read=False
    ).order_by(Notification.id.desc()).limit(10).all()

    # Get transaction history for this card
    transactions = Transaction.query.filter_by(
        card_id=card.id
    ).order_by(Transaction.id.desc()).limit(20).all()

    # Calculate progress
    progress = card.get_progress_to_next_reward()

    return render_template("customer_portal.html",
                          customer=customer,
                          card=card,
                          merchant=merchant,
                          reward_tiers=reward_tiers,
                          notifications=notifications,
                          transactions=transactions,
                          progress=progress)


def customer_notifications(card_id):
    """API endpoint for customer notifications."""
    card = LoyaltyCard.query.get_or_404(card_id)
    if not card.is_active:
        abort(404)

    # Security check: if a user is logged in, verify they own this card's merchant
    if 'user_id' in session:
        current_merchant_id = get_current_merchant_id()
        if card.merchant_id != current_merchant_id:
            abort(404)

    notifications = Notification.query.filter_by(
        card_id=card_id, is_read=False
    ).order_by(Notification.id.desc()).all()

    return jsonify({
        'notifications': [
            {
                'id': n.id,
                'title': n.title,
                'body': n.body,
                'sent_at': n.sent_at.isoformat() if n.sent_at else None
            }
            for n in notifications
        ]
    })


def customer_mark_read(card_id):
    """Mark notifications as read."""
    card = LoyaltyCard.query.get_or_404(card_id)
    if not card.is_active:
        abort(404)

    # Security check: if a user is logged in, verify they own this card's merchant
    if 'user_id' in session:
        current_merchant_id = get_current_merchant_id()
        if card.merchant_id != current_merchant_id:
            abort(404)

    Notification.query.filter_by(
        card_id=card_id, is_read=False
    ).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})


def customer_submit_feedback(card_id):
    """Submit feedback from customer portal."""
    card = LoyaltyCard.query.get_or_404(card_id)
    if not card.is_active:
        abort(404)

    # Security check: if a user is logged in, verify they own this card's merchant
    if 'user_id' in session:
        current_merchant_id = get_current_merchant_id()
        if card.merchant_id != current_merchant_id:
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
        tx = Transaction(
            merchant_id=card.merchant_id,
            customer_id=card.customer_id,
            card_id=card.id,
            type="earn",
            points=1,
            description="Feedback submitted"
        )
        tx.apply()
        db.session.add(tx)
        feedback.stamp_earned = True

        db.session.commit()

        # Create notification for positive feedback
        if rating >= 4:
            notification = Notification(
                merchant_id=card.merchant_id,
                customer_id=card.customer_id,
                title="Thank you for your feedback!",
                body="Your positive feedback helps us improve.",
                data=json.dumps({'type': 'feedback', 'rating': rating})
            )
            db.session.add(notification)

        db.session.commit()
        flash("Thank you for your feedback!", "ok")
        return redirect(url_for('customer_portal', card_id=card.id))

    return render_template("submit_feedback.html", card=card)


def customer_redeem_reward(card_id):
    """Redeem a reward from the customer portal."""
    card = LoyaltyCard.query.get_or_404(card_id)
    if not card.is_active:
        abort(404)

    # Security check: if a user is logged in, verify they own this card's merchant
    if 'user_id' in session:
        current_merchant_id = get_current_merchant_id()
        if card.merchant_id != current_merchant_id:
            abort(404)

    if request.method == "POST":
        reward_tier_id_raw = request.form.get("reward_tier_id")
        try:
            reward_tier_id = int(reward_tier_id_raw)
        except (TypeError, ValueError):
            flash("Invalid reward selection.", "error")
            return redirect(url_for('customer_portal', card_id=card.id))

        # Security: Find tier by merchant and id only
        # If the tier doesn't belong to this card's merchant, abort with 404
        reward_tier = RewardTier.query.filter_by(
            merchant_id=card.merchant_id,
            id=reward_tier_id
        ).first()

        if not reward_tier:
            # Don't reveal existence - return 404 to prevent enumeration
            abort(404)

        if card.points_balance < reward_tier.threshold_stamps:
            flash("Not enough points for that reward.", "error")
        else:
            tx = Transaction(
                merchant_id=card.merchant_id,
                customer_id=card.customer_id,
                card_id=card.id,
                type="redeem",
                points=reward_tier.threshold_stamps,
                description=f"Redeemed: {reward_tier.name}"
            )
            tx.apply()
            db.session.add(tx)

            # Create reward claim
            claim = RewardClaim(
                merchant_id=card.merchant_id,
                customer_id=card.customer_id,
                card_id=card.id,
                reward_tier_id=reward_tier.id,
                redemption_code=secrets.token_hex(8).upper()
            )
            db.session.add(claim)

            # Notify customer
            notification = Notification(
                merchant_id=card.merchant_id,
                customer_id=card.customer_id,
                title="Reward Unlocked!",
                body=f"You've redeemed: {reward_tier.name}",
                data=json.dumps({'type': 'reward', 'reward': reward_tier.name})
            )
            db.session.add(notification)

            db.session.commit()
            flash(f"Reward redeemed: {reward_tier.name}!", "ok")

    return redirect(url_for('customer_portal', card_id=card.id))


def register_customer_portal(app):
    """Register customer portal routes."""
    # Customer portal is PUBLIC - accessed via wallet pass
    app.add_url_rule("/c/<int:card_id>", "customer_portal", customer_portal, methods=["GET"])
    app.add_url_rule("/c/<int:card_id>/notifications", "customer_notifications", customer_notifications, methods=["GET"])
    app.add_url_rule("/c/<int:card_id>/notifications/read", "customer_mark_read", customer_mark_read, methods=["POST"])
    app.add_url_rule("/c/<int:card_id>/feedback", "customer_submit_feedback", customer_submit_feedback, methods=["GET", "POST"])
    app.add_url_rule("/c/<int:card_id>/redeem", "customer_redeem_reward", customer_redeem_reward, methods=["POST"])
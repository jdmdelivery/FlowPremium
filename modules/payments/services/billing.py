"""FlowPremium billing helpers."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from flask import current_app
from flask_login import current_user

from extensions import db
from modules.streaming.models import Payment

logger = logging.getLogger(__name__)

PAYMENT_METHODS = frozenset({"paypal", "cashapp_manual", "square_cashapp", "manual"})
PAYMENT_STATUSES = frozenset({"pending", "paid", "failed", "cancelled"})


def get_plan_catalog() -> dict[str, dict[str, Any]]:
    return current_app.config.get("PAYMENT_PLANS") or {}


def resolve_plan(plan_id: str) -> dict[str, Any] | None:
    plans = get_plan_catalog()
    plan = plans.get(plan_id)
    if not plan:
        return None
    amount = float(plan["amount"])
    if amount <= 0:
        return None
    return {
        "id": plan_id,
        "name": plan.get("name", plan_id),
        "description": plan.get("description", ""),
        "amount": round(amount, 2),
        "currency": plan.get("currency", "USD"),
    }


def resolve_payment_amount(plan_id: str | None, payment_id: int | None = None) -> tuple[float, str, str]:
    """
    Server-side amount validation. Never trust client-supplied amounts.
    Returns (amount, currency, payment_type).
    """
    if payment_id:
        payment = db.session.get(Payment, payment_id)
        if not payment or payment.status != "pending":
            raise ValueError("Invalid or inactive payment")
        return round(float(payment.amount), 2), payment.currency, payment.payment_type

    if not plan_id:
        raise ValueError("Plan is required")

    plan = resolve_plan(plan_id)
    if not plan:
        raise ValueError("Unknown plan")
    return plan["amount"], plan["currency"], "plan"


def _customer_fields(
    customer_name: str | None,
    customer_email: str | None,
) -> tuple[str | None, str | None, int | None]:
    user_id = None
    name = (customer_name or "").strip() or None
    email = (customer_email or "").strip().lower() or None

    if current_user.is_authenticated:
        user_id = current_user.id
        name = name or current_user.username
        email = email or current_user.email
    return name, email, user_id


def create_pending_payment(
    *,
    plan_id: str,
    method: str,
    customer_name: str | None = None,
    customer_email: str | None = None,
    payment_type: str = "plan",
) -> Payment:
    if method not in PAYMENT_METHODS:
        raise ValueError("Invalid payment method")

    plan = resolve_plan(plan_id)
    if not plan:
        raise ValueError("Unknown plan")

    name, email, user_id = _customer_fields(customer_name, customer_email)
    if not user_id and not email:
        raise ValueError("Email is required for guest checkout")

    payment = Payment(
        user_id=user_id,
        customer_name=name,
        customer_email=email,
        amount=plan["amount"],
        currency=plan["currency"],
        method=method,
        status="pending",
        payment_type=payment_type,
        reference_id=plan_id,
        reference_note=None,
    )
    db.session.add(payment)
    db.session.flush()
    payment.reference_note = payment.reference_code
    payment.sync_legacy_fields()
    db.session.commit()
    logger.info("Created pending payment id=%s method=%s amount=%s", payment.id, method, payment.amount)
    return payment


def submit_cashapp_reference(payment_id: int, note: str) -> Payment:
    payment = db.session.get(Payment, payment_id)
    if not payment:
        raise ValueError("Payment not found")
    if payment.method != "cashapp_manual":
        raise ValueError("Not a Cash App manual payment")
    if payment.status != "pending":
        raise ValueError("Payment is not pending")

    extra = (note or "").strip()
    if extra:
        payment.reference_note = f"{payment.reference_code} | {extra}"
    payment.sync_legacy_fields()
    db.session.commit()
    return payment


def mark_payment_paid(payment: Payment, provider_payment_id: str | None = None) -> Payment:
    if payment.status == "paid":
        return payment
    if payment.status in ("cancelled", "failed"):
        raise ValueError("Payment cannot be marked paid")

    payment.status = "paid"
    payment.paid_at = datetime.utcnow()
    if provider_payment_id:
        payment.provider_payment_id = provider_payment_id
    payment.sync_legacy_fields()
    db.session.commit()
    logger.info("Payment marked paid id=%s", payment.id)
    return payment


def cancel_payment(payment: Payment) -> Payment:
    if payment.status == "paid":
        raise ValueError("Paid payments cannot be cancelled")
    payment.status = "cancelled"
    payment.sync_legacy_fields()
    db.session.commit()
    logger.info("Payment cancelled id=%s", payment.id)
    return payment


def fail_payment(payment: Payment, reason: str = "") -> Payment:
    payment.status = "failed"
    if reason:
        meta = {}
        if payment.metadata_json:
            try:
                meta = json.loads(payment.metadata_json)
            except json.JSONDecodeError:
                meta = {}
        meta["failure_reason"] = reason
        payment.metadata_json = json.dumps(meta)
    payment.sync_legacy_fields()
    db.session.commit()
    logger.warning("Payment failed id=%s reason=%s", payment.id, reason)
    return payment


def payment_totals() -> dict[str, float]:
    now = datetime.utcnow()
    start_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    paid = Payment.query.filter_by(status="paid").all()
    day_total = sum(p.amount for p in paid if p.paid_at and p.paid_at >= start_day)
    month_total = sum(p.amount for p in paid if p.paid_at and p.paid_at >= start_month)
    return {"day": round(day_total, 2), "month": round(month_total, 2)}


def create_episode_payment(user, episode, method: str = "paypal") -> Payment:
    """Create a pending payment for a single episode (amount validated server-side)."""
    if method not in PAYMENT_METHODS:
        raise ValueError("Invalid payment method")
    if episode.is_free:
        raise ValueError("Episode is free")
    amount = round(float(episode.price), 2)
    if amount <= 0:
        raise ValueError("Invalid episode price")

    payment = Payment(
        user_id=user.id,
        customer_name=user.username,
        customer_email=user.email,
        amount=amount,
        currency="USD",
        method=method,
        status="pending",
        payment_type="episode",
        reference_id=str(episode.id),
    )
    db.session.add(payment)
    db.session.flush()
    payment.reference_note = payment.reference_code
    payment.sync_legacy_fields()
    db.session.commit()
    logger.info("Created episode payment id=%s episode=%s", payment.id, episode.id)
    return payment


def payments_by_status(status: str | None = None, limit: int = 200) -> list[Payment]:
    q = Payment.query.order_by(Payment.created_at.desc())
    if status:
        q = q.filter_by(status=status)
    return q.limit(limit).all()


def activate_payment_benefits(payment: Payment) -> None:
    """Grant subscription or episode access when payment is confirmed."""
    if not payment.user_id:
        return

    if payment.payment_type == "episode" and payment.reference_id:
        from modules.streaming.services.payment import grant_episode_purchase

        grant_episode_purchase(payment.user_id, int(payment.reference_id), payment.id)
        return

    if payment.payment_type == "plan":
        from modules.streaming.services.payment import grant_subscription

        days = 30 if payment.reference_id == "monthly" else 365
        grant_subscription(payment.user_id, days=days, payment_id=payment.id)

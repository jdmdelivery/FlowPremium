import json
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from extensions import db
from modules.streaming.models import Episode, EpisodePurchase, Payment, Subscription


class PaymentProvider(ABC):
    @abstractmethod
    def create_checkout(self, user, amount: float, payment_type: str, reference_id: str) -> dict:
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        pass


class ManualPaymentProvider(PaymentProvider):
    def is_configured(self) -> bool:
        return True

    def create_checkout(self, user, amount: float, payment_type: str, reference_id: str) -> dict:
        payment = Payment(
            user_id=user.id,
            amount=amount,
            payment_type=payment_type,
            reference_id=reference_id,
            method="manual",
            status="pending",
        )
        payment.sync_legacy_fields()
        db.session.add(payment)
        db.session.commit()
        return {"payment_id": payment.id, "status": "pending", "provider": "manual"}


class StripePaymentProvider(PaymentProvider):
    def is_configured(self) -> bool:
        from flask import current_app
        return bool(current_app.config.get("STRIPE_SECRET_KEY"))

    def create_checkout(self, user, amount: float, payment_type: str, reference_id: str) -> dict:
        raise NotImplementedError("Configure STRIPE_SECRET_KEY to enable Stripe payments")


class PayPalPaymentProvider(PaymentProvider):
    def is_configured(self) -> bool:
        from flask import current_app
        return bool(current_app.config.get("PAYPAL_CLIENT_ID"))

    def create_checkout(self, user, amount: float, payment_type: str, reference_id: str) -> dict:
        raise NotImplementedError("Configure PAYPAL_CLIENT_ID to enable PayPal payments")


def get_payment_provider() -> PaymentProvider:
    from flask import current_app
    if current_app.config.get("STRIPE_SECRET_KEY"):
        return StripePaymentProvider()
    if current_app.config.get("PAYPAL_CLIENT_ID"):
        return PayPalPaymentProvider()
    return ManualPaymentProvider()


def approve_payment(payment: Payment) -> Payment:
    payment.status = "paid"
    payment.paid_at = datetime.utcnow()
    payment.sync_legacy_fields()
    db.session.commit()
    return payment


def grant_episode_purchase(user_id: int, episode_id: int, payment_id: int | None = None) -> EpisodePurchase:
    existing = EpisodePurchase.query.filter_by(user_id=user_id, episode_id=episode_id).first()
    if existing:
        return existing
    purchase = EpisodePurchase(user_id=user_id, episode_id=episode_id, payment_id=payment_id)
    db.session.add(purchase)
    db.session.commit()
    return purchase


def grant_subscription(user_id: int, days: int = 30, payment_id: int | None = None) -> Subscription:
    now = datetime.utcnow()
    sub = Subscription(
        user_id=user_id,
        plan_type="monthly",
        starts_at=now,
        expires_at=now + timedelta(days=days),
        is_active=True,
        payment_id=payment_id,
    )
    db.session.add(sub)
    db.session.commit()
    return sub


def purchase_episode(user, episode: Episode) -> dict:
    if episode.is_free:
        return {"success": True, "message": "Episode is free"}

    existing = EpisodePurchase.query.filter_by(user_id=user.id, episode_id=episode.id).first()
    if existing:
        return {"success": True, "message": "Already purchased"}

    provider = get_payment_provider()
    result = provider.create_checkout(
        user=user,
        amount=episode.price,
        payment_type="episode",
        reference_id=str(episode.id),
    )

    if provider.is_configured() and isinstance(provider, ManualPaymentProvider):
        payment = Payment.query.get(result["payment_id"])
        approve_payment(payment)
        grant_episode_purchase(user.id, episode.id, payment.id)
        return {"success": True, "message": "Purchase recorded (manual mode)", "payment_id": payment.id}

    return {"success": False, "message": "Payment pending approval", **result}


def admin_grant_episode(user_id: int, episode_id: int) -> EpisodePurchase:
    payment = Payment(
        user_id=user_id,
        amount=0,
        payment_type="episode",
        reference_id=str(episode_id),
        method="manual",
        status="paid",
        paid_at=datetime.utcnow(),
        metadata_json=json.dumps({"granted_by": "admin"}),
    )
    payment.sync_legacy_fields()
    db.session.add(payment)
    db.session.flush()
    return grant_episode_purchase(user_id, episode_id, payment.id)


def admin_grant_subscription(user_id: int, days: int = 30) -> Subscription:
    payment = Payment(
        user_id=user_id,
        amount=0,
        payment_type="subscription",
        method="manual",
        status="paid",
        paid_at=datetime.utcnow(),
        metadata_json=json.dumps({"granted_by": "admin", "days": days}),
    )
    payment.sync_legacy_fields()
    db.session.add(payment)
    db.session.flush()
    return grant_subscription(user_id, days, payment.id)

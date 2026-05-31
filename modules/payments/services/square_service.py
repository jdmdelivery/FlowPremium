"""Square Cash App Pay integration (optional)."""

from __future__ import annotations

import json
import logging
import uuid
import urllib.error
import urllib.request

from flask import current_app

from extensions import db
from modules.payments.services.billing import activate_payment_benefits, fail_payment, mark_payment_paid
from modules.streaming.models import Payment

logger = logging.getLogger(__name__)


def is_square_configured() -> bool:
    return bool(
        current_app.config.get("SQUARE_ACCESS_TOKEN")
        and current_app.config.get("SQUARE_APPLICATION_ID")
        and current_app.config.get("SQUARE_LOCATION_ID")
    )


def _api_base() -> str:
    env = (current_app.config.get("SQUARE_ENV") or "sandbox").lower()
    if env == "production":
        return "https://connect.squareup.com"
    return "https://connect.squareupsandbox.com"


def public_config() -> dict | None:
    if not is_square_configured():
        return None
    return {
        "application_id": current_app.config["SQUARE_APPLICATION_ID"],
        "location_id": current_app.config["SQUARE_LOCATION_ID"],
        "environment": current_app.config.get("SQUARE_ENV", "sandbox"),
    }


def charge_square_payment(payment: Payment, source_id: str) -> Payment:
    if not is_square_configured():
        raise RuntimeError("Square is not configured")
    if payment.method != "square_cashapp":
        raise ValueError("Invalid payment method")
    if payment.status != "pending":
        raise ValueError("Payment is not pending")

    amount_cents = int(round(payment.amount * 100))
    payload = {
        "idempotency_key": str(uuid.uuid4()),
        "source_id": source_id,
        "amount_money": {"amount": amount_cents, "currency": payment.currency},
        "location_id": current_app.config["SQUARE_LOCATION_ID"],
        "reference_id": payment.reference_code,
        "note": f"FlowPremium {payment.reference_id or payment.payment_type}",
    }

    url = f"{_api_base()}/v2/payments"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {current_app.config['SQUARE_ACCESS_TOKEN']}",
            "Content-Type": "application/json",
            "Square-Version": "2024-01-18",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.error("Square payment error: %s", detail)
        fail_payment(payment, "Square charge failed")
        raise RuntimeError("Square payment failed") from exc

    square_payment = result.get("payment", {})
    if square_payment.get("status") != "COMPLETED":
        fail_payment(payment, f"Square status {square_payment.get('status')}")
        raise ValueError("Square payment not completed")

    mark_payment_paid(payment, provider_payment_id=square_payment.get("id"))
    activate_payment_benefits(payment)
    return payment

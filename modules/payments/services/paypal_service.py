"""PayPal Checkout Orders API integration."""

from __future__ import annotations

import logging

import requests
from flask import current_app

from extensions import db
from modules.payments.services.billing import activate_payment_benefits, fail_payment, mark_payment_paid
from modules.streaming.models import Payment

logger = logging.getLogger(__name__)


def is_paypal_configured() -> bool:
    client_id = (current_app.config.get("PAYPAL_CLIENT_ID") or "").strip()
    secret = (current_app.config.get("PAYPAL_CLIENT_SECRET") or "").strip()
    return bool(client_id and secret)


def paypal_mode() -> str:
    return (current_app.config.get("PAYPAL_MODE") or "sandbox").lower()


def api_base() -> str:
    if paypal_mode() == "live":
        return "https://api-m.paypal.com"
    return "https://api-m.sandbox.paypal.com"


def sdk_base() -> str:
    """PayPal JS SDK host (sandbox uses same CDN; credentials determine environment)."""
    return "https://www.paypal.com"


def verify_paypal_connection() -> tuple[bool, str]:
    """Validate credentials by requesting an OAuth token."""
    if not is_paypal_configured():
        return False, "PayPal credentials not configured"
    try:
        get_access_token()
        return True, "PayPal connection OK"
    except RuntimeError as exc:
        return False, str(exc)


def _request(method: str, path: str, payload: dict | None = None, token: str | None = None) -> dict:
    url = f"{api_base()}{path}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = requests.request(method, url, json=payload, headers=headers, timeout=30)
        if resp.status_code >= 400:
            logger.error("PayPal HTTP error %s: %s", resp.status_code, resp.text)
            raise RuntimeError(f"PayPal API error: {resp.status_code}")
        return resp.json() if resp.text else {}
    except requests.RequestException as exc:
        logger.error("PayPal network error: %s", exc)
        raise RuntimeError("PayPal network error") from exc


def get_access_token() -> str:
    client_id = current_app.config["PAYPAL_CLIENT_ID"]
    secret = current_app.config["PAYPAL_CLIENT_SECRET"]
    try:
        resp = requests.post(
            f"{api_base()}/v1/oauth2/token",
            auth=(client_id, secret),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
            timeout=30,
        )
        if resp.status_code >= 400:
            logger.error("PayPal token error: %s", resp.text)
            raise RuntimeError("PayPal authentication failed")
        return resp.json()["access_token"]
    except requests.RequestException as exc:
        logger.error("PayPal token network error: %s", exc)
        raise RuntimeError("PayPal authentication failed") from exc


def create_paypal_order(payment: Payment) -> dict:
    if not is_paypal_configured():
        raise RuntimeError("PayPal is not configured")

    token = get_access_token()
    amount = f"{payment.amount:.2f}"
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": payment.reference_code,
                "custom_id": str(payment.id),
                "amount": {
                    "currency_code": payment.currency,
                    "value": amount,
                },
                "description": f"FlowPremium {payment.reference_id or payment.payment_type}",
            }
        ],
    }
    order = _request("POST", "/v2/checkout/orders", payload, token=token)
    payment.provider_payment_id = order.get("id")
    payment.method = "paypal"
    payment.sync_legacy_fields()
    db.session.commit()
    return order


def capture_paypal_order(order_id: str, payment_id: int) -> Payment:
    if not is_paypal_configured():
        raise RuntimeError("PayPal is not configured")

    payment = db.session.get(Payment, payment_id)
    if not payment:
        raise ValueError("Payment not found")
    if payment.method != "paypal":
        raise ValueError("Invalid payment method")
    if payment.status != "pending":
        raise ValueError("Payment is not pending")
    if payment.provider_payment_id and payment.provider_payment_id != order_id:
        raise ValueError("Order mismatch")

    token = get_access_token()
    try:
        result = _request("POST", f"/v2/checkout/orders/{order_id}/capture", {}, token=token)
    except RuntimeError:
        fail_payment(payment, "PayPal capture failed")
        raise

    status = result.get("status")
    if status != "COMPLETED":
        fail_payment(payment, f"PayPal status {status}")
        raise ValueError("PayPal payment not completed")

    capture_id = order_id
    try:
        capture_id = result["purchase_units"][0]["payments"]["captures"][0]["id"]
    except (KeyError, IndexError, TypeError):
        pass

    mark_payment_paid(payment, provider_payment_id=capture_id)
    activate_payment_benefits(payment)
    return payment

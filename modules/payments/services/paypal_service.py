"""PayPal Checkout Orders API integration."""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request

from flask import current_app

from extensions import db
from modules.payments.services.billing import activate_payment_benefits, fail_payment, mark_payment_paid
from modules.streaming.models import Payment

logger = logging.getLogger(__name__)


def is_paypal_configured() -> bool:
    return bool(
        current_app.config.get("PAYPAL_CLIENT_ID")
        and current_app.config.get("PAYPAL_CLIENT_SECRET")
    )


def _api_base() -> str:
    mode = (current_app.config.get("PAYPAL_MODE") or "sandbox").lower()
    if mode == "live":
        return "https://api-m.paypal.com"
    return "https://api-m.sandbox.paypal.com"


def _request(method: str, path: str, payload: dict | None = None, token: str | None = None) -> dict:
    url = f"{_api_base()}{path}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.error("PayPal HTTP error %s: %s", exc.code, detail)
        raise RuntimeError(f"PayPal API error: {exc.code}") from exc
    except urllib.error.URLError as exc:
        logger.error("PayPal network error: %s", exc)
        raise RuntimeError("PayPal network error") from exc


def get_access_token() -> str:
    client_id = current_app.config["PAYPAL_CLIENT_ID"]
    secret = current_app.config["PAYPAL_CLIENT_SECRET"]
    credentials = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    url = f"{_api_base()}/v1/oauth2/token"
    req = urllib.request.Request(
        url,
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["access_token"]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.error("PayPal token error: %s", detail)
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

    capture_id = None
    try:
        capture_id = result["purchase_units"][0]["payments"]["captures"][0]["id"]
    except (KeyError, IndexError, TypeError):
        capture_id = order_id

    mark_payment_paid(payment, provider_payment_id=capture_id or order_id)
    activate_payment_benefits(payment)
    return payment

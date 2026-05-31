"""Public and API payment routes."""

from __future__ import annotations

import logging

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from extensions import db
from modules.payments.services.billing import (
    cancel_payment,
    create_pending_payment,
    get_plan_catalog,
    mark_payment_paid,
    payments_by_status,
    payment_totals,
    resolve_plan,
    submit_cashapp_reference,
)
from modules.payments.services.paypal_service import (
    capture_paypal_order,
    create_paypal_order,
    is_paypal_configured,
    paypal_mode,
    verify_paypal_connection,
)
from modules.payments.services.square_service import charge_square_payment, is_square_configured, public_config
from modules.streaming.models import Payment
from utils.auth import admin_required

logger = logging.getLogger(__name__)

payments_bp = Blueprint("payments", __name__)


def _payment_methods_context():
    configured = is_paypal_configured()
    return {
        "paypal_enabled": configured,
        "paypal_client_id": current_app.config.get("PAYPAL_CLIENT_ID") if configured else None,
        "paypal_mode": paypal_mode(),
        "cashapp_tag": current_app.config.get("CASHAPP_TAG") or "",
        "square_enabled": is_square_configured(),
        "square_config": public_config(),
    }


@payments_bp.route("/api/paypal/status")
def paypal_status():
    """Diagnostic endpoint: PayPal env vars and API connectivity."""
    mode = paypal_mode()
    client_id = (current_app.config.get("PAYPAL_CLIENT_ID") or "").strip()
    secret_set = bool((current_app.config.get("PAYPAL_CLIENT_SECRET") or "").strip())

    if not is_paypal_configured():
        return jsonify(
            {
                "configured": False,
                "ready": False,
                "mode": mode,
                "client_id_set": bool(client_id),
                "client_secret_set": secret_set,
                "message": "PayPal credentials not configured",
            }
        )

    ready, message = verify_paypal_connection()
    return jsonify(
        {
            "configured": True,
            "ready": ready,
            "mode": mode,
            "client_id_set": True,
            "client_secret_set": secret_set,
            "message": message,
        }
    )


@payments_bp.route("/payments")
def payments_index():
    plans = get_plan_catalog()
    selected_plan = request.args.get("plan", "monthly")
    if selected_plan not in plans:
        selected_plan = next(iter(plans.keys()), "monthly")
    return render_template(
        "payments/index.html",
        plans=plans,
        selected_plan=selected_plan,
        **_payment_methods_context(),
    )


@payments_bp.route("/payments/status/<int:payment_id>")
def payment_status(payment_id):
    payment = db.session.get(Payment, payment_id)
    if not payment:
        flash("Pago no encontrado / Payment not found", "error")
        return redirect(url_for("payments.payments_index"))
    return render_template("payments/status.html", payment=payment, **_payment_methods_context())


@payments_bp.route("/payments/cashapp/start", methods=["POST"])
def cashapp_start():
    plan_id = request.form.get("plan_id", "monthly")
    try:
        payment = create_pending_payment(
            plan_id=plan_id,
            method="cashapp_manual",
            customer_name=request.form.get("customer_name"),
            customer_email=request.form.get("customer_email"),
        )
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("payments.payments_index", plan=plan_id))

    return render_template(
        "payments/cashapp.html",
        payment=payment,
        cashapp_tag=current_app.config.get("CASHAPP_TAG") or "",
    )


@payments_bp.route("/payments/cashapp/confirm", methods=["POST"])
def cashapp_confirm():
    payment_id = int(request.form.get("payment_id", 0))
    note = request.form.get("reference_note", "")
    try:
        payment = submit_cashapp_reference(payment_id, note)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("payments.payments_index"))
    flash(
        "Referencia enviada. Tu servicio se activa cuando el pago sea confirmado.",
        "success",
    )
    return redirect(url_for("payments.payment_status", payment_id=payment.id))


@payments_bp.route("/api/paypal/create-order", methods=["POST"])
def paypal_create_order():
    if not is_paypal_configured():
        return jsonify({"error": "PayPal not configured"}), 503

    data = request.get_json(silent=True) or {}
    plan_id = data.get("plan_id", "monthly")

    try:
        payment = create_pending_payment(
            plan_id=plan_id,
            method="paypal",
            customer_name=data.get("customer_name"),
            customer_email=data.get("customer_email"),
        )
        order = create_paypal_order(payment)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        logger.exception("PayPal create order failed")
        return jsonify({"error": str(exc)}), 502

    return jsonify(
        {
            "order_id": order.get("id"),
            "payment_id": payment.id,
            "amount": payment.amount,
            "currency": payment.currency,
        }
    )


@payments_bp.route("/api/paypal/capture-order", methods=["POST"])
def paypal_capture_order():
    if not is_paypal_configured():
        return jsonify({"error": "PayPal not configured"}), 503

    data = request.get_json(silent=True) or {}
    order_id = data.get("order_id")
    payment_id = data.get("payment_id")
    if not order_id or not payment_id:
        return jsonify({"error": "order_id and payment_id required"}), 400

    try:
        payment = capture_paypal_order(order_id, int(payment_id))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        logger.exception("PayPal capture failed")
        return jsonify({"error": str(exc)}), 502

    return jsonify({"status": payment.status, "payment_id": payment.id})


@payments_bp.route("/api/square/charge", methods=["POST"])
def square_charge():
    if not is_square_configured():
        return jsonify({"error": "Square not configured"}), 503

    data = request.get_json(silent=True) or {}
    source_id = data.get("source_id")
    plan_id = data.get("plan_id", "monthly")
    if not source_id:
        return jsonify({"error": "source_id required"}), 400

    try:
        payment = create_pending_payment(
            plan_id=plan_id,
            method="square_cashapp",
            customer_name=data.get("customer_name"),
            customer_email=data.get("customer_email"),
        )
        payment = charge_square_payment(payment, source_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        logger.exception("Square charge failed")
        return jsonify({"error": str(exc)}), 502

    return jsonify({"status": payment.status, "payment_id": payment.id})


@payments_bp.route("/admin/payments")
@admin_required
def admin_payments():
    status_filter = request.args.get("status")
    totals = payment_totals()
    return render_template(
        "payments/admin.html",
        payments=payments_by_status(status_filter),
        status_filter=status_filter,
        totals=totals,
        pending_count=Payment.query.filter_by(status="pending").count(),
        paid_count=Payment.query.filter_by(status="paid").count(),
        failed_count=Payment.query.filter_by(status="failed").count(),
    )


@payments_bp.route("/admin/payments/<int:payment_id>/mark-paid", methods=["POST"])
@admin_required
def admin_mark_paid(payment_id):
    payment = db.session.get(Payment, payment_id)
    if not payment:
        flash("Pago no encontrado", "error")
        return redirect(url_for("payments.admin_payments"))
    if payment.method != "cashapp_manual":
        flash("Solo pagos Cash App manual", "error")
        return redirect(url_for("payments.admin_payments"))
    try:
        from modules.payments.services.billing import activate_payment_benefits

        mark_payment_paid(payment)
        activate_payment_benefits(payment)
        flash("Cash App marcado como pagado", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    status = request.form.get("status_filter") or None
    return redirect(url_for("payments.admin_payments", status=status))


@payments_bp.route("/admin/payments/<int:payment_id>/cancel", methods=["POST"])
@admin_required
def admin_cancel(payment_id):
    payment = db.session.get(Payment, payment_id)
    if not payment:
        flash("Pago no encontrado", "error")
        return redirect(url_for("payments.admin_payments"))
    try:
        cancel_payment(payment)
        flash("Pago cancelado", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    status = request.form.get("status_filter") or None
    return redirect(url_for("payments.admin_payments", status=status))

"""Payment flow tests."""

from extensions import db
from modules.streaming.models import EpisodePurchase, Payment


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_payments_page_renders(client):
    resp = client.get("/payments")
    assert resp.status_code == 200
    assert b"PayPal" in resp.data
    assert b"Cash App" in resp.data


def test_create_cashapp_manual_payment(client, app):
    with app.app_context():
        app.config["CASHAPP_TAG"] = "$FlowPremium"

    resp = client.post(
        "/payments/cashapp/start",
        data={
            "plan_id": "monthly",
            "customer_name": "Guest User",
            "customer_email": "guest@test.com",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert b"FP-" in resp.data

    with app.app_context():
        payment = Payment.query.filter_by(method="cashapp_manual").first()
        assert payment is not None
        assert payment.status == "pending"
        assert payment.amount == 9.99
        assert payment.reference_code.startswith("FP-")


def test_admin_mark_cashapp_paid(admin_client, app):
    with app.app_context():
        payment = Payment(
            user_id=1,
            customer_email="paid@test.com",
            amount=9.99,
            currency="USD",
            method="cashapp_manual",
            status="pending",
            payment_type="plan",
            reference_id="monthly",
            reference_note="FP-000001",
        )
        payment.sync_legacy_fields()
        db.session.add(payment)
        db.session.commit()
        payment_id = payment.id

    resp = admin_client.post(
        f"/admin/payments/{payment_id}/mark-paid",
        data={"status_filter": "pending"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        payment = db.session.get(Payment, payment_id)
        assert payment.status == "paid"
        assert payment.paid_at is not None


def test_admin_cancel_payment(admin_client, app):
    with app.app_context():
        payment = Payment(
            user_id=1,
            amount=9.99,
            method="cashapp_manual",
            status="pending",
            payment_type="plan",
            reference_id="monthly",
        )
        payment.sync_legacy_fields()
        db.session.add(payment)
        db.session.commit()
        payment_id = payment.id

    resp = admin_client.post(
        f"/admin/payments/{payment_id}/cancel",
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        payment = db.session.get(Payment, payment_id)
        assert payment.status == "cancelled"


def test_paypal_create_order_without_credentials(client):
    resp = client.post(
        "/api/paypal/create-order",
        json={"plan_id": "monthly", "customer_email": "x@test.com"},
    )
    assert resp.status_code == 503
    assert "not configured" in resp.get_json()["error"].lower()


def test_paypal_create_order_rejects_bad_plan(client, app):
    with app.app_context():
        app.config["PAYPAL_CLIENT_ID"] = "test-id"
        app.config["PAYPAL_CLIENT_SECRET"] = "test-secret"

    resp = client.post(
        "/api/paypal/create-order",
        json={"plan_id": "invalid", "customer_email": "x@test.com"},
    )
    assert resp.status_code == 400


def test_episode_purchase_redirects_to_paypal_checkout(user_client, app, sample_content):
    with app.app_context():
        app.config["PAYPAL_CLIENT_ID"] = "test-id"
        app.config["PAYPAL_CLIENT_SECRET"] = "test-secret"

    ep_id = sample_content["premium_episode_id"]
    resp = user_client.post(f"/streaming/purchase/{ep_id}", follow_redirects=False)
    assert resp.status_code == 302
    assert f"/streaming/checkout/{ep_id}" in resp.location


def test_episode_checkout_page(user_client, app, sample_content):
    with app.app_context():
        app.config["PAYPAL_CLIENT_ID"] = "test-id"
        app.config["PAYPAL_CLIENT_SECRET"] = "test-secret"

    ep_id = sample_content["premium_episode_id"]
    resp = user_client.get(f"/streaming/checkout/{ep_id}")
    assert resp.status_code == 200
    assert b"paypal.com/sdk/js" in resp.data
    assert b"Pagar con PayPal" in resp.data or b"Pay with PayPal" in resp.data
    assert b"Pagar con Cash App" in resp.data or b"Pay with Cash App" in resp.data


def test_episode_checkout_cashapp_only(user_client, app, sample_content):
    with app.app_context():
        app.config["PAYPAL_CLIENT_ID"] = ""
        app.config["PAYPAL_CLIENT_SECRET"] = ""
        app.config["CASHAPP_TAG"] = "$Thelion02"

    ep_id = sample_content["premium_episode_id"]
    resp = user_client.get(f"/streaming/checkout/{ep_id}")
    assert resp.status_code == 200
    assert b"cash.app/$Thelion02" in resp.data
    assert b"Ya envi" in resp.data or b"already sent" in resp.data.lower()


def test_episode_cashapp_submit_and_admin_approve(user_client, admin_client, app, sample_content):
    with app.app_context():
        app.config["CASHAPP_TAG"] = "$Thelion02"

    ep_id = sample_content["premium_episode_id"]
    resp = user_client.post(
        f"/streaming/checkout/{ep_id}/cashapp",
        data={
            "customer_name": "user",
            "customer_email": "user@test.com",
            "reference": "Test payment note",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        payment = Payment.query.filter_by(
            method="cashapp_manual", payment_type="episode", status="pending"
        ).first()
        assert payment is not None
        assert payment.reference_id == str(ep_id)
        assert payment.amount == 9.99
        assert "Test payment note" in (payment.reference_note or "")
        payment_id = payment.id

    resp = admin_client.post(
        f"/admin/payments/{payment_id}/approve",
        data={"status_filter": "pending"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        payment = db.session.get(Payment, payment_id)
        assert payment.status == "paid"
        purchase = EpisodePurchase.query.filter_by(
            user_id=payment.user_id, episode_id=ep_id
        ).first()
        assert purchase is not None


def test_admin_cashapp_panel(admin_client, app):
    with app.app_context():
        payment = Payment(
            user_id=2,
            customer_email="user@test.com",
            amount=9.99,
            method="cashapp_manual",
            status="pending",
            payment_type="episode",
            reference_id="1",
            reference_note="FP-000099 | test",
        )
        payment.sync_legacy_fields()
        db.session.add(payment)
        db.session.commit()

    resp = admin_client.get("/admin/payments/cashapp")
    assert resp.status_code == 200
    assert b"Pagos Cash App" in resp.data or b"Cash App Payments" in resp.data


def test_paypal_status_not_configured(client):
    resp = client.get("/api/paypal/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["configured"] is False
    assert data["ready"] is False


def test_paypal_status_configured(monkeypatch, client, app):
    with app.app_context():
        app.config["PAYPAL_CLIENT_ID"] = "test-client"
        app.config["PAYPAL_CLIENT_SECRET"] = "test-secret"
        app.config["PAYPAL_MODE"] = "sandbox"

    monkeypatch.setattr(
        "modules.payments.routes.verify_paypal_connection",
        lambda: (True, "PayPal connection OK"),
    )

    resp = client.get("/api/paypal/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["configured"] is True
    assert data["ready"] is True
    assert data["mode"] == "sandbox"


def test_payments_page_hides_paypal_without_credentials(client):
    resp = client.get("/payments")
    assert resp.status_code == 200
    assert b"paypal.com/sdk/js" not in resp.data
    assert b"not configured" in resp.data.lower() or b"No configurado" in resp.data


def test_payments_page_loads_paypal_sdk_when_configured(client, app):
    with app.app_context():
        app.config["PAYPAL_CLIENT_ID"] = "sandbox-client-id"
        app.config["PAYPAL_CLIENT_SECRET"] = "sandbox-secret"

    resp = client.get("/payments")
    assert resp.status_code == 200
    assert b"paypal.com/sdk/js" in resp.data
    assert b"Pagar con PayPal" in resp.data or b"Pay with PayPal" in resp.data


def test_admin_payments_panel(admin_client):
    resp = admin_client.get("/admin/payments")
    assert resp.status_code == 200
    assert b"Total" in resp.data or b"total" in resp.data.lower()


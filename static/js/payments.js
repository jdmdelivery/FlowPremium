(function () {
    "use strict";

    const cfg = window.FLOWPREMIUM_PAYMENTS || {};

    function selectedPlan() {
        const checked = document.querySelector('input[name="plan_id"]:checked');
        return checked ? checked.value : cfg.selectedPlan || "monthly";
    }

    function guestFields() {
        const name = document.querySelector('input[name="customer_name"]');
        const email = document.querySelector('input[name="customer_email"]');
        return {
            customer_name: name ? name.value : undefined,
            customer_email: email ? email.value : undefined,
        };
    }

    function syncCashAppForm() {
        const planInput = document.getElementById("cashapp-plan");
        if (planInput) planInput.value = selectedPlan();
        const name = document.querySelector(".sync-name");
        const email = document.querySelector(".sync-email");
        const nameSrc = document.querySelector('input[name="customer_name"]');
        const emailSrc = document.querySelector('input[name="customer_email"]');
        if (name && nameSrc) name.value = nameSrc.value;
        if (email && emailSrc) email.value = emailSrc.value;
    }

    document.querySelectorAll('input[name="plan_id"]').forEach((radio) => {
        radio.addEventListener("change", () => {
            document.querySelectorAll(".plan-option").forEach((el) => el.classList.remove("active"));
            radio.closest(".plan-option")?.classList.add("active");
            syncCashAppForm();
        });
    });

    document.querySelector('form[action*="cashapp/start"]')?.addEventListener("submit", syncCashAppForm);

    async function postJson(url, payload) {
        const res = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || "Request failed");
        return data;
    }

    if (cfg.paypalEnabled && window.paypal) {
        paypal.Buttons({
            createOrder: async () => {
                const data = await postJson(cfg.createOrderUrl, {
                    plan_id: selectedPlan(),
                    ...guestFields(),
                });
                window.__fpPaymentId = data.payment_id;
                return data.order_id;
            },
            onApprove: async (data) => {
                const capture = await postJson(cfg.captureOrderUrl, {
                    order_id: data.orderID,
                    payment_id: window.__fpPaymentId,
                });
                if (capture.payment_id) {
                    window.location.href = cfg.statusUrl + "/" + capture.payment_id;
                }
            },
            onError: (err) => {
                console.error("PayPal error", err);
                alert("PayPal payment failed. Try again.");
            },
        }).render("#paypal-button-container");
    }

    async function initSquare() {
        if (!cfg.squareEnabled || !cfg.squareConfig || !window.Square) return;
        const payments = Square.payments(cfg.squareConfig.application_id, cfg.squareConfig.location_id);
        const cashApp = await payments.cashAppPay({
            redirectURL: window.location.href,
            referenceId: "FP-" + Date.now(),
        });
        await cashApp.attach("#square-cash-app-button", {
            shape: "semiround",
            width: "full",
        });
        cashApp.addEventListener("ontokenization", async (event) => {
            if (event.detail.status !== "OK") return;
            try {
                const result = await postJson(cfg.squareChargeUrl, {
                    source_id: event.detail.token,
                    plan_id: selectedPlan(),
                    ...guestFields(),
                });
                window.location.href = cfg.statusUrl + "/" + result.payment_id;
            } catch (err) {
                console.error(err);
                alert(err.message || "Square payment failed");
            }
        });
    }

    initSquare().catch((err) => console.warn("Square init skipped", err));
})();

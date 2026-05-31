(function () {
    "use strict";

    const cfg = window.FLOWPREMIUM_EPISODE_CHECKOUT;
    if (!cfg) return;

    const toggleBtn = document.getElementById("cashapp-toggle-form");
    const form = document.getElementById("cashapp-episode-form");
    if (toggleBtn && form) {
        toggleBtn.addEventListener("click", () => {
            form.classList.toggle("hidden");
            toggleBtn.setAttribute(
                "aria-expanded",
                form.classList.contains("hidden") ? "false" : "true"
            );
        });
    }

    if (!cfg.paypalEnabled || !window.paypal) return;

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

    paypal.Buttons({
        createOrder: async () => {
            const data = await postJson(cfg.createOrderUrl, { episode_id: cfg.episodeId });
            window.__fpPaymentId = data.payment_id;
            return data.order_id;
        },
        onApprove: async (data) => {
            await postJson(cfg.captureOrderUrl, {
                order_id: data.orderID,
                payment_id: window.__fpPaymentId,
            });
            window.location.href = cfg.watchUrl;
        },
        onError: (err) => {
            console.error("PayPal error", err);
            alert("PayPal payment failed. Try again.");
        },
    }).render("#paypal-button-container");
})();

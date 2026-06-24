"""Public legal pages required for Google AdSense and site compliance."""

from flask import Blueprint, render_template

legal_bp = Blueprint("legal", __name__)


@legal_bp.route("/privacy-policy")
def privacy_policy():
    return render_template("legal/privacy_policy.html")


@legal_bp.route("/terms")
def terms():
    return render_template("legal/terms.html")


@legal_bp.route("/contact")
def contact():
    from flask import current_app

    return render_template(
        "legal/contact.html",
        contact_email=current_app.config.get("CONTACT_EMAIL", ""),
    )

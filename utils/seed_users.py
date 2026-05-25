"""Seed default admin users (idempotent)."""

from extensions import db
from models.user import User

DEFAULT_USERS = (
    {
        "email": "admin@admin.com",
        "username": "admin",
        "password": "admin123",
        "is_admin": True,
    },
    {
        "email": "manager@admin.com",
        "username": "manager",
        "password": "manager123",
        "is_admin": True,
    },
)


def ensure_default_users() -> list[str]:
    """Create default users if they do not exist. Returns status messages."""
    messages: list[str] = []

    for spec in DEFAULT_USERS:
        existing = User.query.filter(
            (User.email == spec["email"]) | (User.username == spec["username"])
        ).first()
        if existing:
            messages.append(
                f"Skipped (already exists): {spec['username']} / {spec['email']}"
            )
            continue

        user = User(
            email=spec["email"],
            username=spec["username"],
            is_admin=spec["is_admin"],
        )
        user.set_password(spec["password"])
        db.session.add(user)
        messages.append(f"Created: {spec['username']} / {spec['email']}")

    db.session.commit()
    return messages

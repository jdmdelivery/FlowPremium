from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "stream_users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    purchases = db.relationship("EpisodePurchase", back_populates="user", lazy="dynamic")
    subscriptions = db.relationship("Subscription", back_populates="user", lazy="dynamic")
    payments = db.relationship("Payment", back_populates="user", lazy="dynamic")
    watch_progress = db.relationship("WatchProgress", back_populates="user", lazy="dynamic")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


def get_user_by_id(user_id):
    """Flask-Login user_loader helper."""
    if user_id is None:
        return None
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None

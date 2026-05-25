from datetime import datetime

from extensions import db


class Series(db.Model):
    __tablename__ = "series"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    cover_image = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    seasons = db.relationship(
        "Season", back_populates="series", lazy="dynamic", cascade="all, delete-orphan"
    )
    episodes = db.relationship(
        "Episode", back_populates="series", lazy="dynamic", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Series {self.title}>"


class Season(db.Model):
    __tablename__ = "seasons"

    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(db.Integer, db.ForeignKey("series.id"), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    season_number = db.Column(db.Integer, default=1, nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    series = db.relationship("Series", back_populates="seasons")
    episodes = db.relationship(
        "Episode", back_populates="season", lazy="dynamic", cascade="all, delete-orphan"
    )


class Episode(db.Model):
    __tablename__ = "episodes"

    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(db.Integer, db.ForeignKey("series.id"), nullable=False, index=True)
    season_id = db.Column(db.Integer, db.ForeignKey("seasons.id"), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    video_path = db.Column(db.String(500))
    thumbnail = db.Column(db.String(500))
    duration_seconds = db.Column(db.Integer, default=0)
    price = db.Column(db.Float, default=0.0, nullable=False)
    is_free = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    series = db.relationship("Series", back_populates="episodes")
    season = db.relationship("Season", back_populates="episodes")
    purchases = db.relationship("EpisodePurchase", back_populates="episode", lazy="dynamic")

    @property
    def duration_formatted(self) -> str:
        mins, secs = divmod(self.duration_seconds or 0, 60)
        return f"{mins}:{secs:02d}"

    def display_thumbnail(self) -> str | None:
        """Episode thumbnail, or fallback to this episode's series cover only."""
        if self.thumbnail:
            return self.thumbnail
        if self.series and self.series.cover_image:
            return self.series.cover_image
        return None


class EpisodePurchase(db.Model):
    __tablename__ = "episode_purchases"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    episode_id = db.Column(db.Integer, db.ForeignKey("episodes.id"), nullable=False, index=True)
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"))
    purchased_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="purchases")
    episode = db.relationship("Episode", back_populates="purchases")
    payment = db.relationship("Payment", back_populates="episode_purchases")

    __table_args__ = (db.UniqueConstraint("user_id", "episode_id"),)


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    plan_type = db.Column(db.String(50), default="monthly", nullable=False)
    starts_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="subscriptions")
    payment = db.relationship("Payment", back_populates="subscriptions")

    @property
    def is_valid(self) -> bool:
        now = datetime.utcnow()
        return self.is_active and self.starts_at <= now <= self.expires_at


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default="USD", nullable=False)
    payment_type = db.Column(db.String(50), nullable=False)
    reference_id = db.Column(db.String(255))
    provider = db.Column(db.String(50), default="manual", nullable=False)
    status = db.Column(db.String(50), default="pending", nullable=False)
    metadata_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    approved_at = db.Column(db.DateTime)

    user = db.relationship("User", back_populates="payments")
    episode_purchases = db.relationship("EpisodePurchase", back_populates="payment", lazy="dynamic")
    subscriptions = db.relationship("Subscription", back_populates="payment", lazy="dynamic")


class WatchProgress(db.Model):
    __tablename__ = "watch_progress"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    episode_id = db.Column(db.Integer, db.ForeignKey("episodes.id"), nullable=False)
    position_seconds = db.Column(db.Integer, default=0, nullable=False)
    completed = db.Column(db.Boolean, default=False, nullable=False)
    completed_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="watch_progress")
    episode = db.relationship("Episode")

    __table_args__ = (db.UniqueConstraint("user_id", "episode_id"),)

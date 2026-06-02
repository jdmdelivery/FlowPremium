from datetime import datetime

from extensions import db


class Series(db.Model):
    __tablename__ = "stream_series"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    cover_image = db.Column(db.String(500))
    thumbnail_url = db.Column(db.String(1000))
    hero_image_url = db.Column(db.String(1000))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    seasons = db.relationship(
        "Season", back_populates="series", lazy="dynamic", cascade="all, delete-orphan"
    )
    episodes = db.relationship(
        "Episode", back_populates="series", lazy="dynamic", cascade="all, delete-orphan"
    )

    def first_episode_thumbnail_key(self) -> str | None:
        ep = (
            Episode.query.filter_by(series_id=self.id, is_active=True)
            .order_by(Episode.id)
            .first()
        )
        return ep.thumbnail_url if ep else None

    def card_image_key(self) -> str | None:
        return (
            self.thumbnail_url
            or self.hero_image_url
            or self.cover_image
            or self.first_episode_thumbnail_key()
        )

    def hero_image_key(self) -> str | None:
        return (
            self.hero_image_url
            or self.thumbnail_url
            or self.cover_image
            or self.first_episode_thumbnail_key()
        )

    def __repr__(self) -> str:
        return f"<Series {self.title}>"


class Season(db.Model):
    __tablename__ = "stream_seasons"

    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(
        db.Integer, db.ForeignKey("stream_series.id"), nullable=False, index=True
    )
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
    __tablename__ = "stream_episodes"

    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(
        db.Integer, db.ForeignKey("stream_series.id"), nullable=False, index=True
    )
    season_id = db.Column(
        db.Integer, db.ForeignKey("stream_seasons.id"), nullable=False, index=True
    )
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    video_url_r2 = db.Column(db.String(1000))
    thumbnail_url = db.Column(db.String(1000))
    subtitle_url = db.Column(db.String(1000))
    subtitle_status = db.Column(db.String(32), default="none", nullable=False)
    subtitle_lang = db.Column(db.String(16), default="es")
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

    @property
    def has_video(self) -> bool:
        return bool(self.video_url_r2)

    @property
    def has_subtitles(self) -> bool:
        return bool(self.subtitle_url) and self.subtitle_status == "ready"

    @property
    def video_url(self) -> str | None:
        return self.video_url_r2

    @video_url.setter
    def video_url(self, value: str | None) -> None:
        self.video_url_r2 = value

    def display_thumbnail(self) -> str | None:
        if self.thumbnail_url:
            return self.thumbnail_url
        if self.series:
            key = self.series.card_image_key()
            if key:
                return key
        return None


class EpisodePurchase(db.Model):
    __tablename__ = "stream_purchases"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("stream_users.id"), nullable=False, index=True
    )
    episode_id = db.Column(
        db.Integer, db.ForeignKey("stream_episodes.id"), nullable=False, index=True
    )
    payment_id = db.Column(db.Integer, db.ForeignKey("stream_payments.id"))
    purchased_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="purchases")
    episode = db.relationship("Episode", back_populates="purchases")
    payment = db.relationship("Payment", back_populates="episode_purchases")

    __table_args__ = (db.UniqueConstraint("user_id", "episode_id"),)


class Subscription(db.Model):
    __tablename__ = "stream_subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("stream_users.id"), nullable=False, index=True
    )
    plan_type = db.Column(db.String(50), default="monthly", nullable=False)
    starts_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    payment_id = db.Column(db.Integer, db.ForeignKey("stream_payments.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="subscriptions")
    payment = db.relationship("Payment", back_populates="subscriptions")

    @property
    def is_valid(self) -> bool:
        now = datetime.utcnow()
        return self.is_active and self.starts_at <= now <= self.expires_at


class Payment(db.Model):
    __tablename__ = "stream_payments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("stream_users.id"), nullable=True, index=True
    )
    customer_name = db.Column(db.String(255))
    customer_email = db.Column(db.String(255))
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default="USD", nullable=False)
    method = db.Column(db.String(50), default="manual", nullable=False)
    status = db.Column(db.String(50), default="pending", nullable=False)
    provider_payment_id = db.Column(db.String(255))
    reference_note = db.Column(db.String(500))
    screenshot_url = db.Column(db.String(1000))
    payment_type = db.Column(db.String(50), nullable=False, default="plan")
    reference_id = db.Column(db.String(255))
    metadata_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    paid_at = db.Column(db.DateTime)

    provider = db.Column(db.String(50))
    approved_at = db.Column(db.DateTime)

    user = db.relationship("User", back_populates="payments")
    episode_purchases = db.relationship("EpisodePurchase", back_populates="payment", lazy="dynamic")
    subscriptions = db.relationship("Subscription", back_populates="payment", lazy="dynamic")

    @property
    def reference_code(self) -> str:
        return f"FP-{self.id:06d}"

    @property
    def display_customer(self) -> str:
        if self.user:
            return self.user.username
        return self.customer_name or self.customer_email or "Guest"

    def sync_legacy_fields(self) -> None:
        self.provider = self.method
        self.approved_at = self.paid_at


class WatchProgress(db.Model):
    __tablename__ = "stream_watch_progress"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("stream_users.id"), nullable=False)
    episode_id = db.Column(
        db.Integer, db.ForeignKey("stream_episodes.id"), nullable=False
    )
    position_seconds = db.Column(db.Integer, default=0, nullable=False)
    completed = db.Column(db.Boolean, default=False, nullable=False)
    completed_at = db.Column(db.DateTime)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    user = db.relationship("User", back_populates="watch_progress")
    episode = db.relationship("Episode")

    __table_args__ = (db.UniqueConstraint("user_id", "episode_id"),)

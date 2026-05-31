-- FlowPremium PostgreSQL schema (stream_* tables)
-- Tables are created automatically via db.create_all() on deploy.

CREATE TABLE IF NOT EXISTS stream_users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    username VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stream_series (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    cover_image VARCHAR(500),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stream_seasons (
    id SERIAL PRIMARY KEY,
    series_id INTEGER NOT NULL REFERENCES stream_series(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    season_number INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stream_episodes (
    id SERIAL PRIMARY KEY,
    series_id INTEGER NOT NULL REFERENCES stream_series(id) ON DELETE CASCADE,
    season_id INTEGER NOT NULL REFERENCES stream_seasons(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    video_url_r2 VARCHAR(1000),
    thumbnail_url VARCHAR(1000),
    duration_seconds INTEGER DEFAULT 0,
    price DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    is_free BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stream_payments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES stream_users(id) ON DELETE SET NULL,
    customer_name VARCHAR(255),
    customer_email VARCHAR(255),
    amount DOUBLE PRECISION NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'USD',
    method VARCHAR(50) NOT NULL DEFAULT 'manual',
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    provider_payment_id VARCHAR(255),
    reference_note VARCHAR(500),
    payment_type VARCHAR(50) NOT NULL DEFAULT 'plan',
    reference_id VARCHAR(255),
    metadata_json TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMP,
    provider VARCHAR(50),
    approved_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stream_purchases (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES stream_users(id) ON DELETE CASCADE,
    episode_id INTEGER NOT NULL REFERENCES stream_episodes(id) ON DELETE CASCADE,
    payment_id INTEGER REFERENCES stream_payments(id) ON DELETE SET NULL,
    purchased_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, episode_id)
);

CREATE TABLE IF NOT EXISTS stream_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES stream_users(id) ON DELETE CASCADE,
    plan_type VARCHAR(50) NOT NULL DEFAULT 'monthly',
    starts_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    payment_id INTEGER REFERENCES stream_payments(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stream_watch_progress (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES stream_users(id) ON DELETE CASCADE,
    episode_id INTEGER NOT NULL REFERENCES stream_episodes(id) ON DELETE CASCADE,
    position_seconds INTEGER NOT NULL DEFAULT 0,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    completed_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, episode_id)
);

CREATE INDEX IF NOT EXISTS idx_stream_seasons_series ON stream_seasons(series_id);
CREATE INDEX IF NOT EXISTS idx_stream_episodes_series ON stream_episodes(series_id);
CREATE INDEX IF NOT EXISTS idx_stream_episodes_season ON stream_episodes(season_id);
CREATE INDEX IF NOT EXISTS idx_stream_purchases_user ON stream_purchases(user_id);
CREATE INDEX IF NOT EXISTS idx_stream_purchases_episode ON stream_purchases(episode_id);

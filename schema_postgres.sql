CREATE TABLE IF NOT EXISTS charities (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    tags TEXT NOT NULL,
    country TEXT NOT NULL,
    is_featured TEXT NOT NULL DEFAULT 'False',
    image_url TEXT NOT NULL,
    upcoming_event TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'subscriber',
    selected_charity_id BIGINT REFERENCES charities(id),
    charity_percentage INTEGER NOT NULL DEFAULT 10,
    country_code TEXT NOT NULL DEFAULT 'IN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan TEXT NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    charity_percent INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scores (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    score INTEGER NOT NULL,
    played_at DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS draws (
    id BIGSERIAL PRIMARY KEY,
    draw_month TEXT NOT NULL,
    mode TEXT NOT NULL,
    numbers TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    rollover_amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    simulated_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS winners (
    id BIGSERIAL PRIMARY KEY,
    draw_id BIGINT NOT NULL REFERENCES draws(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    match_count INTEGER NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    proof_path TEXT,
    verification_status TEXT NOT NULL DEFAULT 'awaiting-upload',
    payment_status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS donations (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    charity_id BIGINT NOT NULL REFERENCES charities(id) ON DELETE CASCADE,
    amount NUMERIC(10, 2) NOT NULL,
    donated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL
);

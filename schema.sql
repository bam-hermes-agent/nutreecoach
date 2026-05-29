-- =======================================================
-- NutreeCoach - Schema PostgreSQL
-- =======================================================
-- SQL pur, performant, relationnel. Pas de MongoDB ici.
-- =======================================================

-- Extension pour UUID
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =======================================================
-- 1. UTILISATEURS
-- =======================================================
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    telegram_id     BIGINT UNIQUE NOT NULL,
    username        TEXT,
    first_name      TEXT,
    language        TEXT DEFAULT 'fr',

    -- Profil physique
    gender          TEXT CHECK (gender IN ('male', 'female', 'other')),
    birth_date      DATE,
    height_cm       NUMERIC(5,1),
    activity_level  TEXT CHECK (activity_level IN ('sedentary', 'light', 'moderate', 'active', 'very_active')),

    -- Objectifs
    goal            TEXT CHECK (goal IN ('weight_loss', 'muscle_gain', 'recomposition', 'maintenance', 'general_health')),
    target_weight   NUMERIC(5,1),
    daily_calories  INTEGER,
    protein_g       NUMERIC(5,1),
    carbs_g         NUMERIC(5,1),
    fat_g           NUMERIC(5,1),

    -- Préférences alimentaires
    dietary_prefs   TEXT[] DEFAULT '{}',  -- {'vegetarian', 'vegan', 'gluten_free', ...}
    allergies       TEXT[] DEFAULT '{}',

    -- Abonnement
    subscription_tier   TEXT DEFAULT 'free' CHECK (subscription_tier IN ('free', 'premium', 'lifetime')),
    subscription_until  TIMESTAMPTZ,
    stars_paid          BIGINT DEFAULT 0,

    -- RGPD
    gdpr_consent        BOOLEAN DEFAULT FALSE,
    gdpr_consent_date   TIMESTAMPTZ,
    data_anonymized     BOOLEAN DEFAULT FALSE,

    -- Stats
    total_meals_logged  INTEGER DEFAULT 0,
    current_streak      INTEGER DEFAULT 0,
    longest_streak      INTEGER DEFAULT 0,
    last_active_at      TIMESTAMPTZ DEFAULT NOW(),

    -- Métadonnées
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_users_subscription ON users(subscription_tier) WHERE subscription_tier = 'premium';

-- =======================================================
-- 2. MESURES CORPORELLES (mensurations > poids seul)
-- =======================================================
CREATE TABLE body_measurements (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    measured_at     DATE NOT NULL DEFAULT CURRENT_DATE,

    -- Poids (toujours suivi)
    weight_kg       NUMERIC(5,2),

    -- Mensurations (les vraies valeurs)
    waist_cm        NUMERIC(5,1),
    hips_cm         NUMERIC(5,1),
    chest_cm        NUMERIC(5,1),
    left_arm_cm     NUMERIC(5,1),
    right_arm_cm    NUMERIC(5,1),
    left_thigh_cm   NUMERIC(5,1),
    right_thigh_cm  NUMERIC(5,1),
    neck_cm         NUMERIC(5,1),

    -- Photos de progression
    photo_path      TEXT,       -- Chemin local vers l'image

    -- Notes
    notes           TEXT,

    -- Métadonnées
    source          TEXT DEFAULT 'manual' CHECK (source IN ('manual', 'proactive_prompt', 'photo_analysis')),
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(user_id, measured_at)
);

CREATE INDEX idx_measurements_user_date ON body_measurements(user_id, measured_at DESC);

-- =======================================================
-- 3. REPAS LOGGÉS
-- =======================================================
CREATE TABLE meals (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    meal_date       DATE NOT NULL DEFAULT CURRENT_DATE,
    meal_type       TEXT NOT NULL CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack', 'other')),
    logged_at       TIMESTAMPTZ DEFAULT NOW(),

    -- Source
    source          TEXT CHECK (source IN ('text', 'barcode', 'photo', 'voice', 'manual')),

    -- Données flexibles en JSONB
    -- Contient: [{name:"riz", grams:150, kcal:195, protein:4.5, carbs:43, fat:0.3, source_api:"openfoodfacts", barcode:"123456"}]
    foods           JSONB NOT NULL DEFAULT '[]',

    -- Totaux calculés
    total_kcal      NUMERIC(7,1) NOT NULL,
    total_protein   NUMERIC(6,1),
    total_carbs     NUMERIC(6,1),
    total_fat       NUMERIC(6,1),

    -- Photo éphémère (supprimée après analyse)
    photo_path      TEXT,

    -- Métadonnées
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_meals_user_date ON meals(user_id, meal_date DESC);
CREATE INDEX idx_meals_user_recent ON meals(user_id, logged_at DESC) WHERE logged_at > NOW() - INTERVAL '7 days';

-- =======================================================
-- 4. SUIVI QUOTIDIEN (dénormalisé pour lecture rapide)
-- =======================================================
CREATE TABLE daily_progress (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date            DATE NOT NULL DEFAULT CURRENT_DATE,

    -- Calories
    calories_consumed   NUMERIC(7,1) DEFAULT 0,
    calories_goal       INTEGER,
    calories_remaining  NUMERIC(7,1),

    -- Macros
    protein_g       NUMERIC(6,1) DEFAULT 0,
    carbs_g         NUMERIC(6,1) DEFAULT 0,
    fat_g           NUMERIC(6,1) DEFAULT 0,

    -- Objectifs macros
    protein_goal    NUMERIC(5,1),
    carbs_goal      NUMERIC(5,1),
    fat_goal        NUMERIC(5,1),

    -- Repas
    meal_count      INTEGER DEFAULT 0,
    water_liters    NUMERIC(3,1),

    -- Bien-être
    mood            INTEGER CHECK (mood BETWEEN 1 AND 5),
    energy_level    INTEGER CHECK (energy_level BETWEEN 1 AND 5),
    notes           TEXT,

    -- Audit
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(user_id, date)
);

CREATE INDEX idx_daily_user_date ON daily_progress(user_id, date DESC);

-- =======================================================
-- 5. LOG DE COACHING (interactions IA Hermès)
-- =======================================================
CREATE TABLE coaching_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    interaction_at  TIMESTAMPTZ DEFAULT NOW(),

    -- Type de coaching
    interaction_type TEXT NOT NULL CHECK (interaction_type IN (
        'user_question', 'proactive_checkin', 'daily_summary',
        'motivation', 'slip_response', 'goal_setting', 'advice'
    )),

    -- Messages
    user_message    TEXT,
    coach_response  TEXT,

    -- Métriques
    tokens_used     INTEGER,
    response_time_ms INTEGER,
    user_rating     INTEGER CHECK (user_rating BETWEEN 1 AND 5),
    safety_flagged  BOOLEAN DEFAULT FALSE,  -- TCA ou hors-sujet ?

    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_coaching_user_date ON coaching_log(user_id, interaction_at DESC);

-- =======================================================
-- 6. ABONNEMENTS & PAIEMENTS
-- =======================================================
CREATE TABLE subscriptions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    telegram_payment_id TEXT UNIQUE,

    tier            TEXT NOT NULL CHECK (tier IN ('free', 'premium', 'lifetime')),
    stars_amount    BIGINT NOT NULL,
    currency        TEXT DEFAULT 'XTR',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,
    is_active       BOOLEAN DEFAULT TRUE,

    -- Statut
    status          TEXT DEFAULT 'completed' CHECK (status IN ('pending', 'completed', 'refunded', 'cancelled')),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_subscriptions_user ON subscriptions(user_id, is_active);

-- =======================================================
-- 7. CACHE DES ALIMENTS (OpenFoodFacts, USDA, etc.)
-- =======================================================
CREATE TABLE food_cache (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    barcode         TEXT UNIQUE,
    name            TEXT NOT NULL,
    brand           TEXT,
    category        TEXT,

    -- Nutrition pour 100g
    kcal_per_100g   NUMERIC(6,1),
    protein_per_100g NUMERIC(5,1),
    carbs_per_100g  NUMERIC(5,1),
    fat_per_100g    NUMERIC(5,1),
    fiber_per_100g  NUMERIC(5,1),

    -- Métadonnées
    source          TEXT NOT NULL CHECK (source IN ('openfoodfacts', 'usda', 'edamam', 'manual')),
    confidence      NUMERIC(3,2),
    serving_size_g  NUMERIC(5,1),
    raw_data        JSONB,
    last_updated    TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(barcode, source)
);

CREATE INDEX idx_food_barcode ON food_cache(barcode);
CREATE INDEX idx_food_name ON food_cache USING gin(to_tsvector('french', name));

-- =======================================================
-- VUES UTILES
-- =======================================================

-- Tendance de poids sur 14 jours (moyenne mobile)
CREATE VIEW weight_trend_14d AS
SELECT
    user_id,
    measured_at as date,
    weight_kg,
    AVG(weight_kg) OVER (
        PARTITION BY user_id
        ORDER BY measured_at
        ROWS 13 PRECEDING
    ) as moving_avg_14d,
    weight_kg - LAG(weight_kg, 7) OVER (
        PARTITION BY user_id
        ORDER BY measured_at
    ) as week_over_week_change
FROM body_measurements
WHERE weight_kg IS NOT NULL;

-- Rappel quotidien de pesée (utilisateurs n'ayant pas pesé aujourd'hui)
CREATE VIEW users_pending_weigh_in AS
SELECT u.id, u.telegram_id, u.first_name
FROM users u
LEFT JOIN body_measurements bm
    ON bm.user_id = u.id
    AND bm.measured_at = CURRENT_DATE
WHERE bm.id IS NULL
  AND u.gdpr_consent = TRUE;

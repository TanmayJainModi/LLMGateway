-- =====================================================
-- Teams
-- =====================================================

CREATE TABLE teams (
    id SERIAL PRIMARY KEY,
    team_name VARCHAR(100) NOT NULL,
    api_key VARCHAR(255) UNIQUE NOT NULL,
    monthly_budget DECIMAL(10,2) NOT NULL,
    monthly_spend DECIMAL(10,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- Providers
-- =====================================================

CREATE TABLE providers (
    id SERIAL PRIMARY KEY,
    provider_name VARCHAR(50) UNIQUE NOT NULL
);

-- =====================================================
-- Models
-- =====================================================

CREATE TABLE models (
    id SERIAL PRIMARY KEY,
    provider_id INTEGER NOT NULL
        REFERENCES providers(id)
        ON DELETE CASCADE,

    model_name VARCHAR(100) NOT NULL,

    UNIQUE(provider_id, model_name)
);

-- =====================================================
-- Team Model Access
-- =====================================================

CREATE TABLE team_model_access (

    id SERIAL PRIMARY KEY,

    team_id INTEGER NOT NULL
        REFERENCES teams(id)
        ON DELETE CASCADE,

    model_id INTEGER NOT NULL
        REFERENCES models(id)
        ON DELETE CASCADE,

    requests_per_minute INTEGER NOT NULL,
    requests_per_day INTEGER NOT NULL,

    max_input_tokens INTEGER,
    max_output_tokens INTEGER,

    enabled BOOLEAN DEFAULT TRUE,

    UNIQUE(team_id, model_id)
);

-- =====================================================
-- Usage
-- =====================================================

CREATE TABLE usage (

    id SERIAL PRIMARY KEY,

    team_id INTEGER
        REFERENCES teams(id)
        ON DELETE CASCADE,

    model_id INTEGER
        REFERENCES models(id)
        ON DELETE CASCADE,

    input_tokens INTEGER,
    output_tokens INTEGER,

    estimated_cost DECIMAL(10,6),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
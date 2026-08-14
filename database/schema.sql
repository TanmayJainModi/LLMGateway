-- =====================================================
-- Teams
-- =====================================================

CREATE TABLE teams (
    id SERIAL PRIMARY KEY,
    team_name VARCHAR(100) NOT NULL,
    api_key VARCHAR(255) UNIQUE NOT NULL,
    monthly_budget DECIMAL(10,2) NOT NULL,
    monthly_spend DECIMAL(10,2) DEFAULT 0,
    daily_budget DECIMAL(10,2),
    daily_spend DECIMAL(10,2) DEFAULT 0,
    daily_spend_date DATE DEFAULT CURRENT_DATE,
    
    -- Request Enrichment & Policy Enforcement Columns
    default_system_prompt TEXT,
    compliance_disclaimer TEXT,
    blocked_keywords TEXT[],
    enable_request_filter BOOLEAN DEFAULT TRUE,

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
    input_price_per_million_tokens DECIMAL(10,6) NOT NULL DEFAULT 0.0,
    output_price_per_million_tokens DECIMAL(10,6) NOT NULL DEFAULT 0.0,
    currency VARCHAR(10) NOT NULL DEFAULT 'USD',

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
    tokens_per_minute INTEGER NOT NULL DEFAULT 100000,

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

-- =====================================================
-- Admin Users
-- =====================================================

CREATE TABLE admin_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    admin_api_key VARCHAR(255) UNIQUE NOT NULL,
    role VARCHAR(50) DEFAULT 'admin',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- Audit Logs
-- =====================================================

CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    admin_user VARCHAR(100) NOT NULL,
    admin_email VARCHAR(255),
    ip_address VARCHAR(45),
    user_agent TEXT,
    action VARCHAR(100) NOT NULL,
    target_team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    reason TEXT,
    old_values JSONB,
    new_values JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- Team Alerts
-- =====================================================

CREATE TABLE team_alerts (
    id SERIAL PRIMARY KEY,
    team_id INTEGER REFERENCES teams(id) ON DELETE CASCADE,
    thresholds DECIMAL(5,2)[] NOT NULL DEFAULT '{80.0, 90.0, 95.0, 100.0}',
    alert_email VARCHAR(255),
    webhook_url VARCHAR(255),
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- Provider Health History (RCA & Auditing)
-- =====================================================

CREATE TABLE provider_health_history (
    id SERIAL PRIMARY KEY,
    provider_name VARCHAR(50) NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    previous_status VARCHAR(20),
    reason TEXT NOT NULL,
    latency_avg_ms INTEGER NOT NULL,
    latency_p99_ms INTEGER NOT NULL,
    error_rate_pct DECIMAL(5,2) NOT NULL,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
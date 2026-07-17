-- Optional: run in the Supabase SQL editor to pre-create tables.
-- (The app also auto-creates tables on first boot via SQLAlchemy; this file is
-- for reference / manual control.)

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'user',
    is_active BOOLEAN DEFAULT TRUE,
    api_key VARCHAR(64) UNIQUE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS drives (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    folder_id VARCHAR(255) NOT NULL,
    default_agency VARCHAR(64) DEFAULT '',
    is_active BOOLEAN DEFAULT TRUE,
    last_synced TIMESTAMPTZ,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    drive_id INTEGER REFERENCES drives(id),
    gfile_id VARCHAR(255) NOT NULL,
    name VARCHAR(512) NOT NULL,
    mime_type VARCHAR(128) DEFAULT '',
    file_size INTEGER DEFAULT 0,
    md5 VARCHAR(64) DEFAULT '',
    modified_time VARCHAR(64) DEFAULT '',
    status VARCHAR(20) DEFAULT 'pending',
    pages INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    error TEXT DEFAULT '',
    indexed_at TIMESTAMPTZ,
    UNIQUE (drive_id, gfile_id)
);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);

CREATE TABLE IF NOT EXISTS sync_jobs (
    id SERIAL PRIMARY KEY,
    job_type VARCHAR(20) DEFAULT 'delta',
    status VARCHAR(20) DEFAULT 'running',
    stats JSONB DEFAULT '{}',
    log TEXT DEFAULT '',
    started_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    title VARCHAR(255) DEFAULT 'New chat',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES chat_sessions(id),
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    sources JSONB DEFAULT '[]',
    model_used VARCHAR(128) DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS models (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(32) NOT NULL,
    model_id VARCHAR(255) NOT NULL,
    display_name VARCHAR(255) DEFAULT '',
    context_length INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    fetched_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (provider, model_id)
);

CREATE TABLE IF NOT EXISTS answer_cache (
    id SERIAL PRIMARY KEY,
    question_hash VARCHAR(64) UNIQUE NOT NULL,
    question TEXT NOT NULL,
    mode VARCHAR(10) DEFAULT 'auto',
    answer TEXT NOT NULL,
    sources JSONB DEFAULT '[]',
    model_used VARCHAR(128) DEFAULT '',
    embedding JSONB DEFAULT '[]',
    hits INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(64) NOT NULL,
    detail JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS settings (
    key VARCHAR(64) PRIMARY KEY,
    value TEXT DEFAULT ''
);

-- Database initialization for Multi-Agent Task Dispatch System

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Agents table
CREATE TABLE IF NOT EXISTS agents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    provider        VARCHAR(100) NOT NULL,
    name            VARCHAR(100) NOT NULL,
    display_name    VARCHAR(200),
    description     TEXT,
    tags            JSONB NOT NULL DEFAULT '[]',
    status          VARCHAR(20) NOT NULL DEFAULT 'active',
    config_hash     VARCHAR(64),
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_provider_name
    ON agents (provider, name);

CREATE INDEX IF NOT EXISTS idx_agents_tags
    ON agents USING GIN (tags);

-- Tasks table
CREATE TABLE IF NOT EXISTS tasks (
    id              UUID PRIMARY KEY,
    agent_provider  VARCHAR(100) NOT NULL,
    agent_name      VARCHAR(100) NOT NULL,
    status          VARCHAR(30) NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Task messages table
CREATE TABLE IF NOT EXISTS task_messages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id         UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    role            VARCHAR(20) NOT NULL,
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_task_messages_task_id
    ON task_messages (task_id);

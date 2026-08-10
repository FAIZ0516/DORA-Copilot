CREATE SCHEMA IF NOT EXISTS ai_assistant;

CREATE TABLE IF NOT EXISTS ai_assistant.zara_workflows (
    id UUID PRIMARY KEY,
    user_id VARCHAR(120) NOT NULL,
    name VARCHAR(160) NOT NULL,
    definition JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_zara_workflows_user_id
    ON ai_assistant.zara_workflows (user_id);

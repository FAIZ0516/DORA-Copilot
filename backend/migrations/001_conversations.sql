CREATE SCHEMA IF NOT EXISTS ai_assistant;

CREATE TABLE IF NOT EXISTS ai_assistant.conversations (
    id uuid PRIMARY KEY,
    title varchar(160) NOT NULL,
    user_id varchar(120),
    state jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz
);

CREATE INDEX IF NOT EXISTS ix_conversations_user_updated
    ON ai_assistant.conversations (user_id, updated_at DESC)
    WHERE archived_at IS NULL;

CREATE TABLE IF NOT EXISTS ai_assistant.messages (
    id uuid PRIMARY KEY,
    conversation_id uuid NOT NULL
        REFERENCES ai_assistant.conversations(id) ON DELETE CASCADE,
    role varchar(20) NOT NULL,
    content text NOT NULL,
    structured_content jsonb,
    query_id uuid,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_messages_conversation_created
    ON ai_assistant.messages (conversation_id, created_at);

-- saved_searches: User-defined Crosshair filters with Telegram alert support.
-- When new opportunities match a saved search and meet the DOS threshold,
-- the /api/saved-searches/check endpoint fires a Telegram alert.

CREATE TABLE IF NOT EXISTS saved_searches (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name             text NOT NULL,
    filters          jsonb NOT NULL DEFAULT '{}',
    dos_threshold    int  NOT NULL DEFAULT 65,
    telegram_chat_id text,
    last_alerted_at  timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- RLS: users can only see and manage their own saved searches.
ALTER TABLE saved_searches ENABLE ROW LEVEL SECURITY;

CREATE POLICY saved_searches_select ON saved_searches
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY saved_searches_insert ON saved_searches
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY saved_searches_delete ON saved_searches
    FOR DELETE USING (auth.uid() = user_id);

-- Index for efficient per-user lookups.
CREATE INDEX IF NOT EXISTS idx_saved_searches_user_id ON saved_searches (user_id);

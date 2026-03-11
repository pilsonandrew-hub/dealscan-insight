-- Rover event tracking table for preference learning
CREATE TABLE IF NOT EXISTS rover_events (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL CHECK (event_type IN ('view', 'click', 'save', 'bid', 'purchase')),
  item_data JSONB NOT NULL DEFAULT '{}',
  weight FLOAT NOT NULL DEFAULT 0.2,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS rover_events_user_id_idx ON rover_events(user_id);
CREATE INDEX IF NOT EXISTS rover_events_timestamp_idx ON rover_events(timestamp DESC);

-- RLS: users can only see their own events
ALTER TABLE rover_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY rover_events_user_policy ON rover_events
  FOR ALL USING (auth.uid() = user_id);

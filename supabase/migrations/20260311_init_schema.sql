-- DealerScope initial schema for new Supabase project
-- Run this on project lbnxzvqppccajllsqaaw

-- ---------------------------------------------------------------
-- opportunities table
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS opportunities (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  listing_id TEXT UNIQUE NOT NULL,
  source TEXT NOT NULL,
  title TEXT,
  year INT,
  make TEXT,
  model TEXT,
  trim TEXT,
  mileage INT,
  state TEXT,
  vin TEXT,
  current_bid FLOAT,
  buy_now_price FLOAT,
  mmr FLOAT,
  estimated_transport FLOAT,
  auction_fees FLOAT,
  gross_margin FLOAT,
  roi FLOAT,
  dos_score FLOAT,
  auction_end_date TIMESTAMPTZ,
  listing_url TEXT,
  image_url TEXT,
  raw_data JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS opportunities_dos_score_idx ON opportunities(dos_score DESC);
CREATE INDEX IF NOT EXISTS opportunities_created_at_idx ON opportunities(created_at DESC);
CREATE INDEX IF NOT EXISTS opportunities_source_idx ON opportunities(source);
CREATE INDEX IF NOT EXISTS opportunities_state_idx ON opportunities(state);

-- RLS: publicly readable (backend uses service role to write)
ALTER TABLE opportunities ENABLE ROW LEVEL SECURITY;
CREATE POLICY opportunities_read_policy ON opportunities
  FOR SELECT USING (true);

-- ---------------------------------------------------------------
-- rover_events table
-- ---------------------------------------------------------------
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

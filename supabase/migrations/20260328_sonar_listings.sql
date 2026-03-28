CREATE TABLE IF NOT EXISTS public.sonar_listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id TEXT,
    source TEXT,
    title TEXT,
    year INTEGER,
    make TEXT,
    model TEXT,
    trim TEXT,
    mileage INTEGER,
    state TEXT,
    city TEXT,
    current_bid NUMERIC,
    auction_end_date TIMESTAMPTZ,
    listing_url TEXT,
    image_url TEXT,
    photo_url TEXT,
    agency_name TEXT,
    condition TEXT,
    title_status TEXT,
    vin TEXT,
    source_site TEXT,
    dos_score NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sonar_listings_make ON public.sonar_listings(make);
CREATE INDEX IF NOT EXISTS idx_sonar_listings_created ON public.sonar_listings(created_at DESC);
ALTER TABLE public.sonar_listings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access" ON public.sonar_listings FOR ALL TO service_role USING (true);
CREATE POLICY "Anon read" ON public.sonar_listings FOR SELECT TO anon USING (true);

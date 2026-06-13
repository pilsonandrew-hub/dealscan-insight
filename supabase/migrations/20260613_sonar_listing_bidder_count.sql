ALTER TABLE public.sonar_listings
ADD COLUMN IF NOT EXISTS bidder_count INTEGER;

ALTER TABLE public.sonar_listings
DROP CONSTRAINT IF EXISTS sonar_listings_bidder_count_nonnegative;

ALTER TABLE public.sonar_listings
ADD CONSTRAINT sonar_listings_bidder_count_nonnegative
CHECK (bidder_count IS NULL OR bidder_count >= 0);

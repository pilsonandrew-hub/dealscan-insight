-- Persist governed listing photo-count evidence on opportunity rows.
ALTER TABLE public.opportunities
ADD COLUMN IF NOT EXISTS photo_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE public.opportunities
DROP CONSTRAINT IF EXISTS opportunities_photo_count_nonnegative;

ALTER TABLE public.opportunities
ADD CONSTRAINT opportunities_photo_count_nonnegative
CHECK (photo_count >= 0);

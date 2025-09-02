-- PHASE 1 CONTINUED: Fix scraping_jobs (corrected syntax)

-- Fix scraping_jobs access control
ALTER TABLE public.scraping_jobs ADD COLUMN IF NOT EXISTS owner_id uuid;

-- Create trigger to stamp owner_id from JWT on INSERT
CREATE OR REPLACE FUNCTION public.set_owner_from_jwt()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  IF NEW.owner_id IS NULL THEN
    NEW.owner_id := auth.uid();
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_scraping_jobs_owner ON public.scraping_jobs;
CREATE TRIGGER trg_scraping_jobs_owner
BEFORE INSERT ON public.scraping_jobs
FOR EACH ROW EXECUTE FUNCTION public.set_owner_from_jwt();

-- Clean slate for scraping_jobs RLS  
DROP POLICY IF EXISTS "Users can manage their own scraping jobs" ON public.scraping_jobs;

-- Owner-only RLS policies for scraping_jobs
CREATE POLICY "sj select own"
ON public.scraping_jobs FOR SELECT TO authenticated  
USING (owner_id = auth.uid());

CREATE POLICY "sj modify own"
ON public.scraping_jobs FOR ALL TO authenticated
USING (owner_id = auth.uid())
WITH CHECK (owner_id = auth.uid());

-- Admin override for scraping_jobs
CREATE POLICY "sj admin all"  
ON public.scraping_jobs FOR ALL TO authenticated
USING (coalesce((auth.jwt()->>'is_admin')::boolean, false))
WITH CHECK (true);

-- Add status column for finite state machine
ALTER TABLE public.scraping_jobs 
  ADD COLUMN IF NOT EXISTS status text DEFAULT 'queued',
  ADD COLUMN IF NOT EXISTS idempotency_key text;

-- Add constraint for valid statuses (without IF NOT EXISTS)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'scraping_jobs_status_chk') THEN
    ALTER TABLE public.scraping_jobs 
    ADD CONSTRAINT scraping_jobs_status_chk 
    CHECK (status IN ('queued','running','failed','succeeded'));
  END IF;
END $$;

-- Create unique index for idempotency  
CREATE UNIQUE INDEX IF NOT EXISTS uq_sj_owner_idem
  ON public.scraping_jobs(owner_id, coalesce(idempotency_key,''));

-- Add performance indexes
CREATE INDEX IF NOT EXISTS idx_sj_owner_status ON public.scraping_jobs(owner_id, status);
CREATE INDEX IF NOT EXISTS idx_profiles_user_id ON public.profiles(user_id);
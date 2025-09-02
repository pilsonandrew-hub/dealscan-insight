-- 1.3 SCRAPING JOBS - Add ownership and secure RLS
-- Remove emergency lockdown and existing policies
DROP POLICY IF EXISTS "emergency_scraping" ON public.scraping_jobs;
DROP POLICY IF EXISTS "sj admin all" ON public.scraping_jobs;
DROP POLICY IF EXISTS "sj modify own" ON public.scraping_jobs;
DROP POLICY IF EXISTS "sj select own" ON public.scraping_jobs;

-- Ensure owner_id exists and is properly constrained
-- (Note: owner_id already exists in the table schema)
UPDATE public.scraping_jobs SET owner_id = auth.uid() WHERE owner_id IS NULL;

-- Make owner_id NOT NULL and add foreign key constraint
ALTER TABLE public.scraping_jobs 
  ALTER COLUMN owner_id SET NOT NULL,
  ADD CONSTRAINT scraping_jobs_owner_fk FOREIGN KEY (owner_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Create trigger to auto-set owner_id from JWT on INSERT
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

-- Ensure RLS is enabled
ALTER TABLE public.scraping_jobs ENABLE ROW LEVEL SECURITY;

-- Owner-only policies
CREATE POLICY "sj_select_own"
ON public.scraping_jobs FOR SELECT TO authenticated
USING (owner_id = auth.uid());

CREATE POLICY "sj_modify_own"
ON public.scraping_jobs FOR ALL TO authenticated
USING (owner_id = auth.uid())
WITH CHECK (owner_id = auth.uid());

-- Admin override policy
CREATE POLICY "sj_admin_all"
ON public.scraping_jobs FOR ALL TO authenticated
USING (COALESCE((auth.jwt()->>'is_admin')::boolean, false))
WITH CHECK (true);

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_sj_owner_status ON public.scraping_jobs(owner_id, status, started_at DESC);
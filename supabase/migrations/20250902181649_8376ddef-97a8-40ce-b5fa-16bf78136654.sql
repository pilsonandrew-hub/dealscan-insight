-- 2.1 SECURE ALL USER-OWNED TABLES - Batch implementation
-- Opportunities table is already secured, but let's ensure proper indexes
CREATE INDEX IF NOT EXISTS idx_opportunities_user_created 
  ON public.opportunities(user_id, created_at DESC);

-- Market prices - ensure proper user_id constraint
ALTER TABLE public.market_prices 
  ALTER COLUMN user_id SET NOT NULL;

-- Add foreign key constraint if not exists
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints 
    WHERE constraint_name = 'market_prices_user_fk'
  ) THEN
    ALTER TABLE public.market_prices 
      ADD CONSTRAINT market_prices_user_fk 
      FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
  END IF;
END $$;

-- Dealer sales - ensure proper user_id constraint  
ALTER TABLE public.dealer_sales 
  ALTER COLUMN user_id SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints 
    WHERE constraint_name = 'dealer_sales_user_fk'
  ) THEN
    ALTER TABLE public.dealer_sales 
      ADD CONSTRAINT dealer_sales_user_fk 
      FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
  END IF;
END $$;

-- Scoring jobs - ensure proper user_id constraint
ALTER TABLE public.scoring_jobs 
  ALTER COLUMN user_id SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints 
    WHERE constraint_name = 'scoring_jobs_user_fk'
  ) THEN
    ALTER TABLE public.scoring_jobs 
      ADD CONSTRAINT scoring_jobs_user_fk 
      FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
  END IF;
END $$;

-- Performance indexes for RLS queries
CREATE INDEX IF NOT EXISTS idx_dealer_sales_user_ymm 
  ON public.dealer_sales(user_id, year, make, model);
CREATE INDEX IF NOT EXISTS idx_market_prices_user_vehicle 
  ON public.market_prices(user_id, make, model, year);
CREATE INDEX IF NOT EXISTS idx_scoring_jobs_user_status 
  ON public.scoring_jobs(user_id, status, created_at DESC);
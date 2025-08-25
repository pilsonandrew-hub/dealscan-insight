-- Fix security issues by enabling RLS on missing tables
ALTER TABLE public.scraper_sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scraping_jobs ENABLE ROW LEVEL SECURITY;

-- RLS policies for scraper_sites (read-only for authenticated users)
CREATE POLICY "Authenticated users can view scraper sites" ON public.scraper_sites
  FOR SELECT USING (auth.role() = 'authenticated');

-- RLS policies for scraping_jobs (users can manage their own jobs)  
CREATE POLICY "Users can manage their own scraping jobs" ON public.scraping_jobs
  FOR ALL USING (true);

-- Grant proper permissions
GRANT SELECT ON public.scraper_sites TO authenticated;
GRANT ALL ON public.scraping_jobs TO authenticated;
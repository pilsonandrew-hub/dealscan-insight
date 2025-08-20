-- Create scoring_jobs table for tracking deal scoring progress
CREATE TABLE public.scoring_jobs (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
  progress INTEGER NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
  total_listings INTEGER NOT NULL DEFAULT 0,
  processed_listings INTEGER NOT NULL DEFAULT 0,
  opportunities_created INTEGER NOT NULL DEFAULT 0,
  started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  completed_at TIMESTAMP WITH TIME ZONE,
  error_message TEXT,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Add RLS policies for scoring_jobs
ALTER TABLE public.scoring_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Scoring jobs are viewable by everyone" 
ON public.scoring_jobs 
FOR SELECT 
USING (true);

CREATE POLICY "Anyone can insert scoring jobs" 
ON public.scoring_jobs 
FOR INSERT 
WITH CHECK (true);

CREATE POLICY "Anyone can update scoring jobs" 
ON public.scoring_jobs 
FOR UPDATE 
USING (true);

-- Add missing columns to public_listings table
ALTER TABLE public.public_listings 
ADD COLUMN IF NOT EXISTS scored_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS score_metadata JSONB DEFAULT '{}';

-- Add missing columns to opportunities table 
ALTER TABLE public.opportunities 
ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'new' CHECK (status IN ('new', 'read', 'flagged', 'dismissed'));

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_scoring_jobs_status ON public.scoring_jobs(status);
CREATE INDEX IF NOT EXISTS idx_scoring_jobs_started_at ON public.scoring_jobs(started_at);
CREATE INDEX IF NOT EXISTS idx_public_listings_scored_at ON public.public_listings(scored_at);
CREATE INDEX IF NOT EXISTS idx_opportunities_status ON public.opportunities(status);

-- Add trigger for updated_at on scoring_jobs
CREATE TRIGGER update_scoring_jobs_updated_at
  BEFORE UPDATE ON public.scoring_jobs
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_updated_at();
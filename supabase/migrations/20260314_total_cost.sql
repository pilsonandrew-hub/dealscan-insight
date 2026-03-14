ALTER TABLE public.opportunities ADD COLUMN IF NOT EXISTS recon_reserve FLOAT;
ALTER TABLE public.opportunities ADD COLUMN IF NOT EXISTS total_cost FLOAT;

ALTER TABLE public.opportunities
ADD COLUMN IF NOT EXISTS acquisition_price_basis FLOAT,
ADD COLUMN IF NOT EXISTS acquisition_basis_source TEXT,
ADD COLUMN IF NOT EXISTS projected_total_cost FLOAT;

COMMENT ON COLUMN public.opportunities.acquisition_price_basis IS
  'Resolved hammer-price basis used for projected economics and score-critical cost calculations.';

COMMENT ON COLUMN public.opportunities.acquisition_basis_source IS
  'Provenance for acquisition_price_basis, including current_bid, expected_close, blended, and fallback labels.';

COMMENT ON COLUMN public.opportunities.projected_total_cost IS
  'Projected all-in acquisition cost using acquisition_price_basis plus premium, doc fee, transport, and recon reserve.';

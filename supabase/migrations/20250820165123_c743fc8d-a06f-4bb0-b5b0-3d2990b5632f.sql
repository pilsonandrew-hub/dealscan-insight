-- Create dealer_sales table for Manheim CSV data and API responses
CREATE TABLE public.dealer_sales (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  vin TEXT,
  make TEXT NOT NULL,
  model TEXT NOT NULL,
  year INTEGER NOT NULL,
  mileage INTEGER,
  sale_price NUMERIC NOT NULL,
  sale_date DATE,
  trim TEXT,
  title_status TEXT DEFAULT 'clean',
  auction_house TEXT,
  location TEXT,
  state TEXT,
  condition_grade TEXT,
  source_type TEXT DEFAULT 'csv', -- 'csv', 'manheim_api', 'kbb_api', etc.
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Create indexes for performance
CREATE INDEX idx_dealer_sales_make_model_year ON public.dealer_sales (make, model, year);
CREATE INDEX idx_dealer_sales_vin ON public.dealer_sales (vin);
CREATE INDEX idx_dealer_sales_state ON public.dealer_sales (state);
CREATE INDEX idx_dealer_sales_sale_date ON public.dealer_sales (sale_date);

-- Create opportunities table to store calculated arbitrage opportunities
CREATE TABLE public.opportunities (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  listing_id UUID REFERENCES public.public_listings(id),
  vin TEXT,
  make TEXT NOT NULL,
  model TEXT NOT NULL,
  year INTEGER NOT NULL,
  mileage INTEGER,
  current_bid NUMERIC NOT NULL,
  estimated_sale_price NUMERIC NOT NULL,
  total_cost NUMERIC NOT NULL,
  potential_profit NUMERIC NOT NULL,
  roi_percentage NUMERIC NOT NULL,
  risk_score INTEGER NOT NULL,
  confidence_score INTEGER NOT NULL,
  transportation_cost NUMERIC DEFAULT 0,
  fees_cost NUMERIC DEFAULT 0,
  buyer_premium NUMERIC DEFAULT 0,
  doc_fee NUMERIC DEFAULT 0,
  profit_margin NUMERIC NOT NULL,
  source_site TEXT NOT NULL,
  location TEXT,
  state TEXT,
  status TEXT DEFAULT 'moderate' CHECK (status IN ('hot', 'good', 'moderate')),
  score INTEGER DEFAULT 0,
  auction_end TIMESTAMP WITH TIME ZONE,
  market_data JSONB DEFAULT '{}', -- Store API responses
  calculation_metadata JSONB DEFAULT '{}',
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Create indexes for opportunities
CREATE INDEX idx_opportunities_status ON public.opportunities (status);
CREATE INDEX idx_opportunities_state ON public.opportunities (state);
CREATE INDEX idx_opportunities_roi ON public.opportunities (roi_percentage);
CREATE INDEX idx_opportunities_profit ON public.opportunities (potential_profit);
CREATE INDEX idx_opportunities_active ON public.opportunities (is_active);
CREATE INDEX idx_opportunities_auction_end ON public.opportunities (auction_end);

-- Create market_prices table for caching API responses
CREATE TABLE public.market_prices (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  make TEXT NOT NULL,
  model TEXT NOT NULL,
  year INTEGER NOT NULL,
  trim TEXT,
  avg_price NUMERIC NOT NULL,
  low_price NUMERIC NOT NULL,
  high_price NUMERIC NOT NULL,
  sample_size INTEGER DEFAULT 0,
  source_api TEXT NOT NULL, -- 'manheim', 'kbb', 'edmunds', 'nada'
  state TEXT, -- for regional pricing
  last_updated TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT (now() + INTERVAL '1 hour'),
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Create indexes for market_prices
CREATE INDEX idx_market_prices_make_model_year ON public.market_prices (make, model, year);
CREATE INDEX idx_market_prices_expires_at ON public.market_prices (expires_at);
CREATE INDEX idx_market_prices_source ON public.market_prices (source_api);

-- Enable RLS on all tables
ALTER TABLE public.dealer_sales ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.opportunities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.market_prices ENABLE ROW LEVEL SECURITY;

-- Create policies for public access (adjust based on auth requirements)
CREATE POLICY "Dealer sales are viewable by everyone" 
ON public.dealer_sales FOR SELECT USING (true);

CREATE POLICY "Opportunities are viewable by everyone" 
ON public.opportunities FOR SELECT USING (true);

CREATE POLICY "Market prices are viewable by everyone" 
ON public.market_prices FOR SELECT USING (true);

-- Create policies for inserts (for API/scraper operations)
CREATE POLICY "Anyone can insert dealer sales" 
ON public.dealer_sales FOR INSERT WITH CHECK (true);

CREATE POLICY "Anyone can insert opportunities" 
ON public.opportunities FOR INSERT WITH CHECK (true);

CREATE POLICY "Anyone can insert market prices" 
ON public.market_prices FOR INSERT WITH CHECK (true);

-- Create updated_at trigger for dealer_sales
CREATE TRIGGER update_dealer_sales_updated_at
BEFORE UPDATE ON public.dealer_sales
FOR EACH ROW
EXECUTE FUNCTION public.handle_updated_at();

-- Create updated_at trigger for opportunities
CREATE TRIGGER update_opportunities_updated_at
BEFORE UPDATE ON public.opportunities
FOR EACH ROW
EXECUTE FUNCTION public.handle_updated_at();

-- Create function to clean expired market prices
CREATE OR REPLACE FUNCTION public.clean_expired_market_prices()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  DELETE FROM public.market_prices WHERE expires_at < now();
END;
$$;
-- Create missing ML tables and infrastructure
-- Complete migration with all dependencies

-- First create the update function
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Field provenance tracking for ML model inputs
CREATE TABLE IF NOT EXISTS public.field_provenance (
    id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    field_name TEXT NOT NULL,
    source_table TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    confidence_score DECIMAL(5,4) DEFAULT 0.0,
    last_validated TIMESTAMP WITH TIME ZONE DEFAULT now(),
    validation_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- ML model performance metrics
CREATE TABLE IF NOT EXISTS public.model_performance_metrics (
    id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    metric_type TEXT NOT NULL, -- 'accuracy', 'precision', 'recall', 'f1', 'mae', 'rmse'
    metric_value DECIMAL(10,6) NOT NULL,
    dataset_size INTEGER,
    test_split DECIMAL(3,2) DEFAULT 0.2,
    evaluated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- ML models registry
CREATE TABLE IF NOT EXISTS public.ml_models (
    id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    model_type TEXT NOT NULL, -- 'regression', 'classification', 'clustering'
    status TEXT NOT NULL DEFAULT 'training', -- 'training', 'active', 'deprecated'
    accuracy DECIMAL(5,4),
    training_data_size INTEGER,
    features_used TEXT[],
    hyperparameters JSONB DEFAULT '{}'::jsonb,
    deployed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Add critical performance indexes
CREATE INDEX IF NOT EXISTS idx_opportunities_user_profit ON public.opportunities(user_id, potential_profit DESC) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_public_listings_active_created ON public.public_listings(is_active, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_public_listings_site_active ON public.public_listings(source_site, is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_dealer_sales_user_date ON public.dealer_sales(user_id, sale_date DESC);
CREATE INDEX IF NOT EXISTS idx_user_alerts_user_dismissed ON public.user_alerts(user_id, dismissed, created_at DESC);

-- Enable RLS on new tables
ALTER TABLE public.field_provenance ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.model_performance_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ml_models ENABLE ROW LEVEL SECURITY;

-- RLS policies for ML tables
CREATE POLICY "Service role can manage field provenance" ON public.field_provenance
    FOR ALL USING (auth.role() = 'service_role'::text);

CREATE POLICY "Authenticated users can read field provenance" ON public.field_provenance
    FOR SELECT USING (auth.role() = 'authenticated'::text);

CREATE POLICY "Service role can manage model metrics" ON public.model_performance_metrics
    FOR ALL USING (auth.role() = 'service_role'::text);

CREATE POLICY "Authenticated users can read model metrics" ON public.model_performance_metrics
    FOR SELECT USING (auth.role() = 'authenticated'::text);

CREATE POLICY "Service role can manage ML models" ON public.ml_models
    FOR ALL USING (auth.role() = 'service_role'::text);

CREATE POLICY "Authenticated users can read ML models" ON public.ml_models
    FOR SELECT USING (auth.role() = 'authenticated'::text);

-- Add triggers for timestamp management
CREATE TRIGGER update_field_provenance_updated_at
    BEFORE UPDATE ON public.field_provenance
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_ml_models_updated_at
    BEFORE UPDATE ON public.ml_models
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();
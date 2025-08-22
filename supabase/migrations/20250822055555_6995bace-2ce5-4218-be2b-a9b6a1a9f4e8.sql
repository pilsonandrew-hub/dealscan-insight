-- Create user_settings table for storing user preferences
CREATE TABLE public.user_settings (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL,
  enabled_sites TEXT[] DEFAULT ARRAY['GovDeals', 'PublicSurplus'],
  scanning_mode TEXT DEFAULT 'safe' CHECK (scanning_mode IN ('safe', 'fast')),
  scan_interval INTEGER DEFAULT 10 CHECK (scan_interval >= 5 AND scan_interval <= 60),
  max_risk_score INTEGER DEFAULT 50 CHECK (max_risk_score >= 1 AND max_risk_score <= 100),
  min_roi_percentage INTEGER DEFAULT 15 CHECK (min_roi_percentage >= 1 AND min_roi_percentage <= 100),
  preferred_states TEXT[] DEFAULT ARRAY['CA', 'TX', 'FL'],
  notifications_enabled BOOLEAN DEFAULT true,
  email_alerts BOOLEAN DEFAULT false,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Enable Row Level Security
ALTER TABLE public.user_settings ENABLE ROW LEVEL SECURITY;

-- Create policies for user settings
CREATE POLICY "Users can view their own settings" 
ON public.user_settings 
FOR SELECT 
USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own settings" 
ON public.user_settings 
FOR INSERT 
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own settings" 
ON public.user_settings 
FOR UPDATE 
USING (auth.uid() = user_id);

-- Create unique index on user_id
CREATE UNIQUE INDEX idx_user_settings_user_id ON public.user_settings(user_id);

-- Create trigger for automatic timestamp updates
CREATE TRIGGER update_user_settings_updated_at
BEFORE UPDATE ON public.user_settings
FOR EACH ROW
EXECUTE FUNCTION public.handle_updated_at();
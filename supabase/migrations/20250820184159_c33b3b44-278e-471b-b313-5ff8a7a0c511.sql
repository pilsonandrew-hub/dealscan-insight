-- Create profiles table for user management
CREATE TABLE public.profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT,
  display_name TEXT,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  UNIQUE(user_id)
);

-- Enable RLS on profiles
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- Profiles policies
CREATE POLICY "Users can view their own profile" 
ON public.profiles 
FOR SELECT 
USING (auth.uid() = user_id);

CREATE POLICY "Users can update their own profile" 
ON public.profiles 
FOR UPDATE 
USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own profile" 
ON public.profiles 
FOR INSERT 
WITH CHECK (auth.uid() = user_id);

-- Add user_id columns to existing tables
ALTER TABLE public.opportunities ADD COLUMN user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;
ALTER TABLE public.dealer_sales ADD COLUMN user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;  
ALTER TABLE public.market_prices ADD COLUMN user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;

-- Update existing RLS policies to be user-scoped instead of public
DROP POLICY IF EXISTS "Opportunities are viewable by everyone" ON public.opportunities;
DROP POLICY IF EXISTS "Anyone can insert opportunities" ON public.opportunities;

CREATE POLICY "Users can view their own opportunities" 
ON public.opportunities 
FOR SELECT 
USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own opportunities" 
ON public.opportunities 
FOR INSERT 
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own opportunities" 
ON public.opportunities 
FOR UPDATE 
USING (auth.uid() = user_id);

-- Secure dealer_sales table
DROP POLICY IF EXISTS "Dealer sales are viewable by everyone" ON public.dealer_sales;
DROP POLICY IF EXISTS "Anyone can insert dealer sales" ON public.dealer_sales;

CREATE POLICY "Users can view their own dealer sales" 
ON public.dealer_sales 
FOR SELECT 
USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own dealer sales" 
ON public.dealer_sales 
FOR INSERT 
WITH CHECK (auth.uid() = user_id);

-- Secure market_prices table
DROP POLICY IF EXISTS "Market prices are viewable by everyone" ON public.market_prices;
DROP POLICY IF EXISTS "Anyone can insert market prices" ON public.market_prices;

CREATE POLICY "Users can view their own market prices" 
ON public.market_prices 
FOR SELECT 
USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own market prices" 
ON public.market_prices 
FOR INSERT 
WITH CHECK (auth.uid() = user_id);

-- Secure scoring_jobs table 
DROP POLICY IF EXISTS "Scoring jobs are viewable by everyone" ON public.scoring_jobs;
DROP POLICY IF EXISTS "Anyone can insert scoring jobs" ON public.scoring_jobs;
DROP POLICY IF EXISTS "Anyone can update scoring jobs" ON public.scoring_jobs;

ALTER TABLE public.scoring_jobs ADD COLUMN user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;

CREATE POLICY "Users can view their own scoring jobs" 
ON public.scoring_jobs 
FOR SELECT 
USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own scoring jobs" 
ON public.scoring_jobs 
FOR INSERT 
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own scoring jobs" 
ON public.scoring_jobs 
FOR UPDATE 
USING (auth.uid() = user_id);

-- Create function to handle new user profile creation
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  INSERT INTO public.profiles (user_id, email, display_name)
  VALUES (
    NEW.id, 
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'display_name', split_part(NEW.email, '@', 1))
  );
  RETURN NEW;
END;
$$;

-- Trigger to create profile on user signup
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Add updated_at trigger for profiles
CREATE TRIGGER update_profiles_updated_at
  BEFORE UPDATE ON public.profiles
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_updated_at();
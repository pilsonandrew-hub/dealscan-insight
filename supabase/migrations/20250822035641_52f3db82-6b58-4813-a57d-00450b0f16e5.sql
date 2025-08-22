-- Fix Critical Security Issue #2: Secure scraper configurations
-- Remove public access to scraper_configs table and implement proper RLS

-- Drop existing public policy
DROP POLICY IF EXISTS "Scraper configs are viewable by everyone" ON scraper_configs;

-- Create secure RLS policies for scraper_configs
CREATE POLICY "Only authenticated users can view scraper configs" 
ON scraper_configs 
FOR SELECT 
TO authenticated 
USING (true);

CREATE POLICY "Only service role can modify scraper configs" 
ON scraper_configs 
FOR ALL 
TO service_role 
USING (true);

-- Fix database function security issues
-- Update functions to have proper search_path settings
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $function$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.clean_expired_market_prices()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER  
SET search_path = public
AS $function$
BEGIN
  DELETE FROM public.market_prices WHERE expires_at < now();
END;
$function$;

-- Create audit log table for security monitoring
CREATE TABLE IF NOT EXISTS public.security_audit_log (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id),
  action TEXT NOT NULL,
  resource TEXT,
  ip_address INET,
  user_agent TEXT,
  status TEXT NOT NULL CHECK (status IN ('success', 'failure', 'warning')),
  details JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Enable RLS on audit log
ALTER TABLE public.security_audit_log ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for audit log
CREATE POLICY "Users can view their own audit logs" 
ON public.security_audit_log 
FOR SELECT 
TO authenticated 
USING (auth.uid() = user_id);

CREATE POLICY "System can insert audit logs" 
ON public.security_audit_log 
FOR INSERT 
TO authenticated 
WITH CHECK (true);

-- Create function to log security events
CREATE OR REPLACE FUNCTION public.log_security_event(
  p_action TEXT,
  p_resource TEXT DEFAULT NULL,
  p_status TEXT DEFAULT 'success',
  p_details JSONB DEFAULT '{}'
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $function$
BEGIN
  INSERT INTO public.security_audit_log (
    user_id,
    action,
    resource,
    status,
    details
  ) VALUES (
    auth.uid(),
    p_action,
    p_resource,
    p_status,
    p_details
  );
END;
$function$;
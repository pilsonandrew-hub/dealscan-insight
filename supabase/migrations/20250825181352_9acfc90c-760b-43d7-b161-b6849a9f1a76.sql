-- Fix security issues identified by linter

-- Fix Function Search Path Mutable - secure all functions with proper search_path
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public', 'pg_catalog';

-- Update existing functions to have secure search_path
CREATE OR REPLACE FUNCTION public.log_security_event(p_action text, p_resource text DEFAULT NULL::text, p_status text DEFAULT 'success'::text, p_details jsonb DEFAULT '{}'::jsonb)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path = 'public', 'pg_catalog'
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

CREATE OR REPLACE FUNCTION public.handle_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path = 'public', 'pg_catalog'
AS $function$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.handle_new_user()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path = 'public', 'pg_catalog'
AS $function$
BEGIN
  INSERT INTO public.profiles (user_id, email, display_name)
  VALUES (
    NEW.id, 
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'display_name', split_part(NEW.email, '@', 1))
  );
  RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.clean_expired_market_prices()
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path = 'public', 'pg_catalog'
AS $function$
BEGIN
  DELETE FROM public.market_prices WHERE expires_at < now();
END;
$function$;
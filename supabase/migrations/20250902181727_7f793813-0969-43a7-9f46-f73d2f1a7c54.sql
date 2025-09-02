-- 2.2 COMPREHENSIVE AUDIT LOGGING SYSTEM
-- Enhanced security events table for complete audit trail
CREATE TABLE IF NOT EXISTS public.security_events (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  user_id uuid REFERENCES auth.users(id),
  ip_address inet,
  user_agent text,
  action text NOT NULL,
  table_name text,
  row_id text,
  success boolean NOT NULL DEFAULT true,
  error_message text,
  context jsonb DEFAULT '{}',
  severity text DEFAULT 'info' CHECK (severity IN ('debug', 'info', 'warn', 'error', 'critical'))
);

-- Enable RLS on security events
ALTER TABLE public.security_events ENABLE ROW LEVEL SECURITY;

-- Admin-only access to security events
CREATE POLICY "security_events_admin_only"
ON public.security_events FOR ALL TO authenticated
USING (COALESCE((auth.jwt()->>'is_admin')::boolean, false))
WITH CHECK (COALESCE((auth.jwt()->>'is_admin')::boolean, false));

-- Service role for system operations
CREATE POLICY "security_events_service_manage"
ON public.security_events FOR ALL TO service_role
USING (true)
WITH CHECK (true);

-- Generic audit trigger function for sensitive operations
CREATE OR REPLACE FUNCTION public.audit_sensitive_operation()
RETURNS trigger 
LANGUAGE plpgsql 
SECURITY DEFINER 
SET search_path = public
AS $$
BEGIN
  -- Log all modifications to sensitive tables
  INSERT INTO public.security_events (
    user_id, action, table_name, row_id, success, context
  ) VALUES (
    auth.uid(),
    TG_OP,
    TG_TABLE_NAME,
    COALESCE(NEW.id::text, OLD.id::text),
    true,
    jsonb_build_object(
      'table', TG_TABLE_NAME,
      'operation', TG_OP,
      'user_id', auth.uid(),
      'timestamp', now()
    )
  );
  
  RETURN COALESCE(NEW, OLD);
END $$;

-- Attach audit triggers to all sensitive tables
DROP TRIGGER IF EXISTS trg_audit_profiles ON public.profiles;
CREATE TRIGGER trg_audit_profiles 
AFTER INSERT OR UPDATE OR DELETE ON public.profiles 
FOR EACH ROW EXECUTE FUNCTION public.audit_sensitive_operation();

DROP TRIGGER IF EXISTS trg_audit_scraping_jobs ON public.scraping_jobs;
CREATE TRIGGER trg_audit_scraping_jobs 
AFTER INSERT OR UPDATE OR DELETE ON public.scraping_jobs 
FOR EACH ROW EXECUTE FUNCTION public.audit_sensitive_operation();

DROP TRIGGER IF EXISTS trg_audit_opportunities ON public.opportunities;
CREATE TRIGGER trg_audit_opportunities 
AFTER INSERT OR UPDATE OR DELETE ON public.opportunities 
FOR EACH ROW EXECUTE FUNCTION public.audit_sensitive_operation();

-- Index for audit queries
CREATE INDEX IF NOT EXISTS idx_security_events_user_time 
  ON public.security_events(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_events_action_time 
  ON public.security_events(action, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_events_severity_time 
  ON public.security_events(severity, created_at DESC);
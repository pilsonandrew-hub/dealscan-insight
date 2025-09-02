-- PHASE 1: CRITICAL SECURITY FIXES - Simplified
-- Fix the most critical issue: profiles table RLS policy (stops email exfiltration)

-- Clean slate for profiles
DROP POLICY IF EXISTS "Users can view their own profile" ON public.profiles;
DROP POLICY IF EXISTS "Users can update their own profile" ON public.profiles;  
DROP POLICY IF EXISTS "Users can insert their own profile" ON public.profiles;

-- Owner-only access (using user_id for profiles table)
CREATE POLICY "profiles select own"
ON public.profiles FOR SELECT TO authenticated
USING (user_id = auth.uid());

CREATE POLICY "profiles update own" 
ON public.profiles FOR UPDATE TO authenticated
USING (user_id = auth.uid())
WITH CHECK (user_id = auth.uid());

CREATE POLICY "profiles insert own"
ON public.profiles FOR INSERT TO authenticated  
WITH CHECK (user_id = auth.uid());

-- Admin override (boolean claim is_admin)
CREATE POLICY "profiles admin all"
ON public.profiles FOR ALL TO authenticated
USING (coalesce((auth.jwt()->>'is_admin')::boolean, false))
WITH CHECK (true);

-- Fix security_audit_log access (restrict to admin only)
DROP POLICY IF EXISTS "Users can view their own audit logs" ON public.security_audit_log;
DROP POLICY IF EXISTS "System can insert audit logs" ON public.security_audit_log;

-- Admin-only access for audit logs  
CREATE POLICY "audit_admin_only"
ON public.security_audit_log FOR ALL TO authenticated
USING (coalesce((auth.jwt()->>'is_admin')::boolean, false))
WITH CHECK (coalesce((auth.jwt()->>'is_admin')::boolean, false));

-- System can still insert audit logs via service role
CREATE POLICY "audit_system_insert" 
ON public.security_audit_log FOR INSERT TO service_role
WITH CHECK (true);
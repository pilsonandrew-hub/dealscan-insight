-- CRITICAL FIX: Ensure RLS is enabled and no permissive policies allow public access

-- Double-check RLS is enabled on all sensitive tables  
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dealer_sales ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.opportunities ENABLE ROW LEVEL SECURITY; 
ALTER TABLE public.security_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.error_reports ENABLE ROW LEVEL SECURITY;

-- Remove any potentially permissive policies and ensure strict user-only access

-- Profiles: Strict user-only access
DROP POLICY IF EXISTS "Users can view their own profile" ON public.profiles;
DROP POLICY IF EXISTS "Users can update their own profile" ON public.profiles; 
DROP POLICY IF EXISTS "Users can insert their own profile" ON public.profiles;
-- Keep only our secure policies (already created, but let's ensure they're correct)

-- Dealer Sales: Ensure only user can see their own data
DROP POLICY IF EXISTS "Users can view their own dealer sales" ON public.dealer_sales;
DROP POLICY IF EXISTS "Users can insert their own dealer sales" ON public.dealer_sales;

CREATE POLICY "dealer_sales_user_only_select"
ON public.dealer_sales FOR SELECT TO authenticated
USING (user_id = auth.uid());

CREATE POLICY "dealer_sales_user_only_insert" 
ON public.dealer_sales FOR INSERT TO authenticated
WITH CHECK (user_id = auth.uid());

CREATE POLICY "dealer_sales_admin_override"
ON public.dealer_sales FOR ALL TO authenticated  
USING (coalesce((auth.jwt()->>'is_admin')::boolean, false))
WITH CHECK (true);

-- Opportunities: Ensure only user can see their own data
DROP POLICY IF EXISTS "Users can view their own opportunities" ON public.opportunities;
DROP POLICY IF EXISTS "Users can insert their own opportunities" ON public.opportunities;
DROP POLICY IF EXISTS "Users can update their own opportunities" ON public.opportunities;

CREATE POLICY "opportunities_user_only_select"
ON public.opportunities FOR SELECT TO authenticated
USING (user_id = auth.uid());

CREATE POLICY "opportunities_user_only_modify"
ON public.opportunities FOR ALL TO authenticated
USING (user_id = auth.uid())  
WITH CHECK (user_id = auth.uid());

CREATE POLICY "opportunities_admin_override"
ON public.opportunities FOR ALL TO authenticated
USING (coalesce((auth.jwt()->>'is_admin')::boolean, false))
WITH CHECK (true);

-- Security Audit Log: Admin only (already fixed but double-check)
DROP POLICY IF EXISTS "Users can view their own audit logs" ON public.security_audit_log;
-- Keep admin-only policies

-- Error Reports: Service role only
DROP POLICY IF EXISTS "Service role can manage error reports" ON public.error_reports;

CREATE POLICY "error_reports_service_only"
ON public.error_reports FOR ALL TO service_role  
WITH CHECK (true);

CREATE POLICY "error_reports_admin_read" 
ON public.error_reports FOR SELECT TO authenticated
USING (coalesce((auth.jwt()->>'is_admin')::boolean, false));

-- Revoke any public permissions that might exist
REVOKE ALL ON public.profiles FROM anon, public;
REVOKE ALL ON public.dealer_sales FROM anon, public;  
REVOKE ALL ON public.opportunities FROM anon, public;
REVOKE ALL ON public.security_audit_log FROM anon, public;
REVOKE ALL ON public.error_reports FROM anon, public;

-- Grant only necessary permissions to authenticated users
GRANT SELECT, INSERT, UPDATE ON public.profiles TO authenticated;
GRANT SELECT, INSERT ON public.dealer_sales TO authenticated;
GRANT SELECT, INSERT, UPDATE ON public.opportunities TO authenticated;
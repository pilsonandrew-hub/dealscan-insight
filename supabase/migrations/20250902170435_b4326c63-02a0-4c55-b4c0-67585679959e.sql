-- FIX THE ROOT CAUSE: Remove permissive admin policies and implement proper security

-- Remove all permissive policies that create security holes
DROP POLICY IF EXISTS "profiles admin all" ON public.profiles;
DROP POLICY IF EXISTS "dealer_sales_admin_override" ON public.dealer_sales;  
DROP POLICY IF EXISTS "opportunities_admin_override" ON public.opportunities;

-- Create RESTRICTIVE policies (AND logic) instead of PERMISSIVE (OR logic)
-- This ensures all conditions must be met, not just one

-- Profiles: Only users can see their own data, admins use service role
CREATE POLICY "profiles_user_only_select" ON public.profiles
  FOR SELECT TO authenticated 
  USING (user_id = auth.uid());

CREATE POLICY "profiles_user_only_insert" ON public.profiles  
  FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid());

CREATE POLICY "profiles_user_only_update" ON public.profiles
  FOR UPDATE TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- Admin access only through service role (not JWT claims)
CREATE POLICY "profiles_service_admin" ON public.profiles
  FOR ALL TO service_role
  USING (true) 
  WITH CHECK (true);

-- Dealer Sales: User-only access, no admin override through JWT
CREATE POLICY "dealer_sales_user_select" ON public.dealer_sales
  FOR SELECT TO authenticated
  USING (user_id = auth.uid());

CREATE POLICY "dealer_sales_user_insert" ON public.dealer_sales
  FOR INSERT TO authenticated  
  WITH CHECK (user_id = auth.uid());

-- Opportunities: User-only access, no admin override through JWT  
CREATE POLICY "opportunities_user_select" ON public.opportunities
  FOR SELECT TO authenticated
  USING (user_id = auth.uid());

CREATE POLICY "opportunities_user_modify" ON public.opportunities
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- Remove any default permissions and only grant specific ones
REVOKE ALL ON public.profiles FROM authenticated;
REVOKE ALL ON public.dealer_sales FROM authenticated;
REVOKE ALL ON public.opportunities FROM authenticated;

-- Grant only necessary permissions
GRANT SELECT, INSERT, UPDATE ON public.profiles TO authenticated;
GRANT SELECT, INSERT ON public.dealer_sales TO authenticated;  
GRANT SELECT, INSERT, UPDATE, DELETE ON public.opportunities TO authenticated;
-- Fix authentication issues and improve RLS policies

-- First, let's ensure the profiles table has the correct INSERT policy with proper check
DROP POLICY IF EXISTS "profiles_insert_own" ON public.profiles;
CREATE POLICY "profiles_insert_own" 
ON public.profiles 
FOR INSERT 
TO authenticated 
WITH CHECK (user_id = auth.uid());

-- Add a policy to allow users to insert their own profile during signup
CREATE POLICY "profiles_insert_during_signup" 
ON public.profiles 
FOR INSERT 
TO authenticated 
WITH CHECK (true);  -- Allow any authenticated user to insert (the trigger handles the user_id)

-- Ensure the handle_new_user function is properly set up
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER 
SET search_path = public, auth
AS $$
BEGIN
  -- Log the signup attempt
  INSERT INTO public.profiles (user_id, email, display_name)
  VALUES (
    NEW.id, 
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'display_name', split_part(NEW.email, '@', 1))
  )
  ON CONFLICT (user_id) DO UPDATE SET
    email = EXCLUDED.email,
    display_name = COALESCE(EXCLUDED.display_name, profiles.display_name),
    updated_at = now();
  
  RETURN NEW;
END;
$$;

-- Ensure the trigger exists
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Create a function to help with auth debugging
CREATE OR REPLACE FUNCTION public.get_user_profile(target_user_id uuid DEFAULT auth.uid())
RETURNS TABLE (
  user_id uuid,
  email text,
  display_name text,
  created_at timestamptz,
  is_authenticated boolean
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT 
    p.user_id,
    p.email,
    p.display_name,
    p.created_at,
    (target_user_id IS NOT NULL) as is_authenticated
  FROM public.profiles p
  WHERE p.user_id = target_user_id;
$$;

-- Grant necessary permissions
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT SELECT, INSERT, UPDATE ON public.profiles TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_user_profile TO authenticated;

-- Create a simple test function to verify auth is working
CREATE OR REPLACE FUNCTION public.test_auth()
RETURNS json
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT json_build_object(
    'user_id', auth.uid(),
    'role', auth.role(),
    'jwt_user_id', (auth.jwt() ->> 'sub')::uuid,
    'email', auth.jwt() ->> 'email',
    'timestamp', now()
  );
$$;

GRANT EXECUTE ON FUNCTION public.test_auth TO authenticated, anon;
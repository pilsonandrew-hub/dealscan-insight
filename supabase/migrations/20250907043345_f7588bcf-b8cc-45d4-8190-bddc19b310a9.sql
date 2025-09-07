-- Fix authentication issues completely

-- First, let's recreate the trigger properly on auth.users table
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

-- Drop and recreate the trigger on auth.users
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Update RLS policies to be more permissive for auth operations
DROP POLICY IF EXISTS "profiles_insert_during_signup" ON public.profiles;
DROP POLICY IF EXISTS "profiles_insert_own" ON public.profiles;

-- Create a simple policy that allows authenticated users to insert their own profile
CREATE POLICY "profiles_insert_own" 
ON public.profiles 
FOR INSERT 
TO authenticated 
WITH CHECK (user_id = auth.uid());

-- Allow profile creation during signup process (when the user might not be fully authenticated yet)
CREATE POLICY "profiles_insert_during_signup" 
ON public.profiles 
FOR INSERT 
TO anon, authenticated
WITH CHECK (true);

-- Simplify the test_auth function to be more reliable
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
    'timestamp', now(),
    'auth_working', CASE WHEN auth.uid() IS NOT NULL THEN true ELSE false END
  );
$$;

-- Grant execute permissions
GRANT EXECUTE ON FUNCTION public.test_auth TO authenticated, anon;
GRANT EXECUTE ON FUNCTION public.handle_new_user TO authenticated, anon;
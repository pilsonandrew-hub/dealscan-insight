-- Fix migration - drop existing policies first
DROP POLICY IF EXISTS "Users can view their own labels" ON public.labels;
DROP POLICY IF EXISTS "Users can insert their own labels" ON public.labels;

-- Recreate RLS policies for labels
CREATE POLICY "Users can view their own labels" 
ON public.labels FOR SELECT 
USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own labels" 
ON public.labels FOR INSERT 
WITH CHECK (auth.uid() = user_id);
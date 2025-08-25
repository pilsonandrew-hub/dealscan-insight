-- Drop existing policies if they exist to avoid conflicts
DROP POLICY IF EXISTS "Users can view their own labels" ON public.labels;
DROP POLICY IF EXISTS "Users can insert their own labels" ON public.labels;

-- Create the policies with correct names
CREATE POLICY "Users can view their own labels" 
ON public.labels FOR SELECT 
USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own labels" 
ON public.labels FOR INSERT 
WITH CHECK (auth.uid() = user_id);
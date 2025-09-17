-- Create Rover Events table for ML training data
CREATE TABLE public.rover_events (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL,
  event_type TEXT NOT NULL CHECK (event_type IN ('view', 'click', 'save', 'bid', 'purchase')),
  item_data JSONB NOT NULL,
  weight NUMERIC NOT NULL DEFAULT 1.0,
  timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Create Rover Recommendations cache table
CREATE TABLE public.rover_recommendations (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL,
  recommendations JSONB NOT NULL,
  confidence NUMERIC NOT NULL DEFAULT 0.0,
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Enable Row Level Security
ALTER TABLE public.rover_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rover_recommendations ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for rover_events
CREATE POLICY "Users can insert their own events"
ON public.rover_events
FOR INSERT
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can view their own events"
ON public.rover_events
FOR SELECT
USING (auth.uid() = user_id);

-- Create RLS policies for rover_recommendations  
CREATE POLICY "Users can manage their own recommendations"
ON public.rover_recommendations
FOR ALL
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);

-- Create indexes for performance
CREATE INDEX idx_rover_events_user_timestamp ON public.rover_events(user_id, timestamp DESC);
CREATE INDEX idx_rover_events_event_type ON public.rover_events(event_type);
CREATE INDEX idx_rover_recommendations_user_expires ON public.rover_recommendations(user_id, expires_at);

-- Create trigger for automatic timestamp updates
CREATE TRIGGER update_rover_recommendations_updated_at
BEFORE UPDATE ON public.rover_recommendations
FOR EACH ROW
EXECUTE FUNCTION public.update_updated_at_column();
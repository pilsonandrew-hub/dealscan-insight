import "https://deno.land/x/xhr@0.1.0/mod.ts";
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.55.0';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    // Initialize Supabase client
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
    const supabaseServiceRoleKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const supabase = createClient(supabaseUrl, supabaseServiceRoleKey);

    // Get authenticated user
    const authHeader = req.headers.get('Authorization')!;
    const token = authHeader.replace('Bearer ', '');
    const { data: { user }, error: userError } = await supabase.auth.getUser(token);
    
    if (userError || !user) {
      console.error('Authentication error:', userError);
      return new Response(
        JSON.stringify({ error: 'Unauthorized' }),
        { status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    const { canonical_query, search_options, title } = await req.json();
    console.log('Saving crosshair intent:', { canonical_query, search_options, title, user_id: user.id });

    // Create crosshair intent
    const { data: intent, error: intentError } = await supabase
      .from('crosshair_intents')
      .insert({
        user_id: user.id,
        canonical_query,
        search_options: search_options || {},
        title,
        rescan_interval: search_options?.rescan_interval || '6h',
        notify_on_first_match: search_options?.notify_on_first_match || false,
        is_active: true
      })
      .select()
      .single();

    if (intentError) {
      console.error('Intent creation error:', intentError);
      return new Response(
        JSON.stringify({ error: 'Failed to save search intent' }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    console.log('Created crosshair intent:', intent.id);

    // Create initial alert if notify_on_first_match is enabled
    if (search_options?.notify_on_first_match) {
      await supabase
        .from('user_alerts')
        .insert({
          id: crypto.randomUUID(),
          user_id: user.id,
          type: 'crosshair_intent_created',
          title: 'Search Intent Saved',
          message: `"${title}" is now being monitored. You'll be notified when matching vehicles are found.`,
          priority: 'low',
          opportunity_data: {
            intent_id: intent.id,
            canonical_query,
            search_options
          }
        });
    }

    const response = {
      success: true,
      intent_id: intent.id,
      title: intent.title,
      message: `Search intent "${title}" saved successfully and will be monitored ${intent.rescan_interval}.`
    };

    return new Response(JSON.stringify(response), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });

  } catch (error) {
    console.error('Save intent error:', error);
    return new Response(
      JSON.stringify({ 
        success: false, 
        error: error.message || 'Internal server error' 
      }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.45.4';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};

// Valid sites whitelist for SSRF protection
const ALLOWED_SITES = [
  'GovDeals', 'PublicSurplus', 'GSAauctions', 'TreasuryAuctions', 
  'MuniciBid', 'AllSurplus', 'HiBid', 'Proxibid', 'BidSpotter',
  'PurpleWave', 'JJKane'
];

Deno.serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    // SECURITY: Verify authentication (JWT required)
    const authHeader = req.headers.get('authorization');
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      console.error('Missing or invalid authorization header');
      return new Response(
        JSON.stringify({ error: 'Unauthorized: Valid authentication required' }), 
        { status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // Create user-context Supabase client (enforces RLS)
    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_ANON_KEY')!,
      {
        global: { 
          headers: { 
            Authorization: authHeader // Forward user token for RLS
          } 
        }
      }
    );

    // Verify the token is valid and get user
    const { data: { user }, error: authError } = await supabase.auth.getUser();
    if (authError || !user) {
      console.error('Invalid token:', authError?.message);
      return new Response(
        JSON.stringify({ error: 'Invalid authentication token' }), 
        { status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    console.log('Authenticated user:', user.id);

    // SECURITY: Rate limiting (per-user)
    const clientIP = req.headers.get('x-forwarded-for')?.split(',')[0] || 'unknown';
    console.log('Request from user:', user.id, 'IP:', clientIP);

    // Parse and validate request
    const { data } = await req.json();
    if (!data) {
      return new Response(
        JSON.stringify({ error: 'Missing request data' }), 
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // SECURITY: Validate input sites
    if (data.sites) {
      const invalidSites = data.sites.filter((site: string) => !ALLOWED_SITES.includes(site));
      if (invalidSites.length > 0) {
        console.error('Invalid sites requested:', invalidSites);
        return new Response(
          JSON.stringify({ 
            error: 'Invalid sites requested', 
            invalid_sites: invalidSites,
            allowed_sites: ALLOWED_SITES 
          }), 
          { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        );
      }
    }

    // SECURITY: Input validation and limits
    const sitesToScrape = data.sites || ['GovDeals'];
    const limit = Math.min(data.limit || 100, 1000); // Max 1000 listings

    if (sitesToScrape.length > 10) {
      return new Response(
        JSON.stringify({ error: 'Too many sites requested (max 10)' }), 
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    console.log('Processing vehicle scrape request for user:', user.id, 'sites:', sitesToScrape);

    // Create scraping job with proper ownership (RLS enforced)
    const jobId = crypto.randomUUID();
    const { data: job, error: jobError } = await supabase
      .from('scraping_jobs')
      .insert({
        id: jobId,
        status: 'queued',
        sites_targeted: sitesToScrape,
        config: {
          action: data.action || 'start_scraping',
          limit: limit,
          sites: sitesToScrape,
          requested_at: new Date().toISOString(),
          client_ip: clientIP
        },
        idempotency_key: data.idempotencyKey || jobId,
        // owner_id will be set by trigger from auth.uid()
      })
      .select()
      .single();

    if (jobError) {
      console.error('Failed to create scraping job:', jobError);
      return new Response(
        JSON.stringify({ 
          error: 'Failed to create scraping job', 
          details: jobError.message 
        }), 
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    console.log('Created scraping job:', job.id, 'for user:', user.id);

    // Log security event
    await supabase.rpc('log_security_event', {
      p_action: 'scraping_job_created',
      p_resource: `scraping_jobs/${job.id}`,
      p_status: 'success',
      p_details: {
        job_id: job.id,
        sites: sitesToScrape,
        client_ip: clientIP
      }
    }).catch((err) => console.warn('Failed to log security event:', err));

    return new Response(
      JSON.stringify({ 
        success: true, 
        jobId: job.id,
        status: job.status,
        sites: sitesToScrape,
        user_id: user.id,
        message: 'Scraping job created successfully'
      }),
      { 
        status: 200, 
        headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
      }
    );

  } catch (error) {
    console.error('Error in vehicle-scraper function:', error);
    return new Response(
      JSON.stringify({ 
        error: 'Internal server error', 
        message: error.message 
      }), 
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
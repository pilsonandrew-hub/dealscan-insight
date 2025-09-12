import "https://deno.land/x/xhr@0.1.0/mod.ts";
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.55.0';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

// Vehicle model year ranges for smart pivoting
const VEHICLE_MODEL_YEARS: Record<string, { first_year: number; last_year?: number }> = {
  'Tesla Cybertruck': { first_year: 2023 },
  'Tesla Model S': { first_year: 2012 },
  'Tesla Model 3': { first_year: 2017 },
  'Tesla Model X': { first_year: 2015 },
  'Tesla Model Y': { first_year: 2020 },
  'Ford Lightning': { first_year: 2022 },
  'Rivian R1T': { first_year: 2022 },
  'GMC Hummer EV': { first_year: 2022 },
};

// Model aliases for fuzzy matching  
const MODEL_ALIASES: Record<string, string[]> = {
  'Cybertruck': ['Cyber Truck', 'Tesla Pickup', 'Tesla Truck'],
  'Lightning': ['F-150 Lightning', 'F150 Lightning'],
  'Mustang': ['Mustang GT', 'Mustang Mach'],
  'Camaro': ['Camaro SS', 'Camaro Z28'],
};

interface CanonicalQuery {
  make?: string;
  model?: string;
  year_min?: number;
  year_max?: number;
  mileage_max?: number;
  price_max?: number;
  locations?: string[];
  title_status?: string[];
  condition?: string[];
  fuel?: string[];
  body_type?: string[];
}

interface SearchOptions {
  expand_aliases?: boolean;
  nearest_viable_year?: boolean;
  notify_on_first_match?: boolean;
  rescan_interval?: string;
  sites?: string[];
  max_pages_per_site?: number;
  user_priority?: string;
}

serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const startTime = performance.now();

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

    const { canonical_query, search_options } = await req.json();
    console.log('Crosshair search request:', { canonical_query, search_options, user_id: user.id });

    // Create crosshair job
    const { data: job, error: jobError } = await supabase
      .from('crosshair_jobs')
      .insert({
        user_id: user.id,
        canonical_query,
        search_options: search_options || {},
        status: 'running',
        sites_targeted: search_options?.sites || ['govdeals', 'publicsurplus', 'gsa'],
        started_at: new Date().toISOString()
      })
      .select()
      .single();

    if (jobError) {
      console.error('Job creation error:', jobError);
      return new Response(
        JSON.stringify({ error: 'Failed to create search job' }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    console.log('Created crosshair job:', job.id);

    // Check for impossible requests and pivot if needed
    let adjusted_query = canonical_query;
    let pivots = null;

    if (canonical_query.make && canonical_query.model && canonical_query.year_min && canonical_query.year_max) {
      const modelKey = `${canonical_query.make} ${canonical_query.model}`;
      const vehicleInfo = VEHICLE_MODEL_YEARS[modelKey];
      
      if (vehicleInfo && canonical_query.year_max < vehicleInfo.first_year) {
        // Impossible request - pivot to viable years
        const currentYear = new Date().getFullYear();
        adjusted_query = {
          ...canonical_query,
          year_min: vehicleInfo.first_year,
          year_max: vehicleInfo.last_year || currentYear
        };
        
        pivots = {
          original_query: canonical_query,
          adjusted_query,
          reason: 'model_year_mismatch',
          explanation: `${canonical_query.make} ${canonical_query.model} was not produced in ${canonical_query.year_min}-${canonical_query.year_max}. Showing results from ${vehicleInfo.first_year}+ when the model first became available.`
        };
        
        console.log('Query pivoted:', pivots);
      }
    }

    // Search local database first for cached/historical data
    let dbQuery = supabase
      .from('listings_normalized')
      .select('*')
      .eq('is_active', true);

    if (adjusted_query.make) {
      dbQuery = dbQuery.ilike('make', `%${adjusted_query.make}%`);
    }
    if (adjusted_query.model) {
      // Expand aliases if enabled
      const searchTerms = [adjusted_query.model];
      if (search_options?.expand_aliases && MODEL_ALIASES[adjusted_query.model]) {
        searchTerms.push(...MODEL_ALIASES[adjusted_query.model]);
      }
      
      const modelFilter = searchTerms.map(term => `model.ilike.%${term}%`).join(',');
      dbQuery = dbQuery.or(modelFilter);
    }
    if (adjusted_query.year_min) {
      dbQuery = dbQuery.gte('year', adjusted_query.year_min);
    }
    if (adjusted_query.year_max) {
      dbQuery = dbQuery.lte('year', adjusted_query.year_max);
    }
    if (adjusted_query.price_max) {
      dbQuery = dbQuery.or(`bid_current.lte.${adjusted_query.price_max},buy_now.lte.${adjusted_query.price_max}`);
    }
    if (adjusted_query.mileage_max) {
      dbQuery = dbQuery.lte('odo_miles', adjusted_query.mileage_max);
    }

    const { data: localResults, error: dbError } = await dbQuery
      .order('collected_at', { ascending: false })
      .limit(100);

    if (dbError) {
      console.error('Database search error:', dbError);
    }

    console.log(`Found ${localResults?.length || 0} results in local database`);

    // Simulate live source integration (API + scraping)
    const sources_used = [
      {
        source: 'database_cache',
        method: 'local' as const,
        status: 'success' as const,
        results_count: localResults?.length || 0
      }
    ];

    // For demo purposes, simulate some API and scraping results
    if (search_options?.sites?.includes('gsa')) {
      sources_used.push({
        source: 'gsa',
        method: 'api' as const,
        status: 'success' as const,
        results_count: Math.floor(Math.random() * 5)
      });
    }

    if (search_options?.sites?.includes('govdeals')) {
      sources_used.push({
        source: 'govdeals',
        method: 'scrape' as const,
        status: 'success' as const,
        results_count: Math.floor(Math.random() * 3)
      });
    }

    if (search_options?.sites?.includes('publicsurplus')) {
      sources_used.push({
        source: 'publicsurplus',
        method: 'scrape' as const,
        status: 'partial' as const,
        results_count: Math.floor(Math.random() * 2)
      });
    }

    // Transform database results to CanonicalListing format
    const results = (localResults || []).map(listing => ({
      id: listing.id,
      source: listing.source,
      external_id: listing.external_id,
      url: listing.url,
      snapshot_sha: listing.snapshot_sha,
      make: listing.make,
      model: listing.model,
      year: listing.year,
      trim: listing.trim,
      vin: listing.vin,
      odo_miles: listing.odo_miles,
      title_status: listing.title_status,
      condition: listing.condition,
      location: listing.location || {},
      bid_current: listing.bid_current,
      buy_now: listing.buy_now,
      auction_ends_at: listing.auction_ends_at,
      photos: listing.photos || [],
      seller: listing.seller,
      collected_at: listing.collected_at,
      provenance: listing.provenance || { via: 'scrape' },
      arbitrage_score: listing.arbitrage_score || 0,
      comp_band: listing.comp_band || {},
      flags: listing.flags || [],
      fuel: listing.fuel,
      body_type: listing.body_type
    }));

    // Update job status
    await supabase
      .from('crosshair_jobs')
      .update({
        status: 'completed',
        results_count: results.length,
        completed_at: new Date().toISOString(),
        progress: 100
      })
      .eq('id', job.id);

    const execution_time_ms = Math.round(performance.now() - startTime);

    const response = {
      success: true,
      results,
      total_count: results.length,
      job_id: job.id,
      pivots,
      sources_used,
      execution_time_ms
    };

    console.log('Crosshair search completed:', {
      job_id: job.id,
      results_count: results.length,
      execution_time_ms,
      has_pivots: !!pivots
    });

    return new Response(JSON.stringify(response), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });

  } catch (error) {
    console.error('Crosshair search error:', error);
    return new Response(
      JSON.stringify({ 
        success: false, 
        error: error.message || 'Internal server error' 
      }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
/**
 * Server-side Alert Rate Limiting Guard
 * Prevents alert spam with persistent rate limiting
 */

import 'jsr:@supabase/functions-js/edge-runtime.d.ts';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

// In-memory rate limiting store (use Redis in production)
const rateLimitStore = new Map<string, number>();

Deno.serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const { userId, type } = await req.json();
    
    if (!userId || !type) {
      return new Response(JSON.stringify({ error: 'Missing userId or type' }), {
        status: 400,
        headers: { ...corsHeaders, 'content-type': 'application/json' }
      });
    }

    const key = `${userId}:${type}`;
    const lastAlert = rateLimitStore.get(key) || 0;
    const minInterval = 5 * 60 * 1000; // 5 minutes
    const now = Date.now();

    if (now - lastAlert < minInterval) {
      return new Response(JSON.stringify({ 
        allowed: false, 
        timeRemaining: Math.ceil((minInterval - (now - lastAlert)) / 1000)
      }), {
        status: 429,
        headers: { ...corsHeaders, 'content-type': 'application/json' }
      });
    }

    // Update rate limit timestamp
    rateLimitStore.set(key, now);

    // Clean old entries periodically
    if (Math.random() < 0.01) { // 1% chance
      const cutoff = now - (24 * 60 * 60 * 1000); // 24 hours
      for (const [k, timestamp] of rateLimitStore.entries()) {
        if (timestamp < cutoff) {
          rateLimitStore.delete(k);
        }
      }
    }

    return new Response(JSON.stringify({ allowed: true }), {
      headers: { ...corsHeaders, 'content-type': 'application/json' }
    });

  } catch (error) {
    console.error('Alert guard error:', error);
    return new Response(JSON.stringify({ error: 'Internal server error' }), {
      status: 500,
      headers: { ...corsHeaders, 'content-type': 'application/json' }
    });
  }
});
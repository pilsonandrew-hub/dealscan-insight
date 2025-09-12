import "https://deno.land/x/xhr@0.1.0/mod.ts";
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

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
    const { results, format } = await req.json();
    console.log(`Exporting ${results.length} results as ${format}`);

    if (format === 'csv') {
      // Generate CSV
      const headers = [
        'Year', 'Make', 'Model', 'Trim', 'VIN', 'Mileage', 'Price', 'Source', 
        'Location', 'Auction End', 'Arbitrage Score', 'Provenance', 'URL'
      ];
      
      const csvRows = [
        headers.join(','),
        ...results.map((listing: any) => [
          listing.year || '',
          listing.make || '',
          listing.model || '',
          listing.trim || '',
          listing.vin || '',
          listing.odo_miles || '',
          listing.bid_current || listing.buy_now || '',
          listing.source || '',
          `"${listing.location?.city || ''}, ${listing.location?.state || ''}"`,
          listing.auction_ends_at || '',
          Math.round((listing.arbitrage_score || 0) * 100) + '%',
          listing.provenance?.via || '',
          listing.url || ''
        ].join(','))
      ];

      const csvContent = csvRows.join('\n');

      return new Response(JSON.stringify({ content: csvContent }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    if (format === 'pdf') {
      // Generate simple text-based PDF content (in a real implementation, you'd use a PDF library)
      const pdfContent = `CROSSHAIR SEARCH RESULTS
Generated: ${new Date().toISOString()}
Total Results: ${results.length}

${results.map((listing: any, index: number) => `
${index + 1}. ${listing.year} ${listing.make} ${listing.model}
   Price: $${listing.bid_current || listing.buy_now || 'N/A'}
   Mileage: ${listing.odo_miles ? listing.odo_miles.toLocaleString() : 'N/A'} miles
   Location: ${listing.location?.city || 'N/A'}, ${listing.location?.state || 'N/A'}
   Source: ${listing.source} (${listing.provenance?.via || 'unknown'})
   Arbitrage Score: ${Math.round((listing.arbitrage_score || 0) * 100)}%
   URL: ${listing.url}
   ${listing.auction_ends_at ? `Auction Ends: ${listing.auction_ends_at}` : ''}
`).join('\n')}

End of Report`;

      return new Response(JSON.stringify({ content: pdfContent }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    return new Response(
      JSON.stringify({ error: 'Unsupported format' }),
      { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );

  } catch (error) {
    console.error('Export error:', error);
    return new Response(
      JSON.stringify({ 
        success: false, 
        error: error.message || 'Internal server error' 
      }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
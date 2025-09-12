import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { 
  ExternalLink, 
  Eye, 
  Bell, 
  Download, 
  Pin, 
  Clock, 
  MapPin, 
  DollarSign,
  Gauge,
  AlertTriangle,
  CheckCircle,
  Info
} from "lucide-react";
import { CanonicalListing, SearchResponse } from "@/types/crosshair";
import { formatDistanceToNow } from "date-fns";

interface CrosshairResultsProps {
  searchResponse: SearchResponse;
  onWatch?: (listing: CanonicalListing) => void;
  onExport?: (format: 'csv' | 'pdf') => void;
  onPinQuery?: () => void;
}

export const CrosshairResults = ({ 
  searchResponse, 
  onWatch, 
  onExport, 
  onPinQuery 
}: CrosshairResultsProps) => {
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  
  const { results, pivots, sources_used, total_count, execution_time_ms } = searchResponse;

  const getProvenanceColor = (via: 'api' | 'scrape') => {
    return via === 'api' ? 'bg-green-100 text-green-800' : 'bg-blue-100 text-blue-800';
  };

  const getArbitrageColor = (score: number) => {
    if (score >= 0.7) return 'text-green-600';
    if (score >= 0.5) return 'text-yellow-600';
    return 'text-red-600';
  };

  const formatPrice = (price?: number) => {
    if (!price) return 'N/A';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0,
    }).format(price);
  };

  const formatTimeRemaining = (endTime?: string) => {
    if (!endTime) return 'N/A';
    try {
      return formatDistanceToNow(new Date(endTime), { addSuffix: true });
    } catch {
      return 'N/A';
    }
  };

  return (
    <div className="space-y-6">
      {/* Pivot Banner */}
      {pivots && (
        <Card className="border-yellow-200 bg-yellow-50">
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
              <div>
                <h4 className="font-medium text-yellow-800">Query Adjusted</h4>
                <p className="text-sm text-yellow-700 mt-1">{pivots.explanation}</p>
                <div className="mt-2 text-xs text-yellow-600">
                  <span className="font-medium">Original:</span> {pivots.original_query.year_min}-{pivots.original_query.year_max} →{' '}
                  <span className="font-medium">Adjusted:</span> {pivots.adjusted_query.year_min}-{pivots.adjusted_query.year_max}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Sources Status */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg">Source Status</CardTitle>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Clock className="w-4 h-4" />
              {execution_time_ms}ms
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {sources_used.map((source, index) => (
              <div key={index} className="flex items-center justify-between p-3 border rounded-lg">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${
                    source.status === 'success' ? 'bg-green-500' :
                    source.status === 'partial' ? 'bg-yellow-500' : 'bg-red-500'
                  }`} />
                  <span className="font-medium">{source.source}</span>
                  <Badge 
                    variant={source.method === 'api' ? 'default' : 'secondary'}
                    className="text-xs"
                  >
                    {source.method.toUpperCase()}
                  </Badge>
                </div>
                <span className="text-sm text-muted-foreground">
                  {source.results_count} results
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Results Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xl font-semibold">
            {total_count} Results Found
          </h3>
          <p className="text-sm text-muted-foreground">
            Showing unified results from API and scraping sources
          </p>
        </div>
        
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onExport?.('csv')}
          >
            <Download className="w-4 h-4 mr-2" />
            CSV
          </Button>
          <Button
            variant="outline" 
            size="sm"
            onClick={() => onExport?.('pdf')}
          >
            <Download className="w-4 h-4 mr-2" />
            PDF
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onPinQuery}
          >
            <Pin className="w-4 h-4 mr-2" />
            Pin Query
          </Button>
        </div>
      </div>

      {/* Results */}
      {results.length === 0 ? (
        <Card className="text-center py-12">
          <CardContent>
            <Info className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-medium mb-2">No Results Found</h3>
            <p className="text-muted-foreground mb-4">
              No vehicles matching your criteria were found across the selected sources.
            </p>
            <Button variant="outline" onClick={onPinQuery}>
              <Bell className="w-4 h-4 mr-2" />
              Set Up Alert for Future Matches
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
          {results.map((listing) => (
            <Card key={listing.id} className="overflow-hidden">
              <div className="relative">
                {listing.photos.length > 0 ? (
                  <img 
                    src={listing.photos[0]} 
                    alt={`${listing.year} ${listing.make} ${listing.model}`}
                    className="w-full h-48 object-cover"
                    onError={(e) => {
                      e.currentTarget.src = '/placeholder.svg';
                    }}
                  />
                ) : (
                  <div className="w-full h-48 bg-muted flex items-center justify-center">
                    <span className="text-muted-foreground">No image</span>
                  </div>
                )}
                
                {/* Provenance chip */}
                <Badge 
                  className={`absolute top-2 right-2 ${getProvenanceColor(listing.provenance.via)}`}
                >
                  {listing.provenance.via.toUpperCase()}
                </Badge>

                {/* Arbitrage score */}
                <div className="absolute top-2 left-2 bg-white/90 rounded-md px-2 py-1">
                  <div className="flex items-center gap-1">
                    <Gauge className="w-3 h-3" />
                    <span className={`text-xs font-medium ${getArbitrageColor(listing.arbitrage_score)}`}>
                      {Math.round(listing.arbitrage_score * 100)}%
                    </span>
                  </div>
                </div>
              </div>

              <CardContent className="p-4">
                <div className="space-y-3">
                  {/* Title */}
                  <div>
                    <h4 className="font-semibold text-lg">
                      {listing.year} {listing.make} {listing.model}
                    </h4>
                    {listing.trim && (
                      <p className="text-sm text-muted-foreground">{listing.trim}</p>
                    )}
                  </div>

                  {/* Key metrics */}
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div className="flex items-center gap-1">
                      <DollarSign className="w-3 h-3 text-muted-foreground" />
                      <span className="font-medium">
                        {formatPrice(listing.bid_current || listing.buy_now)}
                      </span>
                    </div>
                    {listing.odo_miles && (
                      <div>
                        <span className="text-muted-foreground">{listing.odo_miles.toLocaleString()} mi</span>
                      </div>
                    )}
                  </div>

                  {/* Comp band */}
                  {listing.comp_band.p50 && (
                    <div className="text-xs text-muted-foreground">
                      Market: {formatPrice(listing.comp_band.p25)} - {formatPrice(listing.comp_band.p75)}
                      <span className="ml-2 font-medium">
                        Median: {formatPrice(listing.comp_band.p50)}
                      </span>
                    </div>
                  )}

                  {/* Location and timing */}
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <div className="flex items-center gap-1">
                      <MapPin className="w-3 h-3" />
                      <span>{listing.location.city}, {listing.location.state}</span>
                    </div>
                    {listing.auction_ends_at && (
                      <div className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        <span>{formatTimeRemaining(listing.auction_ends_at)}</span>
                      </div>
                    )}
                  </div>

                  {/* Flags */}
                  {listing.flags.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {listing.flags.slice(0, 3).map((flag, index) => (
                        <Badge key={index} variant="outline" className="text-xs">
                          {flag}
                        </Badge>
                      ))}
                      {listing.flags.length > 3 && (
                        <Badge variant="outline" className="text-xs">
                          +{listing.flags.length - 3}
                        </Badge>
                      )}
                    </div>
                  )}

                  <Separator />

                  {/* Actions */}
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      asChild
                    >
                      <a href={listing.url} target="_blank" rel="noopener noreferrer">
                        <ExternalLink className="w-3 h-3 mr-1" />
                        View
                      </a>
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => onWatch?.(listing)}
                    >
                      <Eye className="w-3 h-3 mr-1" />
                      Watch
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};
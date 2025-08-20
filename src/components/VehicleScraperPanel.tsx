import { useState, useEffect } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Play, RefreshCw, Database, ExternalLink, Car, MapPin, DollarSign, Calendar } from 'lucide-react'
import { useVehicleScraper } from '@/hooks/useVehicleScraper'
import { FEDERAL_SITES, STATE_SITES, type SiteName } from '@/types/scraper'
import { formatDistanceToNow } from 'date-fns'

export const VehicleScraperPanel = () => {
  const {
    listings,
    isLoading,
    isScraping,
    error,
    startScraping,
    fetchListings,
    refreshListings
  } = useVehicleScraper()

  const [selectedSites, setSelectedSites] = useState<SiteName[]>(['GovDeals', 'PublicSurplus'])

  useEffect(() => {
    fetchListings()
  }, [fetchListings])

  const handleSiteToggle = (site: SiteName, checked: boolean) => {
    if (checked) {
      setSelectedSites(prev => [...prev, site])
    } else {
      setSelectedSites(prev => prev.filter(s => s !== site))
    }
  }

  const handleStartScraping = async () => {
    if (selectedSites.length === 0) {
      return
    }
    await startScraping(selectedSites)
  }

  const formatCurrency = (amount?: number) => {
    if (!amount) return 'N/A'
    return new Intl.NumberFormat('en-US', { 
      style: 'currency', 
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount)
  }

  const formatMileage = (mileage?: number) => {
    if (!mileage) return 'N/A'
    return new Intl.NumberFormat('en-US').format(mileage) + ' mi'
  }

  return (
    <div className="space-y-6">
      {/* Scraper Controls */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Car className="h-5 w-5" />
            Vehicle Auction Scraper
          </CardTitle>
          <CardDescription>
            Scrape government and surplus auction sites for vehicle listings
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Site Selection */}
          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <h4 className="font-medium mb-3">Federal & Nationwide Sites</h4>
              <ScrollArea className="h-48 border rounded-md p-3">
                <div className="space-y-2">
                  {FEDERAL_SITES.map((site) => (
                    <div key={site} className="flex items-center space-x-2">
                      <Checkbox
                        id={site}
                        checked={selectedSites.includes(site)}
                        onCheckedChange={(checked) => handleSiteToggle(site, !!checked)}
                        disabled={isScraping}
                      />
                      <label htmlFor={site} className="text-sm cursor-pointer">
                        {site}
                      </label>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </div>

            <div>
              <h4 className="font-medium mb-3">State & Municipal Sites</h4>
              <ScrollArea className="h-48 border rounded-md p-3">
                <div className="space-y-2">
                  {STATE_SITES.map((site) => (
                    <div key={site} className="flex items-center space-x-2">
                      <Checkbox
                        id={site}
                        checked={selectedSites.includes(site)}
                        onCheckedChange={(checked) => handleSiteToggle(site, !!checked)}
                        disabled={isScraping}
                      />
                      <label htmlFor={site} className="text-sm cursor-pointer">
                        {site}
                      </label>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </div>
          </div>

          {/* Control Buttons */}
          <div className="flex gap-3">
            <Button
              onClick={handleStartScraping}
              disabled={isScraping || selectedSites.length === 0}
              className="flex items-center gap-2"
            >
              <Play className="h-4 w-4" />
              {isScraping ? 'Scraping...' : 'Start Scraping'}
            </Button>
            <Button
              variant="outline"
              onClick={refreshListings}
              disabled={isLoading}
              className="flex items-center gap-2"
            >
              <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>

          {selectedSites.length > 0 && (
            <div>
              <p className="text-sm text-muted-foreground mb-2">Selected sites ({selectedSites.length})</p>
              <div className="flex flex-wrap gap-1">
                {selectedSites.map((site) => (
                  <Badge key={site} variant="secondary" className="text-xs">
                    {site}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Error Display */}
          {error && (
            <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive">
              <strong>Error:</strong> {error}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Listings Display */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database className="h-5 w-5" />
            Scraped Vehicle Listings ({listings.length})
          </CardTitle>
          <CardDescription>
            Recent vehicle listings from auction sites
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading && listings.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              Loading listings...
            </div>
          ) : listings.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No listings found. Try running the scraper to collect data.
            </div>
          ) : (
            <ScrollArea className="h-96">
              <div className="space-y-4">
                {listings.map((listing) => (
                  <Card key={listing.id} className="p-4">
                    <div className="flex justify-between items-start mb-3">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline">{listing.source_site}</Badge>
                        {listing.title_status && (
                          <Badge variant={listing.title_status === 'clean' ? 'default' : 'destructive'}>
                            {listing.title_status}
                          </Badge>
                        )}
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => window.open(listing.listing_url, '_blank')}
                      >
                        <ExternalLink className="h-4 w-4" />
                      </Button>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div>
                        <h4 className="font-medium text-base mb-2">
                          {listing.year && `${listing.year} `}
                          {listing.make && `${listing.make} `}
                          {listing.model && listing.model}
                          {listing.trim && ` ${listing.trim}`}
                        </h4>
                        {listing.vin && (
                          <p className="text-sm text-muted-foreground">VIN: {listing.vin}</p>
                        )}
                      </div>

                      <div className="space-y-2">
                        {listing.current_bid && (
                          <div className="flex items-center gap-2 text-sm">
                            <DollarSign className="h-4 w-4 text-green-600" />
                            <span className="font-medium">{formatCurrency(listing.current_bid)}</span>
                          </div>
                        )}
                        {listing.mileage && (
                          <div className="flex items-center gap-2 text-sm">
                            <Car className="h-4 w-4 text-blue-600" />
                            <span>{formatMileage(listing.mileage)}</span>
                          </div>
                        )}
                        {listing.location && (
                          <div className="flex items-center gap-2 text-sm">
                            <MapPin className="h-4 w-4 text-orange-600" />
                            <span>{listing.location}</span>
                          </div>
                        )}
                      </div>

                      <div className="space-y-2">
                        {listing.auction_end && (
                          <div className="flex items-center gap-2 text-sm">
                            <Calendar className="h-4 w-4 text-purple-600" />
                            <span>{new Date(listing.auction_end).toLocaleDateString()}</span>
                          </div>
                        )}
                        <p className="text-xs text-muted-foreground">
                          Scraped {formatDistanceToNow(new Date(listing.created_at), { addSuffix: true })}
                        </p>
                      </div>
                    </div>

                    {listing.description && (
                      <>
                        <Separator className="my-3" />
                        <p className="text-sm text-muted-foreground line-clamp-2">
                          {listing.description}
                        </p>
                      </>
                    )}
                  </Card>
                ))}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
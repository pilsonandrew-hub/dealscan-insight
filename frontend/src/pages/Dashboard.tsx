import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Layout } from '@/components/Layout'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { 
  TrendingUp, 
  TrendingDown, 
  DollarSign, 
  Car, 
  AlertTriangle,
  Clock,
  Target,
  Brain
} from 'lucide-react'
import { opportunitiesAPI, vehiclesAPI } from '@/lib/api'
import { cn } from '@/lib/utils'

export default function Dashboard() {
  // Fetch dashboard data
  const { data: opportunities, isLoading: opportunitiesLoading } = useQuery({
    queryKey: ['opportunities', { limit: 5, sort_by: 'score' }],
    queryFn: () => opportunitiesAPI.getOpportunities({ page_size: 5, sort_by: 'score' }),
  })

  const { data: vehicleStats, isLoading: statsLoading } = useQuery({
    queryKey: ['vehicle-stats'],
    queryFn: () => vehiclesAPI.getStats(),
  })

  const stats = [
    {
      name: 'Active Opportunities',
      value: opportunities?.data?.total || 0,
      change: '+12%',
      changeType: 'positive' as const,
      icon: Target,
    },
    {
      name: 'Avg. Profit Margin',
      value: '24.5%',
      change: '+2.3%',
      changeType: 'positive' as const,
      icon: TrendingUp,
    },
    {
      name: 'Total Vehicles',
      value: vehicleStats?.data?.summary?.total_vehicles || 0,
      change: '+8%',
      changeType: 'positive' as const,
      icon: Car,
    },
    {
      name: 'High Risk Items',
      value: '23',
      change: '-5%',
      changeType: 'negative' as const,
      icon: AlertTriangle,
    },
  ]

  const topOpportunities = opportunities?.data?.items || []

  return (
    <Layout>
      <div className="p-6">
        <div className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground">
            Welcome back! Here's what's happening with your vehicle opportunities.
          </p>
        </div>

        {/* Stats Grid */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-8">
          {stats.map((stat) => (
            <Card key={stat.name}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">
                  {stat.name}
                </CardTitle>
                <stat.icon className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {typeof stat.value === 'number' ? stat.value.toLocaleString() : stat.value}
                </div>
                <p className="text-xs text-muted-foreground">
                  <span
                    className={cn(
                      stat.changeType === 'positive' ? 'text-green-600' : 'text-red-600'
                    )}
                  >
                    {stat.change}
                  </span>{' '}
                  from last month
                </p>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-7">
          {/* Top Opportunities */}
          <Card className="col-span-4">
            <CardHeader>
              <CardTitle className="flex items-center">
                <Brain className="mr-2 h-5 w-5" />
                Top AI-Scored Opportunities
              </CardTitle>
              <CardDescription>
                Highest scoring vehicle arbitrage opportunities based on ML analysis
              </CardDescription>
            </CardHeader>
            <CardContent>
              {opportunitiesLoading ? (
                <div className="space-y-3">
                  {[...Array(5)].map((_, i) => (
                    <div key={i} className="h-16 bg-gray-100 rounded animate-pulse" />
                  ))}
                </div>
              ) : (
                <div className="space-y-4">
                  {topOpportunities.map((opportunity: any) => (
                    <div
                      key={opportunity.id}
                      className="flex items-center justify-between p-3 border rounded-lg hover:bg-gray-50 transition-colors"
                    >
                      <div className="flex-1">
                        <div className="flex items-center space-x-2">
                          <p className="font-medium">
                            {opportunity.vehicle_info.year} {opportunity.vehicle_info.make} {opportunity.vehicle_info.model}
                          </p>
                          <Badge variant={
                            opportunity.opportunity_score >= 0.8 ? 'default' :
                            opportunity.opportunity_score >= 0.6 ? 'secondary' : 'outline'
                          }>
                            Score: {(opportunity.opportunity_score * 100).toFixed(0)}%
                          </Badge>
                        </div>
                        <div className="flex items-center space-x-4 text-sm text-muted-foreground mt-1">
                          <span>Bid: ${opportunity.vehicle_info.current_bid?.toLocaleString()}</span>
                          <span>Profit: ${opportunity.potential_profit?.toLocaleString()}</span>
                          <span>ROI: {opportunity.roi_percentage?.toFixed(1)}%</span>
                        </div>
                      </div>
                      <div className="flex items-center space-x-2">
                        {opportunity.auction_end && (
                          <div className="text-right text-sm">
                            <div className="flex items-center text-muted-foreground">
                              <Clock className="mr-1 h-3 w-3" />
                              Ends soon
                            </div>
                          </div>
                        )}
                        <Button size="sm" variant="outline">
                          View
                        </Button>
                      </div>
                    </div>
                  ))}
                  
                  {topOpportunities.length === 0 && (
                    <div className="text-center py-8 text-muted-foreground">
                      <Brain className="mx-auto h-12 w-12 mb-4 opacity-50" />
                      <p>No opportunities found</p>
                      <p className="text-sm">Check back later for new analysis results</p>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Market Summary */}
          <Card className="col-span-3">
            <CardHeader>
              <CardTitle>Market Summary</CardTitle>
              <CardDescription>
                Current market overview and trends
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Avg. Vehicle Price</span>
                  <span className="text-lg font-bold">
                    ${vehicleStats?.data?.summary?.avg_price?.toLocaleString() || '0'}
                  </span>
                </div>
                
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Active Auctions</span>
                  <span className="text-lg font-bold">
                    {vehicleStats?.data?.summary?.active_auctions?.toLocaleString() || '0'}
                  </span>
                </div>

                <div className="pt-4 border-t">
                  <h4 className="text-sm font-medium mb-3">Top Makes</h4>
                  <div className="space-y-2">
                    {vehicleStats?.data?.top_makes?.slice(0, 5).map((make: any) => (
                      <div key={make.make} className="flex items-center justify-between">
                        <span className="text-sm">{make.make}</span>
                        <Badge variant="outline">{make.count}</Badge>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="pt-4 border-t">
                  <h4 className="text-sm font-medium mb-3">Risk Distribution</h4>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm">Low Risk</span>
                      <div className="flex items-center space-x-2">
                        <div className="w-16 h-2 bg-green-200 rounded">
                          <div className="w-12 h-2 bg-green-500 rounded"></div>
                        </div>
                        <span className="text-sm">75%</span>
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm">Medium Risk</span>
                      <div className="flex items-center space-x-2">
                        <div className="w-16 h-2 bg-yellow-200 rounded">
                          <div className="w-6 h-2 bg-yellow-500 rounded"></div>
                        </div>
                        <span className="text-sm">20%</span>
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm">High Risk</span>
                      <div className="flex items-center space-x-2">
                        <div className="w-16 h-2 bg-red-200 rounded">
                          <div className="w-1 h-2 bg-red-500 rounded"></div>
                        </div>
                        <span className="text-sm">5%</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Quick Actions */}
        <div className="mt-8">
          <h2 className="text-xl font-semibold mb-4">Quick Actions</h2>
          <div className="grid gap-4 md:grid-cols-3">
            <Card className="card-hover cursor-pointer">
              <CardContent className="p-6 text-center">
                <TrendingUp className="mx-auto h-8 w-8 text-primary mb-2" />
                <h3 className="font-medium">View All Opportunities</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  Browse and filter all available opportunities
                </p>
              </CardContent>
            </Card>

            <Card className="card-hover cursor-pointer">
              <CardContent className="p-6 text-center">
                <Car className="mx-auto h-8 w-8 text-primary mb-2" />
                <h3 className="font-medium">Browse Vehicles</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  Search through all available vehicles
                </p>
              </CardContent>
            </Card>

            <Card className="card-hover cursor-pointer">
              <CardContent className="p-6 text-center">
                <DollarSign className="mx-auto h-8 w-8 text-primary mb-2" />
                <h3 className="font-medium">Upload Data</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  Import new vehicle data for analysis
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </Layout>
  )
}
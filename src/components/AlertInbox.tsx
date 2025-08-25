/**
 * Red Bubble Alert Inbox Component
 * In-house notification system with visual indicators
 */

import React, { useState, useEffect } from 'react';
import { Bell, X, AlertTriangle, TrendingUp, Clock, Car } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import { inHouseAlertSystem, type InHouseAlert } from '@/services/inHouseAlertSystem';

interface AlertInboxProps {
  userId: string;
  onAlertClick?: (alert: InHouseAlert) => void;
}

export function AlertInbox({ userId, onAlertClick }: AlertInboxProps) {
  const [alerts, setAlerts] = useState<InHouseAlert[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  // Load alerts on component mount and user change
  useEffect(() => {
    loadAlerts();
    loadUnreadCount();

    // Refresh every 30 seconds
    const interval = setInterval(() => {
      loadAlerts();
      loadUnreadCount();
    }, 30000);

    return () => clearInterval(interval);
  }, [userId]);

  const loadAlerts = async () => {
    try {
      setLoading(true);
      const userAlerts = await inHouseAlertSystem.getUserAlerts(userId, true);
      setAlerts(userAlerts);
    } catch (error) {
      console.error('Failed to load alerts:', error);
      toast.error('Failed to load alerts');
    } finally {
      setLoading(false);
    }
  };

  const loadUnreadCount = async () => {
    try {
      const count = await inHouseAlertSystem.getUnreadCount(userId);
      setUnreadCount(count);
    } catch (error) {
      console.error('Failed to load unread count:', error);
    }
  };

  const handleAlertClick = async (alert: InHouseAlert) => {
    try {
      await inHouseAlertSystem.markAlertViewed(alert.id);
      await loadUnreadCount();
      
      if (onAlertClick) {
        onAlertClick(alert);
      }
      
      // Close inbox after clicking alert
      setIsOpen(false);
    } catch (error) {
      console.error('Failed to mark alert as viewed:', error);
    }
  };

  const handleDismissAlert = async (alert: InHouseAlert, event: React.MouseEvent) => {
    event.stopPropagation();
    
    try {
      await inHouseAlertSystem.dismissAlert(alert.id);
      await loadAlerts();
      await loadUnreadCount();
      toast.success('Alert dismissed');
    } catch (error) {
      console.error('Failed to dismiss alert:', error);
      toast.error('Failed to dismiss alert');
    }
  };

  const handleClearAll = async () => {
    try {
      await inHouseAlertSystem.clearAllAlerts(userId);
      await loadAlerts();
      await loadUnreadCount();
      toast.success('All alerts cleared');
    } catch (error) {
      console.error('Failed to clear alerts:', error);
      toast.error('Failed to clear alerts');
    }
  };

  const getAlertIcon = (type: InHouseAlert['type']) => {
    switch (type) {
      case 'hot_deal':
        return <TrendingUp className="h-4 w-4 text-red-500" />;
      case 'price_drop':
        return <TrendingUp className="h-4 w-4 text-green-500" />;
      case 'ending_soon':
        return <Clock className="h-4 w-4 text-orange-500" />;
      case 'new_opportunity':
        return <Car className="h-4 w-4 text-blue-500" />;
      default:
        return <AlertTriangle className="h-4 w-4 text-gray-500" />;
    }
  };

  const getPriorityColor = (priority: InHouseAlert['priority']) => {
    switch (priority) {
      case 'critical':
        return 'bg-red-500 text-white';
      case 'high':
        return 'bg-orange-500 text-white';
      case 'medium':
        return 'bg-yellow-500 text-white';
      case 'low':
        return 'bg-gray-500 text-white';
      default:
        return 'bg-gray-500 text-white';
    }
  };

  const formatTimestamp = (timestamp: Date) => {
    const now = new Date();
    const diffMs = now.getTime() - timestamp.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffMins = Math.floor(diffMs / (1000 * 60));

    if (diffMins < 60) {
      return `${diffMins}m ago`;
    } else if (diffHours < 24) {
      return `${diffHours}h ago`;
    } else {
      return timestamp.toLocaleDateString();
    }
  };

  const getOpportunityDetails = (opportunity: any) => {
    return {
      profit: opportunity.profit || 0,
      roi: opportunity.roi || 0,
      vehicle: `${opportunity.year || ''} ${opportunity.make || ''} ${opportunity.model || ''}`.trim()
    };
  };

  return (
    <div className="relative">
      {/* Alert Bell Button with Red Bubble */}
      <Button
        variant="ghost"
        size="sm"
        className="relative p-2"
        onClick={() => setIsOpen(!isOpen)}
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <Badge 
            variant="destructive" 
            className="absolute -top-1 -right-1 h-5 w-5 rounded-full p-0 text-xs flex items-center justify-center animate-pulse"
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </Badge>
        )}
      </Button>

      {/* Alert Inbox Dropdown */}
      {isOpen && (
        <Card className="absolute right-0 top-full mt-2 w-96 max-w-screen-sm z-50 shadow-lg border border-border">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg flex items-center gap-2">
                <Bell className="h-5 w-5" />
                Deal Alerts
                {unreadCount > 0 && (
                  <Badge variant="destructive" className="ml-2">
                    {unreadCount} new
                  </Badge>
                )}
              </CardTitle>
              <div className="flex items-center gap-2">
                {alerts.length > 0 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleClearAll}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    Clear All
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setIsOpen(false)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </CardHeader>

          <CardContent className="p-0">
            <ScrollArea className="h-96">
              {loading ? (
                <div className="p-4 text-center text-muted-foreground">
                  Loading alerts...
                </div>
              ) : alerts.length === 0 ? (
                <div className="p-6 text-center text-muted-foreground">
                  <Bell className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  <p>No alerts yet</p>
                  <p className="text-sm">You'll be notified of new opportunities here</p>
                </div>
              ) : (
                <div className="space-y-0">
                  {alerts.map((alert, index) => {
                    const details = getOpportunityDetails(alert.opportunity);
                    
                    return (
                      <React.Fragment key={alert.id}>
                        <div
                          className={`p-4 cursor-pointer transition-colors hover:bg-muted/50 ${
                            !alert.viewed ? 'bg-accent/30' : ''
                          }`}
                          onClick={() => handleAlertClick(alert)}
                        >
                          <div className="flex items-start gap-3">
                            <div className="flex-shrink-0 mt-1">
                              {getAlertIcon(alert.type)}
                            </div>
                            
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <h4 className="font-medium text-sm truncate">
                                  {alert.title}
                                </h4>
                                <Badge
                                  variant="secondary"
                                  className={`text-xs ${getPriorityColor(alert.priority)}`}
                                >
                                  {alert.priority}
                                </Badge>
                                {!alert.viewed && (
                                  <div className="w-2 h-2 bg-red-500 rounded-full"></div>
                                )}
                              </div>
                              
                              <p className="text-sm text-muted-foreground mb-2">
                                {alert.message}
                              </p>
                              
                              <div className="flex items-center justify-between text-xs text-muted-foreground">
                                <span>{details.vehicle}</span>
                                <span>{formatTimestamp(alert.timestamp)}</span>
                              </div>
                              
                              <div className="flex items-center gap-4 mt-1 text-xs">
                                <span className="text-green-600 font-medium">
                                  +${details.profit.toLocaleString()}
                                </span>
                                <span className="text-blue-600">
                                  {details.roi.toFixed(1)}% ROI
                                </span>
                              </div>
                            </div>
                            
                            <Button
                              variant="ghost"
                              size="sm"
                              className="flex-shrink-0 h-8 w-8 p-0 hover:bg-destructive hover:text-destructive-foreground"
                              onClick={(e) => handleDismissAlert(alert, e)}
                            >
                              <X className="h-3 w-3" />
                            </Button>
                          </div>
                        </div>
                        
                        {index < alerts.length - 1 && <Separator />}
                      </React.Fragment>
                    );
                  })}
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
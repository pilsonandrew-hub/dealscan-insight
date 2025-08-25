/**
 * Real-time notifications and alerts system
 */

import { useEffect, useCallback, useState } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';
import { Opportunity } from '@/types/dealerscope';

interface NotificationSettings {
  enabled: boolean;
  minROI: number;
  minProfit: number;
  maxRisk: number;
  preferredMakes: string[];
  states: string[];
  soundEnabled: boolean;
}

interface Alert {
  id: string;
  type: 'hot_deal' | 'price_drop' | 'ending_soon' | 'new_opportunity';
  opportunity: Opportunity;
  message: string;
  timestamp: Date;
  dismissed: boolean;
}

export function useRealtimeNotifications() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [settings, setSettings] = useState<NotificationSettings>({
    enabled: true,
    minROI: 15,
    minProfit: 2000,
    maxRisk: 60,
    preferredMakes: [],
    states: [],
    soundEnabled: true
  });

  const playNotificationSound = useCallback(() => {
    if (settings.soundEnabled) {
      // Create a simple notification sound
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      const oscillator = audioContext.createOscillator();
      const gainNode = audioContext.createGain();
      
      oscillator.connect(gainNode);
      gainNode.connect(audioContext.destination);
      
      oscillator.frequency.setValueAtTime(800, audioContext.currentTime);
      oscillator.frequency.setValueAtTime(600, audioContext.currentTime + 0.1);
      
      gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.3);
      
      oscillator.start(audioContext.currentTime);
      oscillator.stop(audioContext.currentTime + 0.3);
    }
  }, [settings.soundEnabled]);

  const shouldNotify = useCallback((opportunity: Opportunity): boolean => {
    if (!settings.enabled) return false;
    
    // Check ROI threshold
    if (opportunity.roi < settings.minROI) return false;
    
    // Check profit threshold
    if (opportunity.profit < settings.minProfit) return false;
    
    // Check risk threshold
    if (opportunity.risk_score > settings.maxRisk) return false;
    
    // Check preferred makes (if any specified)
    if (settings.preferredMakes.length > 0 && 
        !settings.preferredMakes.some(make => 
          opportunity.make.toLowerCase().includes(make.toLowerCase()))) {
      return false;
    }
    
    // Check states (if any specified)
    if (settings.states.length > 0 && 
        !settings.states.includes(opportunity.state || '')) {
      return false;
    }
    
    return true;
  }, [settings]);

  const createAlert = useCallback((
    type: Alert['type'], 
    opportunity: Opportunity, 
    message: string
  ): Alert => {
    return {
      id: `${type}-${opportunity.id}-${Date.now()}`,
      type,
      opportunity,
      message,
      timestamp: new Date(),
      dismissed: false
    };
  }, []);

  const addAlert = useCallback((alert: Alert) => {
    setAlerts(prev => [alert, ...prev.slice(0, 49)]); // Keep last 50 alerts
    
    // Show toast notification
    const getIcon = () => {
      switch (alert.type) {
        case 'hot_deal': return '🔥';
        case 'price_drop': return '💰';
        case 'ending_soon': return '⏰';
        case 'new_opportunity': return '🚗';
        default: return '📢';
      }
    };

    toast.success(`${getIcon()} ${alert.message}`, {
      description: `${alert.opportunity.year} ${alert.opportunity.make} ${alert.opportunity.model} - ${alert.opportunity.roi.toFixed(1)}% ROI`,
      action: {
        label: 'View Deal',
        onClick: () => {
          // Navigate to the deal or highlight it
          const element = document.getElementById(`deal-${alert.opportunity.id}`);
          if (element) {
            element.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }
        }
      },
      duration: 10000
    });

    // Play sound
    playNotificationSound();
  }, [playNotificationSound]);

  const dismissAlert = useCallback((alertId: string) => {
    setAlerts(prev => prev.map(alert => 
      alert.id === alertId ? { ...alert, dismissed: true } : alert
    ));
  }, []);

  const clearAllAlerts = useCallback(() => {
    setAlerts([]);
  }, []);

  // Set up real-time subscriptions
  useEffect(() => {
    if (!settings.enabled) return;

    // Subscribe to new opportunities
    const opportunitiesChannel = supabase
      .channel('opportunities-notifications')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'opportunities'
        },
        (payload) => {
          const opportunity = payload.new as Opportunity;
          
          if (shouldNotify(opportunity)) {
            let alertType: Alert['type'] = 'new_opportunity';
            let message = 'New opportunity found';
            
            // Determine alert type based on criteria
            if (opportunity.roi > 30) {
              alertType = 'hot_deal';
              message = 'Hot deal alert!';
            } else if (opportunity.profit > 10000) {
              alertType = 'hot_deal';
              message = 'High-profit opportunity!';
            }
            
            const alert = createAlert(alertType, opportunity, message);
            addAlert(alert);
          }
        }
      )
      .subscribe();

    // Subscribe to opportunity updates (price changes, etc.)
    const updatesChannel = supabase
      .channel('opportunities-updates')
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'opportunities'
        },
        (payload) => {
          const oldOpp = payload.old as Opportunity;
          const newOpp = payload.new as Opportunity;
          
          // Check for significant price drops
          if (newOpp.current_bid < oldOpp.current_bid * 0.95 && shouldNotify(newOpp)) {
            const alert = createAlert(
              'price_drop', 
              newOpp, 
              'Price drop detected!'
            );
            addAlert(alert);
          }
          
          // Check for auction ending soon
          const auctionEnd = new Date(newOpp.auction_end || '');
          const now = new Date();
          const hoursRemaining = (auctionEnd.getTime() - now.getTime()) / (1000 * 60 * 60);
          
          if (hoursRemaining <= 24 && hoursRemaining > 0 && shouldNotify(newOpp)) {
            const alert = createAlert(
              'ending_soon',
              newOpp,
              `Auction ending in ${Math.round(hoursRemaining)} hours`
            );
            addAlert(alert);
          }
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(opportunitiesChannel);
      supabase.removeChannel(updatesChannel);
    };
  }, [settings, shouldNotify, createAlert, addAlert]);

  // Request notification permissions
  useEffect(() => {
    if (settings.enabled && 'Notification' in window) {
      if (Notification.permission === 'default') {
        Notification.requestPermission().then(permission => {
          if (permission === 'granted') {
            console.log('Notifications enabled');
          }
        });
      }
    }
  }, [settings.enabled]);

  const updateSettings = useCallback((newSettings: Partial<NotificationSettings>) => {
    setSettings(prev => ({ ...prev, ...newSettings }));
  }, []);

  const activeAlerts = alerts.filter(alert => !alert.dismissed);
  const unreadCount = activeAlerts.length;

  return {
    alerts: activeAlerts,
    unreadCount,
    settings,
    updateSettings,
    dismissAlert,
    clearAllAlerts,
    addAlert: (type: Alert['type'], opportunity: Opportunity, message: string) => {
      const alert = createAlert(type, opportunity, message);
      addAlert(alert);
    }
  };
}
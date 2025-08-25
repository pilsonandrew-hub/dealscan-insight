/**
 * Real-time Alert Updates Hook
 * Uses Supabase Realtime for instant notification updates
 */

import { useEffect } from 'react';
import { supabase } from '@/integrations/supabase/client';

export function useRealtimeAlerts(userId: string, onChange: () => void) {
  useEffect(() => {
    if (!userId) return;
    
    const channel = supabase
      .channel(`alerts-${userId}`)
      .on(
        'postgres_changes',
        { 
          event: '*', 
          schema: 'public', 
          table: 'user_alerts', 
          filter: `user_id=eq.${userId}` 
        },
        () => onChange()
      )
      .subscribe();
    
    return () => { 
      supabase.removeChannel(channel); 
    };
  }, [userId, onChange]);
}
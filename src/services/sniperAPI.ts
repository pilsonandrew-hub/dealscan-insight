import { supabase } from '@/integrations/supabase/client';
import { settings } from '@/config/settings';

const API_BASE = settings.api.baseUrl;

export interface SniperTargetSummary {
  id: string;
  opportunity_id: string;
  status: string;
}

export interface SniperTargetListResponse<T = unknown> {
  targets: T[];
}

async function getAccessToken(): Promise<string | null> {
  const { data: { session } } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}

function buildAuthHeaders(token: string | null, extra?: Record<string, string>): Record<string, string> {
  return {
    ...(extra || {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export const sniperAPI = {
  async listTargets<T = unknown>(): Promise<SniperTargetListResponse<T>> {
    const token = await getAccessToken();
    if (!token) return { targets: [] };

    const resp = await fetch(`${API_BASE}/api/sniper/targets`, {
      headers: buildAuthHeaders(token),
    });

    if (!resp.ok) {
      throw new Error(`Sniper target list failed: ${resp.status}`);
    }

    return resp.json();
  },

  async createTarget(payload: { opportunity_id: string; max_bid: number; telegram_chat_id?: string }): Promise<any> {
    const token = await getAccessToken();
    if (!token) {
      throw new Error('You must be logged in to snipe.');
    }

    const resp = await fetch(`${API_BASE}/api/sniper/targets`, {
      method: 'POST',
      headers: buildAuthHeaders(token, { 'Content-Type': 'application/json' }),
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}));
      throw new Error(errData.detail || `Sniper target create failed: ${resp.status}`);
    }

    return resp.json().catch(() => ({}));
  },

  async deleteTarget(targetId: string): Promise<void> {
    const token = await getAccessToken();
    if (!token) return;

    const resp = await fetch(`${API_BASE}/api/sniper/targets/${targetId}`, {
      method: 'DELETE',
      headers: buildAuthHeaders(token),
    });

    if (!resp.ok) {
      throw new Error(`Sniper target delete failed: ${resp.status}`);
    }
  },
};

export default sniperAPI;

import { supabase } from '@/integrations/supabase/client';
import { settings } from '@/config/settings';

const API_BASE = settings.api.baseUrl;

async function getAuthToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

function authHeaders(token: string | null, extra?: Record<string, string>): Record<string, string> {
  return {
    ...(extra || {}),
    Authorization: `Bearer ${token ?? ''}`,
  };
}

export type ReconResponse = Record<string, unknown>;

export const reconAPI = {
  async decodeVIN(vin: string): Promise<ReconResponse> {
    const token = await getAuthToken();
    const res = await fetch(`${API_BASE}/api/recon/vin/${vin}`, {
      headers: authHeaders(token),
    });
    if (!res.ok) throw new Error(`VIN decode failed: ${res.status}`);
    return res.json();
  },

  async evaluate(payload: Record<string, unknown>): Promise<ReconResponse> {
    const token = await getAuthToken();
    const res = await fetch(`${API_BASE}/api/recon/evaluate`, {
      method: 'POST',
      headers: authHeaders(token, { 'Content-Type': 'application/json' }),
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const errBody = await res.text();
      throw new Error(errBody || `Evaluate failed: ${res.status}`);
    }
    return res.json();
  },

  async getHistory(): Promise<ReconResponse[]> {
    const token = await getAuthToken();
    const res = await fetch(`${API_BASE}/api/recon/history`, {
      headers: authHeaders(token),
    });
    if (!res.ok) throw new Error(`History failed: ${res.status}`);
    return res.json();
  },

  async promote(reconId: string): Promise<Response> {
    const token = await getAuthToken();
    return fetch(`${API_BASE}/api/recon/promote/${reconId}`, {
      method: 'POST',
      headers: authHeaders(token),
    });
  },
};

export default reconAPI;

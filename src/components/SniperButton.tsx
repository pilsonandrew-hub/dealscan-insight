/**
 * SniperButton — arm a SniperScope bid alert for an opportunity.
 *
 * States:
 *   "idle"    → shows "Snipe This 🎯"
 *   "armed"   → shows "Armed 🎯" (target exists in DB)
 *   "modal"   → shows the max-bid ceiling modal
 *   "loading" → submitting to API
 */

import React, { useCallback, useState } from 'react';
import { Target, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { supabase } from '@/integrations/supabase/client';

const API_BASE =
  import.meta.env.VITE_API_URL ||
  'https://dealscan-insight-production.up.railway.app';

// Minimal shape we need from an opportunity — keeps this component decoupled.
interface SniperOpportunity {
  id?: string;
  year?: number;
  make?: string;
  model?: string;
  current_bid?: number;
  listing_url?: string;
}

interface SniperButtonProps {
  opportunity: SniperOpportunity;
  className?: string;
}

type ButtonState = 'idle' | 'modal' | 'loading' | 'armed' | 'cancelled';

export const SniperButton: React.FC<SniperButtonProps> = ({
  opportunity,
  className = '',
}) => {
  const [state, setState] = useState<ButtonState>('idle');
  const [maxBid, setMaxBid] = useState<string>('');
  const [telegramChatId, setTelegramChatId] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string>('');
  const [armedTargetId, setArmedTargetId] = useState<string | null>(null);

  const vehicleLabel = [opportunity.year, opportunity.make, opportunity.model]
    .filter(Boolean)
    .join(' ');

  // ── Open modal ──────────────────────────────────────────────────────────────
  const handleSnipeClick = useCallback(() => {
    setErrorMsg('');
    // Pre-fill with 10% headroom above current_bid as a sensible default
    if (opportunity.current_bid && !maxBid) {
      setMaxBid(String(Math.round(opportunity.current_bid * 1.1)));
    }
    setState('modal');
  }, [opportunity.current_bid, maxBid]);

  // ── Submit to API ───────────────────────────────────────────────────────────
  const handleSubmit = useCallback(async () => {
    if (!opportunity.id) {
      setErrorMsg('Missing opportunity ID.');
      return;
    }
    const bidValue = parseFloat(maxBid);
    if (!maxBid || isNaN(bidValue) || bidValue <= 0) {
      setErrorMsg('Enter a valid max bid ceiling.');
      return;
    }

    setState('loading');
    setErrorMsg('');

    try {
      // Get Supabase JWT
      const { data: { session } } = await supabase.auth.getSession();
      if (!session?.access_token) {
        setErrorMsg('You must be logged in to snipe.');
        setState('modal');
        return;
      }

      const body: Record<string, unknown> = {
        opportunity_id: opportunity.id,
        max_bid: bidValue,
      };
      if (telegramChatId.trim()) {
        body.telegram_chat_id = telegramChatId.trim();
      }

      const resp = await fetch(`${API_BASE}/api/sniper/targets`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        setErrorMsg(errData.detail || `API error ${resp.status}`);
        setState('modal');
        return;
      }

      const respData = await resp.json().catch(() => ({}));
      if (respData?.target?.id) setArmedTargetId(respData.target.id);
      setState('armed');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMsg(`Network error: ${msg}`);
      setState('modal');
    }
  }, [opportunity.id, maxBid, telegramChatId]);

  // ── Cancel from armed — calls DELETE endpoint to remove DB record ────────────
  const handleCancel = useCallback(async () => {
    if (armedTargetId) {
      try {
        const { data: { session } } = await supabase.auth.getSession();
        if (session?.access_token) {
          await fetch(`${API_BASE}/api/sniper/targets/${armedTargetId}`, {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${session.access_token}` },
          });
        }
      } catch {
        // non-fatal — UI state update still happens
      }
    }
    setState('cancelled');
  }, [armedTargetId]);

  // ── Close modal ──────────────────────────────────────────────────────────────
  const handleCloseModal = useCallback(() => {
    setState('idle');
    setErrorMsg('');
  }, []);

  // ── Render ───────────────────────────────────────────────────────────────────
  if (state === 'cancelled') {
    return (
      <Button
        variant="outline"
        size="sm"
        disabled
        className={`text-muted-foreground ${className}`}
      >
        Cancelled
      </Button>
    );
  }

  if (state === 'armed') {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        <Button
          variant="outline"
          size="sm"
          className="border-green-500 text-green-700 bg-green-50 hover:bg-green-100 cursor-default"
          title="SniperScope is armed — you'll receive alerts at T-60, T-15, T-5"
        >
          <Target className="h-3.5 w-3.5 mr-1 text-green-600" />
          Armed 🎯
        </Button>
        <button
          onClick={handleCancel}
          className="text-xs text-muted-foreground underline hover:text-destructive"
          title="Cancel this sniper target"
        >
          Cancel
        </button>
      </div>
    );
  }

  if (state === 'idle') {
    return (
      <Button
        variant="outline"
        size="sm"
        onClick={handleSnipeClick}
        className={`border-primary/40 text-primary hover:bg-primary/5 ${className}`}
      >
        <Target className="h-3.5 w-3.5 mr-1" />
        Snipe This
      </Button>
    );
  }

  // ── Modal (state === 'modal' or 'loading') ──────────────────────────────────
  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
        onClick={handleCloseModal}
      >
        {/* Modal card */}
        <div
          className="relative bg-card rounded-xl shadow-2xl p-6 w-full max-w-sm border border-border"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Close button */}
          <button
            onClick={handleCloseModal}
            className="absolute top-3 right-3 text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>

          <div className="flex items-center gap-2 mb-4">
            <Target className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-bold">Set Bid Ceiling</h2>
          </div>

          {vehicleLabel && (
            <p className="text-sm text-muted-foreground mb-4 font-medium">{vehicleLabel}</p>
          )}

          {/* Max bid input */}
          <div className="mb-4">
            <label className="text-sm font-medium block mb-1">
              Max bid ceiling ($)
            </label>
            <input
              type="number"
              min={1}
              step={100}
              value={maxBid}
              onChange={(e) => setMaxBid(e.target.value)}
              placeholder="e.g. 9500"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
              autoFocus
            />
          </div>

          {/* Optional Telegram chat ID */}
          <div className="mb-4">
            <label className="text-sm font-medium block mb-1">
              Telegram Chat ID{' '}
              <span className="text-muted-foreground font-normal">(optional)</span>
            </label>
            <input
              type="text"
              value={telegramChatId}
              onChange={(e) => setTelegramChatId(e.target.value)}
              placeholder="e.g. 7529788084"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <p className="text-xs text-muted-foreground mt-1">
              You'll get alerts at T-60, T-15, and T-5 min before close.
            </p>
          </div>

          {/* Error */}
          {errorMsg && (
            <p className="text-xs text-destructive mb-3">{errorMsg}</p>
          )}

          {/* Actions */}
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              className="flex-1"
              onClick={handleCloseModal}
              disabled={state === 'loading'}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              className="flex-1"
              onClick={handleSubmit}
              disabled={state === 'loading'}
            >
              {state === 'loading' ? 'Arming…' : 'Arm SniperScope 🎯'}
            </Button>
          </div>

          {/* Confirmation note shown when armed */}
          {state === 'armed' && (
            <p className="text-xs text-green-700 mt-3 font-medium text-center">
              SniperScope armed 🎯 You'll get alerts at T-60, T-15, T-5
            </p>
          )}
        </div>
      </div>

      {/* Trigger button (visible behind modal) */}
      <Button
        variant="outline"
        size="sm"
        className={`border-primary/40 text-primary ${className}`}
        disabled
      >
        <Target className="h-3.5 w-3.5 mr-1" />
        Snipe This
      </Button>
    </>
  );
};

export default SniperButton;

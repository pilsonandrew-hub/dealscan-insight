import React, { useEffect, useState, useRef } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { ExternalLink, ArrowLeft, Bookmark, Clock } from 'lucide-react';
import { supabase } from '@/integrations/supabase/client';
import { roverAPI } from '@/services/roverAPI';
import { SniperButton } from '@/components/SniperButton';
import { Button } from '@/components/ui/button';

// ─── Types ────────────────────────────────────────────────────────────────────
interface Deal {
  id: string;
  year?: number;
  make?: string;
  model?: string;
  current_bid?: number;
  max_bid?: number;
  gross_margin?: number;
  roi_per_day?: number;
  roi?: number;
  dos_score?: number;
  state?: string;
  source?: string;
  source_site?: string;
  auction_end?: string;
  listing_url?: string;
  investment_grade?: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function fmt$(v: number | null | undefined) {
  if (v == null) return '—';
  return `$${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

function dosColor(score: number | null | undefined) {
  const s = score ?? 0;
  if (s >= 80) return 'bg-emerald-500 text-white';
  if (s >= 65) return 'bg-yellow-500 text-black';
  return 'bg-gray-600 text-white';
}

function gradeColor(grade: string | undefined) {
  switch (grade) {
    case 'Platinum': return 'text-cyan-400';
    case 'Gold':     return 'text-yellow-400';
    case 'Silver':   return 'text-gray-300';
    case 'Bronze':   return 'text-orange-400';
    default:         return 'text-gray-500';
  }
}

// ─── Component ────────────────────────────────────────────────────────────────
const DealDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [deal, setDeal] = useState<Deal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [saveFired, setSaveFired] = useState(false);

  const redirect = searchParams.get('redirect') === '1';
  const redirectTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Fetch deal + user + track click ─────────────────────────────────────────
  useEffect(() => {
    if (!id) {
      setError('No deal ID provided.');
      setLoading(false);
      return;
    }

    (async () => {
      try {
        const [dealResp, sessionResp] = await Promise.all([
          supabase.from('opportunities').select('*').eq('id', id).single(),
          supabase.auth.getSession(),
        ]);

        if (dealResp.error || !dealResp.data) {
          setError('Deal not found.');
          setLoading(false);
          return;
        }

        const data = dealResp.data as Deal;
        setDeal(data);

        const uid = sessionResp.data?.session?.user?.id ?? null;
        setUserId(uid);

        if (uid) {
          roverAPI.trackEvent({
            event: 'click',
            userId: uid,
            item: {
              id: data.id,
              make: data.make ?? '',
              model: data.model ?? '',
              year: data.year ?? 0,
              price: data.current_bid ?? 0,
              current_bid: data.current_bid,
              state: data.state,
              source_site: data.source_site ?? data.source,
            },
          });
        }
      } catch (e) {
        setError('Failed to load deal.');
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  // ── Auto-redirect countdown ──────────────────────────────────────────────────
  useEffect(() => {
    if (!redirect || !deal?.listing_url) return;
    setCountdown(5);
    redirectTimerRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev === null) return null;
        if (prev <= 1) {
          clearInterval(redirectTimerRef.current!);
          window.open(deal.listing_url!, '_blank', 'noopener,noreferrer');
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => {
      if (redirectTimerRef.current) clearInterval(redirectTimerRef.current);
    };
  }, [redirect, deal?.listing_url]);

  // ── Save to Rover ────────────────────────────────────────────────────────────
  const handleSave = async () => {
    if (!deal) return;
    if (!userId) return;
    setSaveFired(true);
    roverAPI.trackEvent({
      event: 'save',
      userId,
      item: {
        id: deal.id,
        make: deal.make ?? '',
        model: deal.model ?? '',
        year: deal.year ?? 0,
        price: deal.current_bid ?? 0,
        current_bid: deal.current_bid,
        state: deal.state,
        source_site: deal.source_site ?? deal.source,
      },
    });
  };

  // ── Loading / error states ───────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500" />
      </div>
    );
  }

  if (error || !deal) {
    return (
      <div className="min-h-screen bg-gray-950 flex flex-col items-center justify-center gap-4 text-gray-300">
        <p className="text-lg">{error ?? 'Deal not found.'}</p>
        <Button variant="outline" onClick={() => navigate('/')}>
          <ArrowLeft className="h-4 w-4 mr-1" /> Back to Dashboard
        </Button>
      </div>
    );
  }

  const title = [deal.year, deal.make, deal.model].filter(Boolean).join(' ');
  const source = deal.source_site ?? deal.source ?? '—';

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-4 md:p-8">
      <div className="max-w-2xl mx-auto">
        {/* Back nav */}
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 mb-6"
        >
          <ArrowLeft className="h-4 w-4" /> Back
        </button>

        {/* Countdown banner */}
        {redirect && countdown !== null && countdown > 0 && (
          <div className="mb-4 rounded-lg bg-yellow-900/40 border border-yellow-600 px-4 py-3 text-sm text-yellow-300 flex items-center gap-2">
            <Clock className="h-4 w-4 shrink-0" />
            Redirecting to listing in <strong>{countdown}s</strong>…
            <button
              className="ml-auto underline text-xs"
              onClick={() => {
                if (redirectTimerRef.current) clearInterval(redirectTimerRef.current);
                setCountdown(null);
              }}
            >
              Cancel
            </button>
          </div>
        )}

        {/* Deal card */}
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-6 shadow-lg">
          {/* Header row */}
          <div className="flex items-start justify-between mb-4">
            <div>
              <h1 className="text-2xl font-bold">{title || 'Unknown Vehicle'}</h1>
              <p className="text-sm text-gray-400 mt-0.5">{source}</p>
            </div>
            {deal.dos_score != null && (
              <span className={`rounded-full px-3 py-1 text-sm font-bold ${dosColor(deal.dos_score)}`}>
                {deal.dos_score} DOS
              </span>
            )}
          </div>

          {/* Grade */}
          {deal.investment_grade && (
            <p className={`text-sm font-semibold mb-4 ${gradeColor(deal.investment_grade)}`}>
              {deal.investment_grade} Grade
            </p>
          )}

          {/* Stats grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mb-6">
            <StatBox label="Current Bid" value={fmt$(deal.current_bid)} />
            <StatBox label="Max Bid" value={fmt$(deal.max_bid)} />
            <StatBox label="Gross Margin" value={fmt$(deal.gross_margin)} />
            <StatBox label="ROI / Day" value={fmt$(deal.roi_per_day)} />
            <StatBox label="State" value={deal.state ?? '—'} />
            {deal.auction_end && (
              <StatBox
                label="Auction End"
                value={new Date(deal.auction_end).toLocaleDateString('en-US', {
                  month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                })}
              />
            )}
          </div>

          {/* Action buttons */}
          <div className="flex flex-wrap gap-3">
            {deal.listing_url ? (
              <Button
                onClick={() => window.open(deal.listing_url!, '_blank', 'noopener,noreferrer')}
                className="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold px-5"
              >
                Bid Now <ExternalLink className="h-4 w-4 ml-1" />
              </Button>
            ) : null}

            <SniperButton
              opportunity={{
                id: deal.id,
                year: deal.year,
                make: deal.make,
                model: deal.model,
                current_bid: deal.current_bid,
                listing_url: deal.listing_url,
              }}
            />

            {userId ? (
              <Button
                variant="outline"
                onClick={handleSave}
                disabled={saveFired}
                className="border-gray-600 text-gray-300 hover:bg-gray-800"
              >
                <Bookmark className="h-4 w-4 mr-1" />
                {saveFired ? 'Saved' : 'Save to Rover'}
              </Button>
            ) : (
              <Button
                variant="outline"
                onClick={() => navigate('/auth')}
                className="border-gray-600 text-gray-400 hover:bg-gray-800 text-sm"
              >
                Sign in to save / snipe
              </Button>
            )}
          </div>

          {/* Not logged in note */}
          {!userId && (
            <p className="text-xs text-gray-500 mt-4">
              Sign in to track this deal, arm Sniper alerts, and get personalized recommendations.
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

// ─── Small stat box ───────────────────────────────────────────────────────────
const StatBox: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="rounded-lg bg-gray-800 px-3 py-2">
    <p className="text-xs text-gray-500 mb-0.5">{label}</p>
    <p className="text-sm font-medium text-gray-100">{value}</p>
  </div>
);

export default DealDetail;

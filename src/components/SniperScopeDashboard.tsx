import React, { useState, useEffect, useMemo } from 'react';
import { Target, Lock, Trash2, Calculator } from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────
interface SniperInputs {
  year: string;
  make: string;
  model: string;
  mmr: string;
  buyerPremiumPct: string;
  auctionFees: string;
  transport: string;
  recon: string;
  targetMargin: string;
  state: string;
}

interface SavedTarget {
  id: string;
  vehicle: string;
  mmr: number;
  maxBid: number;
  margin: number;
  roi: number;
  date: string;
}

// ─── Low-rust states with default transport estimates ────────────────────────
const LOW_RUST_STATES: { value: string; label: string; transport: number }[] = [
  { value: 'AZ', label: 'Arizona', transport: 350 },
  { value: 'CA', label: 'California', transport: 500 },
  { value: 'CO', label: 'Colorado', transport: 400 },
  { value: 'FL', label: 'Florida', transport: 600 },
  { value: 'GA', label: 'Georgia', transport: 550 },
  { value: 'KS', label: 'Kansas', transport: 350 },
  { value: 'NM', label: 'New Mexico', transport: 375 },
  { value: 'NV', label: 'Nevada', transport: 450 },
  { value: 'OK', label: 'Oklahoma', transport: 325 },
  { value: 'OR', label: 'Oregon', transport: 550 },
  { value: 'TX', label: 'Texas', transport: 400 },
  { value: 'UT', label: 'Utah', transport: 425 },
  { value: 'WA', label: 'Washington', transport: 575 },
];

const STORAGE_KEY = 'dealerscope_sniper_targets';

function fmt$(n: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n);
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// ─── SniperScope Calculator ───────────────────────────────────────────────────
export default function SniperScopeDashboard() {
  const [inputs, setInputs] = useState<SniperInputs>({
    year: '',
    make: '',
    model: '',
    mmr: '',
    buyerPremiumPct: '12.5',
    auctionFees: '150',
    transport: '450',
    recon: '500',
    targetMargin: '2500',
    state: '',
  });

  const [saved, setSaved] = useState<SavedTarget[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    } catch {
      return [];
    }
  });

  // Recalculate live
  const calc = useMemo(() => {
    const mmr = parseFloat(inputs.mmr) || 0;
    const buyerPremiumPct = parseFloat(inputs.buyerPremiumPct) || 0;
    const auctionFees = parseFloat(inputs.auctionFees) || 0;
    const transport = parseFloat(inputs.transport) || 0;
    const recon = parseFloat(inputs.recon) || 0;
    const targetMargin = parseFloat(inputs.targetMargin) || 0;

    const buyerPremium = mmr * (buyerPremiumPct / 100);
    const maxBid = mmr - buyerPremium - auctionFees - transport - recon - targetMargin;
    const allInCost = maxBid + buyerPremium + auctionFees + transport + recon;
    const estimatedGrossMargin = mmr - allInCost;
    const roi = allInCost > 0 ? (estimatedGrossMargin / allInCost) * 100 : 0;

    return { mmr, buyerPremium, auctionFees, transport, recon, targetMargin, maxBid, allInCost, estimatedGrossMargin, roi };
  }, [inputs]);

  const marginStatus = useMemo(() => {
    if (calc.estimatedGrossMargin <= 0) return 'red';
    if (calc.estimatedGrossMargin < calc.targetMargin * 0.8) return 'yellow';
    return 'green';
  }, [calc]);

  const set = (key: keyof SniperInputs, value: string) =>
    setInputs(prev => ({ ...prev, [key]: value }));

  const handleStateChange = (state: string) => {
    const stateData = LOW_RUST_STATES.find(s => s.value === state);
    setInputs(prev => ({
      ...prev,
      state,
      transport: stateData ? stateData.transport.toString() : prev.transport,
    }));
  };

  const lockTarget = () => {
    if (!inputs.mmr) return;
    const vehicle = [inputs.year, inputs.make, inputs.model].filter(Boolean).join(' ') || 'Unknown Vehicle';
    const entry: SavedTarget = {
      id: Date.now().toString(),
      vehicle,
      mmr: calc.mmr,
      maxBid: calc.maxBid,
      margin: calc.estimatedGrossMargin,
      roi: calc.roi,
      date: new Date().toISOString(),
    };
    const next = [entry, ...saved];
    setSaved(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  };

  const deleteTarget = (id: string) => {
    const next = saved.filter(t => t.id !== id);
    setSaved(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  };

  const inputCls = "w-full bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-emerald-500 transition-colors";
  const labelCls = "block text-xs text-gray-400 mb-1";

  const maxBidColor = calc.maxBid > 0 ? 'text-emerald-400' : 'text-red-400';
  const marginColor = marginStatus === 'green' ? 'text-emerald-400' : marginStatus === 'yellow' ? 'text-yellow-400' : 'text-red-400';

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Target className="h-6 w-6 text-emerald-400" />
        <div>
          <h2 className="text-xl font-bold text-white">SniperScope</h2>
          <p className="text-sm text-gray-400">Bid execution calculator — find your max bid before you raise your hand</p>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* ── INPUT FORM ─────────────────────────────────────────────────────── */}
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-4">
          <div className="flex items-center gap-2 mb-1">
            <Calculator className="h-4 w-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-gray-200">Vehicle & Cost Inputs</h3>
          </div>

          {/* Vehicle */}
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className={labelCls}>Year</label>
              <input type="number" className={inputCls} placeholder="2021" value={inputs.year}
                onChange={e => set('year', e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>Make</label>
              <input type="text" className={inputCls} placeholder="Ford" value={inputs.make}
                onChange={e => set('make', e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>Model</label>
              <input type="text" className={inputCls} placeholder="F-150" value={inputs.model}
                onChange={e => set('model', e.target.value)} />
            </div>
          </div>

          {/* MMR */}
          <div>
            <label className={labelCls}>MMR — Market Reference Value ($)</label>
            <input type="number" className={inputCls} placeholder="22000" value={inputs.mmr}
              onChange={e => set('mmr', e.target.value)} />
            <p className="text-xs text-gray-600 mt-1">Manheim Market Report value or your best market estimate</p>
          </div>

          {/* Cost inputs grid */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Buyer Premium (%)</label>
              <input type="number" step="0.5" className={inputCls} value={inputs.buyerPremiumPct}
                onChange={e => set('buyerPremiumPct', e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>Auction Fees ($)</label>
              <input type="number" className={inputCls} value={inputs.auctionFees}
                onChange={e => set('auctionFees', e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>Recon Estimate ($)</label>
              <input type="number" className={inputCls} value={inputs.recon}
                onChange={e => set('recon', e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>Target Margin ($)</label>
              <input type="number" className={inputCls} value={inputs.targetMargin}
                onChange={e => set('targetMargin', e.target.value)} />
            </div>
          </div>

          {/* State + transport */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Origin State (low-rust)</label>
              <select className={inputCls} value={inputs.state} onChange={e => handleStateChange(e.target.value)}>
                <option value="">— Select state —</option>
                {LOW_RUST_STATES.map(s => (
                  <option key={s.value} value={s.value}>{s.label} ({s.value})</option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelCls}>Transport ($)</label>
              <input type="number" className={inputCls} value={inputs.transport}
                onChange={e => set('transport', e.target.value)} />
            </div>
          </div>
        </div>

        {/* ── CALCULATED OUTPUT ───────────────────────────────────────────────── */}
        <div className="space-y-4">
          {/* Big Max Bid display */}
          <div className={`bg-gray-900 rounded-xl border p-5 text-center ${
            calc.maxBid > 0 ? 'border-emerald-800/60' : 'border-red-800/60'
          }`}>
            <p className="text-xs text-gray-400 uppercase tracking-widest mb-1">Max Bid Ceiling</p>
            <p className={`text-5xl font-black tracking-tight ${maxBidColor}`}>
              {inputs.mmr ? fmt$(calc.maxBid) : '—'}
            </p>
            {inputs.mmr && calc.maxBid <= 0 && (
              <p className="text-red-400 text-xs mt-2">⚠ Costs exceed MMR — deal underwater at this margin target</p>
            )}
          </div>

          {/* Summary metrics */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-3 text-center">
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">All-In Cost</p>
              <p className="text-lg font-bold text-white">{inputs.mmr ? fmt$(calc.allInCost) : '—'}</p>
            </div>
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-3 text-center">
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Est. Gross Margin</p>
              <p className={`text-lg font-bold ${inputs.mmr ? marginColor : 'text-white'}`}>
                {inputs.mmr ? fmt$(calc.estimatedGrossMargin) : '—'}
              </p>
            </div>
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-3 text-center">
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">ROI</p>
              <p className={`text-lg font-bold ${inputs.mmr ? marginColor : 'text-white'}`}>
                {inputs.mmr ? `${calc.roi.toFixed(1)}%` : '—'}
              </p>
            </div>
          </div>

          {/* Cost breakdown table */}
          <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-400 uppercase tracking-wide">Cost Item</th>
                  <th className="text-right px-4 py-2.5 text-xs font-semibold text-gray-400 uppercase tracking-wide">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                <tr>
                  <td className="px-4 py-2.5 text-gray-300">MMR (Market Value)</td>
                  <td className="px-4 py-2.5 text-right text-emerald-400 font-medium">{inputs.mmr ? fmt$(calc.mmr) : '—'}</td>
                </tr>
                <tr>
                  <td className="px-4 py-2.5 text-gray-300">Buyer Premium ({inputs.buyerPremiumPct}%)</td>
                  <td className="px-4 py-2.5 text-right text-red-400">-{inputs.mmr ? fmt$(calc.buyerPremium) : '—'}</td>
                </tr>
                <tr>
                  <td className="px-4 py-2.5 text-gray-300">Auction Fees</td>
                  <td className="px-4 py-2.5 text-right text-red-400">-{inputs.mmr ? fmt$(calc.auctionFees) : '—'}</td>
                </tr>
                <tr>
                  <td className="px-4 py-2.5 text-gray-300">Transport</td>
                  <td className="px-4 py-2.5 text-right text-red-400">-{inputs.mmr ? fmt$(calc.transport) : '—'}</td>
                </tr>
                <tr>
                  <td className="px-4 py-2.5 text-gray-300">Recon Estimate</td>
                  <td className="px-4 py-2.5 text-right text-red-400">-{inputs.mmr ? fmt$(calc.recon) : '—'}</td>
                </tr>
                <tr>
                  <td className="px-4 py-2.5 text-gray-300">Target Margin</td>
                  <td className="px-4 py-2.5 text-right text-red-400">-{inputs.mmr ? fmt$(calc.targetMargin) : '—'}</td>
                </tr>
                <tr className="border-t-2 border-emerald-800/60">
                  <td className="px-4 py-3 font-bold text-white">MAX BID CEILING</td>
                  <td className={`px-4 py-3 text-right font-black text-lg ${maxBidColor}`}>
                    {inputs.mmr ? fmt$(calc.maxBid) : '—'}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Lock button */}
          <button
            onClick={lockTarget}
            disabled={!inputs.mmr}
            className="w-full flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold py-2.5 px-4 rounded-lg transition-colors"
          >
            <Lock className="h-4 w-4" />
            Lock Target
          </button>
        </div>
      </div>

      {/* ── SAVED TARGETS ────────────────────────────────────────────────────── */}
      {saved.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wide mb-3">
            Saved Targets ({saved.length})
          </h3>
          <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-x-auto">
            <table className="w-full text-sm min-w-[600px]">
              <thead>
                <tr className="border-b border-gray-800">
                  {['Vehicle', 'MMR', 'Max Bid', 'Est. Margin', 'ROI', 'Saved', ''].map(h => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wide last:text-right">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {saved.map(t => {
                  const marginOk = t.margin > 0;
                  return (
                    <tr key={t.id} className="hover:bg-gray-800/50 transition-colors">
                      <td className="px-4 py-3 text-white font-medium">{t.vehicle}</td>
                      <td className="px-4 py-3 text-gray-300">{fmt$(t.mmr)}</td>
                      <td className="px-4 py-3 text-emerald-400 font-semibold">{fmt$(t.maxBid)}</td>
                      <td className={`px-4 py-3 font-medium ${marginOk ? 'text-emerald-400' : 'text-red-400'}`}>
                        {fmt$(t.margin)}
                      </td>
                      <td className={`px-4 py-3 ${marginOk ? 'text-emerald-400' : 'text-red-400'}`}>
                        {t.roi.toFixed(1)}%
                      </td>
                      <td className="px-4 py-3 text-gray-500 text-xs">{fmtDate(t.date)}</td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => deleteTarget(t.id)}
                          className="text-gray-600 hover:text-red-400 transition-colors"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {saved.length === 0 && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 text-center">
          <Lock className="h-8 w-8 text-gray-700 mx-auto mb-2" />
          <p className="text-gray-500 text-sm">No saved targets yet. Run a calculation and click "Lock Target" to save it.</p>
        </div>
      )}
    </div>
  );
}

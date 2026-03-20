import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DollarSign, TrendingUp, AlertTriangle, CheckCircle, Search, Clock, ChevronRight } from 'lucide-react';
import { supabase } from '@/integrations/supabase/client';

const API_BASE = import.meta.env.VITE_API_URL || 'https://dealscan-insight-production.up.railway.app';

interface ReconResult {
  id: string;
  verdict: 'HOT BUY' | 'BUY' | 'WATCH' | 'PASS';
  verdict_reason: string;
  max_bid: number;
  asking_price: number;
  profit_expected: number;
  profit_pessimistic: number;
  profit_optimistic: number;
  adjusted_dos: number;
  reliability_grade: 'A+' | 'A' | 'B' | 'C';
  comp_count: number;
  condition_penalty: number;
  fleet_stigma_penalty: number;
  manheim_sell_fee: number;
  transport_cost: number;
  total_all_in_cost: number;
  promoted_to_pipeline: boolean;
  pricing_source: string;
}

interface FormState {
  vin: string;
  year: string;
  make: string;
  model: string;
  mileage: string;
  asking_price: string;
  source: string;
  state: string;
  condition_grade: string;
  is_fleet: boolean;
  fleet_has_records: boolean;
}

const VERDICT_STYLES: Record<ReconResult['verdict'], string> = {
  'HOT BUY': 'border-orange-500 bg-orange-950',
  'BUY':     'border-green-500 bg-green-950',
  'WATCH':   'border-yellow-500 bg-yellow-950',
  'PASS':    'border-gray-500 bg-gray-900',
};

const VERDICT_BADGE: Record<ReconResult['verdict'], string> = {
  'HOT BUY': 'bg-orange-500 text-white',
  'BUY':     'bg-green-500 text-white',
  'WATCH':   'bg-yellow-500 text-black',
  'PASS':    'bg-gray-500 text-white',
};

const GRADE_COLORS: Record<ReconResult['reliability_grade'], string> = {
  'A+': 'text-yellow-400',
  'A':  'text-green-400',
  'B':  'text-blue-400',
  'C':  'text-orange-400',
};

const defaultForm: FormState = {
  vin: '',
  year: '',
  make: '',
  model: '',
  mileage: '',
  asking_price: '',
  source: '',
  state: '',
  condition_grade: 'Good',
  is_fleet: false,
  fleet_has_records: false,
};

async function getAuthToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

export const ReconPanel: React.FC = () => {
  const [form, setForm] = useState<FormState>(defaultForm);
  const [result, setResult] = useState<ReconResult | null>(null);
  const [history, setHistory] = useState<ReconResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [vinLoading, setVinLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'evaluate' | 'history'>('evaluate');
  const [error, setError] = useState<string | null>(null);
  const [promoted, setPromoted] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (activeTab === 'history') loadHistory();
  }, [activeTab]);

  const setField = (key: keyof FormState, value: string | boolean) => {
    setForm(prev => ({ ...prev, [key]: value }));
  };

  const decodeVIN = async () => {
    if (!form.vin.trim()) return;
    setVinLoading(true);
    setError(null);
    try {
      const token = await getAuthToken();
      const res = await fetch(`${API_BASE}/api/recon/vin/${form.vin.trim()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`VIN decode failed: ${res.status}`);
      const data = await res.json();
      const results = data.Results || [];
      const get = (variable: string) => results.find((r: { Variable: string; Value: string }) => r.Variable === variable)?.Value || '';
      const make = get('Make');
      const model = get('Model');
      const year = get('Model Year') || get('ModelYear');
      setForm(prev => ({
        ...prev,
        make: make || prev.make,
        model: model || prev.model,
        year: year ? String(year) : prev.year,
      }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'VIN decode failed');
    } finally {
      setVinLoading(false);
    }
  };

  const evaluate = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const token = await getAuthToken();
      const payload = {
        vin: form.vin || undefined,
        year: form.year ? parseInt(form.year) : undefined,
        make: form.make || undefined,
        model: form.model || undefined,
        mileage: form.mileage ? parseInt(form.mileage) : undefined,
        asking_price: form.asking_price ? parseFloat(form.asking_price) : undefined,
        source: form.source || undefined,
        state: form.state || undefined,
        condition: form.condition_grade,
        condition_grade: form.condition_grade,
        title_status: "clean",
        fleet: form.is_fleet,
        fleet_has_records: form.fleet_has_records,
      };
      const res = await fetch(`${API_BASE}/api/recon/evaluate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const errBody = await res.text();
        throw new Error(errBody || `Evaluate failed: ${res.status}`);
      }
      const data: ReconResult = await res.json();
      setResult(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Evaluation failed');
    } finally {
      setLoading(false);
    }
  };

  const loadHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getAuthToken();
      const res = await fetch(`${API_BASE}/api/recon/history`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`History failed: ${res.status}`);
      const data: ReconResult[] = await res.json();
      setHistory(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load history');
    } finally {
      setLoading(false);
    }
  };

  const promote = async (recon_id: string) => {
    try {
      const token = await getAuthToken();
      const res = await fetch(`${API_BASE}/api/recon/promote/${recon_id}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Promote failed: ${res.status}`);
      setPromoted(prev => new Set([...prev, recon_id]));
      if (result?.id === recon_id) {
        setResult(prev => prev ? { ...prev, promoted_to_pipeline: true } : prev);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Promote failed');
    }
  };

  const isPromoted = (r: ReconResult) => r.promoted_to_pipeline || promoted.has(r.id);

  return (
    <div className="w-full max-w-2xl mx-auto p-4">
      <div className="mb-4">
        <h2 className="text-2xl font-bold text-foreground">Recon Evaluator</h2>
        <p className="text-sm text-muted-foreground">Evaluate a vehicle deal before you bid</p>
      </div>

      <Tabs value={activeTab} onValueChange={v => setActiveTab(v as 'evaluate' | 'history')}>
        <TabsList className="w-full mb-4">
          <TabsTrigger value="evaluate" className="flex-1">Evaluate</TabsTrigger>
          <TabsTrigger value="history" className="flex-1">History</TabsTrigger>
        </TabsList>

        {/* ── EVALUATE TAB ── */}
        <TabsContent value="evaluate">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Vehicle Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">

              {/* VIN row */}
              <div className="flex gap-2 items-end">
                <div className="flex-1">
                  <Label htmlFor="vin" className="text-xs mb-1 block">VIN (optional)</Label>
                  <Input
                    id="vin"
                    placeholder="1HGBH41JXMN109186"
                    value={form.vin}
                    onChange={e => setField('vin', e.target.value)}
                    className="font-mono text-sm"
                  />
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={decodeVIN}
                  disabled={vinLoading || !form.vin.trim()}
                  className="shrink-0"
                >
                  <Search className="h-4 w-4 mr-1" />
                  {vinLoading ? 'Decoding…' : 'Decode'}
                </Button>
              </div>

              {/* Year / Make / Model */}
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <Label htmlFor="year" className="text-xs mb-1 block">Year</Label>
                  <Input
                    id="year"
                    placeholder="2020"
                    value={form.year}
                    onChange={e => setField('year', e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="make" className="text-xs mb-1 block">Make</Label>
                  <Input
                    id="make"
                    placeholder="Toyota"
                    value={form.make}
                    onChange={e => setField('make', e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="model" className="text-xs mb-1 block">Model</Label>
                  <Input
                    id="model"
                    placeholder="Camry"
                    value={form.model}
                    onChange={e => setField('model', e.target.value)}
                  />
                </div>
              </div>

              {/* Mileage / Asking Price */}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label htmlFor="mileage" className="text-xs mb-1 block">Mileage</Label>
                  <Input
                    id="mileage"
                    placeholder="45000"
                    value={form.mileage}
                    onChange={e => setField('mileage', e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="asking_price" className="text-xs mb-1 block">Asking Price ($)</Label>
                  <Input
                    id="asking_price"
                    placeholder="18500"
                    value={form.asking_price}
                    onChange={e => setField('asking_price', e.target.value)}
                  />
                </div>
              </div>

              {/* Source / State */}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label htmlFor="source" className="text-xs mb-1 block">Source</Label>
                  <Input
                    id="source"
                    placeholder="Manheim, ADESA…"
                    value={form.source}
                    onChange={e => setField('source', e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="state" className="text-xs mb-1 block">State</Label>
                  <Input
                    id="state"
                    placeholder="TX"
                    maxLength={2}
                    value={form.state}
                    onChange={e => setField('state', e.target.value.toUpperCase())}
                  />
                </div>
              </div>

              {/* Condition Grade */}
              <div>
                <Label className="text-xs mb-1 block">Condition Grade</Label>
                <Select value={form.condition_grade} onValueChange={v => setField('condition_grade', v)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Excellent">Excellent</SelectItem>
                    <SelectItem value="Good">Good</SelectItem>
                    <SelectItem value="Fair">Fair</SelectItem>
                    <SelectItem value="Poor">Poor</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Fleet toggles */}
              <div className="flex items-center justify-between py-1">
                <Label htmlFor="is_fleet" className="text-sm cursor-pointer">Fleet Vehicle</Label>
                <Switch
                  id="is_fleet"
                  checked={form.is_fleet}
                  onCheckedChange={v => setField('is_fleet', v)}
                />
              </div>
              {form.is_fleet && (
                <div className="flex items-center justify-between py-1 pl-4 border-l-2 border-muted">
                  <Label htmlFor="fleet_records" className="text-sm cursor-pointer text-muted-foreground">Has Fleet Records</Label>
                  <Switch
                    id="fleet_records"
                    checked={form.fleet_has_records}
                    onCheckedChange={v => setField('fleet_has_records', v)}
                  />
                </div>
              )}

              {error && (
                <div className="flex items-start gap-2 text-sm text-destructive bg-destructive/10 rounded-md p-3">
                  <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <Button
                className="w-full"
                onClick={evaluate}
                disabled={loading}
              >
                {loading ? 'Evaluating…' : 'Evaluate Deal'}
              </Button>
            </CardContent>
          </Card>

          {/* Result Card */}
          {result && (
            <div className={`mt-4 rounded-lg border-2 p-4 ${VERDICT_STYLES[result.verdict]}`}>
              {/* Verdict header */}
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <span className={`text-xs font-bold px-2 py-1 rounded ${VERDICT_BADGE[result.verdict]}`}>
                    {result.verdict}
                  </span>
                  <span className={`text-lg font-bold ${GRADE_COLORS[result.reliability_grade]}`}>
                    {result.reliability_grade}
                  </span>
                </div>
                <span className="text-xs text-muted-foreground">{result.comp_count} comps</span>
              </div>

              <p className="text-sm text-muted-foreground mb-4">{result.verdict_reason || result.reason}</p>

              {/* Key numbers */}
              <div className="grid grid-cols-2 gap-3 mb-4">
                <div className="bg-black/30 rounded-md p-3">
                  <div className="flex items-center gap-1 text-xs text-muted-foreground mb-1">
                    <TrendingUp className="h-3 w-3" />
                    Max Bid
                  </div>
                  <div className="text-lg font-bold text-foreground">
                    ${result.max_bid.toLocaleString()}
                  </div>
                </div>
                <div className="bg-black/30 rounded-md p-3">
                  <div className="flex items-center gap-1 text-xs text-muted-foreground mb-1">
                    <DollarSign className="h-3 w-3" />
                    Expected Profit
                  </div>
                  <div className={`text-lg font-bold ${result.profit_expected >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    ${result.profit_expected.toLocaleString()}
                  </div>
                </div>
                <div className="bg-black/30 rounded-md p-3">
                  <div className="text-xs text-muted-foreground mb-1">Pessimistic</div>
                  <div className={`font-semibold ${result.profit_pessimistic >= 0 ? 'text-green-300' : 'text-red-400'}`}>
                    ${result.profit_pessimistic.toLocaleString()}
                  </div>
                </div>
                <div className="bg-black/30 rounded-md p-3">
                  <div className="text-xs text-muted-foreground mb-1">Optimistic</div>
                  <div className={`font-semibold ${result.profit_optimistic >= 0 ? 'text-green-300' : 'text-red-400'}`}>
                    ${result.profit_optimistic.toLocaleString()}
                  </div>
                </div>
              </div>

              {/* Cost breakdown */}
              <div className="bg-black/20 rounded-md p-3 mb-4 space-y-1 text-sm">
                <div className="flex justify-between text-muted-foreground">
                  <span>All-in Cost</span>
                  <span className="text-foreground font-medium">${result.total_all_in_cost.toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-muted-foreground">
                  <span>Transport</span>
                  <span>${result.transport_cost.toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-muted-foreground">
                  <span>Manheim Fee</span>
                  <span>${result.manheim_sell_fee.toLocaleString()}</span>
                </div>
                {result.condition_penalty > 0 && (
                  <div className="flex justify-between text-muted-foreground">
                    <span>Condition Penalty</span>
                    <span className="text-orange-400">-${result.condition_penalty.toLocaleString()}</span>
                  </div>
                )}
                {result.fleet_stigma_penalty > 0 && (
                  <div className="flex justify-between text-muted-foreground">
                    <span>Fleet Penalty</span>
                    <span className="text-orange-400">-${result.fleet_stigma_penalty.toLocaleString()}</span>
                  </div>
                )}
                <div className="flex justify-between text-muted-foreground">
                  <span>Adj. Days on Lot</span>
                  <span>{result.adjusted_dos}d</span>
                </div>
                <div className="flex justify-between text-xs text-muted-foreground/60 pt-1 border-t border-muted/20">
                  <span>Pricing Source</span>
                  <span>{result.pricing_source}</span>
                </div>
              </div>

              {/* Promote button */}
              {!isPromoted(result) ? (
                <Button
                  className="w-full"
                  variant="outline"
                  onClick={() => promote(result.id)}
                >
                  <ChevronRight className="h-4 w-4 mr-1" />
                  Promote to Pipeline
                </Button>
              ) : (
                <div className="flex items-center justify-center gap-2 text-sm text-green-400 py-2">
                  <CheckCircle className="h-4 w-4" />
                  Added to Pipeline
                </div>
              )}
            </div>
          )}
        </TabsContent>

        {/* ── HISTORY TAB ── */}
        <TabsContent value="history">
          <div className="space-y-3">
            {loading && (
              <div className="flex items-center justify-center py-10 text-muted-foreground">
                <Clock className="h-4 w-4 mr-2 animate-spin" />
                Loading history…
              </div>
            )}
            {!loading && error && (
              <div className="flex items-start gap-2 text-sm text-destructive bg-destructive/10 rounded-md p-3">
                <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}
            {!loading && history.length === 0 && !error && (
              <div className="text-center py-10 text-muted-foreground text-sm">
                No evaluations yet.
              </div>
            )}
            {history.map(item => (
              <Card key={item.id} className="hover:shadow-md transition-all duration-200">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className={`text-xs font-bold px-2 py-0.5 rounded ${VERDICT_BADGE[item.verdict]}`}>
                        {item.verdict}
                      </span>
                      <span className={`text-sm font-bold ${GRADE_COLORS[item.reliability_grade || item.grade]}`}>
                        {item.reliability_grade || item.grade}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-sm">
                      <span className="text-muted-foreground">Ask: ${item.asking_price.toLocaleString()}</span>
                      <span className={`font-semibold ${item.profit_expected || item.profit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        ${item.profit_expected || item.profit.toLocaleString()}
                      </span>
                    </div>
                  </div>

                  <p className="text-xs text-muted-foreground mb-3 line-clamp-2">{item.verdict_reason || item.reason}</p>

                  <div className="flex items-center justify-between">
                    <div className="flex gap-3 text-xs text-muted-foreground">
                      <span>Max Bid: <span className="text-foreground font-medium">${item.max_bid.toLocaleString()}</span></span>
                      <span>{item.comp_count} comps</span>
                    </div>
                    {!isPromoted(item) ? (
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-xs h-7"
                        onClick={() => promote(item.id)}
                      >
                        Promote
                      </Button>
                    ) : (
                      <Badge variant="outline" className="text-green-400 border-green-800 text-xs">
                        <CheckCircle className="h-3 w-3 mr-1" />
                        In Pipeline
                      </Badge>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default ReconPanel;

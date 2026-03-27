import React, { useState, useCallback, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Slider } from '@/components/ui/slider';
import { SonarCard } from './SonarCard';
import { sonarSearchStreaming, filterQuality, SONAR_SOURCES, type SonarResult, type SonarSource } from '@/services/sonarAPI';
import { Search, Share2, ArrowUpDown, Check, Loader2, ClipboardCheck } from 'lucide-react';
import { toast } from 'sonner';
import { fmt$ } from '@/utils/formatters';

type SortKey = 'price_asc' | 'ending_soon' | 'newest';

function sortResults(results: SonarResult[], key: SortKey): SonarResult[] {
  const copy = [...results];
  switch (key) {
    case 'price_asc':
      return copy.sort((a, b) => a.currentBid - b.currentBid);
    case 'ending_soon':
      return copy.sort((a, b) => new Date(a.endsAt).getTime() - new Date(b.endsAt).getTime());
    case 'newest':
      return copy.sort((a, b) => b.year - a.year);
  }
}

type SourceStatus = 'pending' | 'scanning' | 'done';

export const SonarTab: React.FC = () => {
  const [query, setQuery] = useState('');
  const [priceRange, setPriceRange] = useState<[number, number]>([0, 20_000]);
  const [minInput, setMinInput] = useState('0');
  const [maxInput, setMaxInput] = useState('20000');
  const [results, setResults] = useState<SonarResult[]>([]);
  const [excludedResults, setExcludedResults] = useState<SonarResult[]>([]);
  const [showAll, setShowAll] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>('price_asc');
  const [sourceStatuses, setSourceStatuses] = useState<Record<string, SourceStatus>>({});
  const [excludedCount, setExcludedCount] = useState(0);
  const [shareIcon, setShareIcon] = useState<'share' | 'check'>('share');
  const abortRef = useRef(false);

  const handleSearch = useCallback(async (e?: React.FormEvent) => {
    e?.preventDefault();
    abortRef.current = false;
    setIsSearching(true);
    setResults([]);
    setExcludedResults([]);
    setExcludedCount(0);
    setHasSearched(true);

    // Initialize all sources as pending, first one as scanning
    const initial: Record<string, SourceStatus> = {};
    SONAR_SOURCES.forEach((s, i) => { initial[s] = i === 0 ? 'scanning' : 'pending'; });
    setSourceStatuses(initial);

    let nextSourceIdx = 1;

    await sonarSearchStreaming(
      { query, minPrice: priceRange[0], maxPrice: priceRange[1] },
      (batch) => {
        if (abortRef.current) return;
        const { clean, excluded, excludedResults } = filterQuality(batch.results);
        setResults((prev) => [...prev, ...clean]);
        setExcludedResults((prev) => [...prev, ...excludedResults]);
        setExcludedCount((prev) => prev + excluded);
        setSourceStatuses((prev) => {
          const next = { ...prev };
          next[batch.source] = 'done';
          if (nextSourceIdx < SONAR_SOURCES.length) {
            next[SONAR_SOURCES[nextSourceIdx]] = 'scanning';
            nextSourceIdx++;
          }
          return next;
        });
      },
    );

    setIsSearching(false);
  }, [query, priceRange]);

  const handleShare = useCallback(() => {
    const sorted = sortResults(results, sortKey);
    const lines = sorted.map(
      (r, i) =>
        `${i + 1}. ${r.year} ${r.make} ${r.model} ${r.trim} — ${fmt$(r.currentBid)} (${r.timeRemaining} left) — ${r.location}`
    );
    const text = `Sonar Search Results\n${query ? `"${query}"` : 'All vehicles'} · $${priceRange[0].toLocaleString()}–$${priceRange[1].toLocaleString()}\n\n${lines.join('\n')}`;
    navigator.clipboard.writeText(text).then(() => {
      toast.success('Copied to clipboard');
      setShareIcon('check');
      setTimeout(() => setShareIcon('share'), 2000);
    });
  }, [results, sortKey, query, priceRange]);

  const handleMinBlur = useCallback(() => {
    const parsed = Math.max(0, Number(minInput) || 0);
    const clamped = Math.min(parsed, priceRange[1]);
    setPriceRange([clamped, priceRange[1]]);
    setMinInput(String(clamped));
  }, [minInput, priceRange]);

  const handleMaxBlur = useCallback(() => {
    const parsed = Math.max(priceRange[0], Number(maxInput) || 0);
    setPriceRange([priceRange[0], parsed]);
    setMaxInput(String(parsed));
  }, [maxInput, priceRange]);

  const handleSliderChange = useCallback((v: number[]) => {
    const range = v as [number, number];
    setPriceRange(range);
    setMinInput(String(range[0]));
    setMaxInput(String(range[1]));
  }, []);

  const displayResults = showAll ? [...results, ...excludedResults] : results;
  const sorted = sortResults(displayResults, sortKey);
  const damagedIds = new Set(excludedResults.map((r) => r.id));
  const hasExcludedResults = excludedCount > 0;

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <span className="inline-block h-6 w-6 sonar-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6">
              <circle cx="12" cy="12" r="3" fill="currentColor" className="text-cyan-400" />
              <circle cx="12" cy="12" r="7" stroke="currentColor" strokeWidth="1.5" className="text-cyan-400/60 sonar-ring-1" />
              <circle cx="12" cy="12" r="11" stroke="currentColor" strokeWidth="1" className="text-cyan-400/30 sonar-ring-2" />
            </svg>
          </span>
          Sonar
        </h2>
        <p className="text-gray-400 text-sm mt-1">
          Search live auctions across government and public surplus sites
        </p>
      </div>

      {/* Search form */}
      <form onSubmit={handleSearch} className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
            <Input
              placeholder='Try "Tesla Model 3" or "Ford F-150"'
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="pl-10 bg-gray-800 border-gray-700 text-white placeholder:text-gray-500 focus:border-cyan-600 focus:ring-cyan-600/20"
            />
          </div>
          <Button
            type="submit"
            disabled={isSearching}
            className="bg-cyan-600 hover:bg-cyan-500 text-white font-medium px-6 shrink-0"
          >
            {isSearching ? 'Scanning...' : 'Search'}
          </Button>
        </div>

        {/* Budget range — dual slider + number inputs */}
        <div className="space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-400">Budget range</span>
            <span className="text-cyan-400 font-medium">
              {fmt$(priceRange[0])} — {fmt$(priceRange[1])}
            </span>
          </div>
          <Slider
            min={0}
            max={999_999}
            step={500}
            value={priceRange}
            onValueChange={handleSliderChange}
            className="sonar-slider"
          />
          <div className="flex gap-3 items-center">
            <div className="flex-1">
              <label className="text-gray-500 text-xs mb-1 block">Min ($)</label>
              <Input
                type="text"
                inputMode="numeric"
                value={minInput}
                onChange={(e) => setMinInput(e.target.value)}
                onBlur={handleMinBlur}
                className="bg-gray-800 border-gray-700 text-white text-sm h-8"
              />
            </div>
            <span className="text-gray-600 mt-4">—</span>
            <div className="flex-1">
              <label className="text-gray-500 text-xs mb-1 block">Max ($)</label>
              <Input
                type="text"
                inputMode="numeric"
                value={maxInput}
                onChange={(e) => setMaxInput(e.target.value)}
                onBlur={handleMaxBlur}
                className="bg-gray-800 border-gray-700 text-white text-sm h-8"
              />
            </div>
          </div>
        </div>
      </form>

      {/* Per-source progress ticks + skeleton loaders */}
      {isSearching && (
        <div className="space-y-4">
          <div className="flex flex-col items-center justify-center py-8 space-y-6">
            <div className="sonar-pulse-container">
              <div className="sonar-pulse-dot" />
              <div className="sonar-pulse-ring sonar-pulse-ring-1" />
              <div className="sonar-pulse-ring sonar-pulse-ring-2" />
              <div className="sonar-pulse-ring sonar-pulse-ring-3" />
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-3 text-sm">
            {SONAR_SOURCES.map((source) => {
              const status = sourceStatuses[source] ?? 'pending';
              return (
                <span
                  key={source}
                  className={`inline-flex items-center gap-1.5 px-2 py-1 rounded transition-colors ${
                    status === 'done'
                      ? 'text-green-400'
                      : status === 'scanning'
                        ? 'text-cyan-400'
                        : 'text-gray-600'
                  }`}
                >
                  {status === 'done' && <Check className="h-3.5 w-3.5" />}
                  {status === 'scanning' && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  {status === 'pending' && <span className="inline-block h-3.5 w-3.5" />}
                  {source}
                  {status === 'scanning' && '...'}
                </span>
              );
            })}
          </div>

          {/* Skeleton loaders when no results yet */}
          {results.length === 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {[0, 1, 2].map((i) => (
                <div key={i} className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden animate-pulse">
                  <div className="h-44 bg-gray-800" />
                  <div className="p-4 space-y-3">
                    <div className="h-5 bg-gray-800 rounded w-3/4" />
                    <div className="h-4 bg-gray-800 rounded w-1/2" />
                    <div className="h-6 bg-gray-800 rounded w-1/3" />
                    <div className="flex gap-3">
                      <div className="h-3 bg-gray-800 rounded w-16" />
                      <div className="h-3 bg-gray-800 rounded w-20" />
                      <div className="h-3 bg-gray-800 rounded w-14" />
                    </div>
                    <div className="h-3 bg-gray-800 rounded w-full" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Results toolbar */}
      {displayResults.length > 0 && (
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <span className="text-gray-400 text-sm">
              {displayResults.length} result{displayResults.length !== 1 ? 's' : ''}
              {isSearching && ' so far'}
              {excludedCount > 0 && (
                <span className="text-yellow-500/70 ml-1">
                  · {excludedCount} filtered for quality
                </span>
              )}
            </span>
            {hasExcludedResults && (
              <label className="inline-flex items-center gap-2 cursor-pointer select-none">
                <span className="relative inline-block w-8 h-[18px]">
                  <input
                    type="checkbox"
                    checked={showAll}
                    onChange={(e) => setShowAll(e.target.checked)}
                    className="sr-only peer"
                  />
                  <span className="block w-full h-full rounded-full bg-gray-700 peer-checked:bg-red-600/70 transition-colors" />
                  <span className="absolute top-[2px] left-[2px] w-[14px] h-[14px] rounded-full bg-gray-300 peer-checked:translate-x-[14px] transition-transform" />
                </span>
                <span className="text-xs text-gray-500">Show damaged/salvage</span>
              </label>
            )}
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 text-xs">
              <ArrowUpDown className="h-3 w-3 text-gray-500" />
              {(['price_asc', 'ending_soon', 'newest'] as SortKey[]).map((k) => (
                <button
                  key={k}
                  onClick={() => setSortKey(k)}
                  className={`px-2 py-1 rounded text-xs transition-colors ${
                    sortKey === k
                      ? 'bg-cyan-900/50 text-cyan-400 border border-cyan-700/50'
                      : 'text-gray-500 hover:text-gray-300'
                  }`}
                >
                  {k === 'price_asc' ? 'Price' : k === 'ending_soon' ? 'Ending soon' : 'Newest'}
                </button>
              ))}
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleShare}
              className="text-gray-400 hover:text-cyan-400 gap-1"
            >
              {shareIcon === 'check' ? (
                <ClipboardCheck className="h-3.5 w-3.5 text-green-400" />
              ) : (
                <Share2 className="h-3.5 w-3.5" />
              )}
              {shareIcon === 'check' ? 'Copied!' : 'Share'}
            </Button>
          </div>
        </div>
      )}

      {/* Results grid — shows progressively as batches arrive */}
      {displayResults.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {sorted.map((r, i) => (
            <SonarCard key={r.id} result={r} index={i} isDamaged={damagedIds.has(r.id)} />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isSearching && hasSearched && displayResults.length === 0 && (
        <div className="text-center py-16 text-gray-500">
          <p className="text-lg">No vehicles found</p>
          <p className="text-sm mt-1">Try broadening your search or adjusting your budget range</p>
        </div>
      )}
    </div>
  );
};

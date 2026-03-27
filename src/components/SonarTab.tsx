import React, { useState, useCallback, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Slider } from '@/components/ui/slider';
import { SonarCard } from './SonarCard';
import { sonarSearchStreaming, SONAR_SOURCES, type SonarResult, type SonarSource } from '@/services/sonarAPI';
import { Search, Share2, ArrowUpDown, Check, Loader2 } from 'lucide-react';

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
  const [results, setResults] = useState<SonarResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>('price_asc');
  const [sourceStatuses, setSourceStatuses] = useState<Map<SonarSource, SourceStatus>>(new Map());
  const abortRef = useRef(false);

  const handleSearch = useCallback(async (e?: React.FormEvent) => {
    e?.preventDefault();
    abortRef.current = false;
    setIsSearching(true);
    setResults([]);
    setHasSearched(true);

    // Initialize all sources as pending, first one as scanning
    const initial = new Map<SonarSource, SourceStatus>();
    SONAR_SOURCES.forEach((s, i) => initial.set(s, i === 0 ? 'scanning' : 'pending'));
    setSourceStatuses(initial);

    let nextSourceIdx = 1;

    await sonarSearchStreaming(
      { query, minPrice: priceRange[0], maxPrice: priceRange[1] },
      (batch) => {
        if (abortRef.current) return;
        // Add results from this batch
        setResults((prev) => [...prev, ...batch.results]);
        // Mark this source done, next source scanning
        setSourceStatuses((prev) => {
          const next = new Map(prev);
          next.set(batch.source, 'done');
          if (nextSourceIdx < SONAR_SOURCES.length) {
            next.set(SONAR_SOURCES[nextSourceIdx], 'scanning');
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
    navigator.clipboard.writeText(text);
  }, [results, sortKey, query, priceRange]);

  const handleMinInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const val = Math.max(0, Math.min(Number(e.target.value) || 0, priceRange[1]));
    setPriceRange([val, priceRange[1]]);
  }, [priceRange]);

  const handleMaxInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const val = Math.max(priceRange[0], Math.min(Number(e.target.value) || 0, 75_000));
    setPriceRange([priceRange[0], val]);
  }, [priceRange]);

  const sorted = sortResults(results, sortKey);

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
            max={75_000}
            step={500}
            value={priceRange}
            onValueChange={(v) => setPriceRange(v as [number, number])}
            className="sonar-slider"
          />
          <div className="flex gap-3 items-center">
            <div className="flex-1">
              <label className="text-gray-500 text-xs mb-1 block">Min ($)</label>
              <Input
                type="number"
                min={0}
                max={priceRange[1]}
                step={500}
                value={priceRange[0]}
                onChange={handleMinInput}
                className="bg-gray-800 border-gray-700 text-white text-sm h-8"
              />
            </div>
            <span className="text-gray-600 mt-4">—</span>
            <div className="flex-1">
              <label className="text-gray-500 text-xs mb-1 block">Max ($)</label>
              <Input
                type="number"
                min={priceRange[0]}
                max={75_000}
                step={500}
                value={priceRange[1]}
                onChange={handleMaxInput}
                className="bg-gray-800 border-gray-700 text-white text-sm h-8"
              />
            </div>
          </div>
        </div>
      </form>

      {/* Per-source progress ticks */}
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
              const status = sourceStatuses.get(source) ?? 'pending';
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
        </div>
      )}

      {/* Results toolbar */}
      {results.length > 0 && (
        <div className="flex items-center justify-between">
          <span className="text-gray-400 text-sm">
            {results.length} result{results.length !== 1 ? 's' : ''}
            {isSearching && ' so far'}
          </span>
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
              <Share2 className="h-3.5 w-3.5" />
              Share
            </Button>
          </div>
        </div>
      )}

      {/* Results grid — shows progressively as batches arrive */}
      {results.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {sorted.map((r, i) => (
            <SonarCard key={r.id} result={r} index={i} />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isSearching && hasSearched && results.length === 0 && (
        <div className="text-center py-16 text-gray-500">
          <p className="text-lg">No vehicles found</p>
          <p className="text-sm mt-1">Try broadening your search or adjusting your budget range</p>
        </div>
      )}

      {/* Sonar CSS */}
      <style>{`
        .sonar-pulse-container {
          position: relative;
          width: 120px;
          height: 120px;
        }
        .sonar-pulse-dot {
          position: absolute;
          top: 50%;
          left: 50%;
          width: 12px;
          height: 12px;
          margin: -6px 0 0 -6px;
          background: #06b6d4;
          border-radius: 50%;
          box-shadow: 0 0 12px #06b6d4;
        }
        .sonar-pulse-ring {
          position: absolute;
          top: 50%;
          left: 50%;
          border: 2px solid #06b6d4;
          border-radius: 50%;
          opacity: 0;
          animation: sonar-expand 2s ease-out infinite;
        }
        .sonar-pulse-ring-1 {
          width: 40px; height: 40px; margin: -20px 0 0 -20px;
          animation-delay: 0s;
        }
        .sonar-pulse-ring-2 {
          width: 40px; height: 40px; margin: -20px 0 0 -20px;
          animation-delay: 0.6s;
        }
        .sonar-pulse-ring-3 {
          width: 40px; height: 40px; margin: -20px 0 0 -20px;
          animation-delay: 1.2s;
        }
        @keyframes sonar-expand {
          0% { transform: scale(1); opacity: 0.7; }
          100% { transform: scale(3); opacity: 0; }
        }
        .sonar-card-enter {
          animation: sonar-fade-up 0.4s ease-out both;
        }
        @keyframes sonar-fade-up {
          from { opacity: 0; transform: translateY(16px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .sonar-ring-1 { animation: sonar-icon-pulse 2.5s ease-in-out infinite; }
        .sonar-ring-2 { animation: sonar-icon-pulse 2.5s ease-in-out 0.4s infinite; }
        @keyframes sonar-icon-pulse {
          0%, 100% { opacity: 0.3; }
          50% { opacity: 0.8; }
        }
        .sonar-slider [data-orientation="horizontal"] > span:first-child > span {
          background: #06b6d4;
        }
      `}</style>
    </div>
  );
};

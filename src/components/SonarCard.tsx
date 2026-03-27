import React, { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { MapPin, Clock, Gauge, ShieldCheck, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';
import type { SonarResult } from '@/services/sonarAPI';
import { fmt$ } from '@/utils/formatters';

interface SonarCardProps {
  result: SonarResult;
  index: number;
}

const TITLE_STATUS_COLORS: Record<string, string> = {
  Clean: 'bg-green-900/60 text-green-400 border-green-700/50',
  Salvage: 'bg-red-900/60 text-red-400 border-red-700/50',
  Rebuilt: 'bg-yellow-900/60 text-yellow-400 border-yellow-700/50',
};

const PLACEHOLDER_IMG = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="400" height="260" fill="%231f2937"%3E%3Crect width="400" height="260"/%3E%3Ctext x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" fill="%236b7280" font-size="14"%3ENo Image%3C/text%3E%3C/svg%3E';

function formatMileage(mileage: number | null | string): string {
  if (mileage === null || mileage === undefined) return 'Mileage Unknown';
  if (typeof mileage === 'string') {
    const lower = mileage.toLowerCase();
    if (lower === 'tmu' || lower === 'exempt' || lower === 'unknown') return 'Mileage Unknown';
    const parsed = Number(mileage);
    if (isNaN(parsed) || parsed === 0) return 'Mileage Unknown';
    return `${parsed.toLocaleString()} mi`;
  }
  if (mileage === 0) return 'Mileage Unknown';
  return `${mileage.toLocaleString()} mi`;
}

export const SonarCard: React.FC<SonarCardProps> = ({ result, index }) => {
  const [conditionExpanded, setConditionExpanded] = useState(false);
  const [imgError, setImgError] = useState(false);

  const titleColorClass = TITLE_STATUS_COLORS[result.titleStatus] ?? 'bg-gray-800/60 text-gray-400 border-gray-600/50';

  return (
    <Card
      className="bg-gray-900 border-gray-800 overflow-hidden hover:border-cyan-700/50 transition-all duration-300 group"
      style={{ animationDelay: `${index * 120}ms` }}
    >
      <div className="sonar-card-enter">
        {/* Photo */}
        <div className="relative h-44 overflow-hidden bg-gray-800">
          <img
            src={imgError ? PLACEHOLDER_IMG : result.photoUrl}
            alt={`${result.year} ${result.make} ${result.model}`}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
            loading="lazy"
            onError={() => setImgError(true)}
          />
          <Badge className="absolute top-2 right-2 bg-cyan-600/90 text-white border-0 text-xs">
            {result.sourceName}
          </Badge>
        </div>

        <CardContent className="p-4 space-y-3">
          {/* Title */}
          <div>
            <h3 className="text-white font-semibold text-base leading-tight">
              {result.year} {result.make} {result.model}
            </h3>
            <p className="text-gray-400 text-sm">{result.trim}</p>
          </div>

          {/* Price */}
          <div className="flex items-baseline gap-2">
            <span className="text-cyan-400 text-xl font-bold">{fmt$(result.currentBid)}</span>
            <span className="text-gray-500 text-xs">current bid</span>
          </div>

          {/* Meta row */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400">
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3 text-cyan-500" />
              {result.timeRemaining} left
            </span>
            <span className="flex items-center gap-1">
              <MapPin className="h-3 w-3 text-cyan-500" />
              {result.location}
            </span>
            <span className="flex items-center gap-1">
              <Gauge className="h-3 w-3 text-cyan-500" />
              {formatMileage(result.mileage)}
            </span>
          </div>

          {/* Condition — expandable */}
          <div>
            <p className={`text-gray-500 text-xs leading-relaxed ${conditionExpanded ? '' : 'line-clamp-2'}`}>
              {result.condition}
            </p>
            {result.condition.length > 80 && (
              <button
                onClick={() => setConditionExpanded(!conditionExpanded)}
                className="text-cyan-500 text-xs mt-0.5 inline-flex items-center gap-0.5 hover:text-cyan-400"
              >
                {conditionExpanded ? (
                  <><ChevronUp className="h-3 w-3" /> Less</>
                ) : (
                  <><ChevronDown className="h-3 w-3" /> More</>
                )}
              </button>
            )}
          </div>

          {/* Trust section */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="inline-flex items-center gap-1 text-xs text-gray-400 bg-gray-800 rounded px-2 py-0.5">
              <ShieldCheck className="h-3 w-3 text-cyan-500" />
              {result.issuingAgency}
            </span>
            <span className={`inline-block text-xs font-medium rounded px-2 py-0.5 border ${titleColorClass}`}>
              {result.titleStatus} Title
            </span>
          </div>

          {/* As-is disclaimer — prominent warning banner */}
          {result.isAsIs && (
            <div className="flex items-center gap-2 rounded-md border border-amber-700/50 bg-amber-900/30 px-3 py-2 text-amber-400 text-xs font-medium">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              Sold as-is — no warranty or returns
            </div>
          )}

          {/* CTA */}
          <a
            href={result.sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-cyan-400 hover:text-cyan-300 text-sm font-medium transition-colors pt-1"
          >
            View Auction &rarr;
          </a>
        </CardContent>
      </div>
    </Card>
  );
};

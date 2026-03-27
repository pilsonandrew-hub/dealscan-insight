import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { MapPin, Clock, Gauge, ShieldCheck } from 'lucide-react';
import type { SonarResult } from '@/services/sonarAPI';

interface SonarCardProps {
  result: SonarResult;
  index: number;
}

function fmt$(n: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(n);
}

const TITLE_STATUS_COLORS: Record<SonarResult['titleStatus'], string> = {
  Clean: 'bg-green-900/60 text-green-400 border-green-700/50',
  Salvage: 'bg-red-900/60 text-red-400 border-red-700/50',
  Rebuilt: 'bg-yellow-900/60 text-yellow-400 border-yellow-700/50',
};

export const SonarCard: React.FC<SonarCardProps> = ({ result, index }) => {
  return (
    <Card
      className="bg-gray-900 border-gray-800 overflow-hidden hover:border-cyan-700/50 transition-all duration-300 group"
      style={{ animationDelay: `${index * 120}ms` }}
    >
      <div className="sonar-card-enter">
        {/* Photo */}
        <div className="relative h-44 overflow-hidden bg-gray-800">
          <img
            src={result.photoUrl}
            alt={`${result.year} ${result.make} ${result.model}`}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
            loading="lazy"
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
              {result.mileage.toLocaleString()} mi
            </span>
          </div>

          {/* Condition */}
          <p className="text-gray-500 text-xs leading-relaxed line-clamp-2">
            {result.condition}
          </p>

          {/* Trust section */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="inline-flex items-center gap-1 text-xs text-gray-400 bg-gray-800 rounded px-2 py-0.5">
              <ShieldCheck className="h-3 w-3 text-cyan-500" />
              {result.issuingAgency}
            </span>
            <span className={`inline-block text-xs font-medium rounded px-2 py-0.5 border ${TITLE_STATUS_COLORS[result.titleStatus]}`}>
              {result.titleStatus} Title
            </span>
          </div>

          {/* As-is disclaimer */}
          {result.isAsIs && (
            <p className="text-gray-600 text-[11px]">Auction vehicles sold as-is</p>
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

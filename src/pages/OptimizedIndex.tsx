
import React, { useState } from 'react';
import { OptimizedDashboard } from '@/components/OptimizedDashboard';
import { DealerScopeHeader } from '@/components/DealerScopeHeader';

export default function OptimizedIndex() {
  const [activeView, setActiveView] = useState('dashboard');
  
  return (
    <div className="min-h-screen bg-background">
      <DealerScopeHeader 
        activeView={activeView}
        onViewChange={setActiveView}
        newDealsCount={0}
      />
      <main className="container mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-4xl font-bold tracking-tight">DealerScope Elite v4.8</h1>
          <p className="text-xl text-muted-foreground mt-2">
            Advanced automotive arbitrage intelligence with next-level performance optimizations
          </p>
        </div>
        <OptimizedDashboard />
      </main>
    </div>
  );
}

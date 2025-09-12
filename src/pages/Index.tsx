import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import api from "@/services/api";
import { DealerScopeHeader } from "@/components/DealerScopeHeader";
import { DashboardMetrics } from "@/components/DashboardMetrics";
import { DealOpportunities } from "@/components/DealOpportunities";
import { DealInbox } from "@/components/DealInbox";
import { UploadInterface } from "@/components/UploadInterface";
import { SystemMetrics } from "@/components/SystemMetrics";
import { MarketAnalytics } from "@/components/MarketAnalytics";
import { OptimizedOpportunityList } from "@/components/OptimizedOpportunityList";
import { SystemEvaluationPanel } from "@/components/SystemEvaluationPanel";
import { VehicleScraperPanel } from "@/components/VehicleScraperPanel";
import { ScraperTestDashboard } from "@/components/ScraperTestDashboard";
import { DealScoringPanel } from "@/components/DealScoringPanel";
import { V5FeaturesShowcase } from "@/components/V5FeaturesShowcase";
import { ProductionReadinessSummary } from "@/components/ProductionReadinessSummary";
import { CrosshairDashboard } from "@/components/CrosshairDashboard";
import Settings from "@/pages/Settings";
import { useRealtimeOpportunities } from "@/hooks/useRealtimeOpportunities";
import { RealtimeStatusBadge } from "@/components/RealtimeStatusBadge";
import { useToast } from "@/hooks/use-toast";
import { Opportunity } from "@/types/dealerscope";

const Index = () => {
  const [activeView, setActiveView] = useState("dashboard");
  const { toast } = useToast();

  // Fetch initial opportunities and metrics
  const { data: initialOpportunities = { data: [], total: 0, hasMore: false } } = useQuery({
    queryKey: ["opportunities"],
    queryFn: () => api.getOpportunities(1, 100),
    refetchInterval: 30000, // Fallback polling
  });

  // Extract data safely from either response format
  const initialData: any[] = Array.isArray(initialOpportunities) ? initialOpportunities : 
    (initialOpportunities && typeof initialOpportunities === 'object' && 'data' in initialOpportunities ? 
      (initialOpportunities.data || []) : []);

  const { data: metrics = {
    active_opportunities: 0,
    avg_margin: 0,
    potential_revenue: 0,
    success_rate: 0
  } } = useQuery({
    queryKey: ["dashboard-metrics"],
    queryFn: api.getDashboardMetrics,
    refetchInterval: 60000,
  });

  // Real-time opportunities with WebSocket
  const {
    opportunities,
    pipelineStatus,
    newOpportunitiesCount,
    connectionStatus,
    isConnected,
    clearNewCount,
    pausePipeline,
    resumePipeline,
    connect,
    disconnect
  } = useRealtimeOpportunities(initialData);

  const handleUploadSuccess = () => {
    // Real-time updates will handle new opportunities automatically
    setActiveView("dashboard");
  };

  const renderActiveView = () => {
    switch (activeView) {
      case "dashboard":
        return (
          <div className="space-y-8">
            <DashboardMetrics 
              metrics={metrics}
              pipelineStatus={{
                status: pipelineStatus?.status || 'stopped',
                stage: 'processing',
                progress: 0,
                opportunities_found: 0
              }}
              isRealtime={isConnected}
            />
            <DealInbox />
          </div>
        );
      case "crosshair":
        return <CrosshairDashboard />;
      case "opportunities":
        return (
          <DealOpportunities 
            opportunities={opportunities}
            isRealtime={isConnected}
            onNewCountCleared={clearNewCount}
          />
        );
      case "analytics":
        return <MarketAnalytics opportunities={opportunities} />;
      case "upload":
        return <UploadInterface onUploadSuccess={handleUploadSuccess} />;
      case "metrics":
        return <SystemMetrics />;
      case "scraper":
        return <VehicleScraperPanel />;
      case "scraper-test":
        return <ScraperTestDashboard />;
      case "scoring":
        return <DealScoringPanel />;
      case "evaluation":
        return <SystemEvaluationPanel />;
      case "v5features":
        return (
          <div className="space-y-8">
            <V5FeaturesShowcase />
            <ProductionReadinessSummary />
          </div>
        );
      case "settings":
        return <Settings />;
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="flex items-center justify-between p-4 border-b">
        <DealerScopeHeader 
          activeView={activeView} 
          onViewChange={setActiveView}
          newDealsCount={newOpportunitiesCount}
        />
        <RealtimeStatusBadge
          status={connectionStatus}
          newCount={newOpportunitiesCount}
          onConnect={connect}
          onDisconnect={disconnect}
          onClearNew={clearNewCount}
          pipelineRunning={pipelineStatus?.status === 'running'}
          onPausePipeline={pausePipeline}
          onResumePipeline={resumePipeline}
        />
      </div>
      
      <main className="container py-8">
        {renderActiveView()}
      </main>
    </div>
  );
};

export default Index;

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import api from "@/services/api";
import { DealerScopeHeader } from "@/components/DealerScopeHeader";
import { DashboardMetrics } from "@/components/DashboardMetrics";
import { EnhancedDealInbox } from "@/components/EnhancedDealInbox";
import { UploadInterface } from "@/components/UploadInterface";
import { MarketAnalytics } from "@/components/MarketAnalytics";
import { CrosshairDashboard } from "@/components/CrosshairDashboard";
import { RoverDashboard } from "@/components/RoverDashboard";
import { MLModelDashboard } from "@/components/MLModelDashboard";
import { UpdatedDealScoringPanel } from "@/components/UpdatedDealScoringPanel";
import Settings from "@/pages/Settings";
import { useRealtimeOpportunities } from "@/hooks/useRealtimeOpportunities";
import { RealtimeStatusBadge } from "@/components/RealtimeStatusBadge";
import { useToast } from "@/hooks/use-toast";

type View = "dashboard" | "crosshair" | "rover" | "analytics" | "settings";

const Index = () => {
  const [activeView, setActiveView] = useState<View>("dashboard");
  const { toast } = useToast();

  const { data: initialOpportunities = { data: [], total: 0, hasMore: false } } = useQuery({
    queryKey: ["opportunities"],
    queryFn: () => api.getOpportunities(1, 100),
    refetchInterval: 30000,
  });

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
            <EnhancedDealInbox />
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
        );
      case "crosshair":
        return <CrosshairDashboard />;
      case "rover":
        return <RoverDashboard isPremium={true} />;
      case "analytics":
        return (
          <div className="space-y-8">
            <MarketAnalytics opportunities={opportunities} />
            <MLModelDashboard />
            <UpdatedDealScoringPanel />
          </div>
        );
      case "settings":
        return (
          <div className="space-y-8">
            <UploadInterface onUploadSuccess={handleUploadSuccess} />
            <Settings />
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <DealerScopeHeader
        activeView={activeView}
        onViewChange={(v) => setActiveView(v as View)}
        newDealsCount={newOpportunitiesCount}
        isPremium={true}
      />

      <main className="container py-8">
        {renderActiveView()}
      </main>
    </div>
  );
};

export default Index;

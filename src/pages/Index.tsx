import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import api from "@/services/api";
import { DealerScopeHeader } from "@/components/DealerScopeHeader";
import { DashboardMetrics } from "@/components/DashboardMetrics";
import { DealOpportunities } from "@/components/DealOpportunities";
import { UploadInterface } from "@/components/UploadInterface";
import { SystemMetrics } from "@/components/SystemMetrics";
import { useRealtimeOpportunities } from "@/hooks/useRealtimeOpportunities";
import { RealtimeStatusBadge } from "@/components/RealtimeStatusBadge";

const Index = () => {
  const [activeView, setActiveView] = useState("dashboard");

  // Fetch initial opportunities and metrics
  const { data: initialOpportunities = [] } = useQuery({
    queryKey: ["opportunities"],
    queryFn: api.getOpportunities,
    refetchInterval: 30000, // Fallback polling
  });

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
  } = useRealtimeOpportunities(initialOpportunities);

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
              pipelineStatus={pipelineStatus}
              isRealtime={isConnected}
            />
            <DealOpportunities 
              opportunities={opportunities}
              isRealtime={isConnected}
              onNewCountCleared={clearNewCount}
            />
          </div>
        );
      case "upload":
        return <UploadInterface onUploadSuccess={handleUploadSuccess} />;
      case "metrics":
        return <SystemMetrics />;
      case "settings":
        return (
          <div className="space-y-6">
            <div>
              <h2 className="text-2xl font-bold text-foreground">Settings</h2>
              <p className="text-muted-foreground">Configure your DealerScope preferences and data sources</p>
            </div>
            <div className="text-center py-12">
              <p className="text-muted-foreground">Settings interface coming soon...</p>
            </div>
          </div>
        );
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

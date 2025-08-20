import { useState } from "react";
import { DealerScopeHeader } from "@/components/DealerScopeHeader";
import { DashboardMetrics } from "@/components/DashboardMetrics";
import { DealOpportunities } from "@/components/DealOpportunities";
import { UploadInterface } from "@/components/UploadInterface";

const Index = () => {
  const [activeView, setActiveView] = useState("dashboard");
  const [newDealsCount] = useState(3); // Mock new deals notification

  const renderActiveView = () => {
    switch (activeView) {
      case "dashboard":
        return (
          <div className="space-y-8">
            <DashboardMetrics />
            <DealOpportunities />
          </div>
        );
      case "upload":
        return <UploadInterface />;
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
      <DealerScopeHeader 
        activeView={activeView} 
        onViewChange={setActiveView}
        newDealsCount={newDealsCount}
      />
      
      <main className="container py-8">
        {renderActiveView()}
      </main>
    </div>
  );
};

export default Index;

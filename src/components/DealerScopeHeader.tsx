import { TrendingUp, Upload, Settings, Bell, BarChart3, Target, PieChart, Activity, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

interface DealerScopeHeaderProps {
  activeView: string;
  onViewChange: (view: string) => void;
  newDealsCount: number;
}

export const DealerScopeHeader = ({ activeView, onViewChange, newDealsCount }: DealerScopeHeaderProps) => {
  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-16 items-center">
        <div className="mr-8 flex items-center space-x-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-primary-glow">
            <TrendingUp className="h-5 w-5 text-primary-foreground" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-foreground">DealerScope</h1>
            <p className="text-xs text-muted-foreground">v4.8 Professional</p>
          </div>
        </div>

        <nav className="flex items-center space-x-1">
          <Button
            variant={activeView === "dashboard" ? "default" : "ghost"}
            size="sm"
            onClick={() => onViewChange("dashboard")}
            className="relative"
          >
            Dashboard
            {newDealsCount > 0 && activeView !== "dashboard" && (
              <Badge variant="destructive" className="absolute -right-2 -top-2 h-5 w-5 rounded-full p-0 text-xs">
                {newDealsCount}
              </Badge>
            )}
          </Button>
          
          <Button
            variant={activeView === "opportunities" ? "default" : "ghost"}
            size="sm"
            onClick={() => onViewChange("opportunities")}
          >
            <Target className="mr-2 h-4 w-4" />
            Opportunities
          </Button>
          
          <Button
            variant={activeView === "analytics" ? "default" : "ghost"}
            size="sm"
            onClick={() => onViewChange("analytics")}
          >
            <PieChart className="mr-2 h-4 w-4" />
            Analytics
          </Button>
          
          <Button
            variant={activeView === "scraper" ? "default" : "ghost"}
            size="sm"
            onClick={() => onViewChange("scraper")}
          >
            <Search className="mr-2 h-4 w-4" />
            Scraper
          </Button>
          
          <Button
            variant={activeView === "upload" ? "default" : "ghost"}
            size="sm"
            onClick={() => onViewChange("upload")}
          >
            <Upload className="mr-2 h-4 w-4" />
            Upload Data
          </Button>
          
          <Button
            variant={activeView === "metrics" ? "default" : "ghost"}
            size="sm"
            onClick={() => onViewChange("metrics")}
          >
            <BarChart3 className="mr-2 h-4 w-4" />
            Metrics
          </Button>

          <Button
            variant={activeView === "evaluation" ? "default" : "ghost"}
            size="sm"
            onClick={() => onViewChange("evaluation")}
          >
            <Activity className="mr-2 h-4 w-4" />
            Evaluation
          </Button>
          
          <Button
            variant={activeView === "settings" ? "default" : "ghost"}
            size="sm"
            onClick={() => onViewChange("settings")}
          >
            <Settings className="mr-2 h-4 w-4" />
            Settings
          </Button>
        </nav>

        <div className="ml-auto flex items-center space-x-4">
          <Button variant="ghost" size="sm" className="relative">
            <Bell className="h-4 w-4" />
            {newDealsCount > 0 && (
              <Badge variant="destructive" className="absolute -right-1 -top-1 h-4 w-4 rounded-full p-0 text-xs">
                {newDealsCount}
              </Badge>
            )}
          </Button>
          
          <div className="flex items-center space-x-2 text-sm">
            <div className="h-2 w-2 rounded-full bg-success"></div>
            <span className="text-muted-foreground">Live Data</span>
          </div>
        </div>
      </div>
    </header>
  );
};
import { TrendingUp, Upload, Settings, Bell, BarChart3, Target, PieChart, Activity, Search, Sparkles, Crosshair, Brain, Shield, Zap, Bot, TestTube } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import dealerscopeLogo from "@/assets/dealerscope-logo.png";

interface DealerScopeHeaderProps {
  activeView: string;
  onViewChange: (view: string) => void;
  newDealsCount: number;
  isPremium?: boolean;
}

export const DealerScopeHeader = ({ activeView, onViewChange, newDealsCount, isPremium = false }: DealerScopeHeaderProps) => {
  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-16 items-center">
        <div className="mr-8 flex items-center space-x-3">
          <div className="relative h-12 w-12 bg-gradient-to-br from-primary to-primary/70 rounded-xl p-2 shadow-lg shadow-primary/20">
            <img 
              src={dealerscopeLogo} 
              alt="DealerScope" 
              className="h-full w-full object-contain filter drop-shadow-sm"
              onError={(e) => {
                console.log('Logo failed to load:', e);
                e.currentTarget.style.display = 'none';
              }}
              onLoad={() => console.log('Logo loaded successfully')}
            />
            <div className="absolute inset-0 bg-gradient-to-br from-white/20 to-transparent rounded-xl"></div>
          </div>
          <div className="flex flex-col">
            <h1 className="text-xl font-brand font-bold bg-gradient-to-r from-primary to-primary/70 bg-clip-text text-transparent tracking-tight">
              DealerScope
            </h1>
            <p className="text-xs font-medium text-muted-foreground/80 tracking-wide uppercase">
              Professional Intelligence
            </p>
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
            variant={activeView === "crosshair" ? "default" : "ghost"}
            size="sm"
            onClick={() => onViewChange("crosshair")}
          >
            <Crosshair className="mr-2 h-4 w-4" />
            Crosshair
            <Badge variant="secondary" className="ml-2 text-xs">PREMIUM</Badge>
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
            variant={activeView === "scraper-test" ? "default" : "ghost"}
            size="sm"
            onClick={() => onViewChange("scraper-test")}
          >
            <Settings className="mr-2 h-4 w-4" />
            Test Sites
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
            variant={activeView === "ai-engine" ? "default" : "ghost"}
            size="sm"
            onClick={() => onViewChange("ai-engine")}
          >
            <Brain className="mr-2 h-4 w-4" />
            AI Engine
            <Badge variant="secondary" className="ml-2 text-xs">PHASE 3</Badge>
          </Button>

          <Button
            variant={activeView === "rover" ? "default" : "ghost"}
            size="sm"
            onClick={() => onViewChange("rover")}
            disabled={!isPremium}
            className="relative"
          >
            <Bot className="mr-2 h-4 w-4" />
            Rover
            <Badge 
              variant="default" 
              className="ml-2 text-xs bg-gradient-to-r from-purple-500 to-pink-500 text-white"
            >
              PREMIUM
            </Badge>
            {!isPremium && (
              <div className="absolute -top-1 -right-1">
                <div className="w-3 h-3 bg-yellow-400 rounded-full animate-pulse" />
              </div>
            )}
          </Button>

          <Button
            variant={activeView === "anomaly-detection" ? "default" : "ghost"}
            size="sm"
            onClick={() => onViewChange("anomaly-detection")}
          >
            <Shield className="mr-2 h-4 w-4" />
            Anomaly Detection
            <Badge variant="secondary" className="ml-2 text-xs">PHASE 3</Badge>
          </Button>

          <Button
            variant={activeView === "automation" ? "default" : "ghost"}
            size="sm"
            onClick={() => onViewChange("automation")}
          >
            <Zap className="mr-2 h-4 w-4" />
            Automation
            <Badge variant="secondary" className="ml-2 text-xs">PHASE 3</Badge>
          </Button>

          <Button
            variant={activeView === "ml-models" ? "default" : "ghost"}
            size="sm"
            onClick={() => onViewChange("ml-models")}
          >
            <Bot className="mr-2 h-4 w-4" />
            ML Models
            <Badge variant="secondary" className="ml-2 text-xs bg-purple-100 text-purple-700">PHASE 4</Badge>
          </Button>

          <Button
            variant={activeView === "testing" ? "default" : "ghost"}
            size="sm"
            onClick={() => onViewChange("testing")}
          >
            <TestTube className="mr-2 h-4 w-4" />
            Testing Suite
            <Badge variant="secondary" className="ml-2 text-xs bg-purple-100 text-purple-700">PHASE 4</Badge>
          </Button>

          <Button
            variant={activeView === "v5features" ? "default" : "ghost"}
            size="sm"
            onClick={() => onViewChange("v5features")}
            className="relative"
          >
            <Sparkles className="mr-2 h-4 w-4" />
            v5.0 Features
            <Badge variant="secondary" className="ml-2 text-xs">NEW</Badge>
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
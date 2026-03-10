import { Upload, Settings, Bell, PieChart, Crosshair, Bot } from "lucide-react";
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
                e.currentTarget.style.display = 'none';
              }}
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
            variant={activeView === "rover" ? "default" : "ghost"}
            size="sm"
            onClick={() => onViewChange("rover")}
          >
            <Bot className="mr-2 h-4 w-4" />
            Rover
            <Badge variant="default" className="ml-2 text-xs bg-gradient-to-r from-purple-500 to-pink-500 text-white">
              PREMIUM
            </Badge>
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

import { TrendingUp, DollarSign, Target, Activity } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

interface MetricCardProps {
  title: string;
  value: string | number;
  change?: string;
  changeType?: "positive" | "negative" | "neutral";
  icon: React.ReactNode;
  description?: string;
}

const MetricCard = ({ title, value, change, changeType, icon, description }: MetricCardProps) => {
  const getChangeColor = (type?: string) => {
    switch (type) {
      case "positive": return "text-success";
      case "negative": return "text-destructive";
      default: return "text-muted-foreground";
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <div className="text-muted-foreground">{icon}</div>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {change && (
          <p className={`text-xs ${getChangeColor(changeType)}`}>
            {change}
          </p>
        )}
        {description && (
          <p className="text-xs text-muted-foreground mt-1">{description}</p>
        )}
      </CardContent>
    </Card>
  );
};

export const DashboardMetrics = () => {
  const metrics = [
    {
      title: "Active Opportunities",
      value: "47",
      change: "+12% from last week",
      changeType: "positive" as const,
      icon: <Target className="h-4 w-4" />,
      description: "High-confidence arbitrage opportunities"
    },
    {
      title: "Avg. Margin",
      value: "27.3%",
      change: "+2.1% from last month",
      changeType: "positive" as const,
      icon: <TrendingUp className="h-4 w-4" />,
      description: "Average profit margin across all deals"
    },
    {
      title: "Potential Revenue",
      value: "$423,850",
      change: "+18% from last month",
      changeType: "positive" as const,
      icon: <DollarSign className="h-4 w-4" />,
      description: "Total estimated profit from active deals"
    },
    {
      title: "Success Rate",
      value: "89%",
      change: "Stable",
      changeType: "neutral" as const,
      icon: <Activity className="h-4 w-4" />,
      description: "Percentage of tracked deals that closed profitably"
    }
  ];

  const recentActivity = [
    { action: "New opportunity", details: "2021 Ford F-150 in Phoenix", time: "2 minutes ago", type: "opportunity" },
    { action: "Price update", details: "2020 Silverado bid increased", time: "15 minutes ago", type: "update" },
    { action: "Auction ending", details: "2019 RAM 1500 in Dallas", time: "1 hour ago", type: "warning" },
    { action: "Deal won", details: "2020 Tacoma for $28,500", time: "3 hours ago", type: "success" }
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground">Dashboard Overview</h2>
        <p className="text-muted-foreground">Real-time metrics and performance insights</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {metrics.map((metric, index) => (
          <MetricCard key={index} {...metric} />
        ))}
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Market Performance</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span>Ford F-Series</span>
                <span className="font-medium">34% market share</span>
              </div>
              <Progress value={34} className="h-2" />
            </div>
            
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span>Chevrolet Silverado</span>
                <span className="font-medium">28% market share</span>
              </div>
              <Progress value={28} className="h-2" />
            </div>
            
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span>RAM Trucks</span>
                <span className="font-medium">19% market share</span>
              </div>
              <Progress value={19} className="h-2" />
            </div>
            
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span>Toyota Tacoma</span>
                <span className="font-medium">12% market share</span>
              </div>
              <Progress value={12} className="h-2" />
            </div>
            
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span>Other</span>
                <span className="font-medium">7% market share</span>
              </div>
              <Progress value={7} className="h-2" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent Activity</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {recentActivity.map((item, index) => (
                <div key={index} className="flex items-start space-x-3">
                  <div className={`
                    mt-1 h-2 w-2 rounded-full
                    ${item.type === "opportunity" ? "bg-primary" : ""}
                    ${item.type === "update" ? "bg-warning" : ""}
                    ${item.type === "warning" ? "bg-destructive" : ""}
                    ${item.type === "success" ? "bg-success" : ""}
                  `} />
                  <div className="flex-1 space-y-1">
                    <p className="text-sm font-medium">{item.action}</p>
                    <p className="text-xs text-muted-foreground">{item.details}</p>
                    <p className="text-xs text-muted-foreground">{item.time}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
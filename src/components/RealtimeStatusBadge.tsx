/**
 * Real-time connection status indicator
 * Shows WebSocket connection state and allows manual control
 */

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { 
  Wifi, 
  WifiOff, 
  Loader2, 
  AlertCircle, 
  Play, 
  Pause,
  RefreshCw 
} from "lucide-react";
import { WebSocketStatus } from "@/hooks/useWebSocket";

interface RealtimeStatusBadgeProps {
  status: WebSocketStatus;
  newCount?: number;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onClearNew?: () => void;
  pipelineRunning?: boolean;
  onPausePipeline?: () => void;
  onResumePipeline?: () => void;
}

export function RealtimeStatusBadge({
  status,
  newCount = 0,
  onConnect,
  onDisconnect,
  onClearNew,
  pipelineRunning = false,
  onPausePipeline,
  onResumePipeline
}: RealtimeStatusBadgeProps) {
  const getStatusConfig = () => {
    switch (status) {
      case WebSocketStatus.CONNECTED:
        return {
          variant: "default" as const,
          icon: <Wifi className="h-3 w-3" />,
          text: "Live",
          description: "Real-time updates active"
        };
      case WebSocketStatus.CONNECTING:
        return {
          variant: "secondary" as const,
          icon: <Loader2 className="h-3 w-3 animate-spin" />,
          text: "Connecting",
          description: "Establishing connection..."
        };
      case WebSocketStatus.RECONNECTING:
        return {
          variant: "secondary" as const,
          icon: <RefreshCw className="h-3 w-3 animate-spin" />,
          text: "Reconnecting",
          description: "Attempting to reconnect..."
        };
      case WebSocketStatus.ERROR:
        return {
          variant: "destructive" as const,
          icon: <AlertCircle className="h-3 w-3" />,
          text: "Error",
          description: "Connection failed"
        };
      default:
        return {
          variant: "secondary" as const,
          icon: <WifiOff className="h-3 w-3" />,
          text: "Periodic",
          description: "Using periodic updates (backend unavailable)"
        };
    }
  };

  const config = getStatusConfig();

  return (
    <div className="flex items-center gap-2">
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge 
            variant={config.variant} 
            className="flex items-center gap-1 cursor-pointer"
            onClick={newCount > 0 ? onClearNew : undefined}
          >
            {config.icon}
            {config.text}
            {newCount > 0 && (
              <span className="ml-1 px-1 bg-primary text-primary-foreground rounded-full text-xs min-w-[16px] text-center">
                {newCount > 99 ? '99+' : newCount}
              </span>
            )}
          </Badge>
        </TooltipTrigger>
        <TooltipContent>
          <p>{config.description}</p>
          {newCount > 0 && <p className="text-xs">Click to clear new count</p>}
        </TooltipContent>
      </Tooltip>

      {/* Connection controls */}
      {status === WebSocketStatus.DISCONNECTED && (
        <Button
          size="sm"
          variant="outline" 
          onClick={onConnect}
          className="h-6 px-2"
        >
          <Wifi className="h-3 w-3" />
        </Button>
      )}

      {status === WebSocketStatus.CONNECTED && (
        <Button
          size="sm"
          variant="outline"
          onClick={onDisconnect}
          className="h-6 px-2"
        >
          <WifiOff className="h-3 w-3" />
        </Button>
      )}

      {/* Pipeline controls */}
      {status === WebSocketStatus.CONNECTED && (
        <div className="flex items-center gap-1">
          {pipelineRunning ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={onPausePipeline}
                  className="h-6 px-2"
                >
                  <Pause className="h-3 w-3" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>Pause pipeline</p>
              </TooltipContent>
            </Tooltip>
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={onResumePipeline}
                  className="h-6 px-2"
                >
                  <Play className="h-3 w-3" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>Resume pipeline</p>
              </TooltipContent>
            </Tooltip>
          )}
        </div>
      )}
    </div>
  );
}
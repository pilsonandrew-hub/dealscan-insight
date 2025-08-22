import { useState, useEffect } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Settings as SettingsIcon, Bell, Globe, Shield, Zap } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { toast } from "sonner";
import { FEDERAL_SITES, STATE_SITES } from "@/types/scraper";

interface SettingsData {
  enabled_sites: string[];
  scanning_mode: 'safe' | 'fast';
  scan_interval: number;
  max_risk_score: number;
  min_roi_percentage: number;
  preferred_states: string[];
  notifications_enabled: boolean;
  email_alerts: boolean;
}

const Settings = () => {
  const [settings, setSettings] = useState<SettingsData>({
    enabled_sites: ['GovDeals', 'PublicSurplus'],
    scanning_mode: 'safe',
    scan_interval: 10,
    max_risk_score: 50,
    min_roi_percentage: 15,
    preferred_states: ['CA', 'TX', 'FL'],
    notifications_enabled: true,
    email_alerts: false
  });
  
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const loadSettings = async () => {
    setLoading(true);
    try {
      // Load user preferences from database
      const { data, error } = await supabase
        .from('user_settings')
        .select('*')
        .maybeSingle();

      if (error && error.code !== 'PGRST116') {
        throw error;
      }

      if (data) {
        setSettings({
          enabled_sites: data.enabled_sites || ['GovDeals', 'PublicSurplus'],
          scanning_mode: data.scanning_mode || 'safe',
          scan_interval: data.scan_interval || 10,
          max_risk_score: data.max_risk_score || 50,
          min_roi_percentage: data.min_roi_percentage || 15,
          preferred_states: data.preferred_states || ['CA', 'TX', 'FL'],
          notifications_enabled: data.notifications_enabled ?? true,
          email_alerts: data.email_alerts ?? false
        });
      }
    } catch (error) {
      console.error('Error loading settings:', error);
      toast.error('Failed to load settings');
    } finally {
      setLoading(false);
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      const { error } = await supabase
        .from('user_settings')
        .upsert({
          user_id: (await supabase.auth.getUser()).data.user?.id,
          ...settings,
          updated_at: new Date().toISOString()
        });

      if (error) throw error;

      toast.success('Settings saved successfully');
    } catch (error) {
      console.error('Error saving settings:', error);
      toast.error('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const toggleSite = (site: string) => {
    setSettings(prev => ({
      ...prev,
      enabled_sites: prev.enabled_sites.includes(site)
        ? prev.enabled_sites.filter(s => s !== site)
        : [...prev.enabled_sites, site]
    }));
  };

  const toggleState = (state: string) => {
    setSettings(prev => ({
      ...prev,
      preferred_states: prev.preferred_states.includes(state)
        ? prev.preferred_states.filter(s => s !== state)
        : [...prev.preferred_states, state]
    }));
  };

  if (loading) {
    return (
      <div className="container py-8">
        <div className="animate-pulse space-y-6">
          <div className="h-8 bg-muted rounded w-1/4"></div>
          {[1, 2, 3].map(i => (
            <Card key={i}>
              <CardContent className="p-6">
                <div className="space-y-4">
                  <div className="h-4 bg-muted rounded w-1/3"></div>
                  <div className="h-10 bg-muted rounded"></div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="container py-8 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <SettingsIcon className="w-8 h-8" />
            Settings
          </h1>
          <p className="text-muted-foreground mt-2">
            Configure your DealerScope preferences and data sources
          </p>
        </div>
        
        <Button onClick={saveSettings} disabled={saving} size="lg">
          {saving ? 'Saving...' : 'Save Changes'}
        </Button>
      </div>

      {/* Data Sources */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Globe className="w-5 h-5" />
            Data Sources
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div>
            <Label className="text-base font-semibold">Federal Sites</Label>
            <p className="text-sm text-muted-foreground mb-3">
              Select government auction sites to monitor
            </p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {FEDERAL_SITES.map(site => (
                <div key={site} className="flex items-center space-x-2">
                  <Switch
                    id={site}
                    checked={settings.enabled_sites.includes(site)}
                    onCheckedChange={() => toggleSite(site)}
                  />
                  <Label htmlFor={site} className="text-sm">
                    {site}
                  </Label>
                </div>
              ))}
            </div>
          </div>

          <div>
            <Label className="text-base font-semibold">State/Municipal Sites</Label>
            <p className="text-sm text-muted-foreground mb-3">
              Regional auction sites for specific states
            </p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {STATE_SITES.map(site => (
                <div key={site} className="flex items-center space-x-2">
                  <Switch
                    id={site}
                    checked={settings.enabled_sites.includes(site)}
                    onCheckedChange={() => toggleSite(site)}
                  />
                  <Label htmlFor={site} className="text-sm">
                    {site}
                  </Label>
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Scanning Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap className="w-5 h-5" />
            Scanning Configuration
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <Label htmlFor="scanning-mode" className="text-base font-semibold">
                Scanning Mode
              </Label>
              <p className="text-sm text-muted-foreground mb-3">
                Safe mode: 1 page/minute, Fast mode: 5 pages/minute
              </p>
              <Select value={settings.scanning_mode} onValueChange={(value: 'safe' | 'fast') => 
                setSettings(prev => ({ ...prev, scanning_mode: value }))
              }>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="safe">
                    Safe Mode (Recommended)
                  </SelectItem>
                  <SelectItem value="fast">
                    Fast Mode (Higher risk)
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label htmlFor="scan-interval" className="text-base font-semibold">
                Scan Interval (minutes)
              </Label>
              <p className="text-sm text-muted-foreground mb-3">
                How often to check for new deals
              </p>
              <Input
                id="scan-interval"
                type="number"
                min="5"
                max="60"
                value={settings.scan_interval}
                onChange={(e) => setSettings(prev => ({ 
                  ...prev, 
                  scan_interval: parseInt(e.target.value) || 10 
                }))}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Deal Filters */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="w-5 h-5" />
            Deal Filters
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <Label htmlFor="max-risk" className="text-base font-semibold">
                Maximum Risk Score
              </Label>
              <p className="text-sm text-muted-foreground mb-3">
                Only show deals with risk score below this threshold
              </p>
              <Input
                id="max-risk"
                type="number"
                min="1"
                max="100"
                value={settings.max_risk_score}
                onChange={(e) => setSettings(prev => ({ 
                  ...prev, 
                  max_risk_score: parseInt(e.target.value) || 50 
                }))}
              />
            </div>

            <div>
              <Label htmlFor="min-roi" className="text-base font-semibold">
                Minimum ROI Percentage
              </Label>
              <p className="text-sm text-muted-foreground mb-3">
                Only show deals with ROI above this threshold
              </p>
              <Input
                id="min-roi"
                type="number"
                min="1"
                max="100"
                value={settings.min_roi_percentage}
                onChange={(e) => setSettings(prev => ({ 
                  ...prev, 
                  min_roi_percentage: parseInt(e.target.value) || 15 
                }))}
              />
            </div>
          </div>

          <div>
            <Label className="text-base font-semibold">Preferred States</Label>
            <p className="text-sm text-muted-foreground mb-3">
              Focus on vehicles in these states for better logistics
            </p>
            <div className="grid grid-cols-4 md:grid-cols-8 gap-2">
              {['CA', 'TX', 'FL', 'NY', 'PA', 'IL', 'OH', 'GA', 'NC', 'MI', 'NJ', 'VA', 'WA', 'AZ', 'MA', 'TN'].map(state => (
                <Badge
                  key={state}
                  variant={settings.preferred_states.includes(state) ? "default" : "outline"}
                  className="cursor-pointer justify-center"
                  onClick={() => toggleState(state)}
                >
                  {state}
                </Badge>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Notifications */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bell className="w-5 h-5" />
            Notifications
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <Label htmlFor="notifications" className="text-base font-semibold">
                In-App Notifications
              </Label>
              <p className="text-sm text-muted-foreground">
                Show red bubble and toast when new deals are found
              </p>
            </div>
            <Switch
              id="notifications"
              checked={settings.notifications_enabled}
              onCheckedChange={(checked) => setSettings(prev => ({ 
                ...prev, 
                notifications_enabled: checked 
              }))}
            />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <Label htmlFor="email-alerts" className="text-base font-semibold">
                Email Alerts
              </Label>
              <p className="text-sm text-muted-foreground">
                Send email notifications for high-value opportunities
              </p>
            </div>
            <Switch
              id="email-alerts"
              checked={settings.email_alerts}
              onCheckedChange={(checked) => setSettings(prev => ({ 
                ...prev, 
                email_alerts: checked 
              }))}
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default Settings;
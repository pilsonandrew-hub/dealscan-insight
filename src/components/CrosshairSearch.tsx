import React, { useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useToast } from "@/hooks/use-toast";
import { roverAPI } from "@/services/roverAPI";
import { api } from "@/services/api";
import { supabase } from "@/integrations/supabase/client";
import { Search, Target, Plus, X, Settings, Bell } from "lucide-react";
import { SniperButton } from "@/components/SniperButton";

interface CrosshairSearchProps {
  onResultsFound?: (results: any[]) => void;
}

interface SearchCriteria {
  make?: string;
  model?: string;
  yearMin?: number;
  yearMax?: number;
  priceMin?: number;
  priceMax?: number;
  mileageMax?: number;
  state?: string;
  bodyType?: string;
}

const MAKES = [
  "Toyota", "Honda", "Ford", "Chevrolet", "Nissan", "BMW", "Mercedes-Benz",
  "Audi", "Volkswagen", "Hyundai", "Kia", "Mazda", "Subaru", "Lexus"
];

const BODY_TYPES = [
  "Sedan", "SUV", "Truck", "Coupe", "Hatchback", "Convertible", "Wagon", "Van"
];

const US_STATES = [
  "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
  "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
  "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
  "VA", "WA", "WV", "WI", "WY"
];

export const CrosshairSearch: React.FC<CrosshairSearchProps> = ({ onResultsFound }) => {
  const [criteria, setCriteria] = useState<SearchCriteria>({});
  const [savedIntents, setSavedIntents] = useState<string[]>([]);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [results, setResults] = useState<any[]>([]);
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveSearchName, setSaveSearchName] = useState("");
  const [saveDosThreshold, setSaveDosThreshold] = useState("65");
  const [saveTelegramChatId, setSaveTelegramChatId] = useState("");
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  const updateCriteria = useCallback((key: keyof SearchCriteria, value: any) => {
    setCriteria(prev => ({ ...prev, [key]: value }));
  }, []);

  const clearCriteria = useCallback(() => {
    setCriteria({});
    setResults([]);
    setHasSearched(false);
  }, []);

  const executeSearch = useCallback(async () => {
    if (!criteria.make && !criteria.model && !criteria.yearMin) {
      toast({
        title: "Search requires criteria",
        description: "Please specify at least make, model, or year range.",
        variant: "destructive"
      });
      return;
    }

    setSearching(true);
    setHasSearched(true);
    try {
      const { data: searchResults, total } = await api.searchCrosshairOpportunities({
        make: criteria.make,
        model: criteria.model,
        yearMin: criteria.yearMin,
        yearMax: criteria.yearMax,
        state: criteria.state,
        minPrice: criteria.priceMin,
        maxPrice: criteria.priceMax,
        maxMileage: criteria.mileageMax,
        limit: 50,
      });
      // CrosshairSearch uses a plain object shape; map Opportunity → display shape
      const mapped = searchResults.map(o => ({
        id: o.id,
        year: o.year,
        make: o.make,
        model: o.model,
        price: o.current_bid,
        mileage: o.mileage,
        state: o.state,
        roi_percentage: o.roi ? o.roi * 100 : 0,
        dos_score: o.score,
      }));
      setResults(mapped);
      onResultsFound?.(mapped);

      toast({
        title: "Search completed",
        description: `Found ${total} matching opportunities.`
      });
    } catch (error) {
      toast({
        title: "Search failed",
        description: "Please try again later.",
        variant: "destructive"
      });
    } finally {
      setSearching(false);
    }
  }, [criteria, onResultsFound, toast]);

  const saveAsIntent = useCallback(async () => {
    if (!criteria.make && !criteria.model) {
      toast({
        title: "Cannot save intent",
        description: "Please specify at least make or model.",
        variant: "destructive"
      });
      return;
    }

    const title = generateIntentTitle(criteria);
    try {
      await roverAPI.saveIntent(criteria, title);
      setSavedIntents(prev => [...prev, title]);
      toast({
        title: "Intent saved",
        description: `"${title}" will be monitored for new matches.`
      });
    } catch (error) {
      toast({
        title: "Failed to save intent",
        description: "Please try again later.",
        variant: "destructive"
      });
    }
  }, [criteria, toast]);

  const openSaveModal = useCallback(() => {
    if (!criteria.make && !criteria.model && !criteria.yearMin) {
      toast({
        title: "Add criteria first",
        description: "Set at least one filter before saving a search.",
        variant: "destructive",
      });
      return;
    }
    setSaveSearchName(generateIntentTitle(criteria));
    setSaveModalOpen(true);
  }, [criteria, toast]);

  const confirmSaveSearch = useCallback(async () => {
    const name = saveSearchName.trim();
    if (!name) {
      toast({ title: "Name required", variant: "destructive" });
      return;
    }
    setSaving(true);
    try {
      const apiUrl = import.meta.env.VITE_API_URL || "https://dealscan-insight-production.up.railway.app";
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      const resp = await fetch(`${apiUrl}/api/saved-searches`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify({
          name,
          filters: criteria,
          dos_threshold: parseInt(saveDosThreshold) || 65,
          telegram_chat_id: saveTelegramChatId.trim() || undefined,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      toast({ title: "Search saved", description: `"${name}" will alert you when new matches arrive.` });
      setSaveModalOpen(false);
      setSaveSearchName("");
      setSaveTelegramChatId("");
    } catch (err) {
      toast({ title: "Failed to save search", description: "Please try again.", variant: "destructive" });
    } finally {
      setSaving(false);
    }
  }, [saveSearchName, saveDosThreshold, saveTelegramChatId, criteria, toast]);

  return (
    <div className="space-y-6">
      {/* Save Search Modal */}
      {saveModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl p-6 w-full max-w-md space-y-4 border border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">Save Search + Alerts</h3>
              <button onClick={() => setSaveModalOpen(false)} className="text-gray-400 hover:text-gray-600">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <Label htmlFor="ss-name">Search name</Label>
                <Input
                  id="ss-name"
                  value={saveSearchName}
                  onChange={e => setSaveSearchName(e.target.value)}
                  placeholder="e.g. Ford F-150 TX deals"
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="ss-threshold">Min DOS score to alert</Label>
                <Input
                  id="ss-threshold"
                  type="number"
                  min="0"
                  max="100"
                  value={saveDosThreshold}
                  onChange={e => setSaveDosThreshold(e.target.value)}
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="ss-telegram">Telegram chat ID (optional)</Label>
                <Input
                  id="ss-telegram"
                  value={saveTelegramChatId}
                  onChange={e => setSaveTelegramChatId(e.target.value)}
                  placeholder="e.g. -1001234567890"
                  className="mt-1"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Get your chat ID from @userinfobot on Telegram.
                </p>
              </div>
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setSaveModalOpen(false)}>
                Cancel
              </Button>
              <Button className="flex-1" onClick={confirmSaveSearch} disabled={saving}>
                {saving ? "Saving..." : "Save Search"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Search Form */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Target className="h-5 w-5 text-primary" />
                Crosshair Search
              </CardTitle>
              <CardDescription>
                Precision targeting for specific vehicle opportunities
              </CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={clearCriteria}>
              <X className="h-4 w-4 mr-1" />
              Clear
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Basic Criteria */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label htmlFor="make">Make</Label>
              <Select value={criteria.make || ""} onValueChange={(v) => updateCriteria("make", v)}>
                <SelectTrigger>
                  <SelectValue placeholder="Any make" />
                </SelectTrigger>
                <SelectContent>
                  {MAKES.map(make => (
                    <SelectItem key={make} value={make}>{make}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="model">Model</Label>
              <Input
                id="model"
                value={criteria.model || ""}
                onChange={(e) => updateCriteria("model", e.target.value)}
                placeholder="e.g., Camry, F-150"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="bodyType">Body Type</Label>
              <Select value={criteria.bodyType || ""} onValueChange={(v) => updateCriteria("bodyType", v)}>
                <SelectTrigger>
                  <SelectValue placeholder="Any type" />
                </SelectTrigger>
                <SelectContent>
                  {BODY_TYPES.map(type => (
                    <SelectItem key={type} value={type}>{type}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Year Range */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="yearMin">Year From</Label>
              <Input
                id="yearMin"
                type="number"
                value={criteria.yearMin || ""}
                onChange={(e) => updateCriteria("yearMin", parseInt(e.target.value) || undefined)}
                placeholder="2010"
                min="1990"
                max="2026"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="yearMax">Year To</Label>
              <Input
                id="yearMax"
                type="number"
                value={criteria.yearMax || ""}
                onChange={(e) => updateCriteria("yearMax", parseInt(e.target.value) || undefined)}
                placeholder="2024"
                min="1990"
                max="2026"
              />
            </div>
          </div>

          {/* Price and Mileage */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label htmlFor="priceMin">Min Price ($)</Label>
              <Input
                id="priceMin"
                type="number"
                value={criteria.priceMin || ""}
                onChange={(e) => updateCriteria("priceMin", parseInt(e.target.value) || undefined)}
                placeholder="5000"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="priceMax">Max Price ($)</Label>
              <Input
                id="priceMax"
                type="number"
                value={criteria.priceMax || ""}
                onChange={(e) => updateCriteria("priceMax", parseInt(e.target.value) || undefined)}
                placeholder="50000"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="mileageMax">Max Mileage</Label>
              <Input
                id="mileageMax"
                type="number"
                value={criteria.mileageMax || ""}
                onChange={(e) => updateCriteria("mileageMax", parseInt(e.target.value) || undefined)}
                placeholder="100000"
              />
            </div>
          </div>

          {/* State */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="state">State</Label>
              <Select value={criteria.state || ""} onValueChange={(v) => updateCriteria("state", v)}>
                <SelectTrigger>
                  <SelectValue placeholder="Any state" />
                </SelectTrigger>
                <SelectContent>
                  {US_STATES.map(state => (
                    <SelectItem key={state} value={state}>{state}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Actions */}
          <div className="flex flex-wrap gap-2 pt-4">
            <Button onClick={executeSearch} disabled={searching} className="flex-1 min-w-[200px]">
              <Search className="h-4 w-4 mr-2" />
              {searching ? "Searching..." : "Execute Search"}
            </Button>
            <Button variant="outline" onClick={saveAsIntent} disabled={!criteria.make && !criteria.model}>
              <Plus className="h-4 w-4 mr-2" />
              Save as Intent
            </Button>
            <Button variant="outline" onClick={openSaveModal}>
              <Bell className="h-4 w-4 mr-2" />
              Save Search
            </Button>
          </div>

          {/* Active Criteria Display */}
          {Object.keys(criteria).length > 0 && (
            <div className="pt-4 border-t">
              <h4 className="text-sm font-medium mb-2">Active Criteria:</h4>
              <div className="flex flex-wrap gap-2">
                {Object.entries(criteria).map(([key, value]) => 
                  value && (
                    <Badge key={key} variant="secondary">
                      {key}: {value}
                    </Badge>
                  )
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Results */}
      {results.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Search Results ({results.length})</CardTitle>
            <CardDescription>
              Sorted by DOS score — {[criteria.make, criteria.model, criteria.yearMin ? `${criteria.yearMin}+` : null, criteria.state].filter(Boolean).join(', ') || 'all criteria'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {results.map((result, index) => (
                <div key={result.id || index} className="p-3 border rounded-lg">
                  <div className="flex justify-between items-start">
                    <div>
                      <h4 className="font-medium">
                        {result.year} {result.make} {result.model}
                      </h4>
                      <p className="text-sm text-muted-foreground">
                        {result.mileage?.toLocaleString()} miles • ${result.price?.toLocaleString()}
                      </p>
                      {result.state && (
                        <p className="text-xs text-muted-foreground">{result.state}</p>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      {result.dos_score != null && (
                        <Badge variant="default" className="text-xs">
                          DOS {Math.round(result.dos_score)}
                        </Badge>
                      )}
                      <Badge variant="outline">
                        ROI: {result.roi_percentage ? result.roi_percentage.toFixed(1) : 0}%
                      </Badge>
                    </div>
                  </div>
                  <div className="flex gap-2 mt-3">
                    {result.id && (
                      <Button variant="outline" size="sm" asChild>
                        <Link to={`/deal/${result.id}`}>View Deal</Link>
                      </Button>
                    )}
                    <SniperButton
                      opportunity={{
                        id: result.id,
                        year: result.year,
                        make: result.make,
                        model: result.model,
                        current_bid: result.price,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* No Results Message */}
      {!searching && hasSearched && results.length === 0 && (
        <Alert>
          <Settings className="h-4 w-4" />
          <AlertDescription>
            No matches found. Try broadening your search criteria or save as an intent to monitor for future opportunities.
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
};

// Helper functions
function generateIntentTitle(criteria: SearchCriteria): string {
  const parts = [];
  if (criteria.make) parts.push(criteria.make);
  if (criteria.model) parts.push(criteria.model);
  if (criteria.yearMin || criteria.yearMax) {
    const yearRange = `${criteria.yearMin || ""}-${criteria.yearMax || ""}`.replace(/^-/, "≤").replace(/-$/, "+");
    parts.push(yearRange);
  }
  return parts.join(" ") || "Custom Search";
}


export default CrosshairSearch;
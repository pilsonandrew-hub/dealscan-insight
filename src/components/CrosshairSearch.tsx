import React, { useState, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useToast } from "@/hooks/use-toast";
import { roverAPI } from "@/services/roverAPI";
import { Search, Target, Plus, X, Settings } from "lucide-react";

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
  const [results, setResults] = useState<any[]>([]);
  const { toast } = useToast();

  const updateCriteria = useCallback((key: keyof SearchCriteria, value: any) => {
    setCriteria(prev => ({ ...prev, [key]: value }));
  }, []);

  const clearCriteria = useCallback(() => {
    setCriteria({});
    setResults([]);
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
    try {
      // Simulate crosshair search - in real implementation, this would call specific search API
      const searchResults = await simulateCrosshairSearch(criteria);
      setResults(searchResults);
      onResultsFound?.(searchResults);
      
      toast({
        title: "Search completed",
        description: `Found ${searchResults.length} matching opportunities.`
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

  return (
    <div className="space-y-6">
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
                max="2024"
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
                max="2024"
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
              Opportunities matching your criteria
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {results.map((result, index) => (
                <div key={index} className="p-3 border rounded-lg">
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
                    <Badge variant="outline">
                      ROI: {result.roi_percentage || 0}%
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* No Results Message */}
      {!searching && results.length === 0 && Object.keys(criteria).length > 0 && (
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

async function simulateCrosshairSearch(criteria: SearchCriteria): Promise<any[]> {
  // Simulate API delay
  await new Promise(resolve => setTimeout(resolve, 1000));
  
  // Mock results based on criteria
  const mockResults = [
    { year: 2020, make: "Toyota", model: "Camry", price: 18500, mileage: 45000, state: "CA", roi_percentage: 15 },
    { year: 2019, make: "Honda", model: "Accord", price: 17200, mileage: 52000, state: "TX", roi_percentage: 12 },
    { year: 2021, make: "Ford", model: "F-150", price: 32000, mileage: 38000, state: "FL", roi_percentage: 18 }
  ];
  
  return mockResults.filter(result => {
    if (criteria.make && result.make !== criteria.make) return false;
    if (criteria.model && !result.model.toLowerCase().includes(criteria.model.toLowerCase())) return false;
    if (criteria.yearMin && result.year < criteria.yearMin) return false;
    if (criteria.yearMax && result.year > criteria.yearMax) return false;
    if (criteria.priceMin && result.price < criteria.priceMin) return false;
    if (criteria.priceMax && result.price > criteria.priceMax) return false;
    if (criteria.mileageMax && result.mileage > criteria.mileageMax) return false;
    if (criteria.state && result.state !== criteria.state) return false;
    return true;
  });
}

export default CrosshairSearch;
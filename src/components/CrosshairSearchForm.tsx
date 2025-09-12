import { useState } from "react";
import { useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Crosshair, Search, Save, AlertCircle } from "lucide-react";
import { CanonicalQuery, SearchOptions } from "@/types/crosshair";

interface CrosshairSearchFormProps {
  onSearch: (query: CanonicalQuery, options: SearchOptions) => void;
  onSaveIntent: (query: CanonicalQuery, options: SearchOptions, title: string) => void;
  isLoading?: boolean;
}

interface FormData extends CanonicalQuery, SearchOptions {
  title: string;
  action?: 'search' | 'save';
}

export const CrosshairSearchForm = ({ onSearch, onSaveIntent, isLoading }: CrosshairSearchFormProps) => {
  const { register, handleSubmit, watch, setValue, formState: { errors } } = useForm<FormData>();
  const [selectedTitleStatuses, setSelectedTitleStatuses] = useState<string[]>(['clean']);
  const [selectedConditions, setSelectedConditions] = useState<string[]>(['running']);
  const [selectedSites, setSelectedSites] = useState<string[]>(['govdeals', 'publicsurplus', 'gsa']);

  const titleStatuses = [
    { value: 'clean', label: 'Clean Title' },
    { value: 'rebuilt', label: 'Rebuilt' },
    { value: 'salvage', label: 'Salvage' },
    { value: 'flood', label: 'Flood' },
    { value: 'lemon', label: 'Lemon' }
  ];

  const conditions = [
    { value: 'running', label: 'Running' },
    { value: 'non_running', label: 'Non-Running' },
    { value: 'parts', label: 'Parts Only' },
    { value: 'excellent', label: 'Excellent' },
    { value: 'good', label: 'Good' },
    { value: 'fair', label: 'Fair' },
    { value: 'poor', label: 'Poor' }
  ];

  const sites = [
    { value: 'govdeals', label: 'GovDeals' },
    { value: 'publicsurplus', label: 'PublicSurplus' },
    { value: 'gsa', label: 'GSA Auctions' },
    { value: 'manheim', label: 'Manheim (API)' },
    { value: 'state_*', label: 'All State Sites' }
  ];

  const onSubmit = (data: any) => {
    const query: CanonicalQuery = {
      make: data.make || undefined,
      model: data.model || undefined,
      year_min: data.year_min ? parseInt(data.year_min) : undefined,
      year_max: data.year_max ? parseInt(data.year_max) : undefined,
      mileage_max: data.mileage_max ? parseInt(data.mileage_max) : undefined,
      price_max: data.price_max ? parseFloat(data.price_max) : undefined,
      locations: data.locations?.split(',').map((l: string) => l.trim()).filter(Boolean) || ['US'],
      title_status: selectedTitleStatuses as any,
      condition: selectedConditions as any,
      fuel: data.fuel || undefined,
      body_type: data.body_type ? [data.body_type] : undefined,
    };

    const options: SearchOptions = {
      expand_aliases: data.expand_aliases ?? true,
      nearest_viable_year: data.nearest_viable_year ?? true,
      notify_on_first_match: data.notify_on_first_match ?? false,
      rescan_interval: data.rescan_interval || '6h',
      sites: selectedSites,
      max_pages_per_site: data.max_pages_per_site ? parseInt(data.max_pages_per_site) : 10,
      user_priority: data.user_priority || 'medium',
    };

    if (data.action === 'save') {
      onSaveIntent(query, options, data.title || `${query.make} ${query.model} Search`);
    } else {
      onSearch(query, options);
    }
  };

  const toggleArraySelection = (value: string, currentArray: string[], setter: (arr: string[]) => void) => {
    if (currentArray.includes(value)) {
      setter(currentArray.filter(item => item !== value));
    } else {
      setter([...currentArray, value]);
    }
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Crosshair className="h-5 w-5 text-primary" />
          Crosshair: Directed Retrieval
          <Badge variant="secondary" className="ml-2">Premium</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
          {/* Vehicle Criteria */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label htmlFor="make">Make</Label>
              <Input
                id="make"
                {...register("make")}
                placeholder="e.g., Tesla, Ford, BMW"
                className="w-full"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="model">Model</Label>
              <Input
                id="model"
                {...register("model")}
                placeholder="e.g., Cybertruck, F-150"
                className="w-full"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="fuel">Fuel Type</Label>
              <Select onValueChange={(value) => setValue('fuel', [value] as any)}>
                <SelectTrigger>
                  <SelectValue placeholder="Any fuel type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="gasoline">Gasoline</SelectItem>
                  <SelectItem value="diesel">Diesel</SelectItem>
                  <SelectItem value="electric">Electric</SelectItem>
                  <SelectItem value="hybrid">Hybrid</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Year Range */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="year_min">Year From</Label>
              <Input
                id="year_min"
                type="number"
                {...register("year_min")}
                placeholder="2020"
                min="1990"
                max="2025"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="year_max">Year To</Label>
              <Input
                id="year_max"
                type="number"
                {...register("year_max")}
                placeholder="2024"
                min="1990"
                max="2025"
              />
            </div>
          </div>

          {/* Price and Mileage */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="price_max">Max Price ($)</Label>
              <Input
                id="price_max"
                type="number"
                {...register("price_max")}
                placeholder="120000"
                min="0"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="mileage_max">Max Mileage</Label>
              <Input
                id="mileage_max"
                type="number"
                {...register("mileage_max")}
                placeholder="80000"
                min="0"
              />
            </div>
          </div>

          {/* Title Status */}
          <div className="space-y-3">
            <Label>Title Status</Label>
            <div className="flex flex-wrap gap-2">
              {titleStatuses.map((status) => (
                <Badge
                  key={status.value}
                  variant={selectedTitleStatuses.includes(status.value) ? "default" : "outline"}
                  className="cursor-pointer"
                  onClick={() => toggleArraySelection(status.value, selectedTitleStatuses, setSelectedTitleStatuses)}
                >
                  {status.label}
                </Badge>
              ))}
            </div>
          </div>

          {/* Condition */}
          <div className="space-y-3">
            <Label>Condition</Label>
            <div className="flex flex-wrap gap-2">
              {conditions.map((condition) => (
                <Badge
                  key={condition.value}
                  variant={selectedConditions.includes(condition.value) ? "default" : "outline"}
                  className="cursor-pointer"
                  onClick={() => toggleArraySelection(condition.value, selectedConditions, setSelectedConditions)}
                >
                  {condition.label}
                </Badge>
              ))}
            </div>
          </div>

          {/* Sources */}
          <div className="space-y-3">
            <Label>Target Sources</Label>
            <div className="flex flex-wrap gap-2">
              {sites.map((site) => (
                <Badge
                  key={site.value}
                  variant={selectedSites.includes(site.value) ? "default" : "outline"}
                  className="cursor-pointer"
                  onClick={() => toggleArraySelection(site.value, selectedSites, setSelectedSites)}
                >
                  {site.label}
                </Badge>
              ))}
            </div>
          </div>

          {/* Advanced Options */}
          <div className="space-y-4 border-t pt-4">
            <h4 className="text-sm font-medium">Advanced Options</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="expand_aliases"
                  {...register("expand_aliases")}
                  defaultChecked
                />
                <Label htmlFor="expand_aliases" className="text-sm">
                  Expand model aliases
                </Label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="nearest_viable_year"
                  {...register("nearest_viable_year")}
                  defaultChecked
                />
                <Label htmlFor="nearest_viable_year" className="text-sm">
                  Find nearest viable years
                </Label>
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="max_pages_per_site">Max Pages per Site</Label>
                <Input
                  id="max_pages_per_site"
                  type="number"
                  {...register("max_pages_per_site")}
                  placeholder="10"
                  min="1"
                  max="50"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="user_priority">Priority</Label>
                <Select onValueChange={(value) => setValue('user_priority', value as any)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Medium" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="low">Low</SelectItem>
                    <SelectItem value="medium">Medium</SelectItem>
                    <SelectItem value="high">High</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          {/* Save Intent Options */}
          <div className="space-y-4 border-t pt-4">
            <h4 className="text-sm font-medium">Save & Monitor</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="title">Search Name (for saving)</Label>
                <Input
                  id="title"
                  {...register("title")}
                  placeholder="My Tesla Cybertruck Search"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="rescan_interval">Rescan Interval</Label>
                <Select onValueChange={(value) => setValue('rescan_interval', value as any)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Every 6 hours" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1h">Every hour</SelectItem>
                    <SelectItem value="6h">Every 6 hours</SelectItem>
                    <SelectItem value="12h">Every 12 hours</SelectItem>
                    <SelectItem value="daily">Daily</SelectItem>
                    <SelectItem value="weekly">Weekly</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="flex items-center space-x-2">
              <Checkbox
                id="notify_on_first_match"
                {...register("notify_on_first_match")}
              />
              <Label htmlFor="notify_on_first_match" className="text-sm">
                Notify me immediately when first match is found
              </Label>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex gap-4 pt-4">
            <Button
              type="submit"
              disabled={isLoading}
              className="flex-1"
              onClick={() => setValue('action', 'search')}
            >
              <Search className="w-4 h-4 mr-2" />
              {isLoading ? 'Searching...' : 'Search Now'}
            </Button>
            <Button
              type="submit"
              variant="outline"
              disabled={isLoading}
              onClick={() => setValue('action', 'save')}
            >
              <Save className="w-4 h-4 mr-2" />
              Save Intent
            </Button>
          </div>

          {/* Info Banner */}
          <div className="flex items-start gap-2 p-3 bg-muted rounded-md">
            <AlertCircle className="w-4 h-4 text-muted-foreground mt-0.5 flex-shrink-0" />
            <div className="text-sm text-muted-foreground">
              <p><strong>Crosshair</strong> uses dual-mode ingestion: API sources (preferred) + scraping (fallback/augment).</p>
              <p className="mt-1">Impossible requests (e.g., 2020 Cybertruck) will auto-pivot to viable years with explanations.</p>
            </div>
          </div>
        </form>
      </CardContent>
    </Card>
  );
};
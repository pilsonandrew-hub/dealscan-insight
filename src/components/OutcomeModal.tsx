import React, { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import api from "@/services/api";

type OutcomeValue = "won" | "lost" | "passed";

interface OutcomeModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  opportunity: {
    id: string;
    year?: number;
    make?: string;
    model?: string;
    current_bid?: number;
  };
  onSaved?: () => void;
}

export function OutcomeModal({ open, onOpenChange, opportunity, onSaved }: OutcomeModalProps) {
  const { toast } = useToast();
  const [outcome, setOutcome] = useState<OutcomeValue>("won");
  const [soldPrice, setSoldPrice] = useState<string>("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setOutcome("won");
    setSoldPrice(opportunity.current_bid != null ? String(opportunity.current_bid) : "");
  }, [open, opportunity.current_bid]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!opportunity.id) return;

    if (outcome === "won" && !soldPrice.trim()) {
      toast({
        title: "Sold price required",
        description: "Enter the final sale price for a won outcome.",
        variant: "destructive",
      });
      return;
    }

    setSaving(true);
    try {
      await api.recordOutcome({
        opportunity_id: opportunity.id,
        outcome,
        sold_price: outcome === "won" ? Number(soldPrice) : undefined,
      });
      toast({
        title: "Outcome recorded",
        description: `${opportunity.year ?? ""} ${opportunity.make ?? ""} ${opportunity.model ?? ""}`.trim(),
      });
      onSaved?.();
      onOpenChange(false);
    } catch (error) {
      console.error("Failed to record outcome:", error);
      toast({
        title: "Unable to record outcome",
        description: "Please try again.",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Record Outcome</DialogTitle>
          <DialogDescription>
            {opportunity.year ?? ""} {opportunity.make ?? ""} {opportunity.model ?? ""}{" "}
            {opportunity.current_bid != null ? `current bid ${opportunity.current_bid.toLocaleString()}` : ""}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="outcome">Outcome</Label>
            <Select value={outcome} onValueChange={(value) => setOutcome(value as OutcomeValue)}>
              <SelectTrigger id="outcome">
                <SelectValue placeholder="Select outcome" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="won">Won</SelectItem>
                <SelectItem value="lost">Lost</SelectItem>
                <SelectItem value="passed">Passed</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {outcome === "won" && (
            <div className="space-y-2">
              <Label htmlFor="sold_price">Sold Price</Label>
              <Input
                id="sold_price"
                type="number"
                min="0"
                step="1"
                placeholder="Enter sold price"
                value={soldPrice}
                onChange={(event) => setSoldPrice(event.target.value)}
              />
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? "Saving..." : "Submit"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default OutcomeModal;

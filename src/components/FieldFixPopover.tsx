import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Badge } from '@/components/ui/badge';
import { Edit3, Check, X } from 'lucide-react';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';

interface FieldFixPopoverProps {
  url: string;
  clusterId: string;
  field: string;
  oldValue: string;
  cssPath?: string;
  onSave?: (newValue: string) => void;
}

/**
 * Human-in-the-loop field correction popover
 * Allows users to quickly fix extraction errors and contribute to model training
 */
export function FieldFixPopover({
  url,
  clusterId,
  field,
  oldValue,
  cssPath,
  onSave
}: FieldFixPopoverProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [newValue, setNewValue] = useState(oldValue);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSave = async () => {
    if (newValue === oldValue) {
      setIsOpen(false);
      return;
    }

    setIsSubmitting(true);
    
    try {
      // Store the correction in the labels table
      const { error } = await supabase
        .from('labels')
        .insert({
          url,
          cluster_id: clusterId,
          field,
          old_value: oldValue,
          new_value: newValue,
          css_path: cssPath,
          user_id: (await supabase.auth.getUser()).data.user?.id
        });

      if (error) throw error;

      toast.success('Field correction saved', {
        description: 'Your correction will help improve extraction accuracy'
      });

      onSave?.(newValue);
      setIsOpen(false);
    } catch (error) {
      console.error('Failed to save field correction:', error);
      toast.error('Failed to save correction', {
        description: 'Please try again'
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    setNewValue(oldValue);
    setIsOpen(false);
  };

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0 hover:bg-secondary"
          title={`Fix ${field} value`}
        >
          <Edit3 className="h-3 w-3" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80">
        <div className="space-y-4">
          <div>
            <h4 className="font-medium">Fix Field Value</h4>
            <p className="text-sm text-muted-foreground">
              Help improve extraction accuracy by correcting this value
            </p>
          </div>
          
          <div className="space-y-2">
            <div>
              <Label className="text-xs text-muted-foreground">Field</Label>
              <Badge variant="secondary" className="ml-2">
                {field}
              </Badge>
            </div>
            
            <div>
              <Label className="text-xs text-muted-foreground">Original</Label>
              <div className="p-2 bg-muted rounded text-sm font-mono">
                {oldValue || '(empty)'}
              </div>
            </div>
            
            <div>
              <Label htmlFor="new-value">Corrected Value</Label>
              <Input
                id="new-value"
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder="Enter correct value..."
                className="mt-1"
              />
            </div>
          </div>

          <div className="flex justify-end space-x-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleCancel}
              disabled={isSubmitting}
            >
              <X className="h-3 w-3 mr-1" />
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={isSubmitting || newValue === oldValue}
            >
              <Check className="h-3 w-3 mr-1" />
              {isSubmitting ? 'Saving...' : 'Save Fix'}
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

export default FieldFixPopover;
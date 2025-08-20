import { useState, useCallback } from "react";
import { Upload, FileSpreadsheet, CheckCircle, AlertCircle, X } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";

interface UploadFile {
  id: string;
  name: string;
  size: number;
  type: string;
  status: "pending" | "processing" | "success" | "error";
  progress: number;
  records?: number;
  error?: string;
}

export const UploadInterface = () => {
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const { toast } = useToast();

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const validateFile = (file: File): string | null => {
    const maxSize = 50 * 1024 * 1024; // 50MB
    const allowedExtensions = ['.csv', '.xlsx', '.xls'];
    const allowedMimeTypes = [
      'text/csv',
      'application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    ];

    if (file.size > maxSize) {
      return `File size exceeds 50MB limit (${(file.size / 1024 / 1024).toFixed(1)}MB)`;
    }

    const extension = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!allowedExtensions.includes(extension)) {
      return `File type not supported. Please upload CSV or Excel files only.`;
    }

    if (!allowedMimeTypes.includes(file.type) && file.type !== '') {
      return `Invalid file type. Please upload CSV or Excel files only.`;
    }

    return null;
  };

  const processFile = async (file: File): Promise<void> => {
    const fileId = Math.random().toString(36).substr(2, 9);
    const uploadFile: UploadFile = {
      id: fileId,
      name: file.name,
      size: file.size,
      type: file.type,
      status: "processing",
      progress: 0
    };

    setFiles(prev => [...prev, uploadFile]);

    // Simulate processing
    const progressInterval = setInterval(() => {
      setFiles(prev => prev.map(f => 
        f.id === fileId 
          ? { ...f, progress: Math.min(f.progress + Math.random() * 30, 95) }
          : f
      ));
    }, 300);

    try {
      // Simulate API processing delay
      await new Promise(resolve => setTimeout(resolve, 2000 + Math.random() * 2000));

      // Simulate random success/failure
      const isSuccess = Math.random() > 0.2; // 80% success rate

      clearInterval(progressInterval);

      if (isSuccess) {
        const records = Math.floor(Math.random() * 5000) + 500;
        setFiles(prev => prev.map(f => 
          f.id === fileId 
            ? { ...f, status: "success", progress: 100, records }
            : f
        ));
        
        toast({
          title: "Upload Successful",
          description: `Processed ${records.toLocaleString()} records from ${file.name}`,
        });
      } else {
        setFiles(prev => prev.map(f => 
          f.id === fileId 
            ? { ...f, status: "error", progress: 0, error: "Failed to process file. Please check format and try again." }
            : f
        ));
        
        toast({
          title: "Upload Failed",
          description: `Failed to process ${file.name}. Please check the file format.`,
          variant: "destructive"
        });
      }
    } catch (error) {
      clearInterval(progressInterval);
      setFiles(prev => prev.map(f => 
        f.id === fileId 
          ? { ...f, status: "error", progress: 0, error: "Network error occurred." }
          : f
      ));
    }
  };

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);

    const droppedFiles = Array.from(e.dataTransfer.files);
    
    for (const file of droppedFiles) {
      const error = validateFile(file);
      if (error) {
        toast({
          title: "File Validation Error",
          description: error,
          variant: "destructive"
        });
        continue;
      }
      
      await processFile(file);
    }
  }, [toast]);

  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files || []);
    
    for (const file of selectedFiles) {
      const error = validateFile(file);
      if (error) {
        toast({
          title: "File Validation Error",
          description: error,
          variant: "destructive"
        });
        continue;
      }
      
      await processFile(file);
    }
    
    // Clear input
    e.target.value = '';
  }, [toast]);

  const removeFile = (fileId: string) => {
    setFiles(prev => prev.filter(f => f.id !== fileId));
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "success": return <CheckCircle className="h-4 w-4 text-success" />;
      case "error": return <AlertCircle className="h-4 w-4 text-destructive" />;
      default: return <FileSpreadsheet className="h-4 w-4 text-muted-foreground" />;
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground">Upload Sales Data</h2>
        <p className="text-muted-foreground">Upload CSV or Excel files with dealer sales data for market analysis</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Upload Files</CardTitle>
        </CardHeader>
        <CardContent>
          <div
            className={`
              border-2 border-dashed rounded-lg p-8 text-center transition-colors
              ${isDragOver ? 'border-primary bg-primary/5' : 'border-muted'}
              hover:border-primary hover:bg-primary/5
            `}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <Upload className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold mb-2">Drop files here or click to browse</h3>
            <p className="text-muted-foreground mb-4">
              Support for CSV and Excel files up to 50MB
            </p>
            <input
              type="file"
              multiple
              accept=".csv,.xlsx,.xls"
              onChange={handleFileSelect}
              className="hidden"
              id="file-upload"
            />
            <Button asChild>
              <label htmlFor="file-upload" className="cursor-pointer">
                Select Files
              </label>
            </Button>
          </div>
        </CardContent>
      </Card>

      {files.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Upload Queue</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {files.map((file) => (
                <div key={file.id} className="flex items-center space-x-4 p-4 border rounded-lg">
                  {getStatusIcon(file.status)}
                  
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <p className="text-sm font-medium truncate">{file.name}</p>
                      <div className="flex items-center space-x-2">
                        {file.status === "success" && file.records && (
                          <Badge variant="secondary">
                            {file.records.toLocaleString()} records
                          </Badge>
                        )}
                        <Badge 
                          variant={file.status === "success" ? "default" : file.status === "error" ? "destructive" : "secondary"}
                        >
                          {file.status}
                        </Badge>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => removeFile(file.id)}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                    
                    <p className="text-xs text-muted-foreground mb-2">
                      {(file.size / 1024 / 1024).toFixed(1)} MB
                    </p>
                    
                    {file.status === "processing" && (
                      <Progress value={file.progress} className="h-2" />
                    )}
                    
                    {file.error && (
                      <p className="text-xs text-destructive mt-1">{file.error}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>File Requirements</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li>• Supported formats: CSV, Excel (.xlsx, .xls)</li>
            <li>• Maximum file size: 50MB</li>
            <li>• Required columns: Year, Make, Model, Sale Price, Sale Date</li>
            <li>• Optional columns: Mileage, Condition, Location</li>
            <li>• No formulas or macros allowed in Excel files</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
};
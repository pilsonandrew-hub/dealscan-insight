import { useState, useCallback } from "react";
import { Upload, FileSpreadsheet, CheckCircle, AlertCircle, X, Shield } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { validateCSVSecurity, detectDangerousFormulas } from "@/utils/csv-security";
import { VINValidator } from "@/utils/vin-validator";
import { performanceMonitor } from "@/utils/performance-monitor";
import { rateLimiter } from "@/utils/rate-limiter";
import { auditLogger } from "@/utils/audit-logger";
import { dataValidator } from "@/utils/data-validator";
import { batchUtils } from "@/utils/batch-processor";
import { settings } from "@/config/settings";
import apiService from "@/services/api";

interface UploadFile {
  id: string;
  name: string;
  size: number;
  type: string;
  status: "pending" | "processing" | "validating" | "success" | "error";
  progress: number;
  records?: number;
  validRecords?: number;
  warnings?: number;
  error?: string;
  validationReport?: any;
}

interface UploadInterfaceProps {
  onUploadSuccess?: (result: any) => void;
}

export const UploadInterface = ({ onUploadSuccess }: UploadInterfaceProps = {}) => {
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

  // Enhanced security check with performance monitoring and audit logging
  const performSecurityCheck = async (file: File): Promise<{ 
    isSecure: boolean; 
    issues: string[]; 
    riskLevel: 'low' | 'medium' | 'high' 
  }> => {
    const timer = performanceMonitor.startTimer('file_security_check');
    
    try {
      // Rate limiting for security checks
      const rateLimitKey = `security_check_${Date.now()}`;
      if (!rateLimiter.isAllowed(rateLimitKey, { maxRequests: 10, windowMs: 60000 })) {
        auditLogger.log('security_check_rate_limited', 'system', 'warning', { filename: file.name });
        throw new Error('Security check rate limit exceeded. Please wait before uploading more files.');
      }

      // Use enhanced security validation
      const securityResult = validateCSVSecurity(file);
      
      // Log security check
      auditLogger.log(
        'file_security_check',
        'upload',
        securityResult.isSecure ? 'info' : 'warning',
        {
          filename: file.name,
          fileSize: file.size,
          riskLevel: securityResult.riskLevel,
          issuesFound: securityResult.issues.length
        }
      );
      
      // Additional content checks for CSV files
      if (file.name.toLowerCase().endsWith('.csv')) {
        try {
          const content = await file.text();
          const dangerous = detectDangerousFormulas(content);
          if (dangerous.length > 0) {
            securityResult.issues.push(...dangerous.slice(0, 3));
            securityResult.riskLevel = 'high';
            
            auditLogger.log(
              'dangerous_formulas_detected',
              'upload',
              'error',
              {
                filename: file.name,
                formulaCount: dangerous.length,
                samples: dangerous.slice(0, 2)
              }
            );
          }
        } catch (error) {
          console.error('Error reading file for security check:', error);
          auditLogger.logError(error as Error, 'file_security_check');
          securityResult.issues.push('Unable to validate file content');
          securityResult.riskLevel = 'medium';
        }
      }
      
      timer.end(securityResult.isSecure);
      
      return {
        isSecure: securityResult.isSecure && securityResult.issues.length === 0,
        issues: securityResult.issues,
        riskLevel: securityResult.riskLevel
      };
    } catch (error) {
      timer.end(false);
      auditLogger.logError(error as Error, 'file_security_check');
      throw error;
    }
  };

  const processFile = async (file: File): Promise<void> => {
    const fileId = Math.random().toString(36).substr(2, 9);
    const timer = performanceMonitor.startTimer('file_upload_process');
    
    // Log upload start
    auditLogger.logUpload(file.name, file.size, false); // Will update on success
    
    const uploadFile: UploadFile = {
      id: fileId,
      name: file.name,
      size: file.size,
      type: file.type,
      status: "processing",
      progress: 0
    };

    setFiles(prev => [...prev, uploadFile]);

    // Progress simulation
    const progressInterval = setInterval(() => {
      setFiles(prev => prev.map(f => 
        f.id === fileId 
          ? { ...f, progress: Math.min(f.progress + Math.random() * 20, 90) }
          : f
      ));
    }, 500);

    try {
        // Enhanced security validation with configuration
        const securityCheck = await performSecurityCheck(file);
        
        if (!securityCheck.isSecure) {
          clearInterval(progressInterval);
          timer.end(false);
          
          const riskColor = securityCheck.riskLevel === 'high' ? 'destructive' : 
                           securityCheck.riskLevel === 'medium' ? 'default' : 'secondary';
          
          setFiles(prev => prev.map(f => 
            f.id === fileId 
              ? { 
                  ...f, 
                  status: "error", 
                  progress: 0, 
                  error: `Security ${securityCheck.riskLevel} risk: ${securityCheck.issues.slice(0, 2).join(', ')}${securityCheck.issues.length > 2 ? '...' : ''}` 
                }
              : f
          ));
          
          toast({
            title: `Security ${securityCheck.riskLevel.toUpperCase()} Risk`,
            description: `File rejected due to security concerns: ${securityCheck.issues.join(', ')}`,
            variant: riskColor as any
          });
          return;
        }

        // Show warning for medium risk files that are still processed
        if (securityCheck.riskLevel === 'medium') {
          auditLogger.log(
            'medium_risk_file_processed',
            'upload',
            'warning',
            { filename: file.name, issues: securityCheck.issues }
          );
          
          toast({
            title: "Security Notice",
            description: "File flagged for review but proceeding with upload",
            variant: "default"
          });
        }

        // Data validation phase
        setFiles(prev => prev.map(f => 
          f.id === fileId ? { ...f, status: "validating", progress: 50 } : f
        ));

        // Parse and validate CSV data if it's a CSV file
        if (file.name.toLowerCase().endsWith('.csv')) {
          try {
            const content = await file.text();
            const lines = content.split('\n').filter(line => line.trim());
            
            if (lines.length > 1) {
              // Parse CSV headers and sample data
              const headers = lines[0].split(',').map(h => h.trim().replace(/"/g, ''));
              const sampleData = lines.slice(1, Math.min(11, lines.length)).map(line => {
                const values = line.split(',').map(v => v.trim().replace(/"/g, ''));
                const record: Record<string, any> = {};
                headers.forEach((header, index) => {
                  record[header.toLowerCase()] = values[index] || '';
                });
                return record;
              });

              // Validate sample data
              const validationReport = await dataValidator.validateDataset(sampleData);
              
              auditLogger.log(
                'file_validation_complete',
                'upload',
                validationReport.summary.overallValid ? 'info' : 'warning',
                {
                  filename: file.name,
                  validationScore: validationReport.summary.validationScore,
                  errors: validationReport.errors.length,
                  warnings: validationReport.warnings.length
                }
              );

              // Update file status with validation results
              setFiles(prev => prev.map(f => 
                f.id === fileId 
                  ? { 
                      ...f, 
                      validationReport,
                      validRecords: validationReport.validRecords,
                      warnings: validationReport.warnings.length
                    }
                  : f
              ));

              // Show validation warnings if any
              if (validationReport.warnings.length > 0) {
                toast({
                  title: "Data Quality Notice",
                  description: `${validationReport.warnings.length} data quality warnings found`,
                  variant: "default"
                });
              }
            }
          } catch (error) {
            console.warn('CSV validation failed:', error);
            auditLogger.logError(error as Error, 'csv_validation');
          }
        }

        // Use API service for upload with performance monitoring
        const apiTimer = performanceMonitor.monitorAPI('/upload', 'POST');
        const result = await apiService.uploadCSV(file);
        apiTimer.end(result.status === "success");
        
        clearInterval(progressInterval);
        timer.end(result.status === "success");

        if (result.status === "success") {
          // Log successful upload
          auditLogger.logUpload(file.name, file.size, true);
          auditLogger.logDataAccess('opportunities', 'write');
          
          setFiles(prev => prev.map(f => 
            f.id === fileId 
              ? { ...f, status: "success", progress: 100, records: result.rows_processed }
              : f
          ));
          
          toast({
            title: "Upload Successful",
            description: `Processed ${result.rows_processed.toLocaleString()} records from ${file.name}${result.opportunities_generated ? `. Generated ${result.opportunities_generated} opportunities.` : ''}`,
          });
          
          // Call success callback
          onUploadSuccess?.(result);
        } else {
          auditLogger.log(
            'upload_failed',
            'upload',
            'error',
            { filename: file.name, errors: result.errors }
          );
          
          setFiles(prev => prev.map(f => 
            f.id === fileId 
              ? { 
                  ...f, 
                  status: "error", 
                  progress: 0, 
                  error: result.errors?.join(', ') || "Failed to process file" 
                }
              : f
          ));
          
          toast({
            title: "Upload Failed",
            description: `Failed to process ${file.name}. ${result.errors?.join(', ') || ''}`,
            variant: "destructive"
          });
        }
    } catch (error) {
      clearInterval(progressInterval);
      timer.end(false);
      
      const errorMessage = error instanceof Error ? error.message : "Network error occurred";
      
      auditLogger.logError(error as Error, 'file_upload');
      
      setFiles(prev => prev.map(f => 
        f.id === fileId 
          ? { ...f, status: "error", progress: 0, error: errorMessage }
          : f
      ));
      
      toast({
        title: "Upload Error",
        description: errorMessage,
        variant: "destructive"
      });
    }
  };

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);

    const droppedFiles = Array.from(e.dataTransfer.files);
    
    for (const file of droppedFiles) {
      const securityCheck = await performSecurityCheck(file);
      if (!securityCheck.isSecure) {
        toast({
          title: "Security Validation Failed",
          description: `${file.name}: ${securityCheck.issues.join(', ')}`,
          variant: securityCheck.riskLevel === 'high' ? 'destructive' : 'default'
        });
        continue;
      }
      
      await processFile(file);
    }
  }, [toast]);

  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files || []);
    
    for (const file of selectedFiles) {
      const securityCheck = await performSecurityCheck(file);
      if (!securityCheck.isSecure) {
        toast({
          title: "Security Validation Failed",
          description: `${file.name}: ${securityCheck.issues.join(', ')}`,
          variant: securityCheck.riskLevel === 'high' ? 'destructive' : 'default'
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
                        {file.status === "success" && file.validRecords && (
                          <Badge variant="default">
                            {file.validRecords} valid
                          </Badge>
                        )}
                        {file.warnings && file.warnings > 0 && (
                          <Badge variant="secondary">
                            {file.warnings} warnings
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
                    
                    {file.status === "validating" && (
                      <div className="space-y-2">
                        <Progress value={file.progress} className="h-2" />
                        <p className="text-xs text-muted-foreground">Validating data quality...</p>
                      </div>
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
            <li>• Maximum file size: {Math.round(settings.security.maxFileSize / 1024 / 1024)}MB</li>
            <li>• Required columns: VIN, Year, Make, Model, Sale Price, Sale Date</li>
            <li>• Optional columns: Mileage, Condition, Location, State</li>
            <li className="flex items-center space-x-2">
              <Shield className="h-4 w-4 text-warning" />
              <span>Advanced security scanning and data validation enabled</span>
            </li>
            <li className="flex items-center space-x-2">
              <CheckCircle className="h-4 w-4 text-success" />
              <span>Real-time data quality checks and VIN validation</span>
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
};
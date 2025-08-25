#!/usr/bin/env node

/**
 * Provenance validation tool for contract checking
 * Validates extracted data against JSON schemas
 */

import fs from 'fs';
import path from 'path';
import Ajv, { ErrorObject } from 'ajv';
import addFormats from 'ajv-formats';

interface ValidationConfig {
  schemaFile: string;
  minPassRate: number;
  failOnBreach: boolean;
}

interface ValidationResult {
  file: string;
  valid: boolean;
  errors: string[];
  fieldCount: number;
  passedFields: number;
}

async function main() {
  const args = process.argv.slice(2);
  const config = parseArgs(args);
  const jsonFiles = getJsonFiles(args);
  
  if (jsonFiles.length === 0) {
    console.error('❌ No JSON files specified');
    process.exit(1);
  }
  
  console.log('🔍 Validating extraction results against provenance schema...');
  console.log(`📄 Schema: ${config.schemaFile}`);
  console.log(`📊 Min pass rate: ${config.minPassRate * 100}%`);
  console.log(`📁 Files: ${jsonFiles.length}`);
  
  try {
    // Load and compile schema
    const schema = loadSchema(config.schemaFile);
    const ajv = new Ajv({ allErrors: true });
    addFormats(ajv);
    const validate = ajv.compile(schema);
    
    // Validate all files
    const results: ValidationResult[] = [];
    
    for (const file of jsonFiles) {
      const result = await validateFile(file, validate);
      results.push(result);
      
      const status = result.valid ? '✅' : '❌';
      const passRate = result.fieldCount > 0 ? (result.passedFields / result.fieldCount * 100).toFixed(1) : '0';
      console.log(`${status} ${path.basename(file)}: ${passRate}% (${result.passedFields}/${result.fieldCount} fields)`);
      
      if (!result.valid && result.errors.length > 0) {
        console.log(`   Errors: ${result.errors.slice(0, 3).join(', ')}`);
      }
    }
    
    // Calculate overall statistics
    const totalFiles = results.length;
    const validFiles = results.filter(r => r.valid).length;
    const overallPassRate = totalFiles > 0 ? validFiles / totalFiles : 0;
    
    const totalFields = results.reduce((sum, r) => sum + r.fieldCount, 0);
    const passedFields = results.reduce((sum, r) => sum + r.passedFields, 0);
    const fieldPassRate = totalFields > 0 ? passedFields / totalFields : 0;
    
    // Print summary
    console.log('\n📊 VALIDATION SUMMARY');
    console.log('=' .repeat(40));
    console.log(`Files: ${validFiles}/${totalFiles} valid (${(overallPassRate * 100).toFixed(1)}%)`);
    console.log(`Fields: ${passedFields}/${totalFields} valid (${(fieldPassRate * 100).toFixed(1)}%)`);
    
    // Check against minimum pass rate
    const checkPassRate = Math.min(overallPassRate, fieldPassRate);
    if (checkPassRate < config.minPassRate) {
      console.error(`❌ Pass rate (${(checkPassRate * 100).toFixed(1)}%) below threshold (${config.minPassRate * 100}%)`);
      
      if (config.failOnBreach) {
        process.exit(1);
      }
    } else {
      console.log(`✅ Pass rate meets threshold`);
    }
    
    // Save detailed report
    saveReport(results, overallPassRate, fieldPassRate);
    
  } catch (error) {
    console.error('❌ Validation failed:', error);
    process.exit(1);
  }
}

function parseArgs(args: string[]): ValidationConfig {
  const config: ValidationConfig = {
    schemaFile: 'schemas/provenance.schema.json',
    minPassRate: 0.95,
    failOnBreach: false
  };
  
  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--schema':
        config.schemaFile = args[++i];
        break;
      case '--min-pass':
        config.minPassRate = parseFloat(args[++i]);
        break;
      case '--fail-on-breach':
        config.failOnBreach = true;
        break;
    }
  }
  
  return config;
}

function getJsonFiles(args: string[]): string[] {
  const files: string[] = [];
  
  for (const arg of args) {
    if (arg.startsWith('--')) continue;
    if (arg.includes('*')) {
      // Handle glob patterns
      const dir = path.dirname(arg);
      const pattern = path.basename(arg);
      
      if (fs.existsSync(dir)) {
        const dirFiles = fs.readdirSync(dir);
        const matchingFiles = dirFiles
          .filter(file => file.endsWith('.json') && file.includes(pattern.replace('*', '')))
          .map(file => path.join(dir, file));
        files.push(...matchingFiles);
      }
    } else if (fs.existsSync(arg) && arg.endsWith('.json')) {
      files.push(arg);
    }
  }
  
  return files;
}

function loadSchema(schemaFile: string): any {
  if (!fs.existsSync(schemaFile)) {
    console.error(`❌ Schema file not found: ${schemaFile}`);
    process.exit(1);
  }
  
  const content = fs.readFileSync(schemaFile, 'utf8');
  return JSON.parse(content);
}

async function validateFile(file: string, validate: any): Promise<ValidationResult> {
  try {
    const content = fs.readFileSync(file, 'utf8');
    const data = JSON.parse(content);
    
    // Handle different data structures
    let provenanceData: any[] = [];
    
    if (Array.isArray(data)) {
      provenanceData = data;
    } else if (data.artifacts && data.artifacts.provenanceData) {
      provenanceData = data.artifacts.provenanceData;
    } else if (data.provenance) {
      provenanceData = Array.isArray(data.provenance) ? data.provenance : [data.provenance];
    } else {
      // Assume single provenance object
      provenanceData = [data];
    }
    
    const errors: string[] = [];
    let passedFields = 0;
    const totalFields = provenanceData.length;
    
    for (const item of provenanceData) {
      const valid = validate(item);
      if (valid) {
        passedFields++;
      } else {
        const itemErrors = validate.errors?.map((err: ErrorObject) => 
          `${item.field_name || 'unknown'}: ${err.instancePath || 'root'} ${err.message}`
        ) || [];
        errors.push(...itemErrors);
      }
    }
    
    return {
      file,
      valid: errors.length === 0,
      errors: errors.slice(0, 10), // Limit error count
      fieldCount: totalFields,
      passedFields
    };
    
  } catch (error) {
    return {
      file,
      valid: false,
      errors: [`Failed to parse JSON: ${error}`],
      fieldCount: 0,
      passedFields: 0
    };
  }
}

function saveReport(results: ValidationResult[], overallPassRate: number, fieldPassRate: number): void {
  const report = {
    timestamp: new Date().toISOString(),
    summary: {
      totalFiles: results.length,
      validFiles: results.filter(r => r.valid).length,
      overallPassRate: overallPassRate * 100,
      fieldPassRate: fieldPassRate * 100
    },
    results: results.map(r => ({
      file: path.basename(r.file),
      valid: r.valid,
      passRate: r.fieldCount > 0 ? (r.passedFields / r.fieldCount * 100) : 0,
      errors: r.errors.slice(0, 5) // Limit errors in report
    }))
  };
  
  const reportPath = 'artifacts/validation_report.json';
  
  // Ensure directory exists
  const dir = path.dirname(reportPath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(`💾 Detailed report saved to: ${reportPath}`);
}

// Run if called directly
if (require.main === module) {
  main().catch(console.error);
}

export { main as validateProvenance };
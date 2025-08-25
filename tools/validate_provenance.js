#!/usr/bin/env node

/**
 * Provenance Validation Tool
 * Validates extraction results against schemas
 */

const fs = require('fs');
const path = require('path');
const Ajv = require('ajv');
const addFormats = require('ajv-formats');

const args = process.argv.slice(2);
const schemaFile = args.find(arg => arg.startsWith('--schema='))?.replace('--schema=', '');
const minPass = parseFloat(args.find(arg => arg.startsWith('--min-pass='))?.replace('--min-pass=', '')) || 0.95;
const failOnBreach = args.includes('--fail-on-breach');

// Get JSON files to validate (remaining args)
const jsonFiles = args.filter(arg => !arg.startsWith('--') && arg.endsWith('.json'));

async function validateProvenance() {
  console.log('🔍 Validating extraction provenance...');
  
  // Initialize validator
  const ajv = new Ajv({ allErrors: true });
  addFormats(ajv);
  
  let schema = {};
  
  // Load schema if provided
  if (schemaFile && fs.existsSync(schemaFile)) {
    try {
      schema = JSON.parse(fs.readFileSync(schemaFile, 'utf8'));
      console.log(`Loaded schema: ${schemaFile}`);
    } catch (error) {
      console.warn(`Could not load schema ${schemaFile}:`, error.message);
    }
  } else {
    // Default schema for validation
    schema = {
      type: 'object',
      properties: {
        site: { type: 'string' },
        url: { type: 'string', format: 'uri' },
        timestamp: { type: 'string', format: 'date-time' },
        passed: { type: 'boolean' }
      },
      required: ['site', 'url', 'timestamp', 'passed']
    };
  }
  
  const validate = ajv.compile(schema);
  
  let totalFiles = 0;
  let validFiles = 0;
  const results = [];
  
  // Find JSON files to validate
  const filesToValidate = [];
  
  if (jsonFiles.length > 0) {
    // Use specified files
    filesToValidate.push(...jsonFiles.filter(file => fs.existsSync(file)));
  } else {
    // Look for artifacts directory
    const artifactsDir = 'artifacts';
    if (fs.existsSync(artifactsDir)) {
      const files = fs.readdirSync(artifactsDir)
        .filter(file => file.endsWith('.json'))
        .map(file => path.join(artifactsDir, file));
      filesToValidate.push(...files);
    }
  }
  
  if (filesToValidate.length === 0) {
    console.log('📄 No JSON files found to validate');
    console.log('✅ PASS: No validation errors (no files to validate)');
    return;
  }
  
  for (const file of filesToValidate) {
    try {
      const data = JSON.parse(fs.readFileSync(file, 'utf8'));
      const valid = validate(data);
      
      totalFiles++;
      
      if (valid) {
        validFiles++;
        console.log(`✅ ${path.basename(file)}: Valid`);
      } else {
        console.log(`❌ ${path.basename(file)}: Invalid`);
        if (validate.errors) {
          validate.errors.forEach(error => {
            console.log(`   - ${error.instancePath}: ${error.message}`);
          });
        }
      }
      
      results.push({
        file: path.basename(file),
        valid,
        errors: validate.errors || []
      });
      
    } catch (error) {
      totalFiles++;
      console.log(`❌ ${path.basename(file)}: Parse error - ${error.message}`);
      
      results.push({
        file: path.basename(file),
        valid: false,
        errors: [{ message: `Parse error: ${error.message}` }]
      });
    }
  }
  
  const passRate = totalFiles > 0 ? validFiles / totalFiles : 1;
  
  console.log(`\n📊 Validation Results:`);
  console.log(`- Total files: ${totalFiles}`);
  console.log(`- Valid files: ${validFiles}`);
  console.log(`- Pass rate: ${Math.round(passRate * 100)}%`);
  console.log(`- Minimum required: ${Math.round(minPass * 100)}%`);
  
  if (passRate < minPass) {
    console.error(`❌ FAIL: Pass rate below ${Math.round(minPass * 100)}% threshold`);
    if (failOnBreach) {
      process.exit(1);
    }
  } else {
    console.log(`✅ PASS: Validation completed successfully`);
  }
}

validateProvenance().catch(error => {
  console.error('Validation failed:', error);
  process.exit(1);
});
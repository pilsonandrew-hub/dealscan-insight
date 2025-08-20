#!/usr/bin/env node

/**
 * DealerScope 4.8 Complete Project Export Script
 * Generates a downloadable package with all source code, configs, and setup instructions
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const EXPORT_DIR = 'dealerscope-4.8-export';
const PROJECT_NAME = 'DealerScope 4.8 - Vehicle Arbitrage Platform';

// Project structure to export
const EXPORT_STRUCTURE = {
  // Core application files
  src: [
    'App.tsx', 'main.tsx', 'index.css', 'vite-env.d.ts',
    'components/**/*', 'hooks/**/*', 'pages/**/*', 'types/**/*',
    'utils/**/*', 'services/**/*', 'config/**/*', 'lib/**/*',
    'integrations/**/*'
  ],
  
  // Configuration files
  root: [
    'package.json', 'package-lock.json', 'tsconfig.json', 'tsconfig.app.json',
    'tsconfig.node.json', 'vite.config.ts', 'tailwind.config.ts',
    'postcss.config.js', 'eslint.config.js', 'components.json',
    'index.html', '.env.example'
  ],
  
  // Public assets
  public: ['**/*'],
  
  // Supabase configuration
  supabase: ['**/*'],
  
  // Scripts and documentation
  scripts: ['**/*'],
  
  // Documentation files
  docs: [
    'README.md', 'PRODUCTION_DEPLOYMENT_GUIDE.md', 'SECURITY_REPORT.md',
    'FIXES_SUMMARY.md', 'README_SECURITY_OPTIMIZATIONS.md'
  ]
};

class DealerScopeExporter {
  constructor() {
    this.exportPath = path.join(process.cwd(), EXPORT_DIR);
    this.timestamp = new Date().toISOString().replace(/[:.]/g, '-').split('T')[0];
  }

  async export() {
    console.log(`🚀 Starting ${PROJECT_NAME} export...`);
    
    try {
      // Clean and create export directory
      this.cleanExportDir();
      this.createExportDir();
      
      // Export all project files
      await this.exportProjectFiles();
      
      // Generate setup documentation
      this.generateSetupGuide();
      this.generateEnvTemplate();
      this.generateDeploymentScript();
      
      // Create package info
      this.generatePackageInfo();
      
      // Create archive
      const archivePath = await this.createArchive();
      
      console.log(`✅ Export completed successfully!`);
      console.log(`📦 Package location: ${archivePath}`);
      console.log(`📋 Share this file with your developers`);
      
      return archivePath;
      
    } catch (error) {
      console.error('❌ Export failed:', error.message);
      throw error;
    }
  }

  cleanExportDir() {
    if (fs.existsSync(this.exportPath)) {
      fs.rmSync(this.exportPath, { recursive: true, force: true });
    }
  }

  createExportDir() {
    fs.mkdirSync(this.exportPath, { recursive: true });
  }

  async exportProjectFiles() {
    console.log('📁 Copying project files...');
    
    // Copy source files
    this.copyDirectory('src', path.join(this.exportPath, 'src'));
    
    // Copy public files
    this.copyDirectory('public', path.join(this.exportPath, 'public'));
    
    // Copy supabase files
    this.copyDirectory('supabase', path.join(this.exportPath, 'supabase'));
    
    // Copy scripts
    this.copyDirectory('scripts', path.join(this.exportPath, 'scripts'));
    
    // Copy root configuration files
    EXPORT_STRUCTURE.root.forEach(file => {
      const sourcePath = path.join(process.cwd(), file);
      const destPath = path.join(this.exportPath, file);
      
      if (fs.existsSync(sourcePath)) {
        this.copyFile(sourcePath, destPath);
      }
    });
    
    // Copy documentation files
    EXPORT_STRUCTURE.docs.forEach(file => {
      const sourcePath = path.join(process.cwd(), file);
      const destPath = path.join(this.exportPath, file);
      
      if (fs.existsSync(sourcePath)) {
        this.copyFile(sourcePath, destPath);
      }
    });
  }

  copyDirectory(source, destination) {
    if (!fs.existsSync(source)) return;
    
    if (!fs.existsSync(destination)) {
      fs.mkdirSync(destination, { recursive: true });
    }
    
    const files = fs.readdirSync(source);
    
    files.forEach(file => {
      const sourcePath = path.join(source, file);
      const destPath = path.join(destination, file);
      
      if (fs.statSync(sourcePath).isDirectory()) {
        this.copyDirectory(sourcePath, destPath);
      } else {
        this.copyFile(sourcePath, destPath);
      }
    });
  }

  copyFile(source, destination) {
    const destDir = path.dirname(destination);
    if (!fs.existsSync(destDir)) {
      fs.mkdirSync(destDir, { recursive: true });
    }
    fs.copyFileSync(source, destination);
  }

  generateSetupGuide() {
    const setupGuide = `# DealerScope 4.8 - Setup Guide

## 🚀 Quick Start for Developers

### Prerequisites
- Node.js 18+ 
- npm or yarn
- Supabase account (free tier works)

### 1. Installation
\`\`\`bash
# Extract the project
unzip dealerscope-4.8-${this.timestamp}.zip
cd dealerscope-4.8-export

# Install dependencies
npm install
\`\`\`

### 2. Environment Setup
\`\`\`bash
# Copy environment template
cp .env.example .env

# Edit .env with your Supabase credentials
# Get these from your Supabase project dashboard
\`\`\`

### 3. Database Setup
\`\`\`bash
# Initialize Supabase (if not already done)
npx supabase init

# Link to your Supabase project
npx supabase link --project-ref YOUR_PROJECT_REF

# Run migrations
npx supabase db push

# Deploy edge functions
npx supabase functions deploy vehicle-scraper
\`\`\`

### 4. Development
\`\`\`bash
# Start development server
npm run dev

# Open http://localhost:5173
\`\`\`

### 5. Production Deployment
\`\`\`bash
# Build for production
npm run build

# Deploy to your hosting platform
# (Vercel, Netlify, or any static host)
\`\`\`

## 🔧 Key Features Included

### ✅ Vehicle Auction Scraper
- Scrapes 20+ government auction sites
- Async processing with rate limiting
- Data validation and sanitization
- Real-time WebSocket updates

### ✅ Database Schema
- Public listings table
- Scraper configurations
- Audit logging
- Performance monitoring

### ✅ Security Features
- Authentication & authorization
- Input validation
- SSRF protection
- Rate limiting
- Error handling

### ✅ UI Components
- Dashboard with metrics
- Real-time opportunity list
- Scraper control panel
- System health monitoring

## 📊 Architecture

### Frontend
- React 18 + TypeScript
- Tailwind CSS + shadcn/ui
- React Query for state management
- WebSocket real-time updates

### Backend
- Supabase Edge Functions
- PostgreSQL database
- Row Level Security (RLS)
- Real-time subscriptions

### Scraping Engine
- Async web scraping
- Multi-site support
- Error recovery
- Data normalization

## 🛠️ Development Commands

\`\`\`bash
# Development
npm run dev          # Start dev server
npm run build        # Build for production
npm run preview      # Preview production build

# Database
npx supabase start   # Start local Supabase
npx supabase db push # Push schema changes
npx supabase gen types typescript --local > src/integrations/supabase/types.ts

# Functions
npx supabase functions serve                    # Serve functions locally  
npx supabase functions deploy vehicle-scraper   # Deploy scraper function
\`\`\`

## 🔐 Security Configuration

### Required Environment Variables
\`\`\`env
VITE_SUPABASE_URL=your_supabase_url
VITE_SUPABASE_PUBLISHABLE_KEY=your_anon_key
VITE_SUPABASE_PROJECT_ID=your_project_id
\`\`\`

### Supabase Secrets (for Edge Functions)
- Add these in Supabase Dashboard > Edge Functions > Settings
- Required for scraping operations and external API calls

## 📱 Browser Support
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## 🆘 Troubleshooting

### Common Issues
1. **Build fails**: Check Node.js version (18+)
2. **Database errors**: Verify Supabase connection
3. **Function errors**: Check Supabase function logs
4. **CORS issues**: Verify domain configuration

### Support
- Check the logs in Supabase Dashboard
- Review security configuration
- Validate environment variables

---

**DealerScope 4.8** - Production-ready vehicle arbitrage platform
Built with ❤️ for efficient dealer operations
`;

    fs.writeFileSync(path.join(this.exportPath, 'DEVELOPER_SETUP.md'), setupGuide);
  }

  generateEnvTemplate() {
    const envTemplate = `# DealerScope 4.8 Environment Configuration
# Copy this file to .env and fill in your values

# Supabase Configuration
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=your_anon_key_here
VITE_SUPABASE_PROJECT_ID=your_project_ref

# Development Settings
NODE_ENV=development
VITE_APP_TITLE=DealerScope 4.8
VITE_APP_VERSION=4.8.0

# Optional: Analytics & Monitoring
VITE_ENABLE_ANALYTICS=false
VITE_SENTRY_DSN=your_sentry_dsn_here

# Production Only
# VITE_BASE_URL=https://yourdomain.com
`;

    fs.writeFileSync(path.join(this.exportPath, '.env.example'), envTemplate);
  }

  generateDeploymentScript() {
    const deployScript = `#!/bin/bash

# DealerScope 4.8 - One-Click Deployment Script

set -e

echo "🚀 DealerScope 4.8 Deployment Starting..."

# Check requirements
command -v node >/dev/null 2>&1 || { echo "❌ Node.js required but not installed"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "❌ npm required but not installed"; exit 1; }

# Install dependencies
echo "📦 Installing dependencies..."
npm ci

# Build application
echo "🔨 Building application..."
npm run build

# Run tests (if available)
if [ -f "package.json" ] && grep -q '"test"' package.json; then
  echo "🧪 Running tests..."
  npm test
fi

# Deploy to Supabase
if [ -f "supabase/config.toml" ]; then
  echo "🌐 Deploying Edge Functions..."
  npx supabase functions deploy vehicle-scraper
fi

echo "✅ Deployment completed successfully!"
echo "🌍 Your application is ready to use"

# Optional: Open in browser
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open http://localhost:5173
elif command -v open >/dev/null 2>&1; then
  open http://localhost:5173
fi
`;

    const deployPath = path.join(this.exportPath, 'deploy.sh');
    fs.writeFileSync(deployPath, deployScript);
    
    // Make executable on Unix systems
    try {
      fs.chmodSync(deployPath, '755');
    } catch (error) {
      // Ignore on Windows
    }
  }

  generatePackageInfo() {
    const packageInfo = {
      name: "dealerscope-4.8",
      version: "4.8.0",
      description: "Production-ready vehicle arbitrage platform with advanced scraping and analysis capabilities",
      author: "DealerScope Team",
      license: "Proprietary",
      exportDate: new Date().toISOString(),
      features: [
        "Multi-site vehicle auction scraping",
        "Real-time data processing",
        "Advanced profit analysis",
        "WebSocket real-time updates",
        "Comprehensive security features",
        "Production-ready deployment"
      ],
      technologies: {
        frontend: ["React 18", "TypeScript", "Tailwind CSS", "shadcn/ui"],
        backend: ["Supabase", "Edge Functions", "PostgreSQL"],
        scraping: ["Async Processing", "Rate Limiting", "Error Recovery"],
        security: ["RLS", "Authentication", "Input Validation", "SSRF Protection"]
      },
      requirements: {
        node: ">=18.0.0",
        npm: ">=8.0.0",
        browser: "Modern browsers (Chrome 90+, Firefox 88+, Safari 14+)"
      }
    };

    fs.writeFileSync(
      path.join(this.exportPath, 'package-info.json'), 
      JSON.stringify(packageInfo, null, 2)
    );
  }

  async createArchive() {
    const archiveName = `dealerscope-4.8-${this.timestamp}.zip`;
    const archivePath = path.join(process.cwd(), archiveName);
    
    try {
      // Try to use system zip command
      execSync(`cd "${path.dirname(this.exportPath)}" && zip -r "${archivePath}" "${path.basename(this.exportPath)}"`, {
        stdio: 'inherit'
      });
    } catch (error) {
      // Fallback: just return the directory path
      console.log('⚠️  Zip not available, directory created at:', this.exportPath);
      return this.exportPath;
    }
    
    return archivePath;
  }
}

// Main execution
async function main() {
  try {
    const exporter = new DealerScopeExporter();
    const result = await exporter.export();
    
    console.log('\n🎉 Export Summary:');
    console.log('- Complete source code included');
    console.log('- Database schema and migrations');
    console.log('- Setup and deployment guides');
    console.log('- Security configurations');
    console.log('- Ready for immediate development');
    console.log('\n📧 Share this package with your development team!');
    
    return result;
  } catch (error) {
    console.error('\n❌ Export failed:', error.message);
    process.exit(1);
  }
}

// Run if called directly
if (require.main === module) {
  main();
}

module.exports = { DealerScopeExporter };
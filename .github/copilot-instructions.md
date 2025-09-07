# DealerScope - GitHub Copilot Instructions

**ALWAYS follow these instructions first and only fallback to additional search and context gathering if the information here is incomplete or found to be in error.**

DealerScope is a production-ready React/TypeScript vehicle arbitrage analysis platform with enterprise-grade features, comprehensive testing, and professional UI components.

## Working Effectively

### Bootstrap and Environment Setup
```bash
# Prerequisites: Node.js 18+ (tested with Node.js 20.19.4)
node --version  # Should be 18+ (we have 20.19.4)
npm --version   # Should be 8+ (we have 10.8.2)

# Install dependencies - takes ~30 seconds
npm install

# Environment configuration
cp .env.example .env
# Edit .env with your Supabase credentials:
# VITE_SUPABASE_URL=your-supabase-url
# VITE_SUPABASE_ANON_KEY=your-anon-key
```

### Build Commands
```bash
# Production build - takes ~8 seconds. NEVER CANCEL. Set timeout to 60+ seconds.
npm run build

# Development build
npm run build:dev

# Preview production build
npm run preview
```

**CRITICAL TIMING**: Build completes in 7-8 seconds typically. **NEVER CANCEL** - set timeouts to 60+ seconds for safety.

### Development Server
```bash
# Start development server - starts in ~250ms
npm run dev
# Server runs on http://localhost:8080/

# Alternative: Use the enhanced dev script
./scripts/dev.sh dev    # Start development server
./scripts/dev.sh help   # Show all available commands
```

The development server starts extremely fast (under 300ms) and runs on port 8080.

### Testing
```bash
# Run test suite - takes ~4 seconds. NEVER CANCEL. Set timeout to 30+ seconds.
npx vitest run

# Run with coverage
npx vitest run --coverage

# Watch mode for development
npx vitest

# Run specific test files
npx vitest src/__tests__/security/
```

**CRITICAL TIMING**: Test suite runs 45 tests in ~4 seconds. Some tests may fail due to network restrictions or missing Supabase configuration - this is expected in development.

### Code Quality
```bash
# Linting - has many warnings but doesn't block builds
npm run lint

# Type checking
npx tsc --noEmit
```

**NOTE**: Linting shows 500+ TypeScript/ESLint warnings about `any` types and React hooks dependencies. These do not block builds or functionality.

## Validation

### Manual Validation Scenarios
**ALWAYS manually validate any changes by running these complete scenarios:**

1. **Basic Application Flow**:
   ```bash
   npm run dev
   # Navigate to http://localhost:8080/
   # Verify: Professional login page loads with green enterprise status bar
   # Test: Click "Test Connection" button (should show error without Supabase config)
   # Test: Click "Sign Up" tab to verify UI switching works
   ```

2. **Build and Production Validation**:
   ```bash
   npm run build
   npm run preview
   # Navigate to http://localhost:3000/ (preview server)
   # Verify: Same functionality as development
   ```

3. **Test Suite Validation**:
   ```bash
   npx vitest run
   # Expected: ~45 tests, most passing, some may fail due to environment
   # Look for: No major crashes, test infrastructure working
   ```

### Application Features to Validate
- ✅ **Enterprise Systems Status Bar**: Green bar showing "HEALTHY" systems
- ✅ **Authentication UI**: Professional login/signup tabs
- ✅ **Interactive Elements**: Test Connection and Create Test Account buttons
- ✅ **Error Handling**: Proper error messages when Supabase unavailable
- ✅ **Responsive Design**: Professional styling with shadcn/ui components

## Common Tasks

### Development Workflow
```bash
# 1. Start development - every time you work on the project
npm install                    # If dependencies changed
npm run dev                   # Start dev server (port 8080)

# 2. Make changes and validate
npx tsc --noEmit             # Check TypeScript errors
npx vitest run               # Run tests (~4 seconds)

# 3. Before committing
npm run build                # Ensure production build works (~8 seconds)
npm run lint                 # Check for major issues (warnings expected)
```

### Project Structure Navigation
```
src/
├── components/              # UI components (shadcn/ui based)
│   ├── DealInbox.tsx       # Main deal management interface  
│   ├── ui/                 # shadcn/ui component library
│   └── EnhancedDealInbox.tsx # Advanced deal features
├── pages/
│   ├── Index.tsx           # Main dashboard
│   ├── Auth.tsx            # Authentication page (login/signup)
│   └── Settings.tsx        # User preferences
├── contexts/
│   └── ModernAuthContext.tsx # Authentication state management
├── services/
│   └── api.ts              # Supabase integration
├── utils/                  # Utilities and helpers
└── tests/                  # Test files
    ├── components/         # Component tests
    ├── integration/        # Integration tests
    └── security/           # Security validation tests

scripts/                    # Development scripts
├── dev.sh                 # Enhanced development script
├── validate-codex-sync.js # Project validation
└── validation-suite.sh    # Comprehensive validation

.github/workflows/         # CI/CD pipelines
```

### Key Files for Common Changes
- **Authentication**: `src/contexts/ModernAuthContext.tsx`, `src/pages/Auth.tsx`
- **Main Dashboard**: `src/pages/Index.tsx`, `src/components/DealInbox.tsx`
- **UI Components**: `src/components/ui/` (shadcn/ui components)
- **API Integration**: `src/services/api.ts`
- **Configuration**: `vite.config.ts`, `tailwind.config.ts`

## Environment Configuration

### Required Environment Variables
```bash
# .env file (copy from .env.example)
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
```

### Development vs Production
- **Development**: Runs on `http://localhost:8080` with hot reload
- **Production**: Optimized build with code splitting and compression
- **Environment Detection**: Automatic based on NODE_ENV and build mode

## Troubleshooting

### Common Issues

**Build Errors**:
```bash
# Clear and reinstall dependencies
rm -rf node_modules package-lock.json
npm install
```

**Port Conflicts**:
```bash
# Development server uses port 8080
# If occupied, Vite will suggest alternative port
```

**Test Failures**:
- Password security tests may fail without internet (HIBP API)
- Auth context tests may fail without Supabase configuration
- This is expected in sandboxed environments

**Linting Warnings**:
- 500+ TypeScript `any` type warnings are known and do not block functionality
- React hooks dependency warnings are development-only concerns

### Debug Mode
```bash
# Verbose development logging
DEBUG=dealerscope:* npm run dev

# Development mode with detailed errors
NODE_ENV=development npm run dev
```

## Technology Stack

### Core Technologies
- **Frontend**: React 18 + TypeScript 5.8
- **Build Tool**: Vite 5.4 (fast builds and dev server)
- **Styling**: Tailwind CSS + shadcn/ui components
- **Backend**: Supabase (authentication, database, real-time)
- **Testing**: Vitest + jsdom + @testing-library
- **Type Safety**: TypeScript with strict mode

### Key Dependencies
- `@supabase/supabase-js` - Backend integration
- `@radix-ui/*` - Accessible UI primitives (via shadcn/ui)
- `@tanstack/react-query` - Data fetching and state
- `react-router-dom` - Client-side routing
- `tailwindcss` - Utility-first CSS framework

## Production Deployment

### Docker Support
```bash
# Production deployment
docker-compose -f docker-compose.prod.yml up --build

# Development with Docker
docker-compose up --build
```

### Performance Characteristics
- **Cold Build**: 7-8 seconds (3000+ modules)
- **Dev Server Startup**: 250ms
- **Hot Reload**: <100ms for most changes
- **Bundle Size**: ~2MB total (code-split)
- **Test Suite**: 45 tests in ~4 seconds

### CI/CD Integration
- GitHub Actions workflows in `.github/workflows/`
- Automated testing, building, and deployment
- Security scanning and performance validation

## Security Notes

### Authentication Flow
- JWT-based authentication via Supabase
- Row Level Security (RLS) policies
- TOTP two-factor authentication support
- Comprehensive audit logging

### Input Validation
- Zod schema validation throughout
- XSS protection via CSP headers
- SSRF protection for scraping operations
- Rate limiting and abuse protection

## Contact and Support

For issues with these instructions:
1. **First**: Verify you followed the exact commands above
2. **Build Issues**: Check Node.js version (need 18+)
3. **Test Failures**: Expected in sandboxed environments without Supabase
4. **Functionality**: Application should load and show professional login UI

**Expected Working State**: Professional DealerScope login page with green enterprise systems status bar, functional authentication forms, and working Test Connection button (may show connection error without Supabase configuration).
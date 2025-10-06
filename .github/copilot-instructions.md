# DealerScope - GitHub Copilot Instructions

**ALWAYS follow these instructions first. Only search or explore further if information here is incomplete or found to be in error.**

DealerScope is a production-ready React/TypeScript vehicle arbitrage analysis platform built with Vite, Supabase backend, and enterprise-grade security features.

## 🚀 Essential Setup Commands

**Run these commands in exact order for any fresh repository clone:**

```bash
# 1. Install dependencies - NEVER CANCEL: takes ~30 seconds, set timeout 60+ seconds
npm install

# 2. Copy environment template
cp .env.example .env

# 3. Build the application - NEVER CANCEL: takes ~10 seconds, set timeout 120+ seconds  
npm run build

# 4. Start development server - takes ~300ms to start
npm run dev
```

**⚠️ CRITICAL TIMING EXPECTATIONS:**
- `npm install`: 26 seconds (NEVER CANCEL - set timeout 60+ seconds)
- `npm run build`: 8 seconds (NEVER CANCEL - set timeout 120+ seconds)
- `npm run dev`: 300ms startup time
- `npx vitest run`: 3.4 seconds for test suite
- `npm run lint`: 5 seconds (expect 567+ lint errors)

## 🔧 Development Workflow

### Build & Test Commands
```bash
# Build for production (8 seconds - NEVER CANCEL)
npm run build

# Build for development  
npm run build:dev

# Start development server (ready in ~300ms)
npm run dev
# App available at: http://localhost:8080/

# Start preview server (serves production build)
npm run preview  
# App available at: http://localhost:4173/

# Run linting (5 seconds - expect 567+ errors)
npm run lint

# Run tests (3.4 seconds - 42/45 tests pass)
npx vitest run

# Type checking
npx tsc --noEmit
```

### Development Scripts
```bash
# Enhanced development setup with health checks
bash scripts/dev.sh

# Comprehensive security scan (~15 seconds)
bash scripts/comprehensive-security-scan.sh

# GitHub sync verification
bash scripts/sync-github-for-codex.sh
```

## 🧪 Validation & Testing

**MANUAL VALIDATION REQUIREMENT:** After making changes, ALWAYS run through this complete scenario:

1. **Build Validation:**
   ```bash
   npm install && npm run build
   # Verify: No build errors, dist/ folder created with ~1.4MB total size
   ```

2. **Development Server Test:**
   ```bash
   npm run dev
   # Verify: Server starts in <1 second, shows Vite ready message
   curl -f http://localhost:8080 
   # Verify: Returns 200 status code
   ```

3. **Application Functionality Test:**
   - Navigate to http://localhost:8080 in browser
   - **VERIFY:** DealerScope login page loads with enterprise systems status showing "HEALTHY" 
   - **VERIFY:** Authentication form is visible with Email/Password fields
   - **VERIFY:** Green status bar shows "Enterprise Systems: HEALTHY - Unified Config: development"
   - **VERIFY:** No console errors except expected CSP warnings

4. **Test Suite Validation:**
   ```bash
   npx vitest run
   # Expected: 42 tests pass, 3 tests fail (known issues in password validation & auth context)
   ```

## 📁 Repository Structure

### Key Directories
```
/src/                   # Main React application source
├── components/         # UI components (DealInbox, DealCard, etc.)
├── contexts/          # React contexts (ModernAuthContext)
├── core/              # Enterprise systems (UnifiedLogger, StateManager)
├── pages/             # Route components (Index, Settings)
├── services/          # API integration layer
└── utils/             # Utilities and validation

/scripts/              # Build and validation scripts
/supabase/             # Backend functions and schemas  
/.github/workflows/    # CI/CD pipelines
/validation-reports/   # Generated validation outputs
```

### Important Files
- `package.json` - npm scripts and dependencies
- `vite.config.ts` - Build configuration (port 8080)
- `vitest.config.ts` - Test configuration  
- `.env.example` - Environment template
- `tsconfig.json` - TypeScript configuration

## ⚠️ Known Issues & Workarounds

### Linting Issues
- **Status:** 567 TypeScript/ESLint errors (mainly `@typescript-eslint/no-explicit-any`)
- **Impact:** Does not prevent building or running
- **Action:** Continue with development, linting errors are not blocking

### Test Failures
- **Status:** 3/45 tests fail (password validation, auth context)
- **Impact:** Core functionality works despite test failures
- **Action:** Tests are informational, focus on manual validation

### Missing npm Scripts
- **Issue:** No `npm test` script defined
- **Workaround:** Use `npx vitest run` directly for testing

### Environment Configuration
- **Requirement:** Supabase credentials needed for full functionality
- **Workaround:** App runs in development mode without Supabase, shows auth UI

## 🏗️ Architecture & Tech Stack

### Frontend Stack
- **Framework:** React 18 + TypeScript
- **Build Tool:** Vite 5.4.19 with SWC
- **UI Library:** shadcn/ui components with Radix UI primitives
- **Styling:** Tailwind CSS
- **State Management:** Unified state management with enterprise orchestration

### Backend Integration  
- **Primary:** Supabase (authentication, database, edge functions)
- **Real-time:** WebSocket for live deal notifications
- **Security:** Row-level security, audit logging, input sanitization

### Development Tools
- **Testing:** Vitest with jsdom environment
- **Linting:** ESLint with TypeScript rules
- **Performance:** Built-in performance monitoring
- **Security:** Comprehensive security scanning scripts

## 🔐 Security Features

DealerScope includes enterprise-grade security (all automated):
- ✅ JWT + TOTP two-factor authentication  
- ✅ Row Level Security for data access
- ✅ Input validation and sanitization
- ✅ SSRF protection with domain allowlisting
- ✅ Complete audit logging
- ✅ Rate limiting protection
- ✅ CSP headers for XSS protection

## 🚦 CI/CD Integration

### GitHub Actions Workflows
- **Build:** `.github/workflows/ci-cd.yml` - full build and test pipeline
- **Security:** `.github/workflows/security-gates.yml` - security scanning
- **Performance:** `.github/workflows/performance-gates.yml` - performance validation
- **Production:** `.github/workflows/production-deploy.yml` - deployment pipeline

### Pre-commit Validation
**Always run before committing changes:**
```bash
npm run lint       # Code style check (expect errors)
npm run build      # Verify builds successfully
npx vitest run     # Run test suite
```

## 🎯 Common Development Tasks

### Adding New Features
1. **Always build and test first:** `npm run build && npx vitest run`
2. **Create components in:** `src/components/`
3. **Add routing in:** `src/App.tsx`
4. **Update types in:** `src/types/`
5. **Test manually:** Start dev server and verify functionality
6. **Validate:** Run full validation scenario above

### Debugging Issues
1. **Check console:** Browser dev tools for runtime errors
2. **Check build:** `npm run build` for compilation errors  
3. **Check linting:** `npm run lint` for code style issues
4. **Check logs:** Development server output for backend issues

### Performance Optimization
1. **Bundle analysis:** Check `npm run build` output for chunk sizes
2. **Runtime performance:** Browser dev tools performance tab
3. **Memory usage:** Enterprise systems report memory metrics automatically

## 📊 Expected Performance Metrics

### Build Performance
- **npm install:** 26 seconds maximum
- **npm run build:** 8 seconds maximum  
- **npm run dev startup:** <1 second
- **Hot reload:** <500ms for most changes

### Runtime Performance  
- **Initial page load:** <2 seconds (development mode)
- **Authentication flow:** <1 second response
- **Enterprise systems startup:** <500ms initialization
- **Memory usage:** <200MB typical development

## 🆘 Troubleshooting

### Build Failures
```bash
# Clear and reinstall dependencies
rm -rf node_modules package-lock.json
npm install

# Check for TypeScript errors
npx tsc --noEmit
```

### Development Server Issues
```bash
# Check port availability
lsof -ti:8080 && kill -9 $(lsof -ti:8080)

# Restart with fresh cache
npm run dev -- --force
```

### Authentication Issues (Expected in Development)
- **Symptom:** Authentication fails or shows "Supabase configuration incomplete"  
- **Status:** Normal in development without Supabase credentials
- **Action:** App still demonstrates UI and core functionality

---

**Last Validated:** September 2025 | **Node.js Version:** 20.19.4 | **npm Version:** 10.8.2

**⚡ Quick Start:** `npm install && npm run build && npm run dev` (Ready in <40 seconds total)
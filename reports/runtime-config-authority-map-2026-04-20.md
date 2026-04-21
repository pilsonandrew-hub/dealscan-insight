# Runtime Config Authority Map — 2026-04-20

## Evidence-based current split

### 1. `src/config/settings.ts`
**Status:** live, high-impact, primary app/runtime settings surface

**Direct consumers verified:**
- `src/components/CrosshairSearch.tsx`
- `src/components/ReconPanel.tsx`
- `src/components/SniperButton.tsx`
- `src/components/SniperScopeDashboard.tsx`
- `src/components/UploadInterface.tsx`
- `src/components/VINScanner.tsx`
- `src/services/anomalyDetector.ts`
- `src/services/api.ts`
- `src/services/costController.ts`
- `src/services/roverAPI.ts`
- `src/services/sonarAPI.ts`
- `src/utils/batch-processor.ts`
- `src/utils/health-checker.ts`
- plus additional user-settings consumers such as realtime notification/settings flows

**Current role:**
- primary frontend runtime settings for API, websocket, processing, security, cache, environment, and feature-adjacent behavior used by real user-facing flows.

**Judgment:** keep. This is the primary frontend runtime settings authority.

---

## Removed from live authority
- `src/config/deploymentConfig.ts` — removed after consumer search showed no external usage.
- `src/config/environmentManager.ts` — folded into `healthCheck.ts` and `webVitals.ts`, then removed.
- `src/config/productionConfig.ts` — folded into `metricsCollector.ts`, then removed.
- `src/core/UnifiedConfigService.ts` — folded into `UnifiedLogger.ts`, `ErrorBoundary.tsx`, and `safeConsole.ts`, then removed.
- `src/core/AdvancedMetricsCollector.ts` — removed as synthetic duplicate monitoring layer.
- `src/core/SystemIntegrationProtocols.ts` — removed as unconsumed sidecar.
- `src/core/EnterpriseSystemOrchestrator.ts` — removed as unconsumed orchestration sidecar.
- `src/core/UnifiedStateManager.ts` — removed as unconsumed local state framework.
- `src/core/PerformanceEmergencyKit.ts` — removed as synthetic browser infra.
- `src/core/ProductionReadinessGate.ts` — removed as fake browser governance.
- `src/scripts/run-production-assessment.ts` — removed as dead script residue.

## Current authority ranking
1. `src/config/settings.ts` — primary runtime authority

## Hard truth
The big fake enterprise cluster is gone.
The wrapper/config-shim layer around it is gone too.
`settings.ts` is still the only real config authority left in this surface.
The duplicated environment-resolution helper that spread across direct consumers was then replaced with one tiny utility, `src/utils/runtimeEnvironment.ts`.

## Strict next step
Do not let `runtimeEnvironment.ts` grow into a fake config layer.
It should stay a tiny environment-resolution helper only.

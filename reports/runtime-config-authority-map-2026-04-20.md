# Runtime Config Authority Map — 2026-04-20

## Reconciled current truth

### 1. `src/config/settings.ts`
**Status:** live, high-impact, primary app/runtime settings surface

**Direct consumers verified during the cleanup chain included:**
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
- plus other real runtime consumers discovered during the wider audit

**Judgment:** keep. This remains the primary frontend/runtime settings authority.

---

### 2. `src/utils/runtimeEnvironment.ts`
**Status:** tiny shared environment-resolution helper

**Judgment:** keep tiny. This is not a config authority.

---

## Removed from live authority during the cleanup chain
- `src/config/deploymentConfig.ts`
- `src/config/environmentManager.ts`
- `src/config/productionConfig.ts`
- `src/core/UnifiedConfigService.ts`
- `src/core/AdvancedMetricsCollector.ts`
- `src/core/SystemIntegrationProtocols.ts`
- `src/core/EnterpriseSystemOrchestrator.ts`
- `src/core/UnifiedStateManager.ts`
- `src/core/PerformanceEmergencyKit.ts`
- `src/core/ProductionReadinessGate.ts`
- `src/scripts/run-production-assessment.ts`
- `src/monitoring/metricsCollector.ts`
- `src/services/healthCheck.ts`
- `src/services/webVitals.ts`
- `src/utils/safeConsole.ts`

## Hard correction
The earlier version of this report was stale. It still described some later-removed files as surviving narrow authority surfaces.

That is no longer true.

## Current authority ranking
1. `src/config/settings.ts` — primary runtime authority
2. `src/utils/runtimeEnvironment.ts` — tiny helper only, not an authority layer

## Hard truth
The fake enterprise cluster is gone.
The wrapper/config-shim layer around it is gone.
The narrower monitoring and helper residues that temporarily survived are also gone.

`settings.ts` is the real surviving config authority in this frontend surface.

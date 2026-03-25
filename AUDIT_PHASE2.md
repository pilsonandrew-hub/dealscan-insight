## 1
Command: python -c "from backend.ingest.score import score_deal; print(score_deal)"
Status: NEEDS_RUNTIME
Output:
<stdout empty>

Stderr:
bash: python: command not found


## 2
Command: python -c "from backend.ingest.alert_gating import evaluate_alert_gate; print(evaluate_alert_gate)"
Status: NEEDS_RUNTIME
Output:
<stdout empty>

Stderr:
bash: python: command not found


## 3
Command: python -c "from backend.main import app; print([r.path for r in app.routes][:20])"
Status: NEEDS_RUNTIME
Output:
<stdout empty>

Stderr:
bash: python: command not found


## 4
Command: grep -n "ALERTS_ENABLED" webapp/routers/ingest.py | head -5
Status: PASS
Output:
2114:    if os.getenv("ALERTS_ENABLED", "false").lower() != "true":

Stderr:
<stderr empty>


## 5
Command: grep -rn "sk-or-v1\|sk-a9b4a59" webapp/routers/ingest.py | head -5
Status: PASS
Output:
webapp/routers/ingest.py:107:    "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",
webapp/routers/ingest.py:110:DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-a9b4a59a20f448349b64e39d40901284").strip()

Stderr:
<stderr empty>


## 6
Command: git grep -n "sk-or-v1\|sk-ant-\|sk-proj-\|sk-a9b4" -- "*.py" "*.ts" "*.tsx" 2>/dev/null | grep -v ".gitignore\|test\|#" | head -10
Status: PASS
Output:
webapp/routers/ingest.py:107:    "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",
webapp/routers/ingest.py:110:DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-a9b4a59a20f448349b64e39d40901284").strip()

Stderr:
<stderr empty>


## 7
Command: ls src/core/ 2>/dev/null | head -10
Status: PASS
Output:
AdvancedMetricsCollector.ts
DebugCodeCleaner.ts
EnterpriseSystemOrchestrator.ts
ErrorBoundary.tsx
InvestmentGradeSystemReport.ts
PerformanceEmergencyKit.ts
ProductionReadinessGate.ts
SimpleLogger.ts
SystemIntegrationProtocols.ts
UnifiedConfigService.ts

Stderr:
<stderr empty>


## 8
Command: grep -n "codex_write_test" webapp/routers/sniper.py
Status: PASS
Output:
625:# codex_write_test

Stderr:
<stderr empty>


## 9
Command: grep -n "Authorization.*empty\|Bearer.*empty\|getSession\|accessToken" src/services/roverAPI.ts | head -5
Status: PASS
Output:
82:      const { data: { session } } = await supabase.auth.getSession();
105:      const { data: { session } } = await supabase.auth.getSession();

Stderr:
<stderr empty>


## 10
Command: wc -l webapp/routers/ingest.py webapp/routers/sniper.py backend/ingest/score.py
Status: PASS
Output:
    3191 webapp/routers/ingest.py
     625 webapp/routers/sniper.py
      15 backend/ingest/score.py
    3831 total

Stderr:
<stderr empty>

# Self-Improvement Agents — DealerScope

## Current State
- Never disabled — just never configured
- Skills available: skill-creator, coding-agent, gh-issues, subagent-playbooks
- subagent-playbooks and codex-warmstart ARE DealerScope-specific and already in place

## What Self-Improvement Agents Could Do

### Tier 1 — Already Possible (low risk, high value)
1. **Scraper Health Agent** — heartbeat-triggered, checks all 13 actors, files GitHub issue if any fail 2+ runs in a row
2. **Score Drift Detector** — weekly agent that compares DOS distributions, alerts if average drops >5 pts (signals bad data)
3. **Dead Deal Cleaner** — daily agent prunes opportunities past auction date, keeps DB clean
4. **Audit Agent** — already running (12hr Gemini red-team via GitHub Actions)

### Tier 2 — Add Soon (medium complexity)
5. **Notion PSR Ingester** — agent that reads new PSR entries in Notion and back-fills MMR into Supabase
6. **OpenRouter Model Benchmarker** — monthly agent compares model accuracy on "why hot" rationale vs. actual outcomes
7. **Skill Updater** — uses skill-creator to review and update DealerScope skill when architecture changes

### Tier 3 — Future (when we have feedback data)
8. **Rover Tuner** — re-weights Rover affinity vectors based on actual purchase outcomes
9. **DOS Calibrator** — trains updated scoring weights when we have 50+ sale outcomes

## Recommendation
Enable Tier 1 now — they're safe, bounded, and directly useful.
Tier 2 after Manheim PSR data starts flowing in.
Tier 3 after 3 months of outcome data.

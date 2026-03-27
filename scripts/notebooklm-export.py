#!/usr/bin/env python3
"""
notebooklm-export.py
────────────────────
Exports DealerScope docs to notebooklm-export/ with all secrets redacted.
Run after any major audit, architecture change, or weekly refresh.

Usage: python3 scripts/notebooklm-export.py
"""

import re, os, glob
from datetime import datetime

OUTPUT_DIR = os.path.expanduser("~/.openclaw/workspace/notebooklm-export")
WORKSPACE = os.path.expanduser("~/.openclaw/workspace")

SECRET_PATTERNS = [
    (r'eyJhbGciOiJIUzI1NiIs[A-Za-z0-9._-]{50,}', '[SUPABASE_JWT_REDACTED]'),
    (r'apify_api_[A-Za-z0-9]{30,}', '[APIFY_TOKEN_REDACTED]'),
    (r'ghp_[A-Za-z0-9]{30,}', '[GITHUB_PAT_REDACTED]'),
    (r'sk-or-v1-[A-Za-z0-9]{50,}', '[OPENROUTER_KEY_REDACTED]'),
    (r'sk-proj-[A-Za-z0-9]{30,}', '[OPENAI_KEY_REDACTED]'),
    (r'sk-ant-[A-Za-z0-9]{30,}', '[ANTHROPIC_KEY_REDACTED]'),
    (r'ntn_[A-Za-z0-9]{30,}', '[NOTION_TOKEN_REDACTED]'),
    (r'fc-[a-f0-9]{30,}', '[FIRECRAWL_KEY_REDACTED]'),
    (r'xoxb-[0-9-]{20,}-[A-Za-z0-9]{20,}', '[SLACK_TOKEN_REDACTED]'),
    (r'AIzaSy[A-Za-z0-9_-]{33}', '[GEMINI_KEY_REDACTED]'),
    (r'crsr_[A-Za-z0-9]{50,}', '[CURSOR_KEY_REDACTED]'),
    (r'8770839167:[A-Za-z0-9_-]{35}', '[TELEGRAM_BOT_TOKEN_REDACTED]'),
    (r'sbp_[a-f0-9]{38}', '[SUPABASE_MGMT_TOKEN_REDACTED]'),
    (r'sk-a9b[A-Za-z0-9]{30,}', '[DEEPSEEK_KEY_REDACTED]'),
    (r'01e7a2ff-[a-f0-9-]{30,}', '[PERPLEXITY_KEY_REDACTED]'),
    (r'vcp_[A-Za-z0-9]{50,}', '[VERCEL_TOKEN_REDACTED]'),
    (r'440362cc-[a-f0-9-]{30,}', '[RAILWAY_TOKEN_REDACTED]'),
    (r'c5bc110a-[a-f0-9-]{30,}', '[RAILWAY_TOKEN_REDACTED]'),
    (r"ja\\'varioustheclawbot", '[DB_PASSWORD_REDACTED]'),
    (r'7529788084', '[ANDREW_TELEGRAM_ID_REDACTED]'),
    (r'pilson\.andrew@gmail\.com', '[EMAIL_REDACTED]'),
    (r'ff8425cd-[a-f0-9-]{30,}', '[ANDREW_UUID_REDACTED]'),
]

def redact(text):
    for pattern, replacement in SECRET_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text

# Core files — always included
CORE_FILES = {
    f"{WORKSPACE}/MEMORY.md": "01_MEMORY_architecture.md",
    f"{WORKSPACE}/HEARTBEAT.md": "07_HEARTBEAT_current_status.md",
    f"{WORKSPACE}/memory/dealerscope-audit-prompt-FINAL.md": "03_AUDIT_PROMPT_methodology.md",
    f"{WORKSPACE}/memory/something-later.md": "04_ROADMAP_v5_security_compliance.md",
    f"{WORKSPACE}/memory/service-integration-audit.md": "05_SERVICE_INTEGRATION_audit.md",
    f"{WORKSPACE}/memory/self-improvement-agents.md": "06_SELF_IMPROVEMENT_agents.md",
}

os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"NotebookLM Export — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"Output: {OUTPUT_DIR}\n")

# Export core files
for src, dst in CORE_FILES.items():
    if os.path.exists(src):
        with open(src) as f:
            content = redact(f.read())
        out = os.path.join(OUTPUT_DIR, dst)
        with open(out, "w") as f:
            f.write(content)
        print(f"✅ {dst}")
    else:
        print(f"⚠️  MISSING: {src}")

# Find latest audit report
audit_files = sorted(glob.glob(f"{WORKSPACE}/memory/gemini-audit-*.md"), reverse=True)
if audit_files:
    latest = audit_files[0]
    date = os.path.basename(latest).replace("gemini-audit-","").replace(".md","")
    with open(latest) as f:
        content = redact(f.read())
    out = os.path.join(OUTPUT_DIR, f"02_GEMINI_AUDIT_{date}.md")
    with open(out, "w") as f:
        f.write(content)
    print(f"✅ 02_GEMINI_AUDIT_{date}.md (latest)")

# Write index
index = f"""# DealerScope NotebookLM Source Pack
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M PT')}

## Files in this pack
1. MEMORY_architecture — Full system architecture, business rules, tech stack
2. GEMINI_AUDIT — Latest full-system security + code audit
3. AUDIT_PROMPT_methodology — What was audited and how
4. ROADMAP_v5 — Security & compliance upgrade plan
5. SERVICE_INTEGRATION — OpenRouter/Notion/Slack/Firecrawl status
6. SELF_IMPROVEMENT_agents — Agent automation roadmap
7. HEARTBEAT — Current system status, open items, backlog

## Suggested NotebookLM Queries
- "What are the highest-risk open items right now?"
- "Generate an executive audio briefing on DealerScope status"
- "What business rules are most at risk of being violated?"
- "Summarize all open action items"
- "What has been fixed vs what is still open from the audit?"
- "Explain the DealerScope scoring formula in plain English"
- "What would happen if the scrapers went down?"

## All secrets have been redacted from this export.
"""
with open(os.path.join(OUTPUT_DIR, "00_INDEX.md"), "w") as f:
    f.write(index)

print(f"\n✅ 00_INDEX.md")
print(f"\n📦 {len(os.listdir(OUTPUT_DIR))} files ready in {OUTPUT_DIR}")
print("Upload all files to NotebookLM at: https://notebooklm.google.com")

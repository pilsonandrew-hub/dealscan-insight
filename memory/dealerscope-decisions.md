# Architecture Decisions

## 2026-03-11
- backend/main.py = canonical entrypoint (not webapp/main.py)
- Rover = FastAPI module (not separate microservice)
- Alert control plane = FastAPI direct Telegram
- Ingest contract = Apify dataset webhook only
- ALERTS_ENABLED defaults to false
- One canonical record per vehicle (earliest close date)
- Dedup: VIN-first SHA256, fuzzy fallback ±2500 mileage bucket
- SniperScope buyer premium: algebraic formula (% of bid, not % of MMR)
- Alert routing: FastAPI = sole deal alert control plane. OpenClaw Telegram = Andrew/Ja'various chat only. Never route deal alerts through OpenClaw.

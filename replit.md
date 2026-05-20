> **Historical/planning snapshot — not current production truth.**
> Retained for context only. Do not use this file as live evidence that DealerScope is production-ready, V1-complete, enterprise-ready, or deployment-approved. Current truth must come from live code, live Railway/Vercel/Supabase state, current CI, and governed status reports.

# DealerScope on Replit

## Setup Instructions

1. **Install Dependencies**
   ```bash
   npm install
   ```

2. **Environment Variables**
   - Add your Supabase URL and anon key in the Secrets tab
   - Required: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`

3. **Run the Application**
   ```bash
   npm run dev
   ```

## Features
- Vehicle arbitrage analysis platform
- Real-time deal notifications
- Government auction monitoring
- Mobile-friendly interface

## Replit-Specific Notes
- Uses Vite for fast development
- Port 8080 is configured for Cloud Run compatibility
- All dependencies are production-ready
Here's a synthesized master build plan for DealerScope, combining the architect recommendations into a clean, actionable structure.

---

# DealerScope Master Build Plan

**Overall Strategy:**
Prioritize security, then data/schema changes, then backend logic for new features, finally frontend UI. Minimize manual intervention by Codex/Claude through clear, concrete instructions.

## 1. PHASE 1 (Security — build first, blocks everything else)

### C-01: Hardcoded API keys in Apify actors

**Goal:** Remove sensitive API keys from code and inject via Apify Input or Environment Variables.

**Files, Functions, Changes:**

1.  **`apify/actors/ds-jjkane/src/main.js`**
    *   **Change:** Locate and replace hardcoded `ALGOLIA_API_KEY` and `MARKETCHECK_API_KEY` assignments.
    *   **Details:**
        ```javascript
        // BEFORE:
        // const ALGOLIA_API_KEY = "your-hardcoded-algolia-key";
        // const MARKETCHECK_API_KEY = "your-hardcoded-marketcheck-key";

        // AFTER:
        const input = await Actor.getInput() || {};
        const ALGOLIA_API_KEY = input.algoliaApiKey || process.env.ALGOLIA_API_KEY;
        const MARKETCHECK_API_KEY = input.marketcheckApiKey || process.env.MARKETCHECK_API_KEY;

        if (!ALGOLIA_API_KEY) throw new Error('Missing Algolia API Key');
        if (!MARKETCHECK_API_KEY) throw new Error('Missing Marketcheck API Key');
        ```
    *   **Impact:** Ensures keys are dynamically loaded, not committed to git.

2.  **`apify/actors/ds-allsurplus/src/main.js`**
    *   **Change:** Locate and replace hardcoded `MAESTRO_API_KEY` and `MAESTRO_ACCOUNT_ID` Assignments.
    *   **Details:**
        ```javascript
        // BEFORE:
        // const MAESTRO_API_KEY = "your-hardcoded-maestro-key";
        // const MAESTRO_ACCOUNT_ID = "your-hardcoded-account-id";

        // AFTER:
        const input = await Actor.getInput() || {};
        const MAESTRO_API_KEY = input.maestroApiKey || process.env.MAESTRO_API_KEY;
        const MAESTRO_ACCOUNT_ID = input.maestroAccountId || process.env.MAESTRO_ACCOUNT_ID;

        if (!MAESTRO_API_KEY) throw new Error('Missing Maestro API Key');
        if (!MAESTRO_ACCOUNT_ID) throw new Error('Missing Maestro Account ID');
        ```
    *   **Impact:** Same as above for AllSurplus actor.

3.  **`apify/actors/ds-jjkane/.actor/input_schema.json`**
    *   **Change:** Add definitions for `algoliaApiKey`, `marketcheckApiKey`, and `webhookSecret`.
    *   **Details:**
        ```json
        {
          // ... existing schema ...
          "properties": {
            "algoliaApiKey": {
              "type": "string",
              "title": "Algolia API Key",
              "description": "API Key for Algolia integration.",
              "editor": "password",
              "nullable": true
            },
            "marketcheckApiKey": {
              "type": "string",
              "title": "Marketcheck API Key",
              "description": "API Key for Marketcheck integration.",
              "editor": "password",
              "nullable": true
            },
            "webhookSecret": {
              "type": "string",
              "title": "Webhook Secret",
              "description": "Secret for authenticating webhook calls to the backend.",
              "editor": "password",
              "nullable": true
            }
          }
        }
        ```
    *   **Impact:** Allows configuration via Apify UI for secrets.

4.  **`apify/actors/ds-allsurplus/.actor/input_schema.json`**
    *   **Change:** Add definitions for `maestroApiKey` and `maestroAccountId`.
    *   **Details:** Similar to `ds-jjkane`, using `editor: "password"` for `maestroApiKey`.

### C-08: Webhook header mismatch

**Goal:** Ensure the Apify actor sends the correct header name for backend webhook authentication.

**Files, Functions, Changes:**

1.  **`apify/actors/ds-jjkane/src/main.js`**
    *   **Change:** Find the outbound HTTP request (e.g., `fetch` or Apify utility call) that sends the webhook to DealerScope's backend. Modify the header used for the secret.
    *   **Details:** Locate the `headers` object in the webhook sending logic.
        ```javascript
        // BEFORE:
        // headers: {
        //   'Content-Type': 'application/json',
        //   'x-webhook-secret': webhookSecret, // Incorrect header name
        // }

        // AFTER:
        headers: {
          'Content-Type': 'application/json',
          'X-Apify-Webhook-Secret': webhookSecret, // Correct header name
        }
        ```
    *   **Impact:** Webhooks will now be correctly authenticated by the DealerScope backend.

### C-02: Ownership enforcement on outcome creation

**Goal:** Prevent users from creating outcomes for opportunities they do not own.

**Files, Functions, Changes:**

1.  **`webapp/routers/outcomes.py`**
    *   **Function:** `create_outcome` (likely endpoint `POST /opportunities/{opportunity_id}/outcomes`)
        *   **Change:** Before any database write, call `_fetch_opportunity` requiring `user_id`.
        *   **Details:**
            ```python
            # ... imports and boilerplate ...
            from ..dependencies import _fetch_opportunity # Ensure this is imported

            @router.post("/opportunities/{opportunity_id}/outcomes", response_model=OutcomeRead)
            async def create_outcome(
                opportunity_id: int,
                outcome_create: OutcomeCreate,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user), # Assumes valid auth
            ):
                # ADD THIS LINE:
                # This will raise HTTPException(404 or 403) if not found or not owned
                _fetch_opportunity(db, opportunity_id, require_user_id=current_user.id)

                # ... existing outcome creation logic ...
                db_outcome = crud.create_outcome(db=db, outcome=outcome_create, user_id=current_user.id, opportunity_id=opportunity_id)
                return db_outcome
            ```
    *   **Function:** `create_bid_outcome` (likely endpoint `POST /opportunities/{opportunity_id}/bid-outcomes`)
        *   **Change:** Apply the same `_fetch_opportunity` check.
        *   **Details:**
            ```python
            # ...
            @router.post("/opportunities/{opportunity_id}/bid-outcomes", response_model=OutcomeRead)
            async def create_bid_outcome(
                opportunity_id: int,
                bid_outcome_create: BidOutcomeCreate,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user),
            ):
                # ADD THIS LINE:
                _fetch_opportunity(db, opportunity_id, require_user_id=current_user.id)

                # ... existing bid outcome creation logic ...
                db_bid_outcome = crud.create_bid_outcome(db=db, bid_outcome=bid_outcome_create, user_id=current_user.id, opportunity_id=opportunity_id)
                return db_bid_outcome
            ```
    *   **Impact:** Stronger data integrity and security by preventing unauthorized outcome creation.

### C-03: Auth on `/outcomes/summary`

**Goal:** Secure the `/outcomes/summary` endpoint, requiring user authentication.

**Files, Functions, Changes:**

1.  **`webapp/routers/outcomes.py`**
    *   **Function:** `get_outcomes_summary` (likely endpoint `GET /outcomes/summary`)
        *   **Change:** Add a dependency to inject `current_user`, which implicitly handles authentication.
        *   **Details:**
            ```python
            # ... imports ...
            from fastapi import Depends, APIRouter, Header, HTTPException
            from .dependencies import get_db, get_current_user # Ensure get_current_user is imported

            @router.get("/outcomes/summary")
            async def get_outcomes_summary(
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user), # ADD THIS DEPENDENCY
                # authorization: str = Header(...), # Remove this if get_current_user handles token extraction
            ):
                # Now `current_user` is readily available, and the function
                # will only execute if the user is authenticated.
                # If the current implementation uses authorization: str = Header(...) and then _verify_auth(authorization),
                # replace that with Depends(get_current_user).
                # Example:
                # current_user = _verify_auth(authorization) # REMOVE THIS LINE
                summary_data = crud.get_user_outcomes_summary(db=db, user_id=current_user.id) # Ensure this uses user_id
                return summary_data
            ```
    *   **Impact:** The summary endpoint is now protected, only accessible by authenticated users.

## 2. PHASE 2 (DB Migration — before scoring changes)

**Goal:** Extend the `opportunities` table to support the new scoring and lane system.

**Exact SQL:**

```sql
-- Add new columns for the 2-Lane Tier System to the 'opportunities' table
ALTER TABLE opportunities
ADD COLUMN IF NOT EXISTS designated_lane VARCHAR(20) DEFAULT 'unassigned' NOT NULL, -- e.g., 'premium', 'standard', 'rejected'
ADD COLUMN IF NOT EXISTS dos_premium DECIMAL(5,2), -- DOS score calculated with Premium weights
ADD COLUMN IF NOT EXISTS dos_standard DECIMAL(5,2), -- DOS score calculated with Standard weights
ADD COLUMN IF NOT EXISTS risk_flags JSONB DEFAULT '{}'::jsonb NOT NULL, -- JSON object for various risk indicators
ADD COLUMN IF NOT EXISTS vehicle_tier VARCHAR(50) DEFAULT 'unknown' NOT NULL, -- e.g., 'premium', 'standard', 'rejected', 'unsuitable'
ADD COLUMN IF NOT EXISTS ai_confidence_score DECIMAL(3,2), -- AI model confidence score (0.00 to 1.00)
ADD COLUMN IF NOT EXISTS bid_ceiling DECIMAL(10,2), -- Recommended maximum bid amount
ADD COLUMN IF NOT EXISTS min_margin_target DECIMAL(10,2); -- Target minimum margin for deal profitability

-- Create an index to optimize queries fetching opportunities by lane
CREATE INDEX IF NOT EXISTS idx_opportunities_designated_lane ON opportunities (designated_lane);

-- Optional: Add an index for potentially efficient filtering by vehicle_tier or combined DOS scores
CREATE INDEX IF NOT EXISTS idx_opportunities_scoring ON opportunities (vehicle_tier, dos_premium, dos_standard);

-- Optional: Initial data backfill for existing opportunities
-- This will assign a basic designated_lane and vehicle_tier based on a simplified rule
-- Current_date is a placeholder - actual date logic should be defined
UPDATE opportunities
SET
    designated_lane = CASE
        WHEN year IS NOT NULL AND (EXTRACT(YEAR FROM CURRENT_DATE) - year) <= 4 THEN 'premium' -- Cars <= 4 model years old
        WHEN year IS NOT NULL AND (EXTRACT(YEAR FROM CURRENT_DATE) - year) <= 10 THEN 'standard' -- Cars 5-10 model years old
        ELSE 'unassigned' -- Default for older or unclassified vehicles
    END,
    vehicle_tier = CASE
        WHEN year IS NOT NULL AND (EXTRACT(YEAR FROM CURRENT_DATE) - year) <= 4 AND mileage < 75000 THEN 'premium'
        WHEN year IS NOT NULL AND (EXTRACT(YEAR FROM CURRENT_DATE) - year) <= 10 AND mileage < 150000 THEN 'standard'
        WHEN year IS NOT NULL AND (EXTRACT(YEAR FROM CURRENT_DATE) - year) > 10 THEN 'rejected'
        WHEN mileage > 200000 THEN 'rejected'
        ELSE 'unsuitable' -- General unsuitable category
    END
WHERE
    designated_lane = 'unassigned' OR vehicle_tier = 'unknown'; -- Only update if not already set by this or previous logic
```

## 3. PHASE 3 (Scoring split — backend)

**Goal:** Implement the new 2-lane scoring logic, calculate `DOS_Premium`, `DOS_Standard`, `vehicle_tier`, `risk_flags`, `AI_Confidence`, `bid_ceiling`, and `min_margin_target`, and persist these to the DB.

### 3.1. DTO/Schema Updates

**Files, Functions, Changes:**

1.  **`webapp/schemas/opportunity.py` (Pydantic models)**
    *   **Change:** Add new fields to `OpportunityBase` or `OpportunityCreate` / `OpportunityRead`.
    *   **Details:**
        ```python
        from pydantic import BaseModel, root_validator
        from typing import Optional, Dict, Any

        class OpportunityBase(BaseModel):
            # ... existing fields ...
            designated_lane: str = "unassigned" # Added
            dos_premium: Optional[float] = None # Added
            dos_standard: Optional[float] = None # Added
            risk_flags: Dict[str, Any] = {} # Added, using Dict for JSONB
            vehicle_tier: str = "unknown" # Added
            ai_confidence_score: Optional[float] = None # Added
            bid_ceiling: Optional[float] = None # Added
            min_margin_target: Optional[float] = None # Added

            class Config:
                orm_mode = True # For SQLAlchemy ORM

        # Ensure OpportunityRead and OpportunityInDB also inherit these fields
        class OpportunityRead(OpportunityBase):
            id: int
        ```
    *   **Impact:** Enables FastAPI to receive, validate, and serialise the new scoring data.

### 3.2. Scoring Logic Implementation

**Files, Functions, Changes:**

1.  **`backend/ingest/score.py` (New or existing scoring module)**
    *   **Function:** `score_deal(vehicle_data: Dict[str, Any]) -> Dict[str, Any]` (Create this function or update an existing one).
    *   **Details:**
        ```python
        import datetime
        from typing import Dict, Any

        def _calculate_base_tier(vehicle_data: Dict[str, Any]) -> str:
            current_year = datetime.datetime.now().year
            year = vehicle_data.get('year')
            mileage = vehicle_data.get('mileage')

            if not year or not mileage:
                return "unsuitable" # Cannot classify without basic data

            model_years_old = current_year - year

            if model_years_old > 10 or mileage > 200000:
                return "rejected"
            elif model_years_old <= 4 and mileage < 100000: # Example logic for Premium
                return "premium"
            elif model_years_old <= 10 and mileage < 175000: # Example logic for Standard
                return "standard"
            else:
                return "unsuitable" # Fallback for edge cases not fitting premium/standard
        
        def _compute_dos_weights(vehicle_data: Dict[str, Any], tier: str) -> float:
            """
            Calculates DOS based on the vehicle tier and predefined weights.
            Assume `vehicle_data` contains all necessary attributes (MMR_Proximity, Demand_Velocity, etc.)
            which are pre-calculated or extracted from raw data.
            """
            # Placeholder values; replace with actual data extraction/calculation
            mmr_proximity = vehicle_data.get('mmr_proximity', 0.0) # Assume 0-1 scale
            demand_velocity = vehicle_data.get('demand_velocity', 0.0) # Assume 0-1 scale
            low_mileage_factor = 1.0 if vehicle_data.get('mileage', 0) < 50000 else 0.5 # Example
            condition_score = vehicle_data.get('condition_score', 0.5) # Assume 0-1 scale
            freshness_score = vehicle_data.get('freshness_score', 0.5) # Assume 0-1 scale
            net_margin_factor = vehicle_data.get('net_margin_factor', 0.5) # e.g., (actual_margin / target_margin)
            discount_pct_factor = vehicle_data.get('discount_pct_factor', 0.5)
            wholesale_velocity = vehicle_data.get('wholesale_velocity', 0.0)
            risk_score_component = vehicle_data.get('risk_score_component', 0.0) # Higher means worse
            recon_efficiency = vehicle_data.get('recon_efficiency', 0.5)

            if tier == 'premium':
                dos = (mmr_proximity * 0.40) + \
                      (demand_velocity * 0.25) + \
                      (low_mileage_factor * 0.15) + \
                      (condition_score * 0.10) + \
                      (freshness_score * 0.10)
                return min(max(dos, 0.0), 1.0) # Clamp between 0 and 1
            elif tier == 'standard':
                dos = (net_margin_factor * 0.35) + \
                      (discount_pct_factor * 0.25) + \
                      (wholesale_velocity * 0.20) + \
                      ((1 - risk_score_component) * 0.15) + \
                      (recon_efficiency * 0.05)
                return min(max(dos, 0.0), 1.0)
            else: # For 'rejected', 'unsuitable' or 'unassigned', DOS may be low or N/A
                return 0.0

        def _calculate_risk_flags(vehicle_data: Dict[str, Any], tier: str) -> Dict[str, bool]:
            risk_flags = {}
            mileage = vehicle_data.get('mileage', 0)
            year = vehicle_data.get('year', datetime.datetime.now().year)
            current_date = datetime.datetime.now()
            days_on_market = (current_date - datetime.datetime.fromisoformat(vehicle_data.get('listing_date', current_date.isoformat()))).days # Example
            
            # Example risk criteria for Premium vs Standard
            if tier == 'premium':
                risk_flags['over_mileage'] = mileage > 75000 or (mileage / (current_date.year - year + 1)) > 15000
                risk_flags['long_dom'] = days_on_market > 45
            elif tier == 'standard':
                risk_flags['over_mileage'] = mileage > 150000 or (mileage / (current_date.year - year + 1)) > 20000
                risk_flags['long_dom'] = days_on_market > 90
            
            # General risks
            risk_flags['accident_history'] = vehicle_data.get('has_accident', False)
            risk_flags['salvage_title'] = vehicle_data.get('is_salvage', False)
            risk_flags['low_projected_margin'] = vehicle_data.get('projected_margin_usd', 0) < 1000 # Placeholder

            return risk_flags

        def score_deal(vehicle_data: Dict[str, Any]) -> Dict[str, Any]:
            """
            Main function to calculate all new scoring metrics for a vehicle.
            """
            scoring_results = {}

            # 1. Determine vehicle_tier
            vehicle_tier = _calculate_base_tier(vehicle_data)
            scoring_results['vehicle_tier'] = vehicle_tier

            # 2. Calculate DOS scores based on tier
            dos_premium = _compute_dos_weights(vehicle_data, 'premium')
            dos_standard = _compute_dos_weights(vehicle_data, 'standard')
            scoring_results['dos_premium'] = dos_premium
            scoring_results['dos_standard'] = dos_standard

            # 3. Determine designated_lane
            # If rejected/unsuitable, no specific lane. Otherwise, assign based on calculated tier.
            if vehicle_tier in ['rejected', 'unsuitable']:
                scoring_results['designated_lane'] = 'unassigned'
            else:
                scoring_results['designated_lane'] = vehicle_tier

            # 4. Calculate risk flags
            risk_flags = _calculate_risk_flags(vehicle_data, vehicle_tier)
            scoring_results['risk_flags'] = risk_flags

            # 5. Determine AI Confidence Score (Placeholder)
            # This would come from an actual ML model prediction, for now, a heuristic.
            if vehicle_tier == 'premium' and dos_premium > 0.7:
                scoring_results['ai_confidence_score'] = 0.85
            elif vehicle_tier == 'standard' and dos_standard > 0.6:
                scoring_results['ai_confidence_score'] = 0.70
            else:
                scoring_results['ai_confidence_score'] = 0.50 # Lower confidence for unclassified/low score

            # 6. Calculate Bid Ceiling and Min Margin Target
            if vehicle_tier == 'premium':
                scoring_results['bid_ceiling'] = vehicle_data.get('mmr_value', 0) * 0.88
                scoring_results['min_margin_target'] = 2500.0
            elif vehicle_tier == 'standard':
                scoring_results['bid_ceiling'] = vehicle_data.get('mmr_value', 0) * 0.80
                scoring_results['min_margin_target'] = 1500.0
            else:
                scoring_results['bid_ceiling'] = 0.0 # No bid recommended
                scoring_results['min_margin_target'] = 0.0

            return scoring_results
        ```
    *   **Impact:** Centralized logic for comprehensive scoring.

### 3.3. Ingest Pipeline Integration and Persistence

**Files, Functions, Changes:**

1.  **`webapp/routers/ingest.py` (Ingestion endpoint)**
    *   **Function:** `ingest_vehicle(raw_data: Dict[str, Any], ...) -> OpportunityRead`
    *   **Change:** After raw data is normalized/parsed into a `vehicle_data` dictionary, call `score_deal` and update the `opportunity_create` object before saving.
    *   **Details:**
        ```python
        # ... imports ...
        from backend.ingest.score import score_deal # Import the new scoring function
        from webapp.schemas.opportunity import OpportunityCreate # Import updated schema

        @router.post("/ingest-vehicle", response_model=OpportunityRead)
        async def ingest_vehicle(
            raw_data: Dict[str, Any],
            db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user), # Assuming ingestion is authenticated
        ):
            # 1. Normalize/Parse raw_data into a structured dictionary for scoring
            #    (This step is assumed to exist or needs to be built)
            normalized_vehicle_data = normalize_raw_data(raw_data) # Placeholder function

            # 2. Call the new scoring function
            scoring_results = score_deal(normalized_vehicle_data)

            # 3. Create an OpportunityCreate object using normalized data and scoring results
            opportunity_create_data = OpportunityCreate(
                # ... Populate existing fields from normalized_vehicle_data ...
                year=normalized_vehicle_data.get('year'),
                make=normalized_vehicle_data.get('make'),
                model=normalized_vehicle_data.get('model'),
                mileage=normalized_vehicle_data.get('mileage'),
                # Add new scoring fields:
                designated_lane=scoring_results['designated_lane'],
                dos_premium=scoring_results['dos_premium'],
                dos_standard=scoring_results['dos_standard'],
                risk_flags=scoring_results['risk_flags'],
                vehicle_tier=scoring_results['vehicle_tier'],
                ai_confidence_score=scoring_results['ai_confidence_score'],
                bid_ceiling=scoring_results['bid_ceiling'],
                min_margin_target=scoring_results['min_margin_target'],
                # ... other fields ...
            )

            # 4. Save to DB
            db_opportunity = crud.create_opportunity(db=db, opportunity=opportunity_create_data, user_id=current_user.id)
            return db_opportunity
        ```
    *   **Impact:** Automated scoring and persistence of results during the ingestion process.

### 3.4. API Exposure

**Goal:** Make the new scoring data available via the existing JSON API for opportunities.

**Files, Functions, Changes:**

1.  **`webapp/routers/opportunities.py` (Main opportunities endpoint)**
    *   **Function:** `get_opportunity(opportunity_id
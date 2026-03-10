# How DealerScope Works

## Mission

DealerScope is a wholesale vehicle arbitrage intelligence platform. Its purpose is to identify underpriced vehicles at public auto auctions and calculate the exact margin available before a single bid is placed.

---

## The Theory: The MMR Gap

Public auction sellers — private owners, small dealers, fleet liquidators — price vehicles without access to Manheim Market Report (MMR) data. MMR is the wholesale benchmark used by professional buyers. When a seller doesn't know their car is worth $18,000 wholesale, they may start it at $13,500. That $4,500 gap is the arbitrage opportunity.

DealerScope automates the detection of this gap at scale across multiple auction sources simultaneously.

---

## The Flow

```
Apify Scraper
     |
     v
Five-Layer Filter
     |
     v
DOS Score Calculation
     |
     v
Alert (fire / strong buy / watch)
     |
     v
Buy at Auction
     |
     v
Sell Wholesale / Retail
```

1. **Apify scrapes** auction listings from IAAI, Copart, Manheim, and regional platforms
2. **Five-Layer Filter** eliminates bad deals immediately
3. **DOS Score** quantifies the opportunity on a 0–100 scale
4. **Alert** is fired based on score threshold
5. **Buyer acts** — places bid with known all-in cost
6. **Sell** at MMR or retail depending on condition and market timing

---

## The Formula

### All-In Cost

```
All-In Cost = Bid Price + Buyer Premium + Auction Fees + Transport + Recon
```

| Component      | Typical Range     |
|----------------|-------------------|
| Buyer Premium  | 5–10% of bid      |
| Auction Fees   | $150–$500         |
| Transport      | $200–$900         |
| Recon          | $0–$2,500         |

### Margin

```
Margin = MMR - All-In Cost
```

A positive margin means the deal is viable. DealerScope only surfaces deals where Margin > configurable floor (default: $1,500).

---

## The Three Modules

### 1. Crosshair (Active Search)

The buyer knows what they want. Crosshair lets them define a precise vehicle spec — year range, make/model, mileage cap, target states — and immediately surfaces live matching opportunities with DOS scores and margin estimates.

**Use case:** "I want a 2019–2021 F-150 XLT 4WD under 60k miles from TX, OK, or AZ."

### 2. SniperScope (Bid Execution)

Once a target is identified, SniperScope calculates the maximum defensible bid. It takes the MMR, subtracts all-in costs, and returns the bid ceiling that preserves the target margin.

**Formula:**
```
Max Bid = MMR - Buyer Premium - Fees - Transport - Recon - Target Margin
```

### 3. Rover (Passive AI)

Rover runs in the background. It learns from saved intents and bidding behavior, then proactively surfaces opportunities that match your pattern — even ones you didn't search for. It refreshes every 5 minutes and fires alerts when high-score deals appear.

**Use case:** Set a minimum DOS score of 75 and go about your day. Rover alerts you when something fires.

---

## Five-Layer Filter

All listings pass through five gates before receiving a DOS score. Failing any gate removes the listing.

| Gate | Name             | Description                                                  |
|------|------------------|--------------------------------------------------------------|
| 1    | Title Check      | Clean title only. Salvage, rebuilt, or flood titles rejected |
| 2    | Mileage Gate     | Over 120,000 miles rejected by default                       |
| 3    | Margin Floor     | Calculated margin must exceed minimum threshold              |
| 4    | Rust/Region Gate | High-rust states (MI, OH, PA, NY, IL) flagged or excluded   |
| 5    | Damage Filter    | Structural, frame, or airbag damage triggers rejection       |

---

## DOS Score Thresholds

| Score Range | Rating      | Action                            |
|-------------|-------------|-----------------------------------|
| 90–100      | Fire        | Immediate alert, bid aggressively |
| 80–89       | Strong Buy  | High priority, act same day       |
| 65–79       | Watch       | Monitor, verify condition         |
| Under 65    | Pass        | Not surfaced to user              |

---

## Target Vehicles

DealerScope is tuned for the highest-liquidity wholesale segments:

- **Trucks:** F-150, Silverado 1500, Ram 1500, Tacoma, Tundra
- **Mid-SUVs:** Explorer, Equinox, CR-V, RAV4, Traverse
- **CPO-eligible:** Under 5 years old, under 60k miles, clean title
- **Low-rust states preferred:** TX, AZ, NM, NV, FL, CA, CO

Luxury, exotic, and high-salvage vehicles are outside the primary target set.

---

## Summary

DealerScope exists to answer one question before every auction: **"Is this vehicle priced below what the wholesale market will pay for it?"** Every feature in the platform — Crosshair, SniperScope, Rover, the Five-Layer Filter, the DOS score — serves that single question.

# Dealerscope  
  
**DealerScope Variable Management Update: Synthesizing Industry‑Best Metrics and Variance Bands**  
  
**Introduction**  
  
Large dealership groups have moved beyond simple age‑based inventory rules and are using **variable management** frameworks to evaluate each used vehicle like a financial asset.  Platforms such as vAuto’s ProfitTime GPS combine **Cost to Market (CtM), Market Days Supply (MDS)** and **retail sales volume** to assign an investment score to every vehicle.  This report consolidates insights from major dealership analytics (ProfitTime GPS, Provision letter grades, Manheim’s MMR range) and synthesizes them into a single framework to help **DealerScope** refine its bidding strategies and “variance bands.”  
  
The metrics and strategies below draw on public sources to explain how big dealers grade vehicles.  Where specific numbers were unavailable in public documentation, recommended ranges are informed by the approaches described in the provided Grok, Gemini and Claude briefings.  
  
**Core Metrics Used by Top Dealerships**  
  
**Cost to Market (CtM)**  
	•	**Definition:** CtM compares the total investment in the vehicle (purchase price, auction fees, reconditioning, transportation and packing) to the average retail asking price for identical vehicles in the market.  A lower CtM means the dealer acquired the car well below its retail value【187741809733906†L145-L147】.  
	•	**Formula:**  
CtM = \frac{\text{All‑in acquisition cost}}{\text{Average retail asking price}} \times 100  
	•	**Interpretation:** Dealers strive to maintain CtM below ~85 % to leave room for gross profit.  CtM above ~92 % indicates that the vehicle was bought at or near retail value and offers little margin.  
	•	**Why it matters:** CtM is the core measure of **price advantage**.  Incorporating live retail comps rather than just Manheim MMR values makes CtM a more accurate gauge of the spread between wholesale cost and retail opportunity.  Vehicles from government auctions should consistently yield lower CtM percentages because they lack retail competition.  
  
**Market Days Supply (MDS)**  
	•	**Definition:** MDS measures how long it would take to sell the existing inventory of a specific year/make/model at the current sales rate.  It is calculated as the ratio of current supply to the average daily sales rate【420557916877120†L31-L37】.  
	•	**Formula:**  
\text{MDS} = \frac{\text{Current inventory}}{\text{Average daily sales}}  
	•	**Interpretation:** Low MDS indicates high demand and quick turn rates, whereas high MDS signals saturated inventory and slower sales.  Dealership guides typically view **<30 days** as “hot,” **30–45 days** as normal, **45–60 days** as soft and **>60 days** as cold.  
	•	**Impact on pricing:** Vehicles with high MDS may require price reductions or incentives, while low‑MDS vehicles can sustain higher pricing【420557916877120†L59-L62】.  MDS should never be evaluated alone—combining it with CtM and retail sales volume avoids false signals from scarce but unpopular vehicles.  
  
**Retail Sales Volume (RSV)**  
	•	**Definition:** RSV measures how many units of a specific vehicle actually sold at retail in the last 30–60 days.  Dale Pollak notes that ProfitTime’s investment score uses retail sales volume along with CtM and MDS to determine a vehicle’s return potential【906985539822198†L49-L53】.  
	•	**Interpretation:** High RSV confirms genuine consumer demand.  Low RSV could indicate a niche model or simply poor desirability.  When MDS is low but RSV is also low, scarcity may reflect low demand rather than a hot market.  
	•	**Data sources:** Dealers derive RSV from retail listing platforms (AutoTrader/Kelley Blue Book) and sale‑through rates from Manheim.  Adding RSV to DealerScope’s algorithm prevents false positives created by low supply alone.  
  
**Manheim MMR Range**  
	•	**Definition:** Manheim’s Market Report (MMR) range is a **confidence interval** around the mid‑MMR value.  It represents the probability that **70 % of similar vehicles will sell within the high‑and‑low band**【207089475371143†L304-L307】.  A narrow range indicates a predictable market; a wide range indicates uncertainty.  
	•	**Use in bidding:** Dealers treat MMR range width as a proxy for pricing risk.  Tight ranges (<8–10 % spread) justify bidding closer to the mid‑MMR because outcomes are predictable; wide ranges (>15 %) require deeper discounts.  
	•	**Implementation:** DealerScope can integrate MMR high/low values into a **variance score** that adjusts bid ceilings based on range width, odometer adjustments, region and vehicle condition (e.g., AutoGrade scores).  
  
**Price to Market and ROI per Day**  
  
While not as heavily documented, high‑performing dealers monitor **Price to Market** (selling price vs. market price) and **ROI per Day** (expected gross profit divided by projected days to sale).  These metrics help them decide when to hold a Platinum‑grade vehicle longer (because gross per day remains high) and when to cut prices on low‑grade inventory.  
  
**Investment Grades (“Precious Metals”)**  
  
Dealerships categorize vehicles into **Platinum**, **Gold**, **Silver** and **Bronze** bands based on CtM, MDS and RSV.  Each grade dictates pricing strategy and allowed time on lot.  Thresholds may vary by market, but typical ranges are:  
  

| Grade | Approximate CtM (% of retail) | MDS (days) | RSV | Strategy | Comments |
| -------- | ----------------------------- | ------------ | ------------- | ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Platinum | ≤ 85 % | < 30 days | High | Price above market; hold up to 50 – 60 days | These “unicorn” vehicles carry the most profit potential and attract aggressive bidding from franchise dealers. |
| Gold | 85 – 90 % | 30 – 40 days | Moderate–High | Price near market; aim for 30–40‑day turn | Bread‑and‑butter vehicles. |
| Silver | 90 – 95 % | 40 – 55 days | Average | Price slightly below market; turn within 20 – 30 days | Dealers often buy these for F&I upsells rather than front‑end profit. |
| Bronze | ≥ 95 % | > 55 days | Low | Price aggressively below market; sell quickly or pass | Low demand and high supply; dealers hold these only to drive traffic or trades. |
  
  
*Note:* these thresholds come from aggregating public insights and may need adjusting for local markets.  
  
**Segment Tiers and Demand Insights**  
  
An optimized strategy also weights vehicles differently based on segment demand.  High‑volume trucks and SUVs generally command higher margins and faster turns, while sedans, EVs and luxury cars often exhibit slower demand and higher reconditioning costs.  A suggested tiering:  
	1.	**Tier 1 – Maximum demand:** full‑size pickup trucks (F‑150, Silverado, Ram 1500), compact/mid‑size SUVs (Rogue, RAV4, CR‑V, Tucson) and luxury SUVs.  These segments have strong MDS and RSV signals.  
	2.	**Tier 2 – Strong demand:** mid‑size trucks (Tacoma, Ranger), full‑size SUVs (Tahoe, Suburban, Expedition) and any vehicle under US$15 K.  Demand is healthy but supply is higher.  
	3.	**Tier 3 – Selective:** sedans and EVs (except high‑demand Tesla Model 3/Y).  Demand is niche; only pursue with exceptional CtM.  
	4.	**Tier 4 – Avoid unless exceptional:** luxury sedans, sports cars and heavy commercial vehicles.  These carry high depreciation and narrow buyer pools.  
  
DealerScope should assign **segment multipliers** to its scores so that Platinum‑grade trucks receive more weight than Platinum sedans.  
  
**Recommended Enhancements to DealerScope’s Scoring Formula**  
  
Currently, DealerScope’s Day‑of‑Sale (DOS) score weights margin (35 %), velocity (25 %), segment (20 %), model (12 %) and source (8 %).  To align with variable‑management best practices, the scoring formula should emphasise investment fundamentals and time‑weighted returns.  A proposed weighting:  
	•	**Investment Grade (30 %)** – composite of CtM, MDS and RSV, assigning Platinum/Gold/Silver/Bronze grades.  
	•	**ROI per Day Projection (20 %)** – expected gross profit divided by estimated days to sale; prioritises fast‑turn, high‑margin vehicles.  
	•	**Segment Tier (15 %)** – weights vehicles by demand tier.  
	•	**MMR Confidence/Range Width (10 %)** – rewards vehicles with tight MMR ranges.  
	•	**Transport Cost Factor (10 %)** – penalises vehicles that are far from your location or require high transport cost.  
	•	**Source Reliability (10 %)** – adjusts scores based on auction or government channel reliability.  
	•	**Time Pressure (5 %)** – gives a small boost to auctions ending soon, ensuring you act before others.  
  
DealerScope can also introduce **flexible bid ceilings** instead of a fixed 88 % MMR cap.  Suggested variance bands:  
  

| Investment Grade | MMR Range Width | Segment | Recommended All‑in Bid Ceiling |
| ---------------- | --------------------- | -------- | ------------------------------ |
| Platinum | Tight (<8 %) | Tier 1/2 | up to 95 % of MMR |
| Platinum | Wide (>15 %) | any | ≤ 90 % of MMR |
| Gold | Tight/Medium (8–15 %) | Tier 1/2 | 88 – 92 % of MMR |
| Silver | Any | any | ≤ 85 % of MMR |
| Bronze | Any | any | ≤ 80 % of MMR |
  
  
  
These bands mirror how big dealers adjust appraisal ranges based on profit potential and MMR confidence.  
  
**Implementation Recommendations for Codex**  
	1.	**Integrate CtM, MDS and RSV:** Use data feeds (AutoTempest, JDPower, Manheim sale‑through rates) to compute each metric.  Calculate CtM against live retail asking prices【187741809733906†L145-L147】 rather than MMR alone.  Evaluate MDS weekly using the formula【420557916877120†L31-L37】 and cross‑check RSV to confirm demand【906985539822198†L49-L53】.  
	2.	**Incorporate MMR Range in Variance Scores:** Pull high/low MMR values via API and calculate range width.  Tight ranges permit bids near the mid‑MMR; wide ranges trigger stricter caps【207089475371143†L304-L307】.  
	3.	**Compute ROI per Day:** Estimate reconditioning and transport costs, project sale price from retail comps, and compute expected gross profit.  Divide by projected days to sale (based on grade and MDS) to prioritise fast‑money vehicles.  
	4.	**Use Segment Multipliers:** Classify vehicles into demand tiers.  Adjust scores upward for Tier 1 vehicles and downward for Tier 3–4.  Document the logic to allow continuous updates as market preferences shift.  
	4.	**Use Segment Multipliers:** Classify vehicles into demand tiers.  Adjust scores upward for Tier 1 vehicles and downward for Tier 3–4.  Document the logic to allow continuous updates as market preferences shift.  
	5.	**Build Alerts and Dashboards:** Create an interface that surfaces Platinum and Gold opportunities with high ROI/day.  Provide warnings when CtM or MMR range signals indicate high risk.  Track actual sale results to refine thresholds over time.  
	5.	**Build Alerts and Dashboards:** Create an interface that surfaces Platinum and Gold opportunities with high ROI/day.  Provide warnings when CtM or MMR range signals indicate high risk.  Track actual sale results to refine thresholds over time.  
	6.	**Educate Users:** Provide simple explanations of the metrics so that DealerScope users understand why certain vehicles are recommended or rejected.  Transparency builds trust and facilitates manual overrides when necessary.  
  
**Conclusion**  
  
Leading dealership groups have adopted **variable management** by measuring Cost to Market, Market Days Supply and retail sales volume, then layering MMR confidence and segment demand to assign investment grades.  Public sources confirm the definitions and importance of CtM【187741809733906†L145-L147】, MDS【187741809733906†L179-L189】【420557916877120†L31-L37】 and MMR range【207089475371143†L304-L307】.  By combining these metrics with ROI per day and segment insights, DealerScope can evolve from a simple bid‑ceiling tool into a sophisticated acquisition and disposition strategy.  Implementing the recommendations above will help Codex generate tighter variance bands, identify high‑confidence flips and avoid inventory traps, ensuring that DealerScope delivers the best value to its users.  
Leading dealership groups have adopted **variable management** by measuring Cost to Market, Market Days Supply and retail sales volume, then layering MMR confidence and segment demand to assign investment grades.  Public sources confirm the definitions and importance of CtM【187741809733906†L145-L147】, MDS【187741809733906†L179-L189】【420557916877120†L31-L37】 and MMR range【207089475371143†L304-L307】.  By combining these metrics with ROI per day and segment insights, DealerScope can evolve from a simple bid‑ceiling tool into a sophisticated acquisition and disposition strategy.  Implementing the recommendations above will help Codex generate tighter variance bands, identify high‑confidence flips and avoid inventory traps, ensuring that DealerScope delivers the best value to its users.  

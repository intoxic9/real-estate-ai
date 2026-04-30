# CURSOR PROMPTS — US MARKET PIVOT
## Multi-Agent Real Estate Lead Intelligence System (USA)

### What Changed from Dubai Version
- **Compliance**: PDPL → US Fair Housing Act + TCPA + CAN-SPAM + state privacy laws (CCPA if targeting California)
- **Market Knowledge**: Dubai areas → US metro areas (NYC, LA, Miami, Austin, DFW, etc.)
- **Data Sources**: DLD/Bayut → Zillow API, Redfin public data, Census/FRED, county assessor records
- **Currency**: AED → USD
- **Property Types**: Add condos, co-ops, multi-family, single-family
- **Licensing**: RERA → State real estate licensing (varies by state)
- **Cultural Context**: Expat-focused → First-time buyers, investors, relocators, downsizers

### Prompts 1-3: NO CHANGES NEEDED
Your existing scaffolding, schemas, and API routes work as-is. Just update the MarketSnapshot model's field names from `_aed` to `_usd` if you haven't already.

Quick fix — paste this into Cursor before Prompt 4:

```
In the schemas (schemas.py), rename all AED-specific fields to USD:
- median_sale_price_aed → median_sale_price_usd
- price_per_sqft_aed → price_per_sqft_usd
- median_rent_aed → median_rent_usd

Also update the LeadProfile:
- preferred_locations should now accept US cities/neighborhoods (not Dubai areas)
- Add a new field: target_market: str (e.g., "New York Metro", "Austin TX", "Miami FL")
- Add: financing_type: enum [cash, conventional, fha, va, other, unknown]
- Add: is_first_time_buyer: bool (optional)
```

---

## PROMPT 4: CONVERSATION AGENT (US MARKET)

```
Implement the Conversation Agent in /backend/app/agents/conversation_agent.py.

This agent manages adaptive lead intake through natural conversation for the US real estate market.

Behavior:
- Maintains a conversation state machine: GREETING -> INTENT_DISCOVERY -> DETAILS_COLLECTION -> CONSENT -> SUMMARY
- Asks minimal necessary questions to fill the LeadProfile schema
- Adapts questions based on what's already known
- Handles missing information gracefully
- If user declines to share PII, offers analytics-only mode
- Speaks naturally, not like a form

System prompt for the LLM:
"""
You are a knowledgeable US real estate AI assistant. You help potential buyers, sellers, renters, and investors find what they need.

Your knowledge includes:
- Major US metro markets: NYC, Los Angeles, Miami, Chicago, Dallas-Fort Worth, Austin, Denver, Seattle, Phoenix, Atlanta, Nashville, Charlotte, Tampa, Raleigh, and more
- Typical price ranges by city and neighborhood
- Property types: single-family homes, condos, co-ops, townhouses, multi-family, land
- Financing options: conventional mortgages, FHA loans, VA loans, cash purchases, jumbo loans
- First-time buyer programs and down payment assistance
- Investment considerations: rental yield, appreciation, cap rates, 1031 exchanges
- Market conditions: inventory levels, days on market, bidding wars vs buyer's market

Your tone: Professional, helpful, and knowledgeable. Like a trusted friend who happens to be a real estate expert.

RULES YOU MUST FOLLOW:
1. Never guarantee specific returns, appreciation rates, or future prices
2. Never provide specific legal, tax, or mortgage advice — recommend they consult a licensed professional
3. Never make claims about school quality that could violate Fair Housing Act (avoid steering)
4. Always get explicit consent before storing personal information: "Before I save your details so an agent can reach out, I need your permission. Is that okay?"
5. If asked about neighborhood demographics, racial composition, or "safety," redirect to publicly available data sources rather than making characterizations (Fair Housing compliance)
6. Never ask about race, religion, national origin, familial status, disability, or sex — these are protected classes under Fair Housing Act
"""

The agent should return:
{
  "response": str,
  "lead_profile_updates": dict (partial LeadProfile fields),
  "stage": str (current conversation stage),
  "is_complete": bool,
  "consent_requested": bool,
  "consent_given": bool
}

Use LangChain's ChatOpenAI with structured output. Temperature 0.7.

Example conversation flow:
- "Hi! Are you looking to buy, sell, or invest in real estate?"
- [User: "I want to buy my first home"]
- "Exciting! First-time buyers have some great options. What area are you looking in?"
- [User: "Somewhere in Texas, maybe Austin or Dallas"]
- "Both great markets. Austin's median home price is around $450K, Dallas is closer to $380K. Do you have a budget range in mind?"
- [User: "Around 350-400K"]
- "That works well for both areas. Are you looking at single-family homes, townhouses, or condos?"
- ... continues until profile is complete, then asks for consent
```

---

## PROMPT 5: COMPLIANCE AGENT (US MARKET)

```
Implement the Compliance Agent in /backend/app/agents/compliance_agent.py.

This agent is the safety gate. It runs on EVERY lead before routing. Adapted for US regulatory environment.

Input: LeadProfile + full conversation transcript
Output: ComplianceResult

Behavior:

1. CONSENT VERIFICATION
   - Check that consent_given is True AND consent_timestamp exists
   - If consent is missing, block the lead from routing. Hard rule.
   - Log the exact message where consent was given

2. FAIR HOUSING ACT COMPLIANCE
   - Scan the AI's responses for potential Fair Housing violations:
     - Steering: suggesting neighborhoods based on protected characteristics
     - Discriminatory language about neighborhoods (e.g., "family-friendly" can be coded language for familial status discrimination)
     - Questions about protected classes: race, color, religion, sex, national origin, familial status, disability
     - Characterizations of neighborhood demographics or "safety"
   - Flag any violations in blocked_claims list

3. PII REDACTION
   - Scan the transcript for unnecessary PII:
     - Social Security Numbers (XXX-XX-XXXX pattern)
     - Full bank account or credit card numbers
     - Driver's license numbers
   - Redact these from stored transcript using [REDACTED]
   - Keep only: name, email, phone (with consent), property preferences

4. TCPA COMPLIANCE CHECK
   - If phone number is collected, verify consent to be contacted by phone
   - TCPA (Telephone Consumer Protection Act) requires express consent for marketing calls/texts
   - Log whether phone consent was explicit or implied

5. CLAIM BLOCKING
   - Scan AI responses for:
     - "guaranteed returns" / "guaranteed appreciation"
     - Specific ROI predictions ("this will be worth X in 2 years")
     - False urgency ("only 2 units left" unless verified)
     - Unauthorized mortgage rate quotes
     - Tax advice beyond general information
   - Flag in blocked_claims

Use rule-based approach for consent, PII, and TCPA checks (deterministic).
Use LLM with low temperature (0.2) for Fair Housing and claim detection.

Return ComplianceResult with all fields populated.
```

---

## PROMPT 6: INTENT AGENT (US MARKET)

```
Implement the Intent Agent in /backend/app/agents/intent_agent.py.

Input: LeadProfile + conversation transcript
Output: IntentResult

Classification categories:
- buyer_primary: Looking to buy a home to live in (primary residence)
- buyer_investment: Looking to buy property as an investment (rental, flip)
- seller: Looking to sell existing property
- renter: Looking to rent
- refinance: Looking to refinance existing mortgage
- unknown: Cannot determine intent

The agent should:
1. Analyze the conversation transcript for intent signals
2. Consider the LeadProfile fields
3. Return a confidence score between 0.0 and 1.0
4. Provide a rationale list
5. If confidence < 0.6, classify as "unknown" and flag for human review

US-specific intent signals to consider:
- "first-time buyer" / "FHA" / "down payment assistance" → buyer_primary
- "rental income" / "cap rate" / "1031 exchange" / "investment property" → buyer_investment
- "I need to sell" / "listing" / "what's my home worth" / "CMA" → seller
- "apartment" / "lease" / "monthly rent" / "pet-friendly" → renter
- "lower my rate" / "refinance" / "home equity" → refinance
- "relocating for work" / "moving to [city]" → likely buyer_primary
- "house hack" / "duplex" / "multi-family" → buyer_investment

Use LLM with structured output (JSON mode). Temperature 0.3.
Run classification 3 times with different temperatures, take majority vote for calibration.
```

---

## PROMPT 7: SCORING AGENT (US MARKET)

```
Implement the Scoring Agent in /backend/app/agents/scoring_agent.py.

Input: LeadProfile + IntentResult + conversation transcript
Output: ScoreResult (heat_score 0-100, bucket hot/warm/cold)

Scoring signals (weighted):

- Timeline (25% weight):
  immediate/under_30_days = 25 pts
  1_3_months = 18 pts
  3_6_months = 12 pts
  6_12_months = 6 pts
  exploring/no_timeline = 2 pts

- Budget clarity (20% weight):
  Specific range given = 20 pts
  Vague range ("around 400K") = 12 pts
  No budget mentioned = 3 pts

- Location specificity (15% weight):
  Specific city + neighborhood = 15 pts
  Specific city only = 10 pts
  State or region only = 5 pts
  No preference = 2 pts

- Pre-qualification status (15% weight):
  Pre-approved for mortgage = 15 pts
  Pre-qualified = 10 pts
  Has talked to a lender = 6 pts
  Cash buyer = 15 pts
  Not yet / unknown = 2 pts

- Intent confidence (10% weight):
  confidence > 0.8 = 10 pts
  0.6-0.8 = 7 pts
  < 0.6 = 2 pts

- Engagement quality (10% weight):
  Asked detailed questions / multiple messages = 10 pts
  Moderate engagement = 5 pts
  Minimal = 2 pts

- Consent + contact info (5% weight):
  Phone + email + consent = 5 pts
  Email + consent = 3 pts
  Consent only = 2 pts
  No consent = 0 pts

Bucket assignment:
- Hot: score >= 70 (route immediately)
- Warm: score 40-69 (nurture sequence)
- Cold: score < 40 (store, don't pursue)

Note: Added "pre-qualification status" as a US-specific signal — this is the #1 indicator
of a serious buyer in the US market. Someone who is pre-approved is 3-5x more likely to
close than someone who hasn't talked to a lender.

Make all weights configurable via environment variables.
Score calculation is deterministic. LLM generates reasoning only.
```

---

## PROMPT 8: ROUTING AGENT (US MARKET)

```
Implement the Routing Agent in /backend/app/agents/routing_agent.py.

Input: LeadProfile + IntentResult + ScoreResult + ComplianceResult
Output: RoutingResult {routed: bool, destination: str, reason: str, timestamp: datetime}

Behavior:
1. COMPLIANCE GATE
   - If ComplianceResult.compliant is False, DO NOT route. Store as "blocked".
   - Log reason for blocking.

2. STORE LEAD
   - Save all data to PostgreSQL with full audit trail

3. ROUTE HOT LEADS
   - If bucket == "hot" AND compliant == True:
     - Push to Google Sheets
     - Row format: Name, Email, Phone, Intent, Score, Budget Range, Target Markets,
       Timeline, Financing Type, First-Time Buyer (Y/N), Pre-Approval Status, Timestamp
   - Format clearly for the sales team

4. DUPLICATE DETECTION
   - Check for existing lead with same email OR phone within last 30 days
   - If duplicate, update existing record instead of creating new one

5. LEAD ASSIGNMENT (US-specific)
   - If lead specifies a target market (e.g., "Austin TX"), tag the lead
     with that market for geographic routing
   - Hot leads should include a "suggested_agent_market" field so
     the sales team knows which geographic specialist should handle it

Also implement /backend/app/services/sheets_service.py:
- Use Google Sheets API v4
- Service account authentication
- Append row to designated sheet
- Retry logic on API errors
```

---

## PROMPT 9: AGENT ORCHESTRATOR (NO CHANGES)

```
The orchestrator prompt from the original playbook works as-is.
Paste Prompt 9 from the original Cursor Prompt Playbook exactly.
No market-specific changes needed — it's pure coordination logic.
```

---

## PROMPT 10: CHAT INTERFACE (MINOR UPDATES)

```
Same as original Prompt 10, but add this to the end:

Additional US-specific UI elements:
- In the Lead Profile Card on the right, add fields for:
  - Financing Type (FHA, VA, Conventional, Cash)
  - Pre-Approval Status (Yes/No/Unknown)
  - First-Time Buyer badge
  - Target Market(s) with state abbreviations
- Add a small disclaimer footer in the chat:
  "This AI assistant provides general real estate information.
   It is not a licensed real estate agent or mortgage broker.
   Consult a licensed professional for specific advice."
- Fair Housing notice link in the footer
```

---

## PROMPT 11: LEAD MANAGEMENT DASHBOARD (MINOR UPDATES)

```
Same as original Prompt 11, but update the table columns:

- Columns: Name, Intent (buyer_primary/buyer_investment/seller/renter/refinance),
  Score, Bucket, Target Market(s), Financing Type, Pre-Approval, Timeline, Date, Status
- Add a filter for "Target Market" (dropdown of US metros)
- Add a filter for "Financing Type"
- Add a "First-Time Buyer" filter toggle
```

---

## PROMPT 12: MARKET ANALYTICS DASHBOARD (US MARKET)

```
Build the market analytics page in /frontend/src/app/analytics/page.tsx.

This dashboard shows US real estate market trends.

Layout:
- Top: Metro area selector (dropdown or pills):
  New York Metro, Los Angeles, Miami, Chicago, Dallas-Fort Worth, Austin,
  Denver, Seattle, Phoenix, Atlanta, Nashville, Charlotte, Tampa, Raleigh,
  San Francisco, Boston, Portland, Minneapolis, San Diego, Las Vegas

- Main chart area:
  - Time-series line chart showing selected metrics over time
  - Metric toggles:
    - Median Sale Price (USD)
    - Median Price per Sq Ft
    - Median Rent (monthly)
    - Days on Market
    - Inventory Level (months of supply)
    - Mortgage Rate (30-year fixed, from FRED data)
  - Date range: last 3 months, 6 months, 1 year, 2 years, custom
  - Multi-metro overlay: compare 2-3 metros on same chart

- Comparison section:
  - Side-by-side cards comparing two metros
  - Metrics: median price, rent, price/sqft, days on market, inventory,
    year-over-year price change percentage

- Data table:
  - Historical snapshot browser
  - Export to CSV

Fetch from /api/market endpoints.
Use recharts with smooth animations.
Each metro gets a fixed color across all charts.
```

---

## PROMPT 13: NAVIGATION + LAYOUT (NO CHANGES)

```
Paste original Prompt 13 exactly. No market-specific changes needed.
```

---

## PROMPT 14: MARKET DATA PIPELINE (US MARKET)

```
Implement the market data service in /backend/app/services/market_data_service.py.

Data sources for the US market (all legal, no scraping):

1. REDFIN PUBLIC DATA (Primary Source - FREE)
   - Redfin publishes downloadable CSV data at redfin.com/news/data-center/
   - Updated weekly with metro, city, county, and zip-level data
   - Includes: median sale price, homes sold, inventory, days on market,
     price drops, new listings, months of supply
   - Build a function that downloads and parses these CSVs
   - Schedule weekly refresh

2. FRED (Federal Reserve Economic Data - FREE API)
   - FRED API provides mortgage rates, housing starts, CPI shelter index
   - Series IDs:
     - MORTGAGE30US: 30-year fixed mortgage rate
     - HOUST: Housing starts
     - CUSR0000SAH1: CPI shelter component
   - API key is free from fred.stlouisfed.org

3. CENSUS / AMERICAN COMMUNITY SURVEY (FREE)
   - Median household income by metro (for affordability calculations)
   - Population growth rates
   - api.census.gov

4. Seed data script:
   Create /backend/scripts/seed_market_data.py
   Populate the database with realistic US market data for the past 12-24 months.
   Include these metros with approximate ranges:

   - New York Metro: median $650K, rent $3,200/mo, $550/sqft
   - Los Angeles: median $850K, rent $2,800/mo, $600/sqft
   - Miami: median $550K, rent $2,500/mo, $450/sqft
   - Chicago: median $330K, rent $1,800/mo, $250/sqft
   - Dallas-Fort Worth: median $380K, rent $1,700/mo, $200/sqft
   - Austin: median $450K, rent $1,600/mo, $280/sqft
   - Denver: median $550K, rent $1,900/mo, $350/sqft
   - Seattle: median $750K, rent $2,400/mo, $480/sqft
   - Phoenix: median $420K, rent $1,500/mo, $270/sqft
   - Atlanta: median $370K, rent $1,600/mo, $220/sqft
   - Nashville: median $430K, rent $1,700/mo, $290/sqft
   - Charlotte: median $380K, rent $1,500/mo, $230/sqft
   - Tampa: median $370K, rent $1,800/mo, $260/sqft
   - Raleigh: median $400K, rent $1,500/mo, $240/sqft
   - San Francisco: median $1,200K, rent $3,500/mo, $900/sqft
   - Boston: median $680K, rent $2,800/mo, $500/sqft

   Add monthly variation (1-3% random fluctuation) to simulate trends.
   Add days_on_market data (SF: ~25 days, Chicago: ~40 days, etc.)
   Add inventory data (months of supply: 2-6 depending on market)

5. FRED integration helper:
   Create a FREDClient class that fetches mortgage rate data
   using the free FRED API. This is a real, working integration
   (not a placeholder) since the API is free and easy.

Make the seed script runnable: python scripts/seed_market_data.py
```

---

## PROMPT 15: END-TO-END TEST + DOCKER (MINOR UPDATES)

```
Same as original Prompt 15, but update the integration test conversation
to be US-focused:

In /backend/tests/test_full_pipeline.py, simulate this conversation:

User: "Hi, I'm looking to buy my first home"
Bot: [greets, asks about location]
User: "I'm relocating to Austin, Texas for a new job"
Bot: [asks about budget]
User: "My budget is around 350-400K. I'm pre-approved for an FHA loan"
Bot: [asks about property type]
User: "A single-family home with at least 3 bedrooms"
Bot: [asks about timeline]
User: "I need to move within 2-3 months"
Bot: [asks for consent]
User: "Yes, you can save my info. My email is test@example.com"

Expected results:
- Intent: buyer_primary (confidence > 0.8)
- Score: 75+ (hot) because: specific location, clear budget, pre-approved, 2-3 month timeline
- Compliance: pass (consent given, no Fair Housing violations, no PII issues)
- Routing: routed to Google Sheets (or mock)

Also verify:
- Fair Housing compliance: no steering language
- TCPA: phone consent properly tracked
- No claims about appreciation or returns
```

---

## SUMMARY OF CHANGES

| Prompt | Change Level | What Changed |
|--------|-------------|-------------|
| 1-3    | None        | Just rename AED → USD fields |
| 4      | Major       | System prompt: Dubai knowledge → US market knowledge + Fair Housing rules |
| 5      | Major       | PDPL → Fair Housing Act + TCPA + CAN-SPAM compliance |
| 6      | Moderate    | Added buyer_primary vs buyer_investment + refinance intent. US-specific signals |
| 7      | Moderate    | Added pre-qualification as scoring signal. Adjusted weights |
| 8      | Minor       | Added geographic routing for US metros |
| 9      | None        | Orchestrator is market-agnostic |
| 10     | Minor       | Added financing/pre-approval fields + Fair Housing disclaimer |
| 11     | Minor       | Updated table columns and filters |
| 12     | Major       | Dubai areas → 16+ US metros with US-specific metrics (inventory, mortgage rates) |
| 13     | None        | Layout is market-agnostic |
| 14     | Major       | DLD data → Redfin public data + FRED API + Census. All free and legal |
| 15     | Minor       | Updated test conversation to US buyer scenario |

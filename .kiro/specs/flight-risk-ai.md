# Spec: Flight Risk AI

## Goal

Build an AI-driven airline operational risk and financial exposure analysis API.
Given a future flight, the system predicts disruption probability, passenger impact,
and expected financial cost — before the flight departs.

## Architecture

```
POST /analyze-flight
        │
        ▼
  LangGraph Agent (app/graph/graph.py)
        │
  ┌─────┴─────────────────────────────────────────┐
  │  validate_input                               │
  │  retrieve_historical_patterns  ← TiDB SQL     │
  │  retrieve_similar_cases        ← TiDB Vector  │
  │  calculate_operational_risks   ← risk_model   │
  │  calculate_passenger_exposure                 │
  │  calculate_financial_exposure  ← legal_costs  │
  │  ai_risk_analyst               ← Bedrock      │
  │  build_structured_output                      │
  │  validate_output                              │
  └───────────────────────────────────────────────┘
        │
        ▼
  FlightAnalysisOutput (JSON)
```

## Data Layer — TiDB

Database: `airportdb` on TiDB Cloud (ap-southeast-1 compatible, cluster in sa-east-1)

### SQL queries (app/services/tidb.py)
- Route delay rate: actual flight duration vs flightschedule scheduled duration
- Origin airport delay rate
- Hour-of-day delay rate
- Historical booking ratio for the route

### Delay target definition
```
delayed = 1  if  actual_duration_seconds > scheduled_duration_seconds + 900
              (i.e. more than 15 minutes late)
```

### Vector search (app/services/vector_search.py)
Table: `flight_risk_memory`
- Each row is a flight description summary (origin, dest, aircraft, booking ratio, delay)
- Embedding: `VECTOR(1024)` generated via `EMBED_TEXT('tidbcloud_free/amazon/titan-embed-text-v2', description)`
- Search: `VEC_COSINE_DISTANCE` to find TOP-3 similar historical cases

## Risk Engine (app/services/risk_model.py)

### Delay probability
Weighted blend of historical rates:
- Route rate × 0.50
- Origin rate × 0.25
- Hour rate × 0.15
- Weather rate × 0.10
- +0.15 boost for adverse weather conditions

### Overbooking risk
Deterministic from booking_ratio = bookings / capacity:
- > 1.0 → CRITICAL
- 0.95–1.0 → HIGH (0.70)
- 0.85–0.95 → MEDIUM (0.45)
- 0.75–0.85 → LOW (0.25)

### Missed connection
Derived from delay probability × avg_delay / 60 × 0.30 (assumed connection ratio)

### Cancellation
Not available — no cancellation status in dataset. Returns `available: false`.

## Financial Engine (app/services/financial.py)

Config: `app/config/legal_costs.json` (editable)

Formula:
```
expected_loss = delay_prob × bookings × cost_per_delay_tier
              + overflow × overbooking_cost_per_pax
              + connection_prob × bookings × connection_cost_per_pax
```

Overall score (0–100):
```
score = (delay_p×0.5 + ob_p×0.3 + conn_p×0.2) × 70  +  (cost/500k) × 30
```

## AI Layer — Amazon Bedrock (app/services/bedrock.py)

Model: `anthropic.claude-3-haiku-20240307-v1:0`
Region: `ap-southeast-1`

Role: narrative interpretation only.
- Input: deterministic risk data + similar historical cases
- Output: executive summary + 3 prioritized recommendations
- Fallback: deterministic recommendations generated from thresholds if Bedrock fails

## API (app/main.py)

- `GET /health` — checks TiDB and Bedrock connectivity
- `POST /analyze-flight` — full LangGraph pipeline, returns FlightAnalysisOutput JSON

## Implementation Decisions

1. No ML training — weighted historical rates are faster, transparent, and sufficient for demo
2. EMBED_TEXT server-side — no Bedrock for embeddings; TiDB generates them natively
3. All probabilities validated 0..1 in validate_output node
4. All cost bounds validated min ≤ expected ≤ max in validate_output node
5. All nodes have try/except; API never returns 500 due to data or ML failure
6. numpy type conversion handled in _safe() helper before JSON serialization

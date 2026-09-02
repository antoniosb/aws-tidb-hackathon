# Flight Risk AI

> "Before a flight becomes a disruption, we tell the airline how likely it is to go wrong, how many passengers it may affect, and how much it could cost."

AI-driven airline operational risk and financial exposure analysis. Built for the TiDB LATAM Hackathon 2026.

---

## What it does

Given a future flight (origin, destination, departure time, aircraft, bookings), the system:

1. Queries **real historical patterns** from the `airportdb` dataset in TiDB
2. Retrieves **similar historical cases** via TiDB vector search (`EMBED_TEXT` + `VEC_COSINE_DISTANCE`)
3. Calculates **delay, overbooking, and missed-connection probabilities** using deterministic statistical models
4. Estimates **expected financial exposure** (BRL) using configurable legal/compensation rules
5. Generates an **AI executive summary and prioritized recommendations** via Amazon Bedrock Claude

**The LLM never invents numbers.** All probabilities, costs, and passenger counts come from data and deterministic models. Bedrock only interprets and explains.

---

## Architecture

```
POST /analyze-flight
        │
        ▼
  LangGraph (9 nodes)
   validate_input
   retrieve_historical_patterns  ←  TiDB SQL (route/origin/hour delay rates)
   retrieve_similar_cases        ←  TiDB Vector Search (EMBED_TEXT)
   calculate_operational_risks   ←  Weighted historical probabilities
   calculate_passenger_exposure
   calculate_financial_exposure  ←  legal_costs.json (configurable)
   ai_risk_analyst               ←  Amazon Bedrock Claude Haiku
   build_structured_output
   validate_output
        │
        ▼
  FlightAnalysisOutput (JSON)
```

---

## Stack

| Component | Technology |
|-----------|-----------|
| API | FastAPI |
| Orchestration | LangGraph |
| Database | TiDB Cloud (`airportdb`) |
| Vector Search | TiDB `EMBED_TEXT` + `VEC_COSINE_DISTANCE` |
| LLM | Amazon Bedrock — Claude 3 Haiku |
| Schema validation | Pydantic v2 |

---

## How to run

```bash
# 1. Clone and enter the repo
cd aws-tidb-poc

# 2. Create and activate venv
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure credentials
cp .env.example .env
# Fill in TIDB_* and AWS_* values

# 5. (Optional) Pre-populate vector memory for better similar-case results
python scripts/prepare_vector_memory.py

# 6. Start the API
uvicorn app.main:app --port 8000

# 7. Health check
curl http://localhost:8000/health

# 8. Analyze a flight
curl -X POST http://localhost:8000/analyze-flight \
  -H "Content-Type: application/json" \
  -d @examples/demo_request.json
```

---

## Example request

```json
{
  "flight_number": "LH507",
  "origin": "GRU",
  "destination": "FRA",
  "departure_time": "2026-09-02T18:40:00",
  "aircraft_type": "Boeing 767",
  "capacity": 200,
  "bookings": 191,
  "weather": { "condition": "rain" }
}
```

## Example response (abbreviated)

```json
{
  "risks": {
    "delay":     { "probability": 0.31, "level": "MEDIUM" },
    "overbooking": { "probability": 0.70, "level": "HIGH" },
    "missed_connection": { "probability": 0.11, "level": "LOW" }
  },
  "passenger_exposure": { "total_bookings": 191, "estimated_passengers_at_risk": 57 },
  "estimated_passenger_cost": { "min": 25131, "max": 55489, "expected": 39880, "currency": "BRL" },
  "overall_financial_risk_score": 29.2,
  "overall_financial_risk_level": "LOW",
  "summary": "...",
  "recommendations": [...]
}
```

---

## Financial rules

Edit `app/config/legal_costs.json` to adjust compensation values per disruption type.

---

## Key files

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI routes |
| `app/graph/graph.py` | LangGraph pipeline |
| `app/graph/nodes.py` | All 9 node implementations |
| `app/services/tidb.py` | TiDB SQL queries |
| `app/services/vector_search.py` | TiDB vector search |
| `app/services/risk_model.py` | Delay/overbooking/connection models |
| `app/services/financial.py` | Financial exposure calculator |
| `app/services/bedrock.py` | Bedrock Claude integration |
| `app/config/legal_costs.json` | Configurable compensation rules |
| `.kiro/specs/flight-risk-ai.md` | Kiro spec |

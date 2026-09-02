"""Amazon Bedrock integration for AI risk narrative generation."""
import json
import os

import boto3
from dotenv import load_dotenv

load_dotenv()

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "bedrock-runtime",
            region_name=os.environ.get("AWS_REGION", "ap-southeast-1"),
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        )
    return _client


SYSTEM_PROMPT = """You are an airline operational risk analyst.
Your job is to interpret a deterministic flight risk analysis.
Never change or invent probabilities, costs, passenger counts, or historical statistics.
Use only the supplied data.
Be concise, operational and actionable.
Always respond with valid JSON only."""

USER_TEMPLATE = """Analyze this flight risk report and provide a brief executive summary and prioritized recommendations.

Flight: {flight_number} ({origin} → {destination})
Departure: {departure_time}

RISKS (deterministic):
- Delay probability: {delay_prob:.0%} ({delay_level}) — avg {avg_delay:.0f} min historical
- Overbooking probability: {ob_prob} ({ob_level}) — booking ratio: {booking_ratio}
- Missed connection probability: {conn_prob} ({conn_level})

PASSENGER EXPOSURE: {passengers_at_risk} of {total_bookings} passengers at risk

FINANCIAL EXPOSURE: BRL {cost_expected:,.0f} expected (range: {cost_min:,.0f} – {cost_max:,.0f})

SIMILAR HISTORICAL CASES:
{similar_cases}

OVERALL RISK SCORE: {overall_score}/100 ({overall_level})

Respond ONLY with this JSON:
{{
  "summary": "2-3 sentence executive summary",
  "recommendations": [
    {{"priority": 1, "action": "...", "reason": "...", "estimated_impact": "..."}},
    {{"priority": 2, "action": "...", "reason": "...", "estimated_impact": "..."}},
    {{"priority": 3, "action": "...", "reason": "...", "estimated_impact": "..."}}
  ]
}}"""


def _deterministic_fallback(risks: dict, cost: dict, overall_level: str) -> dict:
    delay_p = risks["delay"].get("probability") or 0.0
    ob_p = risks["overbooking"].get("probability") or 0.0
    conn_p = risks["missed_connection"].get("probability") or 0.0

    summary = (
        f"This flight presents {overall_level.lower()} financial exposure. "
        f"Delay risk is {risks['delay']['level'].lower()} ({delay_p:.0%}), "
        f"overbooking risk is {risks['overbooking']['level'].lower()} ({ob_p:.0%}). "
        f"Expected passenger-related cost: BRL {cost['expected']:,.0f}."
    )
    recs = []
    if delay_p >= 0.5:
        recs.append({
            "priority": 1,
            "action": "Pre-position crew and ground staff for delay management",
            "reason": f"High delay probability ({delay_p:.0%})",
            "estimated_impact": "Reduces passenger rebooking costs",
        })
    if ob_p >= 0.4:
        recs.append({
            "priority": len(recs) + 1,
            "action": "Activate voluntary denied-boarding compensation program",
            "reason": f"Elevated overbooking risk ({ob_p:.0%})",
            "estimated_impact": "Avoids involuntary bumping penalties",
        })
    if conn_p >= 0.3:
        recs.append({
            "priority": len(recs) + 1,
            "action": "Alert connection passengers and pre-rebook vulnerable itineraries",
            "reason": f"Missed connection risk {conn_p:.0%}",
            "estimated_impact": "Reduces downstream delay chain",
        })
    if not recs:
        recs.append({
            "priority": 1,
            "action": "Continue standard monitoring",
            "reason": "Risk levels are within acceptable range",
            "estimated_impact": "No immediate action required",
        })
    return {"summary": summary, "recommendations": recs}


def generate_ai_analysis(
    flight_input: dict,
    risks: dict,
    passenger_exposure: dict,
    cost: dict,
    similar_cases: list,
    overall_score: float,
    overall_level: str,
) -> dict:
    try:
        cases_text = "\n".join(
            f"  - Flight {c['origin']}→{c['destination']}: delay {c['delay_minutes']:.0f}min, "
            f"booking ratio {c['booking_ratio']:.0%}, similarity {c['similarity']:.0%}"
            for c in (similar_cases[:3] if similar_cases else [])
        ) or "  No similar cases found"

        ob = risks["overbooking"]
        prompt = USER_TEMPLATE.format(
            flight_number=flight_input.get("flight_number", "N/A"),
            origin=flight_input.get("origin", ""),
            destination=flight_input.get("destination", ""),
            departure_time=flight_input.get("departure_time", ""),
            delay_prob=risks["delay"].get("probability") or 0.0,
            delay_level=risks["delay"]["level"],
            avg_delay=risks["delay"].get("avg_delay_min", 0),
            ob_prob=f"{(ob.get('probability') or 0.0):.0%}",
            ob_level=ob["level"],
            booking_ratio=ob.get("booking_ratio") or "N/A",
            conn_prob=f"{(risks['missed_connection'].get('probability') or 0.0):.0%}",
            conn_level=risks["missed_connection"]["level"],
            passengers_at_risk=passenger_exposure["estimated_passengers_at_risk"],
            total_bookings=passenger_exposure["total_bookings"],
            cost_expected=cost["expected"],
            cost_min=cost["min"],
            cost_max=cost["max"],
            similar_cases=cases_text,
            overall_score=overall_score,
            overall_level=overall_level,
        )

        client = _get_client()
        resp = client.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 800,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            }),
        )
        text = json.loads(resp["body"].read())["content"][0]["text"].strip()

        # Extract JSON robustly
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(text[start:end])
            if "summary" in result and "recommendations" in result:
                return result

        return _deterministic_fallback(risks, cost, overall_level)

    except Exception as e:
        print(f"[bedrock] failed: {e}")
        return _deterministic_fallback(risks, cost, overall_level)

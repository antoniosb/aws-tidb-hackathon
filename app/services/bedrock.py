"""Amazon Bedrock — AI risk narrative generation.
Never invents probabilities, costs, or passenger counts.
Falls back to deterministic recommendations if Bedrock is unavailable.
"""
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
You receive a deterministic flight risk report with pre-calculated probabilities, costs, and passenger counts.
Your role is ONLY to interpret the data — never change, invent, or adjust any number.
Be concise, specific, and actionable. Reference the actual data values in your response.
Always respond with valid JSON only, no markdown, no extra text."""

USER_TEMPLATE = """Interpret this flight risk report. Use only the provided data.

Flight: {flight_number} — {origin} → {destination}
Departure: {departure_time}

RISKS (pre-calculated, do not modify):
- Delay: {delay_prob:.0%} ({delay_level}) — avg historical delay {avg_delay:.0f} min
- Overbooking: {ob_prob} ({ob_level}) — booking ratio {booking_ratio}
- Missed connection: {conn_prob} ({conn_level})
- Cancellation: not available in dataset

PASSENGER EXPOSURE:
- Total bookings: {total_bookings}
- Estimated at risk: {passengers_at_risk}

FINANCIAL EXPOSURE (operational, excl. judicial):
- Expected: BRL {cost_expected:,.0f}
- Range: BRL {cost_min:,.0f} – {cost_max:,.0f}

SIMILAR HISTORICAL CASES:
{similar_cases}

OVERALL RISK SCORE: {overall_score}/100 ({overall_level})

Provide a concise operational interpretation and 2-3 prioritized preventive actions.

Respond ONLY with this JSON (no markdown):
{{
  "summary": "1-2 sentence insight referencing specific risk drivers from the data above",
  "recommendations": [
    {{"priority": 1, "action": "specific preventive action", "reason": "why, citing the data"}},
    {{"priority": 2, "action": "specific preventive action", "reason": "why, citing the data"}},
    {{"priority": 3, "action": "specific preventive action", "reason": "why, citing the data"}}
  ]
}}"""


def _deterministic_fallback(risks: dict, cost: dict, overall_level: str) -> dict:
    delay_p = float(risks.get("delay", {}).get("probability") or 0.0)
    ob_p = float(risks.get("overbooking", {}).get("probability") or 0.0)
    conn_p = float(risks.get("missed_connection", {}).get("probability") or 0.0)
    exp_cost = cost.get("expected", 0.0)

    summary = (
        f"This flight presents {overall_level.lower()} financial risk. "
        f"Delay probability is {delay_p:.0%}, overbooking risk {ob_p:.0%}. "
        f"Expected operational exposure: BRL {exp_cost:,.0f}."
    )

    recs = []
    if delay_p >= 0.5:
        recs.append({
            "priority": 1,
            "action": "Pre-position crew and ground staff for delay contingency",
            "reason": f"Delay probability is {delay_p:.0%} — proactive staffing reduces passenger impact",
        })
    if ob_p >= 0.4:
        recs.append({
            "priority": len(recs) + 1,
            "action": "Activate voluntary denied-boarding compensation program before check-in",
            "reason": f"Overbooking risk {ob_p:.0%} — voluntary bumping avoids involuntary penalties",
        })
    if conn_p >= 0.3:
        recs.append({
            "priority": len(recs) + 1,
            "action": "Identify and protect connecting passengers, pre-rebook vulnerable itineraries",
            "reason": f"Missed connection risk {conn_p:.0%} — early rebooking prevents downstream delays",
        })
    if not recs:
        recs.append({
            "priority": 1,
            "action": "Maintain standard operational monitoring",
            "reason": "Risk levels are within acceptable range",
        })

    return {"summary": summary, "recommendations": recs, "ai_provider": "fallback"}


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
            f"  - {c.get('origin','?')}→{c.get('destination','?')}: "
            f"delay {c.get('delay_minutes', 0):.0f} min, "
            f"booking ratio {c.get('booking_ratio', 0):.0%}, "
            f"similarity {c.get('similarity', 0):.0%}"
            for c in (similar_cases[:3] if similar_cases else [])
        ) or "  No similar cases retrieved"

        ob = risks.get("overbooking", {})
        delay = risks.get("delay", {})
        conn = risks.get("missed_connection", {})
        dt = flight_input.get("departure_time", "")
        dep_str = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)

        prompt = USER_TEMPLATE.format(
            flight_number=flight_input.get("flight_number", "N/A"),
            origin=flight_input.get("origin", ""),
            destination=flight_input.get("destination", ""),
            departure_time=dep_str,
            delay_prob=float(delay.get("probability") or 0.0),
            delay_level=delay.get("level", "UNKNOWN"),
            avg_delay=float(delay.get("avg_delay_min") or 0),
            ob_prob=f"{float(ob.get('probability') or 0.0):.0%}",
            ob_level=ob.get("level", "UNKNOWN"),
            booking_ratio=ob.get("booking_ratio") or "N/A",
            conn_prob=f"{float(conn.get('probability') or 0.0):.0%}",
            conn_level=conn.get("level", "UNKNOWN"),
            total_bookings=passenger_exposure.get("total_bookings", 0),
            passengers_at_risk=passenger_exposure.get("estimated_passengers_at_risk", 0),
            cost_expected=float(cost.get("expected", 0.0)),
            cost_min=float(cost.get("min", 0.0)),
            cost_max=float(cost.get("max", 0.0)),
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
                result["ai_provider"] = "bedrock"
                return result

        fb = _deterministic_fallback(risks, cost, overall_level)
        fb["ai_provider"] = "fallback"
        return fb

    except Exception as e:
        print(f"[bedrock] failed: {e}")
        fb = _deterministic_fallback(risks, cost, overall_level)
        fb["ai_provider"] = "fallback"
        return fb

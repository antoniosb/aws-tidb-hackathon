"""LangGraph node implementations."""
import math
from datetime import datetime

from app.graph.state import AgentState
from app.services import bedrock, financial, risk_model, tidb, vector_search


# ── helpers ───────────────────────────────────────────────────────────────────

def _safe(v):
    """Convert numpy/special types to plain Python for JSON."""
    if v is None:
        return v
    try:
        import numpy as np
        if isinstance(v, np.integer):
            return int(v)
        if isinstance(v, np.floating):
            return float(v)
    except ImportError:
        pass
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


# ── nodes ─────────────────────────────────────────────────────────────────────

def validate_input(state: AgentState) -> AgentState:
    fi = dict(state.get("flight_input", {}))
    errors = list(state.get("errors", []))

    for field in ("origin", "destination", "departure_time"):
        if not fi.get(field):
            errors.append(f"Missing required field: {field}")

    fi["origin"] = (fi.get("origin") or "").strip().upper()
    fi["destination"] = (fi.get("destination") or "").strip().upper()

    if isinstance(fi.get("departure_time"), str):
        try:
            fi["departure_time"] = datetime.fromisoformat(fi["departure_time"])
        except ValueError:
            errors.append("Invalid departure_time format")

    if fi.get("capacity") is not None:
        fi["capacity"] = max(int(fi["capacity"]), 0)
    if fi.get("bookings") is not None:
        fi["bookings"] = max(int(fi["bookings"]), 0)

    return {**state, "flight_input": fi, "errors": errors}


def retrieve_historical_patterns(state: AgentState) -> AgentState:
    fi = state["flight_input"]
    dt = fi.get("departure_time")
    hour = dt.hour if isinstance(dt, datetime) else 12

    patterns = tidb.get_historical_patterns(
        origin=fi["origin"],
        destination=fi["destination"],
        departure_hour=hour,
    )
    return {**state, "historical_patterns": patterns}


def retrieve_similar_cases(state: AgentState) -> AgentState:
    fi = state["flight_input"]
    patterns = state.get("historical_patterns", {})
    booking_ratio = patterns.get("booking_ratio_avg", 0.7)

    if fi.get("capacity") and fi.get("bookings"):
        booking_ratio = fi["bookings"] / fi["capacity"]

    dt = fi.get("departure_time")
    hour = dt.hour if isinstance(dt, datetime) else 12

    vector_search.ensure_table_populated()
    cases = vector_search.find_similar_cases(
        origin=fi["origin"],
        destination=fi["destination"],
        aircraft_type=fi.get("aircraft_type"),
        booking_ratio=booking_ratio,
        departure_hour=hour,
    )
    return {**state, "similar_cases": cases}


def calculate_operational_risks(state: AgentState) -> AgentState:
    fi = state["flight_input"]
    patterns = state.get("historical_patterns", {})
    weather = fi.get("weather") or {}
    weather_condition = weather.get("condition") if isinstance(weather, dict) else None

    delay = risk_model.calculate_delay_probability(patterns, weather_condition)
    ob = risk_model.calculate_overbooking_risk(
        capacity=fi.get("capacity"),
        bookings=fi.get("bookings"),
        booking_ratio_history=patterns.get("booking_ratio_avg", 0.0),
    )
    conn = risk_model.calculate_missed_connection_risk(
        delay_probability=delay["probability"],
        avg_delay_min=delay["avg_delay_min"],
    )

    risks = {
        "delay": {
            "available": True,
            "probability": _safe(delay["probability"]),
            "level": delay["level"],
            "confidence": delay["confidence"],
            "drivers": delay["drivers"],
            "avg_delay_min": _safe(delay["avg_delay_min"]),
        },
        "overbooking": {
            "available": ob["available"],
            "probability": _safe(ob.get("probability")),
            "level": ob["level"],
            "confidence": ob["confidence"],
            "drivers": ob["drivers"],
            "overflow": _safe(ob.get("overflow", 0)),
            "booking_ratio": _safe(ob.get("booking_ratio")),
        },
        "missed_connection": {
            "available": conn["available"],
            "probability": _safe(conn.get("probability")),
            "level": conn["level"],
            "confidence": conn["confidence"],
            "drivers": conn["drivers"],
        },
        "cancellation": {
            "available": False,
            "probability": None,
            "level": "UNKNOWN",
            "confidence": "LOW",
            "drivers": ["No cancellation status field in dataset"],
        },
    }
    return {**state, "risks": risks}


def calculate_passenger_exposure(state: AgentState) -> AgentState:
    fi = state["flight_input"]
    risks = state.get("risks", {})

    total_bookings = fi.get("bookings") or 0
    if total_bookings == 0:
        patterns = state.get("historical_patterns", {})
        total_bookings = int(patterns.get("booking_ratio_avg", 0.7) * (fi.get("capacity") or 150))

    delay_p = float(risks.get("delay", {}).get("probability") or 0.0)
    ob = risks.get("overbooking", {})
    overflow = int(ob.get("overflow") or 0)
    conn_p = float(risks.get("missed_connection", {}).get("probability") or 0.0)

    delay_exposed = int(total_bookings * delay_p)
    ob_exposed = overflow if overflow > 0 else int(total_bookings * float(ob.get("probability") or 0.0) * 0.05)
    conn_exposed = int(total_bookings * conn_p * 0.30)

    at_risk = min(max(delay_exposed, ob_exposed, conn_exposed), total_bookings)

    return {
        **state,
        "passenger_exposure": {
            "total_bookings": int(total_bookings),
            "estimated_passengers_at_risk": int(at_risk),
            "by_event": {
                "delay": delay_exposed,
                "overbooking": ob_exposed,
                "missed_connection": conn_exposed,
                "cancellation": 0,
            },
        },
    }


def calculate_financial_exposure(state: AgentState) -> AgentState:
    risks = state.get("risks", {})
    exposure = state.get("passenger_exposure", {})
    fi = state["flight_input"]

    cost = financial.calculate_financial_exposure(
        risks=risks,
        bookings=exposure.get("total_bookings", fi.get("bookings") or 0),
        capacity=fi.get("capacity"),
    )
    score, level = financial.calculate_overall_score(
        risks=risks,
        cost=cost,
        bookings=exposure.get("total_bookings", 0),
    )
    return {
        **state,
        "estimated_cost": cost,
        "overall_risk_score": _safe(score),
        "overall_risk_level": level,
    }


def ai_risk_analyst(state: AgentState) -> AgentState:
    result = bedrock.generate_ai_analysis(
        flight_input=state["flight_input"],
        risks=state.get("risks", {}),
        passenger_exposure=state.get("passenger_exposure", {}),
        cost=state.get("estimated_cost", {}),
        similar_cases=state.get("similar_cases", []),
        overall_score=state.get("overall_risk_score", 0.0),
        overall_level=state.get("overall_risk_level", "UNKNOWN"),
    )
    return {
        **state,
        "ai_summary": result.get("summary", ""),
        "recommendations": result.get("recommendations", []),
        "ai_provider": result.get("ai_provider", "unknown"),
    }


def build_structured_output(state: AgentState) -> AgentState:
    fi = state["flight_input"]
    risks = state.get("risks", {})
    cost = state.get("estimated_cost", {})

    dt = fi.get("departure_time")
    dep_str = dt.isoformat() if isinstance(dt, datetime) else str(dt)

    output = {
        "flight": {
            "flight_number": fi.get("flight_number", "N/A"),
            "origin": fi["origin"],
            "destination": fi["destination"],
            "departure_time": dep_str,
            "aircraft_type": fi.get("aircraft_type"),
            "capacity": fi.get("capacity"),
            "bookings": fi.get("bookings"),
        },
        "risks": {
            "delay": {
                "available": risks["delay"]["available"],
                "probability": risks["delay"]["probability"],
                "level": risks["delay"]["level"],
                "confidence": risks["delay"]["confidence"],
                "drivers": risks["delay"]["drivers"],
            },
            "overbooking": {
                "available": risks["overbooking"]["available"],
                "probability": risks["overbooking"]["probability"],
                "level": risks["overbooking"]["level"],
                "confidence": risks["overbooking"]["confidence"],
                "drivers": risks["overbooking"]["drivers"],
                "booking_ratio": risks["overbooking"].get("booking_ratio"),
                "overflow": risks["overbooking"].get("overflow", 0),
            },
            "missed_connection": {
                "available": risks["missed_connection"]["available"],
                "probability": risks["missed_connection"]["probability"],
                "level": risks["missed_connection"]["level"],
                "confidence": risks["missed_connection"]["confidence"],
                "drivers": risks["missed_connection"]["drivers"],
            },
            "cancellation": {
                "available": False,
                "probability": None,
                "level": "UNKNOWN",
                "confidence": "LOW",
                "drivers": risks["cancellation"]["drivers"],
            },
        },
        "passenger_exposure": state.get("passenger_exposure", {}),
        "estimated_passenger_cost": {
            "min": cost.get("min", 0.0),
            "max": cost.get("max", 0.0),
            "expected": cost.get("expected", 0.0),
            "currency": cost.get("currency", "BRL"),
        },
        "financial_exposure_by_event": cost.get("by_event", {}),
        "judicial_exposure": cost.get("judicial_exposure", {}),
        "overall_financial_risk_score": state.get("overall_risk_score", 0.0),
        "overall_financial_risk_level": state.get("overall_risk_level", "UNKNOWN"),
        "ai_insight": state.get("ai_summary", ""),
        "recommended_actions": state.get("recommendations", []),
        "ai_provider": state.get("ai_provider", "unknown"),
        "similar_historical_cases": state.get("similar_cases", []),
        "errors": state.get("errors", []),
    }
    return {**state, "final_output": output}


def validate_output(state: AgentState) -> AgentState:
    out = state.get("final_output", {})
    cost = out.get("estimated_passenger_cost", {})

    # Clamp probabilities 0..1
    for risk_key in ("delay", "overbooking", "missed_connection"):
        r = out.get("risks", {}).get(risk_key, {})
        if r.get("probability") is not None:
            r["probability"] = round(min(max(float(r["probability"]), 0.0), 1.0), 4)

    # Ensure cost ordering: min <= expected <= max
    mn = float(cost.get("min") or 0.0)
    mx = float(cost.get("max") or 0.0)
    exp = float(cost.get("expected") or 0.0)
    cost["min"] = round(min(mn, exp, mx), 2)
    cost["max"] = round(max(mn, exp, mx), 2)
    cost["expected"] = round(max(min(exp, cost["max"]), cost["min"]), 2)

    # Clamp score 0..100
    score = out.get("overall_financial_risk_score", 0.0)
    out["overall_financial_risk_score"] = round(min(max(float(score or 0), 0.0), 100.0), 1)

    # Ensure no NaN/Inf in by_event costs
    for ev in out.get("financial_exposure_by_event", {}).values():
        if isinstance(ev, dict):
            for k in ("min", "max", "expected"):
                v = ev.get(k)
                if v is not None and (math.isnan(float(v)) or math.isinf(float(v))):
                    ev[k] = 0.0

    return {**state, "final_output": out}

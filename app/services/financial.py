"""
Financial exposure calculator.
Uses config/legal_costs.json — all figures configurable.

Formula per event:
  min = P(event) * passengers_exposed * min_cost_per_passenger
  max = P(event) * passengers_exposed * max_cost_per_passenger
  expected = (min + max) / 2

Judicial exposure is calculated separately and NEVER added to operational expected cost.

Overall score (0-100):
  risk_component  = (delay_p*0.50 + ob_p*0.30 + conn_p*0.20) * 70
  cost_component  = min(expected_cost / 500_000, 1.0) * 30
  score = risk_component + cost_component
"""
import json
import os


def _load_config() -> dict:
    cfg_path = os.path.join(os.path.dirname(__file__), "../config/legal_costs.json")
    with open(cfg_path) as f:
        return json.load(f)


def _event_cost(prob: float, passengers: int, cfg_key: dict) -> dict:
    """Calculate min/max/expected cost for one risk event."""
    mn = prob * passengers * cfg_key["min_per_passenger"]
    mx = prob * passengers * cfg_key["max_per_passenger"]
    exp = (mn + mx) / 2.0
    return {
        "min": round(mn, 2),
        "max": round(mx, 2),
        "expected": round(exp, 2),
    }


def calculate_financial_exposure(risks: dict, bookings: int, capacity: int | None) -> dict:
    cfg = _load_config()
    currency = "BRL"

    delay = risks.get("delay", {})
    ob = risks.get("overbooking", {})
    conn = risks.get("missed_connection", {})
    canc = risks.get("cancellation", {})

    delay_prob = float(delay.get("probability") or 0.0)
    ob_prob = float(ob.get("probability") or 0.0)
    conn_prob = float(conn.get("probability") or 0.0)
    canc_prob = float(canc.get("probability") or 0.0)

    overflow = int(ob.get("overflow") or 0)

    # ── passengers per event ──────────────────────────────────────────────────
    # Delay: all booked passengers exposed
    delay_pax = int(bookings * delay_prob)

    # Overbooking: confirmed overflow takes priority; else probabilistic
    if overflow > 0:
        ob_pax = overflow
        ob_prob_effective = 1.0  # confirmed event
    else:
        ob_pax = max(int(bookings * ob_prob * 0.05), 0)
        ob_prob_effective = ob_prob

    # Missed connection: ~30% of delayed passengers assumed to have connections
    conn_pax = int(bookings * conn_prob * 0.30)

    # Cancellation: if available, all bookings at risk
    canc_pax = int(bookings * canc_prob) if canc.get("available") else 0

    # ── cost by event ─────────────────────────────────────────────────────────
    delay_cost = _event_cost(delay_prob, bookings, cfg["delay_severe"])
    delay_cost["passengers_exposed"] = delay_pax
    delay_cost["cost_basis"] = cfg["delay_severe"]["cost_basis"]
    delay_cost["available"] = delay.get("available", True)

    ob_cost_cfg = cfg["overbooking"]
    if overflow > 0:
        ob_min = overflow * ob_cost_cfg["min_per_passenger"]
        ob_max = overflow * ob_cost_cfg["max_per_passenger"]
    else:
        ob_min = ob_prob * ob_pax * ob_cost_cfg["min_per_passenger"]
        ob_max = ob_prob * ob_pax * ob_cost_cfg["max_per_passenger"]
    ob_cost = {
        "available": ob.get("available", True),
        "passengers_exposed": ob_pax,
        "min": round(ob_min, 2),
        "max": round(ob_max, 2),
        "expected": round((ob_min + ob_max) / 2.0, 2),
    }

    conn_cost = _event_cost(conn_prob, conn_pax, cfg["missed_connection"])
    conn_cost["passengers_exposed"] = conn_pax
    conn_cost["available"] = conn.get("available", True)

    if canc.get("available") and canc_prob > 0:
        canc_cost = _event_cost(canc_prob, bookings, cfg["cancellation"])
        canc_cost["passengers_exposed"] = canc_pax
        canc_cost["available"] = True
    else:
        canc_cost = {
            "available": False,
            "passengers_exposed": 0,
            "min": 0.0, "max": 0.0, "expected": 0.0,
        }

    # ── operational total (NO judicial) ───────────────────────────────────────
    total_min = delay_cost["min"] + ob_cost["min"] + conn_cost["min"] + canc_cost["min"]
    total_max = delay_cost["max"] + ob_cost["max"] + conn_cost["max"] + canc_cost["max"]
    total_exp = delay_cost["expected"] + ob_cost["expected"] + conn_cost["expected"] + canc_cost["expected"]

    # ── judicial exposure (separate, never added to operational) ──────────────
    jud_cfg = cfg["judicial_exposure"]
    total_affected_pax = max(delay_pax, ob_pax, conn_pax)  # de-dup by taking max
    judicial = {
        "included_in_operational_expected_cost": False,
        "affected_passengers_estimate": total_affected_pax,
        "min_additional": round(total_affected_pax * jud_cfg["min_per_passenger"], 2),
        "max_additional": round(total_affected_pax * jud_cfg["max_per_passenger"], 2),
        "min_per_passenger": jud_cfg["min_per_passenger"],
        "max_per_passenger": jud_cfg["max_per_passenger"],
        "currency": currency,
        "basis": jud_cfg["description"],
    }

    # ── passenger exposure by event ───────────────────────────────────────────
    by_event_pax = {
        "delay": delay_pax,
        "overbooking": ob_pax,
        "missed_connection": conn_pax,
        "cancellation": canc_pax,
    }

    return {
        "by_event": {
            "delay": delay_cost,
            "overbooking": ob_cost,
            "missed_connection": conn_cost,
            "cancellation": canc_cost,
        },
        "operational_expected_cost": {
            "min": round(total_min, 2),
            "max": round(total_max, 2),
            "expected": round(total_exp, 2),
            "currency": currency,
        },
        "judicial_exposure": judicial,
        # kept for backward-compat with validate_output
        "min": round(total_min, 2),
        "max": round(total_max, 2),
        "expected": round(total_exp, 2),
        "currency": currency,
        "_by_event_passengers": by_event_pax,
    }


def calculate_overall_score(risks: dict, cost: dict, bookings: int) -> tuple[float, str]:
    """
    Score 0-100. Deterministic, documented.
    risk_component  = (delay_p*0.50 + ob_p*0.30 + conn_p*0.20) * 70
    cost_component  = min(expected_cost / 500_000, 1.0) * 30
    """
    delay_p = float(risks.get("delay", {}).get("probability") or 0.0)
    ob_p = float(risks.get("overbooking", {}).get("probability") or 0.0)
    conn_p = float(risks.get("missed_connection", {}).get("probability") or 0.0)

    risk_component = (delay_p * 0.50 + ob_p * 0.30 + conn_p * 0.20) * 70.0
    expected_cost = float(cost.get("expected", 0.0))
    cost_component = min(expected_cost / 500_000.0, 1.0) * 30.0

    raw = risk_component + cost_component
    score = round(min(max(raw, 0.0), 100.0), 1)

    if score <= 30:
        level = "LOW"
    elif score <= 60:
        level = "MEDIUM"
    elif score <= 80:
        level = "HIGH"
    else:
        level = "CRITICAL"

    return score, level

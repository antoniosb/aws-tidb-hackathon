"""Financial exposure calculator. All figures from config/legal_costs.json."""
import json
import os


def _load_config() -> dict:
    cfg_path = os.path.join(os.path.dirname(__file__), "../config/legal_costs.json")
    with open(cfg_path) as f:
        return json.load(f)


def calculate_financial_exposure(
    risks: dict,
    bookings: int,
    capacity: int | None,
) -> dict:
    cfg = _load_config()
    currency = cfg.get("currency", "BRL")

    delay_prob = risks["delay"].get("probability") or 0.0
    avg_delay = risks["delay"].get("avg_delay_min", 30.0)
    overflow = risks["overbooking"].get("overflow", 0)
    ob_prob = risks["overbooking"].get("probability") or 0.0
    conn_prob = risks["missed_connection"].get("probability") or 0.0

    # Delay cost
    if avg_delay >= 240:
        cost_pp = cfg["delay"]["severe"]["cost_per_passenger"]
    elif avg_delay >= 120:
        cost_pp = cfg["delay"]["moderate"]["cost_per_passenger"]
    else:
        cost_pp = cfg["delay"]["minor"]["cost_per_passenger"]

    delay_expected = delay_prob * bookings * cost_pp
    delay_min = delay_expected * 0.6
    delay_max = delay_expected * 1.5

    # Overbooking cost
    if overflow > 0:
        ob_affected = overflow
    else:
        ob_affected = ob_prob * bookings * 0.05  # 5% at risk if not confirmed overflow
    ob_cost = cfg["overbooking"]["cost_per_passenger"]
    ob_expected = ob_affected * ob_cost
    ob_min = ob_expected * 0.7
    ob_max = ob_expected * 1.3

    # Missed connection cost
    conn_affected = conn_prob * bookings
    conn_cost = cfg["missed_connection"]["cost_per_passenger"]
    conn_expected = conn_affected * conn_cost
    conn_min = conn_expected * 0.6
    conn_max = conn_expected * 1.4

    total_expected = delay_expected + ob_expected + conn_expected
    total_min = delay_min + ob_min + conn_min
    total_max = delay_max + ob_max + conn_max

    return {
        "min": round(total_min, 2),
        "max": round(total_max, 2),
        "expected": round(total_expected, 2),
        "currency": currency,
        "_breakdown": {
            "delay": round(delay_expected, 2),
            "overbooking": round(ob_expected, 2),
            "missed_connection": round(conn_expected, 2),
        },
    }


def calculate_overall_score(risks: dict, cost: dict, bookings: int) -> tuple[float, str]:
    """
    Score 0-100 based on weighted risk probabilities + financial exposure.
    """
    delay_p = risks["delay"].get("probability") or 0.0
    ob_p = risks["overbooking"].get("probability") or 0.0
    conn_p = risks["missed_connection"].get("probability") or 0.0

    risk_score = (delay_p * 0.50 + ob_p * 0.30 + conn_p * 0.20) * 70.0

    # Financial component: normalize expected cost by rough max (e.g. 500k BRL)
    financial_score = min(cost["expected"] / 500_000, 1.0) * 30.0

    raw = risk_score + financial_score
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

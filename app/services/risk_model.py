"""
Delay probability engine.
Primary: weighted historical rates from real TiDB data.
No ML training needed — avoids cold start and schema uncertainty.
Returns probability 0..1.
"""


def _risk_level(p: float) -> str:
    if p < 0.30:
        return "LOW"
    if p < 0.60:
        return "MEDIUM"
    if p < 0.80:
        return "HIGH"
    return "CRITICAL"


def calculate_delay_probability(patterns: dict, weather_condition: str | None = None) -> dict:
    """
    Weighted blend of historical rates.
    Weights: route 50%, origin 25%, hour 15%, weather 10%.
    Falls back to 0.35 if no data.
    """
    route = patterns.get("route", {})
    route_rate = route.get("delay_rate", 0.0)
    route_count = route.get("count", 0)
    origin_rate = patterns.get("origin_delay_rate", 0.0)
    hour_rate = patterns.get("hour_delay_rate", 0.0)
    weather_rate = patterns.get("weather_delay_rate", 0.0)

    # Weather boost if bad weather provided by user
    bad_weather = weather_condition and any(
        w in (weather_condition or "").lower()
        for w in ["storm", "fog", "snow", "rain", "thunder"]
    )
    weather_boost = 0.15 if bad_weather else 0.0

    if route_count == 0:
        # No route history — use global fallback
        probability = max(origin_rate * 0.6 + hour_rate * 0.4, 0.25)
        confidence = "LOW"
        drivers = ["No direct route history; using origin and departure-hour rates"]
    else:
        probability = (
            route_rate * 0.50
            + origin_rate * 0.25
            + hour_rate * 0.15
            + weather_rate * 0.10
        ) + weather_boost
        confidence = "HIGH" if route_count >= 10 else "MEDIUM"
        drivers = []
        if route_rate > 0.5:
            drivers.append(f"Route delay rate {route_rate:.0%} ({route_count} flights)")
        if origin_rate > 0.4:
            drivers.append(f"Origin airport delay rate {origin_rate:.0%}")
        if hour_rate > 0.4:
            drivers.append("Departure hour historically congested")
        if bad_weather:
            drivers.append(f"Adverse weather: {weather_condition}")
        if not drivers:
            drivers.append(f"Moderate historical delay pattern ({route_rate:.0%} on route)")

    probability = min(max(probability, 0.0), 1.0)
    return {
        "probability": round(probability, 3),
        "level": _risk_level(probability),
        "confidence": confidence,
        "drivers": drivers,
        "avg_delay_min": round(route.get("avg_delay_min", 0.0), 1),
    }


def calculate_overbooking_risk(capacity: int | None, bookings: int | None,
                                booking_ratio_history: float = 0.0) -> dict:
    if capacity is None or bookings is None:
        # Use historical booking ratio as proxy
        if booking_ratio_history > 0:
            probability = min(max((booking_ratio_history - 0.7) / 0.3, 0.0), 1.0)
            drivers = [f"Historical avg booking ratio {booking_ratio_history:.0%}"]
            confidence = "MEDIUM"
        else:
            return {
                "available": False, "probability": None,
                "level": "UNKNOWN", "confidence": "LOW", "drivers": [],
                "overflow": 0, "booking_ratio": None,
            }
        return {
            "available": True,
            "probability": round(probability, 3),
            "level": _risk_level(probability),
            "confidence": confidence,
            "drivers": drivers,
            "overflow": 0,
            "booking_ratio": round(booking_ratio_history, 3),
        }

    ratio = bookings / capacity if capacity > 0 else 0.0
    overflow = max(bookings - capacity, 0)

    if overflow > 0:
        probability = min(0.85 + (overflow / capacity) * 0.15, 1.0)
    elif ratio >= 0.95:
        probability = 0.70
    elif ratio >= 0.85:
        probability = 0.45
    elif ratio >= 0.75:
        probability = 0.25
    else:
        probability = max(ratio - 0.5, 0.0)

    drivers = []
    if overflow > 0:
        drivers.append(f"Confirmed overbooking: {overflow} excess passengers")
    if ratio >= 0.95:
        drivers.append(f"Booking ratio {ratio:.0%} — near/over capacity")
    elif ratio >= 0.85:
        drivers.append(f"Booking ratio {ratio:.0%} — high demand")

    return {
        "available": True,
        "probability": round(probability, 3),
        "level": _risk_level(probability),
        "confidence": "HIGH",
        "drivers": drivers,
        "overflow": overflow,
        "booking_ratio": round(ratio, 3),
    }


def calculate_missed_connection_risk(delay_probability: float, avg_delay_min: float) -> dict:
    """
    Without direct connection data, estimate from delay probability and magnitude.
    Connections with < 60 min margin are at risk when delay > 15 min.
    """
    # Rough estimate: ~30% of passengers have connections with tight margins
    connection_exposure = 0.30
    p = delay_probability * connection_exposure * min(avg_delay_min / 60.0, 1.0) if avg_delay_min > 15 else 0.0
    p = min(p * 2.5, 1.0)  # scale up since it's conditional

    if p < 0.05:
        return {
            "available": True, "probability": round(p, 3),
            "level": "LOW", "confidence": "LOW",
            "drivers": ["Minimal delay risk; connection impact negligible"],
        }
    return {
        "available": True,
        "probability": round(p, 3),
        "level": _risk_level(p),
        "confidence": "LOW",
        "drivers": [
            f"Derived from delay probability {delay_probability:.0%}",
            f"Avg historical delay {avg_delay_min:.0f} min",
            "~30% passengers assumed to have connections",
        ],
    }

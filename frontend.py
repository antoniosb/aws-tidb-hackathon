"""
Flight Risk AI — Streamlit frontend
Run: .venv/bin/streamlit run frontend.py
"""

import json
from datetime import datetime, time

import requests
import streamlit as st

API_URL = "http://localhost:8000"

# ── page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Flight Risk AI",
    page_icon="✈️",
    layout="wide",
)

# ── helpers ───────────────────────────────────────────────────────────────────
RISK_COLORS = {
    "LOW": "🟢",
    "MEDIUM": "🟡",
    "HIGH": "🔴",
    "CRITICAL": "🔥",
    "UNKNOWN": "⚪",
}

LEVEL_CSS = {
    "LOW": "background:#d4edda;color:#155724;padding:4px 10px;border-radius:6px;font-weight:bold",
    "MEDIUM": "background:#fff3cd;color:#856404;padding:4px 10px;border-radius:6px;font-weight:bold",
    "HIGH": "background:#f8d7da;color:#721c24;padding:4px 10px;border-radius:6px;font-weight:bold",
    "CRITICAL": "background:#6f0000;color:#fff;padding:4px 10px;border-radius:6px;font-weight:bold",
    "UNKNOWN": "background:#e2e3e5;color:#383d41;padding:4px 10px;border-radius:6px;font-weight:bold",
}


def badge(level: str) -> str:
    css = LEVEL_CSS.get(level, LEVEL_CSS["UNKNOWN"])
    return f'<span style="{css}">{RISK_COLORS.get(level,"")} {level}</span>'


def pct(v) -> str:
    return f"{v:.0%}" if v is not None else "N/A"


# ── header ────────────────────────────────────────────────────────────────────
st.title("✈️ Flight Risk AI")
st.caption(
    "AI-driven airline operational risk & financial exposure analysis · "
    "TiDB Cloud · Amazon Bedrock · LangGraph"
)

# ── sidebar: health ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("System Status")
    try:
        h = requests.get(f"{API_URL}/health", timeout=5).json()
        st.success("API online")
        st.write("🗄️ TiDB", "✅" if h.get("tidb") else "❌")
        st.write("🤖 Bedrock", "✅" if h.get("bedrock") else "❌")
    except Exception:
        st.error("API offline — start with:\nuvicorn app.main:app --port 8000")

    st.divider()
    st.markdown("**Demo payload**")
    if st.button("Load demo flight"):
        st.session_state["demo"] = True

# ── input form ────────────────────────────────────────────────────────────────
demo = st.session_state.get("demo", False)

with st.form("flight_form"):
    st.subheader("Flight Details")
    c1, c2, c3 = st.columns(3)
    with c1:
        flight_number = st.text_input("Flight number", value="LH507" if demo else "")
        origin = st.text_input("Origin (IATA)", value="GRU" if demo else "", max_chars=3)
        destination = st.text_input("Destination (IATA)", value="FRA" if demo else "", max_chars=3)
    with c2:
        dep_date = st.date_input("Departure date", value=datetime.today())
        dep_time = st.time_input("Departure time", value=time(18, 40) if demo else time(12, 0))
        aircraft_type = st.text_input("Aircraft type", value="Boeing 767" if demo else "")
    with c3:
        capacity = st.number_input("Capacity (seats)", min_value=0, value=200 if demo else 0)
        bookings = st.number_input("Confirmed bookings", min_value=0, value=191 if demo else 0)
        airline_iata = st.text_input("Airline IATA (optional)", value="LH" if demo else "")

    st.subheader("Weather (optional)")
    wc1, wc2, wc3, wc4 = st.columns(4)
    with wc1:
        weather_condition = st.selectbox(
            "Condition",
            ["", "clear", "rain", "fog", "thunderstorm", "snowfall", "fog-rain", "rain-thunderstorm"],
            index=2 if demo else 0,
        )
    with wc2:
        temp = st.number_input("Temp (°C)", value=18 if demo else 22, min_value=-60, max_value=60)
    with wc3:
        wind = st.number_input("Wind (km/h)", value=45 if demo else 15, min_value=0, max_value=300)
    with wc4:
        humidity = st.number_input("Humidity (%)", value=75 if demo else 60, min_value=0, max_value=100)

    submitted = st.form_submit_button("🔍 Analyze Flight", type="primary", use_container_width=True)

# ── call API & render results ─────────────────────────────────────────────────
if submitted:
    departure_time = datetime.combine(dep_date, dep_time).isoformat()
    payload = {
        "flight_number": flight_number or "N/A",
        "origin": origin.upper(),
        "destination": destination.upper(),
        "departure_time": departure_time,
        "aircraft_type": aircraft_type or None,
        "capacity": int(capacity) if capacity else None,
        "bookings": int(bookings) if bookings else None,
        "airline_iata": airline_iata or None,
        "weather": {
            "condition": weather_condition or None,
            "temp_celsius": float(temp),
            "wind_kmh": float(wind),
            "humidity_pct": float(humidity),
        } if weather_condition else None,
    }

    with st.spinner("Analyzing flight risk..."):
        try:
            resp = requests.post(
                f"{API_URL}/analyze-flight",
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.ConnectionError:
            st.error("Cannot connect to API. Make sure the server is running on port 8000.")
            st.stop()
        except Exception as e:
            st.error(f"API error: {e}")
            st.stop()

    # ── overall score ─────────────────────────────────────────────────────────
    score = data.get("overall_financial_risk_score", 0)
    level = data.get("overall_financial_risk_level", "UNKNOWN")

    st.divider()
    st.subheader(f"Analysis: {data.get('flight_number')}  {data.get('origin')} → {data.get('destination')}")

    col_score, col_cost, col_pax = st.columns(3)
    with col_score:
        st.metric("Overall Risk Score", f"{score}/100")
        st.markdown(badge(level), unsafe_allow_html=True)
    with col_cost:
        cost = data.get("estimated_passenger_cost", {})
        st.metric(
            "Expected Financial Exposure",
            f"R$ {cost.get('expected', 0):,.0f}",
            delta=f"Range: R$ {cost.get('min', 0):,.0f} – R$ {cost.get('max', 0):,.0f}",
            delta_color="off",
        )
    with col_pax:
        pe = data.get("passenger_exposure", {})
        st.metric(
            "Passengers at Risk",
            pe.get("estimated_passengers_at_risk", 0),
            delta=f"of {pe.get('total_bookings', 0)} booked",
            delta_color="off",
        )

    # ── risk breakdown ────────────────────────────────────────────────────────
    st.subheader("Risk Breakdown")
    risks = data.get("risks", {})
    r1, r2, r3, r4 = st.columns(4)

    def risk_card(col, title, key):
        risk = risks.get(key, {})
        with col:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                if not risk.get("available"):
                    st.markdown("⚪ Not available")
                    st.caption("Insufficient data")
                    return
                prob = risk.get("probability")
                lvl = risk.get("level", "UNKNOWN")
                st.markdown(badge(lvl), unsafe_allow_html=True)
                st.progress(float(prob or 0), text=f"Probability: {pct(prob)}")
                for d in risk.get("drivers", []):
                    st.caption(f"• {d}")

    risk_card(r1, "✈️ Delay", "delay")
    risk_card(r2, "🎟️ Overbooking", "overbooking")
    risk_card(r3, "🔗 Missed Connection", "missed_connection")
    risk_card(r4, "❌ Cancellation", "cancellation")

    # ── AI summary ────────────────────────────────────────────────────────────
    st.subheader("🤖 AI Risk Analysis")
    summary = data.get("summary", "")
    if summary:
        st.info(summary)

    # ── recommendations ───────────────────────────────────────────────────────
    recs = data.get("recommendations", [])
    if recs:
        st.subheader("📋 Preventive Recommendations")
        for rec in sorted(recs, key=lambda r: r.get("priority", 99)):
            with st.expander(f"#{rec.get('priority')} — {rec.get('action', '')}"):
                st.write("**Reason:**", rec.get("reason", ""))
                if rec.get("estimated_impact"):
                    st.write("**Estimated impact:**", rec["estimated_impact"])

    # ── similar cases ─────────────────────────────────────────────────────────
    cases = data.get("similar_historical_cases", [])
    if cases:
        st.subheader("🔍 Similar Historical Cases")
        for c in cases:
            orig = c.get("origin") or "?"
            dest = c.get("destination") or "?"
            st.markdown(
                f"**{orig} → {dest}** · delay {c.get('delay_minutes', 0):.0f} min · "
                f"booking ratio {c.get('booking_ratio', 0):.0%} · "
                f"similarity {c.get('similarity', 0):.0%}"
            )

    # ── raw JSON toggle ───────────────────────────────────────────────────────
    with st.expander("Raw JSON response"):
        st.json(data)

    # clear demo state after first run
    if "demo" in st.session_state:
        del st.session_state["demo"]

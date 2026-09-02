from typing import Any, Optional
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    flight_input: dict
    historical_patterns: dict
    similar_cases: list[dict]
    risks: dict
    passenger_exposure: dict
    estimated_cost: dict
    overall_risk_score: float
    overall_risk_level: str
    ai_summary: str
    ai_provider: str
    recommendations: list[dict]
    final_output: dict
    errors: list[str]

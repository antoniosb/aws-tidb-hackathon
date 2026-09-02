from typing import Any, Optional

from pydantic import BaseModel


class RiskItem(BaseModel):
    available: bool
    probability: Optional[float]
    level: str
    confidence: str
    drivers: list[str]


class Risks(BaseModel):
    delay: RiskItem
    overbooking: RiskItem
    missed_connection: RiskItem
    cancellation: RiskItem


class PassengerExposure(BaseModel):
    total_bookings: int
    estimated_passengers_at_risk: int


class CostEstimate(BaseModel):
    min: float
    max: float
    expected: float
    currency: str


class Recommendation(BaseModel):
    priority: int
    action: str
    reason: str
    estimated_impact: Optional[str] = None


class FlightAnalysisOutput(BaseModel):
    flight_number: str
    origin: str
    destination: str
    risks: Risks
    passenger_exposure: PassengerExposure
    estimated_passenger_cost: CostEstimate
    overall_financial_risk_score: float
    overall_financial_risk_level: str
    summary: str
    recommendations: list[Recommendation]
    similar_historical_cases: list[dict[str, Any]]

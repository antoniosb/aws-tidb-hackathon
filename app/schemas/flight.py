from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class WeatherInput(BaseModel):
    condition: Optional[str] = None
    temp_celsius: Optional[float] = None
    wind_kmh: Optional[float] = None
    humidity_pct: Optional[float] = None


class FlightInput(BaseModel):
    flight_number: str = "XX0000"
    origin: str  # IATA code e.g. GRU
    destination: str  # IATA code e.g. FRA
    departure_time: datetime
    aircraft_type: Optional[str] = None
    capacity: Optional[int] = None
    bookings: Optional[int] = None
    airline_iata: Optional[str] = None
    weather: Optional[WeatherInput] = None

    @field_validator("origin", "destination", mode="before")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.strip().upper()

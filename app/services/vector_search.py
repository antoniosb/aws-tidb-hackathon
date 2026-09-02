"""TiDB vector search for similar historical flight cases."""
import os
import ssl

import pymysql
from dotenv import load_dotenv

load_dotenv()

_SSL_CA = ssl.get_default_verify_paths().cafile or "/etc/ssl/cert.pem"

TABLE_DDL = """
CREATE TABLE IF NOT EXISTS flight_risk_memory (
    id BIGINT AUTO_RANDOM PRIMARY KEY,
    flight_id INT,
    origin_iata CHAR(3),
    dest_iata CHAR(3),
    description TEXT,
    delay_minutes FLOAT,
    booking_ratio FLOAT,
    embedding VECTOR(1024) GENERATED ALWAYS AS (
        EMBED_TEXT('tidbcloud_free/amazon/titan-embed-text-v2', description)
    ) STORED
)
"""


def _get_conn():
    return pymysql.connect(
        host=os.environ["TIDB_HOST"],
        port=int(os.environ.get("TIDB_PORT", 4000)),
        user=os.environ["TIDB_USER"],
        password=os.environ["TIDB_PASSWORD"],
        database=os.environ.get("TIDB_DATABASE", "airportdb"),
        ssl={"ca": _SSL_CA},
        autocommit=True,
        connect_timeout=15,
    )


def ensure_table_populated() -> bool:
    """Create table and populate with a sample of real flight data if empty."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(TABLE_DDL)
            cur.execute("SELECT COUNT(*) FROM flight_risk_memory")
            count = cur.fetchone()[0]
            if count > 0:
                conn.close()
                return True

            # Populate with 200 representative flights
            cur.execute("""
                INSERT INTO flight_risk_memory (flight_id, origin_iata, dest_iata, description, delay_minutes, booking_ratio)
                SELECT
                    f.flight_id,
                    ao.iata as origin_iata,
                    ad.iata as dest_iata,
                    CONCAT(
                        'Flight ', f.flightno,
                        ' from ', ao.iata, ' to ', ad.iata,
                        '. Aircraft type: ', at2.identifier,
                        '. Departure hour: ', HOUR(f.departure),
                        '. Day of week: ', DAYOFWEEK(f.departure),
                        '. Booking ratio: ', ROUND(COUNT(b.booking_id)/ap.capacity, 2),
                        '. Actual duration minutes: ', ROUND(TIME_TO_SEC(TIMEDIFF(f.arrival, f.departure))/60, 0),
                        '. Scheduled duration minutes: ', ROUND((TIME_TO_SEC(fs.arrival) - TIME_TO_SEC(fs.departure))/60, 0),
                        '. Delay minutes: ', GREATEST(ROUND((TIME_TO_SEC(TIMEDIFF(f.arrival, f.departure)) - (TIME_TO_SEC(fs.arrival) - TIME_TO_SEC(fs.departure)))/60, 0), 0)
                    ) as description,
                    GREATEST((TIME_TO_SEC(TIMEDIFF(f.arrival, f.departure)) - (TIME_TO_SEC(fs.arrival) - TIME_TO_SEC(fs.departure)))/60.0, 0) as delay_minutes,
                    COUNT(b.booking_id)/ap.capacity as booking_ratio
                FROM flight f
                JOIN airport ao ON f.`from` = ao.airport_id
                JOIN airport ad ON f.`to` = ad.airport_id
                JOIN airplane ap ON f.airplane_id = ap.airplane_id
                JOIN airplane_type at2 ON ap.type_id = at2.type_id
                JOIN flightschedule fs ON f.flightno = fs.flightno
                LEFT JOIN booking b ON f.flight_id = b.flight_id
                GROUP BY f.flight_id, ao.iata, ad.iata, at2.identifier, ap.capacity, f.departure, f.arrival, fs.arrival, fs.departure, f.flightno
                HAVING ap.capacity > 0
                ORDER BY RAND()
                LIMIT 200
            """)
        conn.close()
        return True
    except Exception as e:
        print(f"[vector_search] table setup failed: {e}")
        return False


def find_similar_cases(origin: str, destination: str, aircraft_type: str | None,
                       booking_ratio: float, departure_hour: int, top_k: int = 3) -> list[dict]:
    """Search for similar historical cases using TiDB EMBED_TEXT vector search."""
    try:
        query_text = (
            f"Flight from {origin} to {destination}. "
            f"Aircraft type: {aircraft_type or 'unknown'}. "
            f"Departure hour: {departure_hour}. "
            f"Booking ratio: {round(booking_ratio, 2)}."
        )
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    flight_id, origin_iata, dest_iata, description,
                    delay_minutes, booking_ratio,
                    VEC_COSINE_DISTANCE(
                        embedding,
                        EMBED_TEXT('tidbcloud_free/amazon/titan-embed-text-v2', %s)
                    ) as distance
                FROM flight_risk_memory
                ORDER BY distance ASC
                LIMIT %s
            """, (query_text, top_k))
            rows = cur.fetchall()
        conn.close()
        return [
            {
                "flight_id": r[0],
                "origin": r[1] or "?",
                "destination": r[2] or "?",
                "description": (r[3] or "")[:200],
                "delay_minutes": float(r[4] or 0),
                "booking_ratio": float(r[5] or 0),
                "similarity": round(1.0 - float(r[6] or 1.0), 3),
            }
            for r in rows
            if r[1] and r[2]  # skip rows with missing airport codes
        ]
    except Exception as e:
        print(f"[vector_search] query failed: {e}")
        return []

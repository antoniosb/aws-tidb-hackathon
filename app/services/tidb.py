"""TiDB connection and historical pattern queries."""
import os
import ssl

import pymysql
from dotenv import load_dotenv

load_dotenv()

_SSL_CA = ssl.get_default_verify_paths().cafile or "/etc/ssl/cert.pem"


def get_conn() -> pymysql.Connection:
    return pymysql.connect(
        host=os.environ["TIDB_HOST"],
        port=int(os.environ.get("TIDB_PORT", 4000)),
        user=os.environ["TIDB_USER"],
        password=os.environ["TIDB_PASSWORD"],
        database=os.environ.get("TIDB_DATABASE", "airportdb"),
        ssl={"ca": _SSL_CA},
        autocommit=True,
        connect_timeout=10,
    )


def get_historical_patterns(origin: str, destination: str, departure_hour: int) -> dict:
    """
    Query real historical data.
    Delay target: actual flight duration > scheduled duration + 15 min.
    """
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            # Get airport IDs
            cur.execute("SELECT airport_id FROM airport WHERE iata=%s", (origin,))
            row = cur.fetchone()
            origin_id = row[0] if row else None

            cur.execute("SELECT airport_id FROM airport WHERE iata=%s", (destination,))
            row = cur.fetchone()
            dest_id = row[0] if row else None

            # Route delay rate: actual_duration vs scheduled_duration
            route_stats = {"count": 0, "delay_rate": 0.0, "avg_delay_min": 0.0}
            if origin_id and dest_id:
                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN
                            TIME_TO_SEC(TIMEDIFF(f.arrival, f.departure)) >
                            TIME_TO_SEC(fs.arrival) - TIME_TO_SEC(fs.departure) + 900
                        THEN 1 ELSE 0 END) as delayed,
                        AVG(GREATEST(
                            TIME_TO_SEC(TIMEDIFF(f.arrival, f.departure)) -
                            (TIME_TO_SEC(fs.arrival) - TIME_TO_SEC(fs.departure)),
                            0
                        )) / 60.0 as avg_delay_min
                    FROM flight f
                    JOIN flightschedule fs ON f.flightno = fs.flightno
                    WHERE f.`from` = %s AND f.`to` = %s
                """, (origin_id, dest_id))
                row = cur.fetchone()
                if row and row[0]:
                    route_stats = {
                        "count": int(row[0]),
                        "delay_rate": float(row[1] or 0) / float(row[0]) if row[0] else 0.0,
                        "avg_delay_min": float(row[2] or 0),
                    }

            # Origin airport delay rate
            origin_delay_rate = 0.0
            if origin_id:
                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN
                            TIME_TO_SEC(TIMEDIFF(f.arrival, f.departure)) >
                            TIME_TO_SEC(fs.arrival) - TIME_TO_SEC(fs.departure) + 900
                        THEN 1 ELSE 0 END) as delayed
                    FROM flight f
                    JOIN flightschedule fs ON f.flightno = fs.flightno
                    WHERE f.`from` = %s
                """, (origin_id,))
                row = cur.fetchone()
                if row and row[0]:
                    origin_delay_rate = float(row[1] or 0) / float(row[0])

            # Hour-of-day delay rate
            cur.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN
                        TIME_TO_SEC(TIMEDIFF(f.arrival, f.departure)) >
                        TIME_TO_SEC(fs.arrival) - TIME_TO_SEC(fs.departure) + 900
                    THEN 1 ELSE 0 END) as delayed
                FROM flight f
                JOIN flightschedule fs ON f.flightno = fs.flightno
                WHERE HOUR(f.departure) = %s
            """, (departure_hour,))
            row = cur.fetchone()
            hour_delay_rate = float(row[1] or 0) / float(row[0]) if (row and row[0]) else 0.0

            # Booking ratio history for the route
            booking_ratio_avg = 0.0
            if origin_id and dest_id:
                cur.execute("""
                    SELECT AVG(sub.ratio) FROM (
                        SELECT COUNT(b.booking_id) / ap.capacity as ratio
                        FROM flight f
                        JOIN airplane ap ON f.airplane_id = ap.airplane_id
                        LEFT JOIN booking b ON f.flight_id = b.flight_id
                        WHERE f.`from` = %s AND f.`to` = %s
                        GROUP BY f.flight_id, ap.capacity
                        HAVING ap.capacity > 0
                    ) sub
                """, (origin_id, dest_id))
                row = cur.fetchone()
                booking_ratio_avg = float(row[0] or 0) if row else 0.0

            # Weather conditions at origin on historical dates
            weather_delay_rate = 0.0
            if origin_id:
                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN
                            TIME_TO_SEC(TIMEDIFF(f.arrival, f.departure)) >
                            TIME_TO_SEC(fs.arrival) - TIME_TO_SEC(fs.departure) + 900
                        THEN 1 ELSE 0 END) as delayed
                    FROM flight f
                    JOIN flightschedule fs ON f.flightno = fs.flightno
                    JOIN weatherdata w ON DATE(f.departure) = w.log_date
                        AND ABS(HOUR(f.departure)*3600 - TIME_TO_SEC(w.time)) < 7200
                        AND w.station = %s
                    WHERE w.weather IS NOT NULL
                        AND w.weather != ''
                """, (origin_id,))
                row = cur.fetchone()
                weather_delay_rate = float(row[1] or 0) / float(row[0]) if (row and row[0]) else 0.0

        conn.close()
        return {
            "route": route_stats,
            "origin_delay_rate": origin_delay_rate,
            "hour_delay_rate": hour_delay_rate,
            "booking_ratio_avg": booking_ratio_avg,
            "weather_delay_rate": weather_delay_rate,
            "origin_id": origin_id,
            "dest_id": dest_id,
        }
    except Exception as e:
        return {
            "route": {"count": 0, "delay_rate": 0.3, "avg_delay_min": 30.0},
            "origin_delay_rate": 0.3,
            "hour_delay_rate": 0.3,
            "booking_ratio_avg": 0.7,
            "weather_delay_rate": 0.0,
            "origin_id": None,
            "dest_id": None,
            "error": str(e),
        }

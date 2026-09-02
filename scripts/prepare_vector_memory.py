"""
Populate flight_risk_memory table with sample flights for vector search.
Run once before starting the API:
  .venv/bin/python scripts/prepare_vector_memory.py
"""
import os
import ssl
import sys
import time

import pymysql
from dotenv import load_dotenv

load_dotenv()

SSL_CA = ssl.get_default_verify_paths().cafile or "/etc/ssl/cert.pem"
BATCH_SIZE = 10
TARGET = 100


def get_conn():
    return pymysql.connect(
        host=os.environ["TIDB_HOST"],
        port=int(os.environ.get("TIDB_PORT", 4000)),
        user=os.environ["TIDB_USER"],
        password=os.environ["TIDB_PASSWORD"],
        database=os.environ.get("TIDB_DATABASE", "airportdb"),
        ssl={"ca": SSL_CA},
        autocommit=True,
        connect_timeout=15,
    )


DDL = """
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


def main():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute("SELECT COUNT(*) FROM flight_risk_memory WHERE description IS NOT NULL")
        existing = cur.fetchone()[0]
        print(f"Existing rows with embeddings: {existing}")
        if existing >= TARGET:
            print(f"Already have {existing} rows. Done.")
            return

        # Fetch raw flight data
        cur.execute("""
            SELECT
                f.flight_id,
                ao.iata as orig,
                ad.iata as dest,
                at2.identifier as atype,
                ap.capacity,
                COUNT(b.booking_id) as bk,
                HOUR(f.departure) as hr,
                ROUND(TIME_TO_SEC(TIMEDIFF(f.arrival, f.departure))/60,0) as actual_min,
                ROUND((TIME_TO_SEC(fs.arrival) - TIME_TO_SEC(fs.departure))/60,0) as sched_min
            FROM flight f
            JOIN airport ao ON f.`from` = ao.airport_id
            JOIN airport ad ON f.`to` = ad.airport_id
            JOIN airplane ap ON f.airplane_id = ap.airplane_id
            JOIN airplane_type at2 ON ap.type_id = at2.type_id
            JOIN flightschedule fs ON f.flightno = fs.flightno
            LEFT JOIN booking b ON f.flight_id = b.flight_id
            WHERE ap.capacity > 0
            GROUP BY f.flight_id, ao.iata, ad.iata, at2.identifier, ap.capacity,
                     f.departure, f.arrival, fs.arrival, fs.departure
            ORDER BY RAND()
            LIMIT %s
        """, (TARGET - existing,))
        flights = cur.fetchall()
        print(f"Inserting {len(flights)} flights in batches of {BATCH_SIZE}...")

        inserted = 0
        for row in flights:
            fid, orig, dest, atype, cap, bk, hr, actual_min, sched_min = row
            ratio = round(float(bk) / float(cap), 3) if cap else 0
            delay = max(float(actual_min or 0) - float(sched_min or 0), 0)
            desc = (
                f"Flight from {orig} to {dest}. "
                f"Aircraft: {atype}. "
                f"Departure hour: {hr}. "
                f"Booking ratio: {ratio}. "
                f"Delay minutes: {round(delay)}."
            )
            try:
                cur.execute(
                    """INSERT INTO flight_risk_memory
                       (flight_id, origin_iata, dest_iata, description, delay_minutes, booking_ratio)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (fid, orig, dest, desc, round(delay, 1), ratio),
                )
                inserted += 1
                if inserted % BATCH_SIZE == 0:
                    print(f"  {inserted}/{len(flights)} inserted...", flush=True)
                    time.sleep(0.5)  # brief pause to avoid throttling
            except Exception as e:
                print(f"  skip flight {fid}: {e}")

    conn.close()
    print(f"Done. Inserted {inserted} rows.")


if __name__ == "__main__":
    main()

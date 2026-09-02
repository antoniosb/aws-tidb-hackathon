"""
embed.py — TiDB vector search helpers using EMBED_TEXT().

TiDB Cloud generates embeddings server-side, so no Bedrock key is needed here.
Run this once to create the table and insert a sample note, then search it.
"""

import os

import pymysql
from dotenv import load_dotenv

load_dotenv()

SSL_CA = "/etc/ssl/cert.pem" if os.path.exists("/etc/ssl/cert.pem") else None


def get_conn() -> pymysql.Connection:
    ssl = {"ca": SSL_CA} if SSL_CA else True
    return pymysql.connect(
        host=os.environ["TIDB_HOST"],
        port=int(os.environ.get("TIDB_PORT", 4000)),
        user=os.environ["TIDB_USER"],
        password=os.environ["TIDB_PASSWORD"],
        database=os.environ.get("TIDB_DATABASE", "airportdb"),
        ssl=ssl,
        autocommit=True,
    )


CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS flight_notes (
    id       BIGINT AUTO_RANDOM PRIMARY KEY,
    flight_id INT,
    note     TEXT,
    embedding VECTOR(1024) GENERATED ALWAYS AS (
        EMBED_TEXT('tidbcloud_free/amazon/titan-embed-text-v2', note)
    ) STORED
)
"""

INSERT_SAMPLE = """
INSERT INTO flight_notes (flight_id, note)
VALUES (%s, %s)
"""

SEARCH_QUERY = """
SELECT flight_id, note
FROM flight_notes
ORDER BY VEC_COSINE_DISTANCE(
    embedding,
    EMBED_TEXT('tidbcloud_free/amazon/titan-embed-text-v2', %s)
)
LIMIT 5
"""


def setup_table(conn: pymysql.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE)
    print("Tabela flight_notes pronta.")


def insert_note(conn: pymysql.Connection, flight_id: int, note: str) -> None:
    with conn.cursor() as cur:
        cur.execute(INSERT_SAMPLE, (flight_id, note))
    print(f"Nota inserida para voo {flight_id}.")


def search_notes(conn: pymysql.Connection, query: str) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(SEARCH_QUERY, (query,))
        return cur.fetchall()


if __name__ == "__main__":
    conn = get_conn()

    setup_table(conn)
    insert_note(conn, 1, "voo direto de Sao Paulo para Frankfurt")

    results = search_notes(conn, "sem escalas para a Alemanha")
    print("\nResultados da busca semântica:")
    for flight_id, note in results:
        print(f"  voo {flight_id}: {note}")

    conn.close()

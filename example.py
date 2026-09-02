import os

import pymysql
from dotenv import load_dotenv

load_dotenv()

conn = pymysql.connect(
    host=os.environ["TIDB_HOST"],
    port=int(os.environ.get("TIDB_PORT", 4000)),
    user=os.environ["TIDB_USER"],
    password=os.environ["TIDB_PASSWORD"],
    database=os.environ.get("TIDB_DATABASE", "airportdb"),
    ssl={"ca": "/etc/ssl/cert.pem"},
)

with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM flight")
    print(cur.fetchone()[0], "voos carregados")

conn.close()

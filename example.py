import os
import ssl

import pymysql
from dotenv import load_dotenv

load_dotenv()

# Use the system CA bundle that Python's OpenSSL actually trusts
SSL_CA = ssl.get_default_verify_paths().cafile or "/etc/ssl/cert.pem"

conn = pymysql.connect(
    host=os.environ["TIDB_HOST"],
    port=int(os.environ.get("TIDB_PORT", 4000)),
    user=os.environ["TIDB_USER"],
    password=os.environ["TIDB_PASSWORD"],
    database=os.environ.get("TIDB_DATABASE", "airportdb"),
    ssl={"ca": SSL_CA},
)

with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM flight")
    print(cur.fetchone()[0], "voos carregados")

conn.close()

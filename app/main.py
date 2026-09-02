"""Flight Risk AI — FastAPI entry point."""
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.graph.graph import flight_risk_agent
from app.schemas.flight import FlightInput

app = FastAPI(
    title="Flight Risk AI",
    description="AI-driven airline operational risk and financial exposure analysis",
    version="1.0.0",
)


@app.get("/health")
def health():
    tidb_ok = False
    bedrock_ok = False

    try:
        from app.services.tidb import get_conn
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.close()
        tidb_ok = True
    except Exception as e:
        pass

    try:
        import boto3
        client = boto3.client(
            "bedrock-runtime",
            region_name=os.environ.get("AWS_REGION", "ap-southeast-1"),
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        )
        bedrock_ok = client is not None
    except Exception:
        pass

    return {"status": "ok", "tidb": tidb_ok, "bedrock": bedrock_ok}


@app.post("/analyze-flight")
def analyze_flight(request: FlightInput):
    try:
        result = flight_risk_agent.invoke({
            "flight_input": request.model_dump(),
            "errors": [],
        })
        output = result.get("final_output", {})
        return JSONResponse(content=output)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

#!/bin/bash
# deploy.sh — pull latest and restart both services on EC2
set -e

PEM=~/Desktop/aws-tidb.pem
HOST=ec2-user@3.141.10.197

echo "==> Deploying to $HOST..."

ssh -i "$PEM" -o StrictHostKeyChecking=no "$HOST" bash <<'REMOTE'
set -e
cd ~/app
echo "--- pulling latest ---"
git pull origin main

echo "--- stopping old processes ---"
pkill -f 'uvicorn app.main' 2>/dev/null || true
pkill -f 'streamlit run frontend' 2>/dev/null || true
sleep 1

echo "--- starting FastAPI on :8000 ---"
setsid nohup python3.11 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > ~/app/api.log 2>&1 < /dev/null &
echo "API PID: $!"

echo "--- starting Streamlit on :8501 ---"
setsid nohup python3.11 -m streamlit run frontend.py \
  --server.address 0.0.0.0 \
  --server.port 8501 \
  --server.headless true > ~/app/frontend.log 2>&1 < /dev/null &
echo "Streamlit PID: $!"

sleep 4
echo "--- api.log ---"
tail -8 ~/app/api.log
echo "--- frontend.log ---"
tail -8 ~/app/frontend.log
REMOTE

echo ""
echo "==> Done."
echo "    Streamlit : http://3.141.10.197:8501"
echo "    API       : http://3.141.10.197:8000"
echo "    API docs  : http://3.141.10.197:8000/docs"

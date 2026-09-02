# SUBMISSION

## Team

latam-hackathon (fill in your team number)

## Pitch

> "Before a flight becomes a disruption, we tell the airline how likely it is to go wrong, how many passengers it may affect, and how much it could cost."

## O que faz

**Flight Risk AI** é uma API de análise de risco operacional aéreo orientada por dados.
Dado um voo futuro, o sistema consulta padrões históricos reais no TiDB, recupera casos similares via vector search, calcula probabilidades de atraso/overbooking/conexão perdida de forma determinística, estima a exposição financeira esperada, e usa Amazon Bedrock para gerar um resumo executivo e recomendações priorizadas — tudo em uma única chamada REST.

O LLM **nunca inventa números**. Todas as probabilidades e custos vêm de dados reais e modelos estatísticos.

## Stack utilizado

- [x] TiDB Cloud — banco de dados principal (`airportdb`, 12 tabelas, 617k bookings)
- [x] TiDB Vector Search — `EMBED_TEXT` + `VEC_COSINE_DISTANCE` para busca de casos similares
- [x] Amazon Bedrock — Claude 3 Haiku (`ap-southeast-1`) para resumo executivo e recomendações
- [x] LangGraph — orquestração do pipeline de 9 nós
- [x] FastAPI — API REST
- [x] Kiro — desenvolvimento orientado a spec (ver `.kiro/specs/flight-risk-ai.md`)
- [ ] AWS EC2 deployment (local demo)

## Onde olhar

| O que | Onde |
|-------|------|
| TiDB SQL queries (padrões históricos) | `app/services/tidb.py` |
| TiDB Vector Search | `app/services/vector_search.py` |
| Amazon Bedrock | `app/services/bedrock.py` |
| LangGraph pipeline (9 nós) | `app/graph/graph.py`, `app/graph/nodes.py` |
| Risk engine (delay/overbooking/connection) | `app/services/risk_model.py` |
| Financial exposure | `app/services/financial.py` |
| Regras financeiras configuráveis | `app/config/legal_costs.json` |
| Kiro spec | `.kiro/specs/flight-risk-ai.md` |
| Demo request | `examples/demo_request.json` |

## Como rodar

```bash
source .venv/bin/activate
uvicorn app.main:app --port 8000

# health
curl http://localhost:8000/health

# analyze
curl -X POST http://localhost:8000/analyze-flight \
  -H "Content-Type: application/json" \
  -d @examples/demo_request.json
```

## O que faríamos com mais tempo

- UI web simples (Streamlit ou React) para entrada do voo
- Deploy no EC2 com porta 8000 pública
- Mais dados no vetor memory (100+ voos indexados)
- Missed connection usando dados reais de itinerário de passageiros
- Modelo ML (LogisticRegression) com feature engineering completo
- Painel com histórico de análises por rota

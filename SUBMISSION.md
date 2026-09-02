# SUBMISSION.md

## Time
Nome do time: FlyAI - prevendo imprevistos (latam-hackathon-001)
Integrantes:
Clarissa Antunes
José da Cruz Vilela Junior
Antônio Britto
Manuella Borges
Vinicius França

## Pitch
Um radar de risco operacional para companhias aéreas: identifica voos com risco de overbooking e atraso antes que aconteçam, e traduz esse risco em custo evitável de indenização para o time de operações agir preventivamente.

## O que faz
Companhias aéreas pagam indenizações previsíveis por overbooking, atraso e conexão perdida, mas hoje reagem depois que o problema já aconteceu. Nossa aplicação cruza reservas, capacidade de aeronave e histórico de clima no dataset da airportdb para calcular, por voo, os riscos de atraso, cancelamento, overbooking e perda de conexão, e traduz isso em uma faixa de custo esperado em R$, usando busca vetorial para encontrar casos históricos parecidos que embasam a explicação gerada por IA. O agente do time de operações vê, por voo, os percentuais de risco, os passageiros expostos, a faixa de custo estimado, um insight explicando o porquê e uma ação recomendada (ex.: proteger passageiros em conexão e abrir remarcação voluntária).

## Stack — marque o que você realmente usou
- [x] TiDB Cloud Starter na AWS sa-east-1
- [x] Busca vetorial no TiDB (coluna VECTOR + EMBED_TEXT + VEC_COSINE_DISTANCE)
- [x] Amazon Bedrock (ap-southeast-1) — Claude 3 Haiku
- [ ] Publicado na AWS → URL no ar: (demo local)
- [x] Construído com Kiro (.kiro/ commitado — specs e steering)

## Onde olhar

| O que | Arquivo |
|-------|---------|
| Conexão e queries SQL ao TiDB (delay rate, booking ratio, route patterns) | `app/services/tidb.py` |
| Busca vetorial — tabela `flight_risk_memory`, `EMBED_TEXT`, `VEC_COSINE_DISTANCE` | `app/services/vector_search.py` |
| Chamadas ao Amazon Bedrock (Claude 3 Haiku, resumo executivo + recomendações) | `app/services/bedrock.py` |
| Orquestração LangGraph (9 nós: validate → historical → vector → risks → exposure → financial → AI → output → validate) | `app/graph/graph.py`, `app/graph/nodes.py` |
| Motor de risco (delay probability, overbooking, missed connection) | `app/services/risk_model.py` |
| Motor financeiro (custo esperado em R$, score 0–100) | `app/services/financial.py` |
| Regras de custo configuráveis por tipo de disruption | `app/config/legal_costs.json` |
| API REST — POST /analyze-flight, GET /health | `app/main.py` |
| Frontend Streamlit | `frontend.py` |
| Spec Kiro | `.kiro/specs/flight-risk-ai.md` |
| Steering (regra de commit por checkpoint) | `.kiro/steering/workflow.md` |
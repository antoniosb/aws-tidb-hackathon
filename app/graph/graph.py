from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    ai_risk_analyst,
    build_structured_output,
    calculate_financial_exposure,
    calculate_operational_risks,
    calculate_passenger_exposure,
    retrieve_historical_patterns,
    retrieve_similar_cases,
    validate_input,
    validate_output,
)
from app.graph.state import AgentState

workflow = StateGraph(AgentState)

workflow.add_node("validate_input", validate_input)
workflow.add_node("retrieve_historical_patterns", retrieve_historical_patterns)
workflow.add_node("retrieve_similar_cases", retrieve_similar_cases)
workflow.add_node("calculate_operational_risks", calculate_operational_risks)
workflow.add_node("calculate_passenger_exposure", calculate_passenger_exposure)
workflow.add_node("calculate_financial_exposure", calculate_financial_exposure)
workflow.add_node("ai_risk_analyst", ai_risk_analyst)
workflow.add_node("build_structured_output", build_structured_output)
workflow.add_node("validate_output", validate_output)

workflow.add_edge(START, "validate_input")
workflow.add_edge("validate_input", "retrieve_historical_patterns")
workflow.add_edge("retrieve_historical_patterns", "retrieve_similar_cases")
workflow.add_edge("retrieve_similar_cases", "calculate_operational_risks")
workflow.add_edge("calculate_operational_risks", "calculate_passenger_exposure")
workflow.add_edge("calculate_passenger_exposure", "calculate_financial_exposure")
workflow.add_edge("calculate_financial_exposure", "ai_risk_analyst")
workflow.add_edge("ai_risk_analyst", "build_structured_output")
workflow.add_edge("build_structured_output", "validate_output")
workflow.add_edge("validate_output", END)

flight_risk_agent = workflow.compile()

"""LangGraph workflow assembly for reconciliation and investigation."""

import pandas as pd
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from .agent_tools import create_investigation_tools
from .nodes import (
    auto_finalize,
    continue_investigation,
    create_investigation_agent,
    create_load_case_node,
    finalize_investigation,
    finalize_review,
    handle_error,
    human_review_case,
    invoice_not_found,
    prepare_investigation,
    route_case,
)
from .state import AgentState


def create_reconciliation_agent(
    invoices: pd.DataFrame,
    ledger_entries: pd.DataFrame,
    bank_transactions: pd.DataFrame,
):
    """Build the deterministic reconciliation and tool-investigation graph."""

    workflow = StateGraph(AgentState)

    load_case = create_load_case_node(
        invoices,
        ledger_entries,
        bank_transactions,
    )
    tools = create_investigation_tools(
        invoices,
        ledger_entries,
        bank_transactions,
    )
    investigation_agent = create_investigation_agent(tools)
    tool_node = ToolNode(tools)

    workflow.add_node("load_case", load_case)
    workflow.add_node("auto_finalize", auto_finalize)
    workflow.add_node("prepare_investigation", prepare_investigation)
    workflow.add_node("investigation_agent", investigation_agent)
    workflow.add_node("tools", tool_node)
    workflow.add_node("finalize_investigation", finalize_investigation)
    workflow.add_node("human_review", human_review_case)
    workflow.add_node("finalize_review", finalize_review)
    workflow.add_node("handle_error", handle_error)
    workflow.add_node("invoice_not_found", invoice_not_found)

    workflow.add_edge(START, "load_case")
    workflow.add_conditional_edges(
        "load_case",
        route_case,
        {
            "auto": "auto_finalize",
            "investigate": "prepare_investigation",
            "human_review": "human_review",
            "not_found": "invoice_not_found",
            "error": "handle_error",
        },
    )
    workflow.add_edge("prepare_investigation", "investigation_agent")
    workflow.add_conditional_edges(
        "investigation_agent",
        continue_investigation,
        {
            "tools": "tools",
            "finish": "finalize_investigation",
        },
    )
    workflow.add_edge("tools", "investigation_agent")
    workflow.add_edge("finalize_investigation", "human_review")
    workflow.add_edge("human_review", "finalize_review")
    workflow.add_edge("auto_finalize", END)
    workflow.add_edge("finalize_review", END)
    workflow.add_edge("invoice_not_found", END)
    workflow.add_edge("handle_error", END)

    return workflow.compile(checkpointer=InMemorySaver())

import pandas as pd

from langgraph.graph import (StateGraph,START,END)

from langgraph.checkpoint.memory import (InMemorySaver)

from .state import AgentState

from .nodes import (
    create_load_case_node,
    route_case,
    auto_finalize,
    investigate_case,
    human_review_case,
    finalize_review,
    invoice_not_found,
    handle_error
)

def create_reconciliation_agent(invoices:pd.DataFrame,ledger_entries:pd.DataFrame,bank_transactions:pd.DataFrame):

    ## create a state graph
    workflow = StateGraph(AgentState)

    load_case = create_load_case_node(invoices,ledger_entries,bank_transactions)

    ## add nodes to the graph
    workflow.add_node("load_case",load_case)
    workflow.add_node("auto_finalize",auto_finalize)
    workflow.add_node("investigate_case",investigate_case)
    workflow.add_node("human_review",human_review_case)
    workflow.add_node("finalize_review",finalize_review)
    workflow.add_node("handle_error",handle_error)
    workflow.add_node("invoice_not_found",invoice_not_found)


    ## add edges to the graph
    workflow.add_edge(START,"load_case")
    workflow.add_conditional_edges("load_case",route_case,{
        "auto":"auto_finalize",
        "investigate":"investigate_case",
        "human_review":"human_review",
        "not_found":"invoice_not_found",
        "error":"handle_error",
    })
    workflow.add_edge("investigate_case","human_review")
    workflow.add_edge("human_review","finalize_review")
    workflow.add_edge("auto_finalize",END)
    workflow.add_edge("finalize_review",END)
    workflow.add_edge("invoice_not_found",END)
    workflow.add_edge("handle_error",END)

    ## compile the graph
    graph = workflow.compile(checkpointer=InMemorySaver())

    return graph
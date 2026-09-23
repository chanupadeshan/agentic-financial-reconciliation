from pydantic import BaseModel, Field


class InvestigationOutput(BaseModel):
    """
    gives structured output for the LLM to fill in after investigating a reconciliation case. 
    It includes investigation notes and a recommendation for the human reviewer.
    """

    investigation_notes: str = Field(
        description="Short explanation of the reconciliation problem."
    )

    recommendation: str = Field(
        description="Recommended next action for the human reviewer."
    )


INVESTIGATION_SYSTEM_PROMPT = """
                You are a financial reconciliation investigation assistant.

                Your task is to investigate ambiguous financial reconciliation cases.

                Rules:

                1. Use only the supplied evidence.
                2. Do not calculate financial differences yourself.
                3. Do not invent invoices, transactions, vendors, amounts, or dates.
                4. Do not approve or modify financial records.
                5. Explain why the case requires attention.
                6. Provide a clear recommendation for a human reviewer.

                Return:
                - investigation_notes
                - recommendation
            """


def build_investigation_prompt(state: dict) -> str:
    """
    build case-specific investigation prompt for the LLM to investigate a reconciliation case.
    It includes the invoice ID, bank transaction ID, reconciliation result, and evidence.
    """
    

    return f"""
                Invoice ID:
                {state.get("invoice_id")}

                Bank Transaction ID:
                {state.get("bank_transaction_id")}

                Reconciliation Result:
                {state.get("reconciliation_result")}

                Evidence:
                {state.get("evidence")}

                Investigate this reconciliation case.
            """
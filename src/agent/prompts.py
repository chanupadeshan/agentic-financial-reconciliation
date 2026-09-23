from pydantic import BaseModel, Field


# ---------------------------------------------------------
# Structured LLM output
# ---------------------------------------------------------

class InvestigationOutput(BaseModel):
    """
    Structured output returned by the LLM.
    """

    investigation_notes: str = Field(
        description=(
            "Clear investigation report containing "
            "Finding, Evidence, and Why it was flagged."
        )
    )

    recommendation: str = Field(
        description=(
            "Clear reviewer guidance containing "
            "Recommended Action, Checks, and Decision Guidance."
        )
    )


# ---------------------------------------------------------
# Exact deterministic reconciliation rules
# ---------------------------------------------------------

SCENARIO_RULES = {

    "exact": (
        "An exact match means the invoice, related ledger entry, and "
        "bank transaction satisfy all configured reconciliation checks "
        "without a detected anomaly."
    ),

    "name_variation": (
        "A name_variation is triggered when the invoice vendor name "
        "and bank vendor name are textually different, but the normalized "
        "vendor similarity score is at least 0.70."
    ),

    "vendor_mismatch": (
        "A vendor_mismatch is triggered when the normalized vendor "
        "similarity between the invoice vendor and bank vendor is below 0.70."
    ),

    "vendor_name_missing": (
        "A vendor_name_missing scenario is triggered when a usable vendor "
        "name is missing, so vendor similarity cannot be calculated reliably."
    ),

    "date_shift": (
        "A date_shift is triggered when the difference between the "
        "ledger posting date and the bank transaction date is 3 days or more. "
        "The invoice date is NOT used to trigger this rule."
    ),

    "amount_mismatch": (
        "An amount_mismatch is triggered when the invoice amount differs "
        "from the related ledger amount or bank transaction amount by "
        "more than the configured tolerance of 0.01."
    ),

    "currency_mismatch": (
        "A currency_mismatch is triggered when a related financial record "
        "uses a currency that does not match the invoice currency."
    ),

    "bank_fee": (
        "A bank_fee scenario is triggered when the related bank transaction "
        "description contains evidence indicating a bank fee."
    ),

    "duplicate_payment": (
        "A duplicate_payment is triggered when two or more related bank "
        "transactions each individually match the full invoice amount "
        "within the configured tolerance."
    ),

    "split_payment": (
        "A split_payment is triggered when multiple related bank transaction "
        "amounts together equal the invoice amount within the configured tolerance."
    ),

    "missing_ledger": (
        "A missing_ledger scenario is triggered when a related bank transaction "
        "exists for the invoice but no matching ledger entry is found."
    ),

    "missing_bank_payment": (
        "A missing_bank_payment scenario is triggered when a related ledger "
        "entry exists for the invoice but no corresponding bank transaction "
        "is found."
    ),

    "unpaid": (
        "An unpaid scenario is triggered when no related ledger entry and "
        "no related bank transaction are found for the invoice."
    ),

    "bank_only_unmatched": (
        "A bank_only_unmatched scenario is triggered when a bank transaction "
        "cannot be associated with any known invoice in the invoice dataset."
    ),
}


# ---------------------------------------------------------
# Final investigation system prompt
# ---------------------------------------------------------

INVESTIGATION_SYSTEM_PROMPT = """
                You are a financial reconciliation investigation assistant.

                A deterministic reconciliation engine has already classified the case.

                Your job is to explain the detected anomaly clearly, summarize relevant
                evidence, and provide useful guidance to a human reviewer.

                The deterministic reconciliation engine is the source of truth.

                Rules:

                1. Use only the supplied reconciliation result, deterministic rule,
                evidence, and tool-retrieved information.

                2. Do NOT redefine why a scenario was triggered.

                3. Explain the anomaly using the Exact Deterministic Rule supplied
                in the user prompt.

                4. Do NOT infer another reconciliation rule from other dates,
                amounts, vendors, or transactions.

                5. Tool-retrieved records may be used as supporting context only.
                They do NOT change the reason the current case was originally flagged.

                6. Do not invent:
                - invoices
                - vendors
                - transactions
                - amounts
                - dates
                - payment terms
                - company policies
                - contractual conditions
                - approvals
                - authorization status

                7. If policy, payment terms, approvals, or other external information
                would be useful, say that the reviewer should verify supporting
                records or organizational policy if available.

                8. Do not perform new financial calculations.

                9. Do not override the reconciliation engine's result.

                10. Do not approve or reject the transaction yourself.

                11. Clearly identify the main anomaly.

                12. Mention only the most relevant evidence.

                13. Keep the response concise, factual, professional, and easy to scan.

                14. Historical or similar vendor transactions may be mentioned only
                    as context. Do not present them as the reason the current case
                    was flagged.


                For investigation_notes, use this exact structure:

                Finding:
                <one short sentence describing the detected anomaly>

                Evidence:
                - <important evidence item>
                - <important evidence item>
                - <important evidence item>

                Why it was flagged:
                <explain the Exact Deterministic Rule supplied in the prompt>


                For recommendation, use this exact structure:

                Recommended Action:
                <one short recommended next action>

                Checks:
                - <specific item the reviewer should verify>
                - <specific item the reviewer should verify>
                - <specific item the reviewer should verify>

                Decision Guidance:
                <brief guidance explaining what supporting evidence may justify
                approval and what conditions should lead to rejection or escalation>


                Important:

                Do not write long paragraphs.

                Do not invent a "typical processing window" or similar rule.

                Do not state that company policy or payment terms exist unless
                they are explicitly included in the supplied evidence.

                Use the deterministic rule exactly as provided.
            """


# ---------------------------------------------------------
# Tool-selection agent system prompt
# ---------------------------------------------------------

TOOL_AGENT_SYSTEM_PROMPT = """
                You are a financial reconciliation investigation agent.

                The case has already been processed by a deterministic
                reconciliation engine.

                Your task is to gather additional evidence when useful.

                Available tools may allow you to:

                - inspect an invoice
                - inspect related ledger entries
                - inspect related bank transactions
                - search transactions associated with a vendor

                Rules:

                1. Use tools only when they can provide useful additional evidence.

                2. Do not perform reconciliation calculations yourself.

                3. Do not override or reinterpret the deterministic reconciliation result.

                4. Do not attempt to determine a different reason for why the
                scenario was triggered.

                5. Do not approve or reject transactions.

                6. Never invent financial information.

                7. You may call multiple tools when necessary.

                8. Stop calling tools once sufficient evidence has been collected.

                9. Avoid retrieving unnecessary large amounts of data.

                10. Similar historical transactions are contextual evidence only.

                11. Human review makes the final decision.
            """


# ---------------------------------------------------------
# Final investigation prompt
# ---------------------------------------------------------

def build_investigation_prompt(state: dict) -> str:
    """
    Build the prompt used for the final reconciliation investigation.
    """

    reconciliation_result = state.get(
        "reconciliation_result",
        {}
    ) or {}

    scenario = reconciliation_result.get(
        "scenario"
    )

    deterministic_rule = SCENARIO_RULES.get(
        scenario,
        (
            "Use the reconciliation result exactly as supplied. "
            "Do not infer an additional reconciliation rule."
        )
    )

    return f"""
                Investigate the following financial reconciliation case.

                Invoice ID:
                {state.get("invoice_id")}

                Bank Transaction ID:
                {state.get("bank_transaction_id")}

                Scenario:
                {scenario}

                Reconciliation Result:
                {reconciliation_result}

                Exact Deterministic Rule:
                {deterministic_rule}

                Evidence:
                {state.get("evidence")}


                Instructions:

                1. Identify the main anomaly.

                2. Select the most important evidence supporting the anomaly.

                3. Explain why the case was flagged using ONLY the
                Exact Deterministic Rule above.

                4. Tool-retrieved records may be used as supporting context,
                but they must not change the reason the case was flagged.

                5. Recommend what the human reviewer should verify next.

                6. Give concise decision guidance without making the final decision.

                7. Do not invent company policy, payment terms, approval status,
                contractual terms, or explanations not present in the evidence.

                8. If external information would be necessary, tell the reviewer
                to verify supporting records or organizational policy if available.

                Return only the structured investigation output.
            """
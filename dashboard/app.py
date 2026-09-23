from html import escape

import pandas as pd
import streamlit as st

from langgraph.types import Command

from src.reconciliation.reconciliation import (
    reconcile_all_invoices,
)

from src.agent.workflow import (
    create_reconciliation_agent,
)
from src.tools.tools import (
    get_bank_transaction,
    get_bank_transactions,
    get_invoice,
    get_ledger_entries,
)


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Financial Reconciliation Copilot",
    page_icon="💼",
    layout="wide",
)


# =========================================================
# BASIC STYLE
# =========================================================

st.markdown(
    """
    <style>
        .main-title {
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0;
        }

        .subtitle {
            color: #888;
            margin-top: 4px;
            margin-bottom: 25px;
        }

        div[data-testid="stMetric"] {
            padding: 10px 0;
        }

        .status-badge {
            display: inline-block;
            padding: 0.25rem 0.65rem;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 650;
            margin: 0.15rem 0 0.6rem;
        }

        .status-exact, .status-approved {
            color: #166534;
            background: #dcfce7;
            border: 1px solid #86efac;
        }

        .status-auto {
            color: #1e40af;
            background: #dbeafe;
            border: 1px solid #93c5fd;
        }

        .status-pending {
            color: #92400e;
            background: #fef3c7;
            border: 1px solid #fcd34d;
        }

        .status-rejected {
            color: #991b1b;
            background: #fee2e2;
            border: 1px solid #fca5a5;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# TITLE
# =========================================================

st.markdown(
    """
    <p class="main-title">
        Agentic Financial Reconciliation & Audit Copilot
    </p>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <p class="subtitle">
        Upload financial data, reconcile transactions,
        investigate anomalies with AI, and review suspicious cases.
    </p>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# SCENARIO GROUPS
# =========================================================

EXACT_SCENARIOS = [
    "exact",
]

AUTO_PROCESS_SCENARIOS = [
    "unpaid",
    "split_payment",
]

SCENARIO_LABELS = {
    "exact": "Exact",
    "unpaid": "Unpaid",
    "split_payment": "Split payment",
    "name_variation": "Vendor name variation",
    "vendor_mismatch": "Vendor mismatch",
    "vendor_name_missing": "Vendor name missing",
    "amount_mismatch": "Amount mismatch",
    "currency_mismatch": "Currency mismatch",
    "date_shift": "Date shift",
    "bank_fee": "Bank fee",
    "duplicate_payment": "Duplicate payment",
    "missing_ledger": "Missing ledger entry",
    "missing_bank_payment": "Missing bank payment",
    "bank_only_unmatched": "Unmatched bank transaction",
}

ACTION_LABELS = {
    "AUTO_RECONCILE": "Auto reconcile",
    "AUTO_RECONCILE_OR_LOW_RISK_REVIEW": "Low-risk review recommended",
    "INVESTIGATE_DATE_DIFFERENCE": "Investigate date difference",
    "CLASSIFY_AS_NON_AP_OR_INVESTIGATE": "Classify or investigate",
}

STATUS_LABELS = {
    "NOT_REQUIRED": "Auto processed",
    "PENDING": "Pending review",
    "HUMAN_APPROVED": "Human approved",
    "HUMAN_REJECTED": "Human rejected",
}

NO_ATTENTION_SCENARIOS = (
    EXACT_SCENARIOS
    + AUTO_PROCESS_SCENARIOS
)


# =========================================================
# SESSION STATE
# =========================================================

if "reconciliation_results" not in st.session_state:
    st.session_state.reconciliation_results = None

if "invoices" not in st.session_state:
    st.session_state.invoices = None

if "ledger_entries" not in st.session_state:
    st.session_state.ledger_entries = None

if "bank_transactions" not in st.session_state:
    st.session_state.bank_transactions = None

if "agent_graph" not in st.session_state:
    st.session_state.agent_graph = None

if "agent_result" not in st.session_state:
    st.session_state.agent_result = None

if "agent_config" not in st.session_state:
    st.session_state.agent_config = None

if "selected_case_index" not in st.session_state:
    st.session_state.selected_case_index = None

if "agent_run_counter" not in st.session_state:
    st.session_state.agent_run_counter = 0

if "decision_history" not in st.session_state:
    st.session_state.decision_history = []

if "reviewed_cases" not in st.session_state:
    st.session_state.reviewed_cases = set()


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def validate_columns(
    dataframe: pd.DataFrame,
    required_columns: list,
    dataset_name: str,
):
    """
    Check whether required columns exist.
    """

    missing = [
        column
        for column in required_columns
        if column not in dataframe.columns
    ]

    if missing:
        raise ValueError(
            f"{dataset_name} is missing required columns: "
            f"{', '.join(missing)}"
        )


def prepare_data(
    invoices_raw: pd.DataFrame,
    ledger_raw: pd.DataFrame,
    bank_raw: pd.DataFrame,
):
    """
    Convert uploaded CSV column names into the names
    expected by the reconciliation layer.
    """

    invoices = invoices_raw.rename(
        columns={
            "vendor_name": "vendor",
            "invoice_date": "date",
            "total_amount": "amount",
        }
    ).copy()

    ledger_entries = ledger_raw.rename(
        columns={
            "vendor_name": "vendor",
            "posting_date": "date",
        }
    ).copy()

    bank_transactions = bank_raw.rename(
        columns={
            "counterparty_name": "vendor",
            "transaction_date": "date",
        }
    ).copy()


    validate_columns(
        invoices,
        [
            "invoice_id",
            "vendor",
            "amount",
            "currency",
            "date",
        ],
        "Invoices CSV",
    )


    validate_columns(
        ledger_entries,
        [
            "ledger_entry_id",
            "invoice_id",
            "reference",
            "vendor",
            "amount",
            "currency",
            "date",
        ],
        "Ledger CSV",
    )


    validate_columns(
        bank_transactions,
        [
            "transaction_id",
            "reference",
            "vendor",
            "amount",
            "currency",
            "date",
            "description",
        ],
        "Bank CSV",
    )


    return (
        invoices,
        ledger_entries,
        bank_transactions,
    )


def first_id(value):
    """
    Get the first ID from a list-like result.
    """

    if isinstance(value, list):

        if len(value) > 0:
            return str(value[0])

        return None

    if pd.notna(value):
        return str(value)

    return None


def friendly_label(value, labels=None):
    """Convert an internal enum-like value into reviewer-friendly text."""

    if value is None:
        return "Not available"

    text = str(value)
    if labels and text in labels:
        return labels[text]

    return text.replace("_", " ").strip().title()


def case_type_label(case):
    """Return a friendly case type for filters and tables."""

    if case.get("scenario") == "bank_only_unmatched":
        return "Bank only"

    return "Invoice"


def show_status_badge(status, scenario=None):
    """Render a consistent, readable review status badge."""

    if scenario == "exact":
        label = "Exact"
        css_class = "status-exact"
    else:
        label = friendly_label(status, STATUS_LABELS)
        css_class = {
            "NOT_REQUIRED": "status-auto",
            "PENDING": "status-pending",
            "HUMAN_APPROVED": "status-approved",
            "HUMAN_REJECTED": "status-rejected",
        }.get(status, "status-auto")

    st.markdown(
        f'<span class="status-badge {css_class}">{escape(label)}</span>',
        unsafe_allow_html=True,
    )


def split_report_sections(text, headings):
    """Split structured agent prose into named UI sections."""

    sections = {heading: [] for heading in headings}
    current = None

    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        matched = next(
            (
                heading
                for heading in headings
                if line.lower().startswith(f"{heading.lower()}:")
            ),
            None,
        )

        if matched:
            current = matched
            remainder = line.split(":", 1)[1].strip()
            if remainder:
                sections[current].append(remainder)
        elif current and line:
            sections[current].append(line)

    return {
        heading: "\n".join(content).strip()
        for heading, content in sections.items()
    }


def show_agent_findings(investigation, recommendation):
    """Display the structured AI report as clear reviewer sections."""

    notes = split_report_sections(
        investigation,
        ["Finding", "Evidence", "Why it was flagged"],
    )
    guidance = split_report_sections(
        recommendation,
        ["Recommended Action", "Checks", "Decision Guidance"],
    )

    if any(notes.values()):
        left, right = st.columns(2)
        with left.container(border=True):
            st.markdown("#### Finding")
            st.markdown(notes["Finding"] or "No finding supplied.")
        with right.container(border=True):
            st.markdown("#### Why it was flagged")
            st.markdown(
                notes["Why it was flagged"]
                or "No deterministic explanation supplied."
            )

        with st.container(border=True):
            st.markdown("#### Evidence")
            st.markdown(notes["Evidence"] or "No evidence summary supplied.")
    elif investigation:
        with st.container(border=True):
            st.markdown("#### Investigation notes")
            st.markdown(investigation)

    if any(guidance.values()):
        with st.container(border=True):
            st.markdown("#### Recommendation")
            st.markdown(
                guidance["Recommended Action"] or "No action supplied."
            )
            if guidance["Checks"]:
                st.markdown("**Checks**")
                st.markdown(guidance["Checks"])
            if guidance["Decision Guidance"]:
                st.markdown("**Decision guidance**")
                st.markdown(guidance["Decision Guidance"])
    elif recommendation:
        st.info(recommendation)


def show_case_evidence(
    selected_case,
    invoices,
    ledger_entries,
    bank_transactions,
):
    """Display the source records and key differences for a review case."""

    scenario = selected_case.get("scenario")
    invoice_id = selected_case.get("invoice_id")

    st.subheader("Financial Evidence")

    if scenario == "bank_only_unmatched":
        bank_id = first_id(selected_case.get("bank_transaction_ids"))
        bank = get_bank_transaction(bank_id, bank_transactions)

        if bank is None:
            st.error("Bank transaction evidence could not be loaded.")
            return

        st.warning(
            "This bank transaction does not have a matching invoice."
        )

        c1, c2, c3 = st.columns(3)
        c1.metric("Bank Amount", bank.get("amount", "N/A"))
        c2.metric("Currency", bank.get("currency", "N/A"))
        c3.metric("Transaction Date", bank.get("date", "N/A"))

        st.markdown("#### Bank Transaction")
        st.dataframe(
            pd.DataFrame([bank]),
            width="stretch",
            hide_index=True,
        )
        return

    invoice = get_invoice(str(invoice_id), invoices)
    ledgers = get_ledger_entries(str(invoice_id), ledger_entries)
    banks = get_bank_transactions(str(invoice_id), bank_transactions)

    if invoice is None:
        st.error("Invoice evidence could not be loaded.")
        return

    ledger = ledgers[0] if ledgers else {}
    bank = banks[0] if banks else {}

    highlighted_field = {
        "amount_mismatch": "Amount",
        "date_shift": "Date",
        "name_variation": "Vendor",
        "vendor_mismatch": "Vendor",
        "vendor_name_missing": "Vendor",
        "currency_mismatch": "Currency",
    }.get(scenario)

    comparison = pd.DataFrame(
        {
            "Field": ["Vendor", "Amount", "Currency", "Date"],
            "Invoice": [
                invoice.get("vendor"),
                invoice.get("amount"),
                invoice.get("currency"),
                invoice.get("date"),
            ],
            "Ledger": [
                ledger.get("vendor", "Missing"),
                ledger.get("amount", "Missing"),
                ledger.get("currency", "Missing"),
                ledger.get("date", "Missing"),
            ],
            "Bank": [
                bank.get("vendor", "Missing"),
                bank.get("amount", "Missing"),
                bank.get("currency", "Missing"),
                bank.get("date", "Missing"),
            ],
            "Review": [
                "Check" if field == highlighted_field else "Aligned"
                for field in ["Vendor", "Amount", "Currency", "Date"]
            ],
        }
    )

    comparison = comparison.astype(str)

    st.markdown("#### Invoice vs Ledger vs Bank")
    comparison_style = comparison.style.apply(
        lambda row: [
            ("background-color: #fef3c7; font-weight: 600;"
             if row["Review"] == "Check" else "")
            for _ in row
        ],
        axis=1,
    )
    st.dataframe(
        comparison_style,
        width="stretch",
        hide_index=True,
    )

    if scenario == "date_shift":
        st.warning(
            "Date difference flagged: ledger posting date "
            f"{ledger.get('date', 'Missing')} ↔ bank transaction date "
            f"{bank.get('date', 'Missing')}."
        )

    invoice_amount = invoice.get("amount")
    ledger_amount = ledger.get("amount")
    bank_amount = bank.get("amount")

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Invoice Amount",
        invoice_amount if invoice_amount is not None else "N/A",
    )
    c2.metric(
        "Ledger Amount",
        ledger_amount if ledger_amount is not None else "Missing",
    )

    if invoice_amount is not None and bank_amount is not None:
        difference = float(bank_amount) - float(invoice_amount)
        c3.metric(
            "Bank Amount",
            bank_amount,
            delta=round(difference, 2),
        )
    else:
        c3.metric(
            "Bank Amount",
            bank_amount if bank_amount is not None else "Missing",
        )

    with st.expander("View full source records"):
        st.markdown("##### Invoice")
        st.dataframe(
            pd.DataFrame([invoice]),
            width="stretch",
            hide_index=True,
        )

        st.markdown("##### Ledger Entries")
        if ledgers:
            st.dataframe(
                pd.DataFrame(ledgers),
                width="stretch",
                hide_index=True,
            )
        else:
            st.warning("No related ledger entry found.")

        st.markdown("##### Bank Transactions")
        if banks:
            st.dataframe(
                pd.DataFrame(banks),
                width="stretch",
                hide_index=True,
            )
        else:
            st.warning("No related bank transaction found.")


def case_review_key(case):
    """Return a stable key for either an invoice or bank-only case."""

    if case.get("scenario") == "bank_only_unmatched":
        return f"bank:{first_id(case.get('bank_transaction_ids'))}"

    return f"invoice:{case.get('invoice_id')}"


def save_review_decision(selected_case, final_result, decision):
    """Store one human decision for the current Streamlit session."""

    invoice_id = final_result.get("invoice_id")
    if pd.isna(invoice_id):
        invoice_id = None

    history_record = {
        "invoice_id": invoice_id,
        "bank_transaction_id": (
            final_result.get("bank_transaction_id")
            or first_id(selected_case.get("bank_transaction_ids"))
        ),
        "scenario": final_result.get(
            "reconciliation_result", {}
        ).get("scenario"),
        "decision": decision,
        "reviewed_by": final_result.get("reviewed_by"),
        "reviewed_at": final_result.get("reviewed_at"),
        "comment": final_result.get("human_comment"),
        "final_status": final_result.get("final_status"),
    }

    st.session_state.decision_history.append(history_record)
    st.session_state.reviewed_cases.add(case_review_key(selected_case))


def get_review_results(results):
    """Return anomaly cases that have not received a human decision."""

    pending = results[
        ~results["scenario"].isin(NO_ATTENTION_SCENARIOS)
    ].copy()

    if "review_status" in pending.columns:
        pending = pending[pending["review_status"] == "PENDING"]

    if st.session_state.reviewed_cases:
        pending = pending[
            ~pending.apply(case_review_key, axis=1).isin(
                st.session_state.reviewed_cases
            )
        ]

    return pending

# =========================================================
# TABS
# =========================================================

(
    tab_upload,
    tab_overview,
    tab_review,
    tab_agent,
    tab_decisions,
    tab_export,
) = st.tabs(
    [
        "📤 Upload Data",
        "📊 Overview",
        "🔍 Review Cases",
        "🤖 Investigation & Review",
        "📜 Decision History",
        "📥 Export",
    ]
)


# =========================================================
# TAB 1 - UPLOAD DATA
# =========================================================

with tab_upload:

    st.header("Upload Financial Data")

    st.write(
        "Upload the three required CSV files and "
        "run the reconciliation process."
    )


    col1, col2, col3 = st.columns(3)


    with col1:

        invoice_file = st.file_uploader(
            "Invoices CSV",
            type=["csv"],
            key="invoice_upload",
        )

        if invoice_file is not None:
            st.success("Invoices uploaded")


    with col2:

        ledger_file = st.file_uploader(
            "Ledger Entries CSV",
            type=["csv"],
            key="ledger_upload",
        )

        if ledger_file is not None:
            st.success("Ledger uploaded")


    with col3:

        bank_file = st.file_uploader(
            "Bank Transactions CSV",
            type=["csv"],
            key="bank_upload",
        )

        if bank_file is not None:
            st.success(
                "Bank transactions uploaded"
            )


    # -----------------------------------------------------
    # All three files uploaded
    # -----------------------------------------------------

    if (
        invoice_file is not None
        and ledger_file is not None
        and bank_file is not None
    ):

        try:

            invoices_raw = pd.read_csv(
                invoice_file
            )

            ledger_raw = pd.read_csv(
                ledger_file
            )

            bank_raw = pd.read_csv(
                bank_file
            )


            st.divider()

            st.subheader("Uploaded Files")


            m1, m2, m3 = st.columns(3)


            m1.metric(
                "Invoices",
                len(invoices_raw),
            )

            m2.metric(
                "Ledger Entries",
                len(ledger_raw),
            )

            m3.metric(
                "Bank Transactions",
                len(bank_raw),
            )


            # -------------------------------------------------
            # Optional preview
            # -------------------------------------------------

            with st.expander(
                "Preview uploaded data"
            ):

                st.markdown(
                    "#### Invoices"
                )

                st.dataframe(
                    invoices_raw.head(),
                    width="stretch",
                    hide_index=True,
                )


                st.markdown(
                    "#### Ledger Entries"
                )

                st.dataframe(
                    ledger_raw.head(),
                    width="stretch",
                    hide_index=True,
                )


                st.markdown(
                    "#### Bank Transactions"
                )

                st.dataframe(
                    bank_raw.head(),
                    width="stretch",
                    hide_index=True,
                )


            # -------------------------------------------------
            # Run reconciliation
            # -------------------------------------------------

            if st.button(
                "Run Reconciliation",
                type="primary",
                width="stretch",
            ):

                (
                    invoices,
                    ledger_entries,
                    bank_transactions,
                ) = prepare_data(
                    invoices_raw,
                    ledger_raw,
                    bank_raw,
                )


                with st.spinner(
                    "Reconciling financial records..."
                ):

                    results = (
                        reconcile_all_invoices(
                            invoices,
                            ledger_entries,
                            bank_transactions,
                        )
                    )


                # ---------------------------------------------
                # Add dashboard tracking fields
                # ---------------------------------------------

                results[
                    "review_status"
                ] = "PENDING"


                results.loc[
                    results["scenario"].isin(
                        NO_ATTENTION_SCENARIOS
                    ),
                    "review_status",
                ] = "NOT_REQUIRED"


                results[
                    "investigation_notes"
                ] = None

                results[
                    "recommendation"
                ] = None

                results[
                    "human_comment"
                ] = None

                results[
                    "reviewed_by"
                ] = None

                results[
                    "reviewed_at"
                ] = None


                # ---------------------------------------------
                # Save in session
                # ---------------------------------------------

                st.session_state.invoices = (
                    invoices
                )

                st.session_state.ledger_entries = (
                    ledger_entries
                )

                st.session_state.bank_transactions = (
                    bank_transactions
                )

                st.session_state.reconciliation_results = (
                    results
                )


                # ---------------------------------------------
                # Create LangGraph
                # ---------------------------------------------

                st.session_state.agent_graph = (
                    create_reconciliation_agent(
                        invoices,
                        ledger_entries,
                        bank_transactions,
                    )
                )


                st.session_state.agent_result = None
                st.session_state.agent_config = None
                st.session_state.selected_case_index = None
                st.session_state.agent_run_counter = 0
                st.session_state.decision_history = []
                st.session_state.reviewed_cases = set()


                st.success(
                    "Reconciliation completed successfully."
                )


        except Exception as error:

            st.error(
                f"Unable to process the files: {error}"
            )


# =========================================================
# CURRENT RESULTS
# =========================================================

results = (
    st.session_state.reconciliation_results
)


# =========================================================
# TAB 2 - OVERVIEW
# =========================================================

with tab_overview:

    st.header(
        "Reconciliation Overview"
    )


    if results is None:

        st.info(
            "Upload the three CSV files and run "
            "reconciliation first."
        )


    else:

        # -------------------------------------------------
        # Counts
        # -------------------------------------------------

        total_cases = len(
            results
        )


        exact_cases = len(
            results[
                results["scenario"]
                == "exact"
            ]
        )


        auto_cases = len(
            results[
                results["scenario"].isin(
                    AUTO_PROCESS_SCENARIOS
                )
            ]
        )


        attention_cases = len(
            get_review_results(
                results
            )
        )


        # -------------------------------------------------
        # Top metrics
        # -------------------------------------------------

        c1, c2, c3, c4 = (
            st.columns(4)
        )


        c1.metric(
            "Total Cases",
            total_cases,
        )


        c2.metric(
            "Exact Matches",
            exact_cases,
        )


        c3.metric(
            "Auto Processed",
            auto_cases,
        )


        c4.metric(
            "Need Attention",
            attention_cases,
        )

        pending_reviews = int((results["review_status"] == "PENDING").sum())
        approved_reviews = int(
            (results["review_status"] == "HUMAN_APPROVED").sum()
        )
        rejected_reviews = int(
            (results["review_status"] == "HUMAN_REJECTED").sum()
        )
        completed_reviews = approved_reviews + rejected_reviews
        total_reviews = completed_reviews + pending_reviews

        st.markdown("#### Review progress")
        p1, p2, p3 = st.columns(3)
        p1.metric("Pending review", pending_reviews)
        p2.metric("Human approved", approved_reviews)
        p3.metric("Human rejected", rejected_reviews)
        if total_reviews:
            st.progress(
                completed_reviews / total_reviews,
                text=f"{completed_reviews} of {total_reviews} reviews completed",
            )

        st.divider()


        # -------------------------------------------------
        # Scenario summary
        # -------------------------------------------------

        st.subheader(
            "Scenario Distribution"
        )


        scenario_summary = (
            results["scenario"]
            .value_counts()
            .rename_axis("Scenario")
            .reset_index(name="Count")
        )
        scenario_summary["Display Scenario"] = scenario_summary[
            "Scenario"
        ].map(lambda value: friendly_label(value, SCENARIO_LABELS))


        chart_data = (
            scenario_summary[["Display Scenario", "Count"]]
            .set_index("Display Scenario")
        )


        st.bar_chart(
            chart_data
        )


        st.divider()


        # -------------------------------------------------
        # Three scenario groups
        # -------------------------------------------------

        st.subheader(
            "Scenario Summary"
        )


        exact_summary = (
            scenario_summary[
                scenario_summary[
                    "Scenario"
                ].isin(
                    EXACT_SCENARIOS
                )
            ]
        )


        auto_summary = (
            scenario_summary[
                scenario_summary[
                    "Scenario"
                ].isin(
                    AUTO_PROCESS_SCENARIOS
                )
            ]
        )


        attention_summary = (
            scenario_summary[
                ~scenario_summary[
                    "Scenario"
                ].isin(
                    NO_ATTENTION_SCENARIOS
                )
            ]
        )


        col1, col2, col3 = (
            st.columns(3)
        )


        # ---------------------------------------------
        # Exact
        # ---------------------------------------------

        with col1:

            st.markdown(
                "### ✅ Exact"
            )

            st.metric(
                "Cases",
                int(
                    exact_summary[
                        "Count"
                    ].sum()
                ),
            )

            st.caption(
                "All reconciliation checks passed."
            )

            st.dataframe(
                exact_summary[["Display Scenario", "Count"]].rename(
                    columns={"Display Scenario": "Scenario"}
                ),
                width="stretch",
                hide_index=True,
            )


        # ---------------------------------------------
        # Auto Process
        # ---------------------------------------------

        with col2:

            st.markdown(
                "### ⚙️ Auto Process"
            )

            st.metric(
                "Cases",
                int(
                    auto_summary[
                        "Count"
                    ].sum()
                ),
            )

            st.caption(
                "Handled automatically without "
                "manual investigation."
            )

            st.dataframe(
                auto_summary[["Display Scenario", "Count"]].rename(
                    columns={"Display Scenario": "Scenario"}
                ),
                width="stretch",
                hide_index=True,
            )


        # ---------------------------------------------
        # Need Attention
        # ---------------------------------------------

        with col3:

            st.markdown(
                "### ⚠️ Need Attention"
            )

            st.metric(
                "Cases",
                int(
                    attention_summary[
                        "Count"
                    ].sum()
                ),
            )

            st.caption(
                "Requires AI investigation or "
                "human review."
            )

            st.dataframe(
                attention_summary[["Display Scenario", "Count"]].rename(
                    columns={"Display Scenario": "Scenario"}
                ),
                width="stretch",
                hide_index=True,
            )


# =========================================================
# TAB 3 - REVIEW CASES
# =========================================================

with tab_review:

    st.header(
        "Cases Requiring Attention"
    )


    if results is None:

        st.info(
            "Run reconciliation first."
        )


    else:

        review_results = (
            get_review_results(
                results
            )
        )


        if review_results.empty:

            st.success(
                "No cases require review."
            )


        else:

            st.write(
                f"**{len(review_results)} cases** "
                "currently require attention."
            )


            st.subheader(
                "Filters"
            )


            # -------------------------------------------------
            # First filter row
            # -------------------------------------------------

            f1, f2, f3, f4 = (
                st.columns(4)
            )


            with f1:

                scenarios = sorted(
                    review_results[
                        "scenario"
                    ]
                    .dropna()
                    .unique()
                    .tolist()
                )


                selected_scenario = (
                    st.selectbox(
                        "Scenario",
                        ["All"]
                        + scenarios,
                        format_func=lambda value: (
                            "All" if value == "All"
                            else friendly_label(value, SCENARIO_LABELS)
                        ),
                        key=(
                            "review_scenario_filter"
                        ),
                    )
                )


            with f2:

                actions = sorted(
                    review_results[
                        "action"
                    ]
                    .dropna()
                    .unique()
                    .tolist()
                )


                selected_action = (
                    st.selectbox(
                        "Action",
                        ["All"]
                        + actions,
                        format_func=lambda value: (
                            "All" if value == "All"
                            else friendly_label(value, ACTION_LABELS)
                        ),
                        key=(
                            "review_action_filter"
                        ),
                    )
                )


            with f3:

                statuses = sorted(
                    review_results[
                        "review_status"
                    ]
                    .dropna()
                    .unique()
                    .tolist()
                )


                selected_status = (
                    st.selectbox(
                        "Review Status",
                        ["All"]
                        + statuses,
                        format_func=lambda value: (
                            "All" if value == "All"
                            else friendly_label(value, STATUS_LABELS)
                        ),
                        key=(
                            "review_status_filter"
                        ),
                    )
                )


            with f4:

                selected_case_type = st.selectbox(
                    "Case Type",
                    ["All", "Invoice", "Bank only"],
                    key="review_case_type_filter",
                )


            # -------------------------------------------------
            # Second filter row
            # -------------------------------------------------

            s1, s2 = (
                st.columns(2)
            )


            with s1:

                search_invoice = (
                    st.text_input(
                        "Search Invoice ID",
                        placeholder=(
                            "INV-2026-000279"
                        ),
                        key=(
                            "review_invoice_search"
                        ),
                    )
                )


            with s2:

                search_bank = (
                    st.text_input(
                        "Search Bank Transaction ID",
                        placeholder=(
                            "BNK-00000001"
                        ),
                        key=(
                            "review_bank_search"
                        ),
                    )
                )


            # -------------------------------------------------
            # Apply filters
            # -------------------------------------------------

            filtered = (
                review_results.copy()
            )


            if (
                selected_scenario
                != "All"
            ):

                filtered = filtered[
                    filtered["scenario"]
                    == selected_scenario
                ]


            if (
                selected_action
                != "All"
            ):

                filtered = filtered[
                    filtered["action"]
                    == selected_action
                ]


            if (
                selected_status
                != "All"
            ):

                filtered = filtered[
                    filtered[
                        "review_status"
                    ]
                    == selected_status
                ]


            if selected_case_type != "All":

                filtered = filtered[
                    filtered.apply(case_type_label, axis=1)
                    == selected_case_type
                ]


            if search_invoice:

                filtered = filtered[
                    filtered["invoice_id"]
                    .fillna("")
                    .astype(str)
                    .str.contains(
                        search_invoice,
                        case=False,
                    )
                ]


            if search_bank:

                filtered = filtered[
                    filtered[
                        "bank_transaction_ids"
                    ]
                    .astype(str)
                    .str.contains(
                        search_bank,
                        case=False,
                    )
                ]


            st.write(
                f"Showing **{len(filtered)}** cases."
            )


            # -------------------------------------------------
            # Result table
            # -------------------------------------------------

            display_columns = [
                column
                for column in [
                    "invoice_id",
                    "scenario",
                    "action",
                    "ledger_entry_ids",
                    "bank_transaction_ids",
                    "vendor_similarity",
                    "review_status",
                ]
                if column
                in filtered.columns
            ]


            display_frame = filtered[display_columns].copy()
            display_frame.insert(
                1,
                "case_type",
                filtered.apply(case_type_label, axis=1),
            )
            if "scenario" in display_frame:
                display_frame["scenario"] = display_frame["scenario"].map(
                    lambda value: friendly_label(value, SCENARIO_LABELS)
                )
            if "action" in display_frame:
                display_frame["action"] = display_frame["action"].map(
                    lambda value: friendly_label(value, ACTION_LABELS)
                )
            if "review_status" in display_frame:
                display_frame["review_status"] = display_frame[
                    "review_status"
                ].map(lambda value: friendly_label(value, STATUS_LABELS))

            st.dataframe(
                display_frame.rename(
                    columns={
                        "invoice_id": "Invoice ID",
                        "case_type": "Case type",
                        "scenario": "Scenario",
                        "action": "Recommended action",
                        "ledger_entry_ids": "Ledger entries",
                        "bank_transaction_ids": "Bank transactions",
                        "vendor_similarity": "Vendor similarity",
                        "review_status": "Review status",
                    }
                ),
                width="stretch",
                hide_index=True,
            )

            if not filtered.empty:
                open_options = {}
                for index, row in filtered.iterrows():
                    case_id = (
                        first_id(row.get("bank_transaction_ids"))
                        if row.get("scenario") == "bank_only_unmatched"
                        else row.get("invoice_id")
                    )
                    open_options[
                        f"{case_id} — "
                        f"{friendly_label(row.get('scenario'), SCENARIO_LABELS)}"
                    ] = index

                open_label = st.selectbox(
                    "Case to investigate",
                    list(open_options),
                    key="review_open_case",
                )
                if st.button(
                    "Open in Investigation & Review",
                    width="stretch",
                ):
                    st.session_state.selected_case_index = open_options[open_label]
                    st.session_state.agent_case_selector = open_label
                    st.session_state.agent_scenario_filter = "All"
                    st.session_state.agent_action_filter = "All"
                    st.session_state.agent_case_type = "All"
                    st.session_state.agent_status_filter = "All"
                    st.session_state.agent_search_filter = ""
                    st.session_state.agent_result = None
                    st.session_state.agent_config = None
                    st.success(
                        "Case selected. Open the Investigation & Review tab "
                        "to continue."
                    )


# =========================================================
# TAB 4 - AI INVESTIGATION
# =========================================================

with tab_agent:

    st.header(
        "Investigation & Review"
    )


    if results is None:

        st.info(
            "Run reconciliation first."
        )


    else:

        review_results = (
            get_review_results(
                results
            )
        )


        if review_results.empty:

            st.success(
                "There are no cases requiring investigation."
            )


        else:

            # =================================================
            # FILTERS
            # =================================================

            st.subheader(
                "Find a Case"
            )


            f1, f2, f3, f4 = (
                st.columns(4)
            )


            # -------------------------------------------------
            # Scenario
            # -------------------------------------------------

            with f1:

                scenarios = sorted(
                    review_results[
                        "scenario"
                    ]
                    .dropna()
                    .unique()
                    .tolist()
                )


                agent_scenario = (
                    st.selectbox(
                        "Scenario",
                        ["All"]
                        + scenarios,
                        format_func=lambda value: (
                            "All" if value == "All"
                            else friendly_label(value, SCENARIO_LABELS)
                        ),
                        key=(
                            "agent_scenario_filter"
                        ),
                    )
                )


            # -------------------------------------------------
            # Action
            # -------------------------------------------------

            with f2:

                actions = sorted(
                    review_results[
                        "action"
                    ]
                    .dropna()
                    .unique()
                    .tolist()
                )


                agent_action = (
                    st.selectbox(
                        "Action",
                        ["All"]
                        + actions,
                        format_func=lambda value: (
                            "All" if value == "All"
                            else friendly_label(value, ACTION_LABELS)
                        ),
                        key=(
                            "agent_action_filter"
                        ),
                    )
                )


            # -------------------------------------------------
            # Case type
            # -------------------------------------------------

            with f3:

                case_type = (
                    st.selectbox(
                        "Case Type",
                        [
                            "All",
                            "Invoice",
                            "Bank Only",
                        ],
                        key=(
                            "agent_case_type"
                        ),
                    )
                )


            # -------------------------------------------------
            # Review status
            # -------------------------------------------------

            with f4:

                statuses = sorted(
                    review_results[
                        "review_status"
                    ]
                    .dropna()
                    .unique()
                    .tolist()
                )


                agent_status = (
                    st.selectbox(
                        "Review Status",
                        ["All"]
                        + statuses,
                        format_func=lambda value: (
                            "All" if value == "All"
                            else friendly_label(value, STATUS_LABELS)
                        ),
                        key=(
                            "agent_status_filter"
                        ),
                    )
                )


            # -------------------------------------------------
            # ID search
            # -------------------------------------------------

            agent_search = (
                st.text_input(
                    "Search Invoice or Bank Transaction ID",
                    placeholder=(
                        "INV-2026-000279 or BNK-00000001"
                    ),
                    key=(
                        "agent_search_filter"
                    ),
                )
            )


            # =================================================
            # APPLY AI FILTERS
            # =================================================

            filtered_agent_cases = (
                review_results.copy()
            )


            if agent_scenario != "All":

                filtered_agent_cases = (
                    filtered_agent_cases[
                        filtered_agent_cases[
                            "scenario"
                        ]
                        == agent_scenario
                    ]
                )


            if agent_action != "All":

                filtered_agent_cases = (
                    filtered_agent_cases[
                        filtered_agent_cases[
                            "action"
                        ]
                        == agent_action
                    ]
                )


            if agent_status != "All":

                filtered_agent_cases = (
                    filtered_agent_cases[
                        filtered_agent_cases[
                            "review_status"
                        ]
                        == agent_status
                    ]
                )


            # -------------------------------------------------
            # Case type
            # -------------------------------------------------

            if case_type == "Invoice":

                filtered_agent_cases = (
                    filtered_agent_cases[
                        filtered_agent_cases[
                            "scenario"
                        ]
                        != "bank_only_unmatched"
                    ]
                )


            elif case_type == "Bank Only":

                filtered_agent_cases = (
                    filtered_agent_cases[
                        filtered_agent_cases[
                            "scenario"
                        ]
                        == "bank_only_unmatched"
                    ]
                )


            # -------------------------------------------------
            # Search
            # -------------------------------------------------

            if agent_search:

                invoice_mask = (
                    filtered_agent_cases[
                        "invoice_id"
                    ]
                    .fillna("")
                    .astype(str)
                    .str.contains(
                        agent_search,
                        case=False,
                    )
                )


                bank_mask = (
                    filtered_agent_cases[
                        "bank_transaction_ids"
                    ]
                    .astype(str)
                    .str.contains(
                        agent_search,
                        case=False,
                    )
                )


                filtered_agent_cases = (
                    filtered_agent_cases[
                        invoice_mask
                        | bank_mask
                    ]
                )


            st.caption(
                f"{len(filtered_agent_cases)} "
                "cases match the selected filters."
            )


            # =================================================
            # SELECT CASE
            # =================================================

            if filtered_agent_cases.empty:

                st.warning(
                    "No cases match the selected filters."
                )


            else:

                case_options = {}


                for (
                    index,
                    row,
                ) in filtered_agent_cases.iterrows():

                    scenario = row.get(
                        "scenario"
                    )

                    invoice_id = row.get(
                        "invoice_id"
                    )

                    bank_id = first_id(
                        row.get(
                            "bank_transaction_ids"
                        )
                    )


                    if (
                        scenario
                        == "bank_only_unmatched"
                    ):

                        label = (
                            f"{bank_id} — "
                            f"{friendly_label(scenario, SCENARIO_LABELS)}"
                        )

                    else:

                        label = (
                            f"{invoice_id} — "
                            f"{friendly_label(scenario, SCENARIO_LABELS)}"
                        )


                    case_options[
                        label
                    ] = index


                option_labels = list(case_options)
                requested_index = st.session_state.selected_case_index
                default_position = (
                    list(case_options.values()).index(requested_index)
                    if requested_index in case_options.values()
                    else 0
                )
                selected_label = st.selectbox(
                    "Select Case",
                    option_labels,
                    index=default_position,
                    key="agent_case_selector",
                )


                selected_index = (
                    case_options[
                        selected_label
                    ]
                )


                selected_case = (
                    review_results.loc[
                        selected_index
                    ]
                )


                # ---------------------------------------------
                # Reset old AI result when user changes case
                # ---------------------------------------------

                if (
                    st.session_state
                    .selected_case_index
                    != selected_index
                ):

                    st.session_state.selected_case_index = (
                        selected_index
                    )

                    st.session_state.agent_result = (
                        None
                    )

                    st.session_state.agent_config = (
                        None
                    )


                # =================================================
                # CASE SUMMARY
                # =================================================

                st.divider()

                st.subheader(
                    "Case Summary"
                )


                c1, c2, c3 = (
                    st.columns(3)
                )


                invoice_id = (
                    selected_case.get(
                        "invoice_id"
                    )
                )


                scenario = (
                    selected_case.get(
                        "scenario"
                    )
                )


                action = (
                    selected_case.get(
                        "action"
                    )
                )


                with c1:

                    st.caption(
                        "Invoice ID"
                    )

                    if (
                        scenario
                        == "bank_only_unmatched"
                    ):

                        st.write(
                            "Bank-only case"
                        )

                    else:

                        st.write(
                            invoice_id
                        )


                with c2:

                    st.caption(
                        "Scenario"
                    )

                    st.write(
                        friendly_label(scenario, SCENARIO_LABELS)
                    )


                with c3:

                    st.caption(
                        "Current Review Status"
                    )

                    show_status_badge(
                        selected_case.get("review_status"),
                        scenario=scenario,
                    )


                st.markdown(
                    "**Recommended Action**"
                )

                st.info(friendly_label(action, ACTION_LABELS))


                show_case_evidence(
                    selected_case,
                    st.session_state.invoices,
                    st.session_state.ledger_entries,
                    st.session_state.bank_transactions,
                )


                # =================================================
                # RUN AGENT
                # =================================================

                if st.button(
                    "Investigate with AI",
                    type="primary",
                    width="stretch",
                ):

                    graph = (
                        st.session_state
                        .agent_graph
                    )


                    bank_transaction_id = (
                        first_id(
                            selected_case.get(
                                "bank_transaction_ids"
                            )
                        )
                    )


                    st.session_state.agent_run_counter += 1


                    run_number = (
                        st.session_state
                        .agent_run_counter
                    )


                    # -----------------------------------------
                    # Bank-only case
                    # -----------------------------------------

                    if (
                        scenario
                        == "bank_only_unmatched"
                    ):

                        thread_id = (
                            f"bank-"
                            f"{bank_transaction_id}-"
                            f"{run_number}"
                        )


                        input_state = {
                            "bank_transaction_id":
                                bank_transaction_id
                        }


                    # -----------------------------------------
                    # Invoice case
                    # -----------------------------------------

                    else:

                        thread_id = (
                            f"invoice-"
                            f"{invoice_id}-"
                            f"{run_number}"
                        )


                        input_state = {
                            "invoice_id":
                                str(invoice_id)
                        }


                    config = {
                        "configurable": {
                            "thread_id":
                                thread_id
                        }
                    }


                    with st.spinner(
                        "Agent is investigating the case..."
                    ):

                        agent_result = (
                            graph.invoke(
                                input_state,
                                config=config,
                            )
                        )


                    st.session_state.agent_result = (
                        agent_result
                    )

                    st.session_state.agent_config = (
                        config
                    )


                    # -----------------------------------------
                    # Save AI findings to final results
                    # -----------------------------------------

                    if (
                        agent_result.get(
                            "investigation_notes"
                        )
                    ):

                        st.session_state.reconciliation_results.at[
                            selected_index,
                            "investigation_notes",
                        ] = agent_result.get(
                            "investigation_notes"
                        )


                    if (
                        agent_result.get(
                            "recommendation"
                        )
                    ):

                        st.session_state.reconciliation_results.at[
                            selected_index,
                            "recommendation",
                        ] = agent_result.get(
                            "recommendation"
                        )


                    st.rerun()


                # =================================================
                # DISPLAY AGENT RESULT
                # =================================================

                agent_result = (
                    st.session_state
                    .agent_result
                )


                if agent_result:

                    st.divider()

                    st.subheader(
                        "Agent Findings"
                    )


                    investigation = (
                        agent_result.get(
                            "investigation_notes"
                        )
                    )


                    recommendation = (
                        agent_result.get(
                            "recommendation"
                        )
                    )


                    error_message = (
                        agent_result.get(
                            "error_message"
                        )
                    )


                    show_agent_findings(
                        investigation,
                        recommendation,
                    )


                    if error_message:

                        st.warning(
                            error_message
                        )


                    # =================================================
                    # HUMAN-IN-THE-LOOP
                    # =================================================

                    pending_review = (
                        "__interrupt__"
                        in agent_result
                    )


                    if pending_review:

                        st.warning(
                            "This case requires a human decision."
                        )


                        reviewer_name = (
                            st.text_input(
                                "Reviewer Name",
                                placeholder="Enter your name...",
                                key=(
                                    f"reviewer_"
                                    f"{selected_index}"
                                ),
                            )
                        )


                        reviewer_comment = (
                            st.text_area(
                                "Reviewer Comment",
                                placeholder=(
                                    "Explain your decision..."
                                ),
                                key=(
                                    f"comment_"
                                    f"{selected_index}"
                                ),
                            )
                        )


                        approve_col, reject_col = (
                            st.columns(2)
                        )


                        # -----------------------------------------
                        # APPROVE
                        # -----------------------------------------

                        with approve_col:

                            if st.button(
                                "✅ Approve",
                                width="stretch",
                            ):

                                final_result = (
                                    st.session_state
                                    .agent_graph
                                    .invoke(
                                        Command(
                                            resume={
                                                "decision":
                                                    "approve",

                                                "reviewed_by":
                                                    (reviewer_name.strip()
                                                     or "Unknown"),

                                                "comment":
                                                    reviewer_comment,
                                            }
                                        ),

                                        config=(
                                            st.session_state
                                            .agent_config
                                        ),
                                    )
                                )


                                st.session_state.agent_result = (
                                    final_result
                                )


                                st.session_state.reconciliation_results.at[
                                    selected_index,
                                    "review_status",
                                ] = "HUMAN_APPROVED"


                                st.session_state.reconciliation_results.at[
                                    selected_index,
                                    "human_comment",
                                ] = final_result.get("human_comment")


                                st.session_state.reconciliation_results.at[
                                    selected_index,
                                    "reviewed_by",
                                ] = final_result.get("reviewed_by")


                                st.session_state.reconciliation_results.at[
                                    selected_index,
                                    "reviewed_at",
                                ] = final_result.get("reviewed_at")


                                save_review_decision(
                                    selected_case,
                                    final_result,
                                    "APPROVED",
                                )


                                st.rerun()


                        # -----------------------------------------
                        # REJECT
                        # -----------------------------------------

                        with reject_col:

                            if st.button(
                                "❌ Reject",
                                width="stretch",
                            ):

                                final_result = (
                                    st.session_state
                                    .agent_graph
                                    .invoke(
                                        Command(
                                            resume={
                                                "decision":
                                                    "reject",

                                                "reviewed_by":
                                                    (reviewer_name.strip()
                                                     or "Unknown"),

                                                "comment":
                                                    reviewer_comment,
                                            }
                                        ),

                                        config=(
                                            st.session_state
                                            .agent_config
                                        ),
                                    )
                                )


                                st.session_state.agent_result = (
                                    final_result
                                )


                                st.session_state.reconciliation_results.at[
                                    selected_index,
                                    "review_status",
                                ] = "HUMAN_REJECTED"


                                st.session_state.reconciliation_results.at[
                                    selected_index,
                                    "human_comment",
                                ] = final_result.get("human_comment")


                                st.session_state.reconciliation_results.at[
                                    selected_index,
                                    "reviewed_by",
                                ] = final_result.get("reviewed_by")


                                st.session_state.reconciliation_results.at[
                                    selected_index,
                                    "reviewed_at",
                                ] = final_result.get("reviewed_at")


                                save_review_decision(
                                    selected_case,
                                    final_result,
                                    "REJECTED",
                                )


                                st.rerun()


                    # =================================================
                    # FINAL STATUS
                    # =================================================

                    final_status = (
                        agent_result.get(
                            "final_status"
                        )
                    )


                    if final_status:

                        if (
                            final_status
                            == "HUMAN_APPROVED"
                        ):

                            st.success(
                                "Final Status: HUMAN APPROVED"
                            )


                        elif (
                            final_status
                            == "HUMAN_REJECTED"
                        ):

                            st.error(
                                "Final Status: HUMAN REJECTED"
                            )


                        elif (
                            final_status
                            == "ERROR"
                        ):

                            st.error(
                                "Final Status: ERROR"
                            )


                        else:

                            st.info(
                                f"Final Status: "
                                f"{final_status}"
                            )


# =========================================================
# TAB 5 - DECISION HISTORY
# =========================================================

with tab_decisions:

    st.header("Human Review Decision History")

    if not st.session_state.decision_history:
        st.info("No reviewed cases yet.")

    else:
        history_df = pd.DataFrame(st.session_state.decision_history)
        history_columns = [
            "invoice_id",
            "bank_transaction_id",
            "scenario",
            "decision",
            "reviewed_by",
            "reviewed_at",
            "comment",
            "final_status",
        ]

        history_display = history_df[history_columns].copy()
        history_display["scenario"] = history_display["scenario"].map(
            lambda value: friendly_label(value, SCENARIO_LABELS)
        )
        history_display["decision"] = history_display["decision"].map(
            lambda value: friendly_label(value)
        )
        history_display["final_status"] = history_display[
            "final_status"
        ].map(lambda value: friendly_label(value, STATUS_LABELS))

        st.dataframe(
            history_display.rename(
                columns={
                    "invoice_id": "Invoice ID",
                    "bank_transaction_id": "Bank transaction ID",
                    "scenario": "Scenario",
                    "decision": "Decision",
                    "reviewed_by": "Reviewed by",
                    "reviewed_at": "Reviewed at",
                    "comment": "Reviewer comment",
                    "final_status": "Final status",
                }
            ),
            width="stretch",
            hide_index=True,
        )


# =========================================================
# TAB 6 - EXPORT
# =========================================================

with tab_export:

    st.header(
        "Export Results"
    )


    if results is None:

        st.info(
            "Run reconciliation first."
        )


    else:

        exact_cases = len(
            results[
                results["scenario"]
                == "exact"
            ]
        )


        auto_cases = len(
            results[
                results["scenario"].isin(
                    AUTO_PROCESS_SCENARIOS
                )
            ]
        )


        attention_cases = len(
            get_review_results(
                results
            )
        )


        approved_cases = len(
            results[
                results["review_status"]
                == "HUMAN_APPROVED"
            ]
        )


        rejected_cases = len(
            results[
                results["review_status"]
                == "HUMAN_REJECTED"
            ]
        )


        pending_cases = len(
            results[
                results["review_status"]
                == "PENDING"
            ]
        )


        # -------------------------------------------------
        # Summary
        # -------------------------------------------------

        c1, c2, c3 = (
            st.columns(3)
        )


        c1.metric(
            "Total Cases",
            len(results),
        )

        c2.metric(
            "Exact",
            exact_cases,
        )

        c3.metric(
            "Auto Processed",
            auto_cases,
        )


        c4, c5, c6 = (
            st.columns(3)
        )


        c4.metric(
            "Pending Review",
            pending_cases,
        )


        c5.metric(
            "Human Approved",
            approved_cases,
        )


        c6.metric(
            "Human Rejected",
            rejected_cases,
        )


        st.divider()


        # -------------------------------------------------
        # Audit-ready export
        # -------------------------------------------------

        export_results = results.copy()
        export_results.insert(
            1,
            "case_type",
            results.apply(case_type_label, axis=1),
        )
        export_results["scenario_label"] = export_results["scenario"].map(
            lambda value: friendly_label(value, SCENARIO_LABELS)
        )
        export_results["action_label"] = export_results["action"].map(
            lambda value: friendly_label(value, ACTION_LABELS)
        )
        export_results["final_review_status"] = export_results[
            "review_status"
        ].map(lambda value: friendly_label(value, STATUS_LABELS))

        audit_columns = [
            "invoice_id",
            "case_type",
            "bank_transaction_ids",
            "ledger_entry_ids",
            "scenario",
            "scenario_label",
            "action",
            "action_label",
            "review_status",
            "final_review_status",
            "investigation_notes",
            "recommendation",
            "reviewed_by",
            "reviewed_at",
            "human_comment",
        ]
        audit_columns.extend(
            column
            for column in export_results.columns
            if column not in audit_columns
        )
        export_results = export_results[audit_columns]

        # -------------------------------------------------
        # Final result preview
        # -------------------------------------------------

        with st.expander(
            "Preview final results"
        ):

            st.dataframe(
                export_results,
                width="stretch",
                hide_index=True,
            )


        # -------------------------------------------------
        # Download
        # -------------------------------------------------

        csv_data = (
            export_results
            .to_csv(index=False)
            .encode("utf-8")
        )


        st.download_button(
            "Download Final Reconciliation Results",
            data=csv_data,
            file_name=(
                "reconciliation_results.csv"
            ),
            mime="text/csv",
            type="primary",
            width="stretch",
        )
from __future__ import annotations

from decimal import Decimal

import pandas as pd
import streamlit as st

from reconciliation import generate_test_data, reconcile


st.set_page_config(page_title="Payments Reconciliation", layout="wide")
st.title("Payments Reconciliation Dashboard")
st.caption("Assessment dataset: March 2025 synthetic platform vs bank settlement records")

platform_file = st.file_uploader(
    "Platform Transactions CSV",
    type=["csv"],
    accept_multiple_files=False,
)
settlement_file = st.file_uploader(
    "Bank Settlements CSV",
    type=["csv"],
    accept_multiple_files=False,
)

sample_platform_df, sample_settlement_df = generate_test_data()
st.subheader("Download Sample CSVs")
sample_col1, sample_col2 = st.columns(2)
with sample_col1:
    st.download_button(
        label="Download Sample Platform CSV",
        data=sample_platform_df.to_csv(index=False),
        file_name="sample_platform_transactions.csv",
        mime="text/csv",
    )
with sample_col2:
    st.download_button(
        label="Download Sample Settlements CSV",
        data=sample_settlement_df.to_csv(index=False),
        file_name="sample_bank_settlements.csv",
        mime="text/csv",
    )

platform_required_cols = {
    "transaction_id",
    "customer_id",
    "amount",
    "currency",
    "timestamp",
}
settlement_required_cols = {
    "settlement_id",
    "transaction_id",
    "settled_amount",
    "settlement_date",
}

if platform_file is not None and settlement_file is not None:
    try:
        platform_df = pd.read_csv(platform_file)
        settlement_df = pd.read_csv(settlement_file)

        missing_platform = sorted(list(platform_required_cols - set(platform_df.columns)))
        missing_settlement = sorted(list(settlement_required_cols - set(settlement_df.columns)))

        if missing_platform:
            st.error(
                "Platform CSV is missing required columns: " + ", ".join(missing_platform)
            )
            st.stop()
        if missing_settlement:
            st.error(
                "Settlement CSV is missing required columns: " + ", ".join(missing_settlement)
            )
            st.stop()

        platform_df["timestamp"] = pd.to_datetime(platform_df["timestamp"])
        settlement_df["settlement_date"] = pd.to_datetime(settlement_df["settlement_date"]).dt.date
    except Exception as exc:
        st.error(f"Failed to parse uploaded CSV files: {exc}")
        st.stop()
elif platform_file is not None or settlement_file is not None:
    st.warning("Please upload both CSV files to run reconciliation on uploaded data.")
    st.stop()
else:
    st.info("No files uploaded — showing synthetic demo data.")
    platform_df, settlement_df = sample_platform_df, sample_settlement_df

result = reconcile(platform_df, settlement_df, recon_month="2025-03")

col1, col2, col3 = st.columns(3)
col1.metric("Total Platform Transactions", result.summary["total_transactions"])
col2.metric("Total Settlement Rows", result.summary["total_settled_rows"])
col3.metric("Total Gap Amount (USD)", f"${result.summary['total_gap_amount']}")

st.subheader("Mismatch Breakdown")

if result.gaps.empty:
    st.success("No gaps found.")
else:
    color_map = {
        "late_settlement_next_month": "#f59e0b",
        "rounding_difference_aggregate": "#3b82f6",
        "duplicate_entry": "#ef4444",
        "orphan_refund_no_original": "#10b981",
    }

    def format_gap_amount(value: object) -> str:
        amount = Decimal(str(value))
        if amount == amount.quantize(Decimal("0.01")):
            return f"${amount:.2f}"
        return f"${amount:.3f}"

    display_gaps = result.gaps.copy()
    display_gaps["gap_tag"] = display_gaps["gap_type"]
    display_gaps["gap_amount_fmt"] = display_gaps["gap_amount"].map(format_gap_amount)

    styled_gaps = display_gaps[
        ["transaction_id", "gap_tag", "reason", "gap_amount_fmt"]
    ].rename(
        columns={
            "gap_tag": "Gap Type",
            "gap_amount_fmt": "Gap Amount",
        }
    )

    def style_gap_types(row: pd.Series) -> list[str]:
        c = color_map.get(row["Gap Type"], "#6b7280")
        styles = [""] * len(row)
        gap_col_idx = list(row.index).index("Gap Type")
        styles[gap_col_idx] = (
            f"background-color: {c}; color: white; font-weight: 600; border-radius: 4px;"
        )
        amount_col_idx = list(row.index).index("Gap Amount")
        styles[amount_col_idx] = "min-width: 140px; white-space: nowrap; text-align: right;"
        return styles

    st.dataframe(
        styled_gaps.style.apply(style_gap_types, axis=1),
        use_container_width=True,
        height=320,
    )
    st.download_button(
        label="Download Gap Report (CSV)",
        data=result.gaps.to_csv(index=False),
        file_name="gap_report.csv",
        mime="text/csv",
    )

with st.expander("Assumptions", expanded=False):
    st.markdown("- Single USD currency")
    st.markdown("- UTC timestamps")
    st.markdown("- T+1 to T+2 settlement window")
    st.markdown("- Month-end cutoff = 2025-03-31")
    st.markdown("- IDs are exact-match (no fuzzy matching)")

st.subheader("Matched Transactions")
matched_display_df = result.matched.copy()
for col in ["amount", "settled_amount"]:
    if col in matched_display_df.columns:
        matched_display_df[col] = matched_display_df[col].apply(
            lambda x: f"{float(x):.2f}" if pd.notna(x) else ""
        )
st.dataframe(matched_display_df, use_container_width=True)

st.subheader("Unmatched / Exception Transactions")
unmatched_display_df = result.unmatched.copy()
for col in ["amount", "settled_amount"]:
    if col in unmatched_display_df.columns:
        unmatched_display_df[col] = unmatched_display_df[col].apply(
            lambda x: f"{float(x):.2f}" if pd.notna(x) else ""
        )
if "_merge" in unmatched_display_df.columns:
    unmatched_display_df["Match Status"] = unmatched_display_df["_merge"].map(
        {
            "left_only": "Platform only — no settlement",
            "right_only": "Settlement only — no platform record",
            "both": "Flagged by reconciliation rule",
        }
    )
    unmatched_display_df = unmatched_display_df.drop(columns=["_merge"])
st.dataframe(unmatched_display_df, use_container_width=True)

st.subheader("Production Limitations")
st.info(
    "This demo assumes a single currency and does not model FX conversions or cross-currency settlement behavior. "
    "It uses synthetic, clean IDs and simple rules, while production systems need fuzzy matching, reversals, chargebacks, and backfills. "
    "It also runs on batch snapshots and does not include event-time ordering guarantees, ledger immutability controls, or audit workflows."
)

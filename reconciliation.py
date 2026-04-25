from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ReconciliationResult:
    summary: dict[str, Any]
    matched: pd.DataFrame
    unmatched: pd.DataFrame
    gaps: pd.DataFrame


def generate_test_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create one month of fake platform and settlement data with planted gaps.

    Assumptions:
    - Currency is USD for all rows.
    - Timestamps are ISO-8601 and UTC-like naive values for this exercise.
    - Settlement dates are date-only values in YYYY-MM-DD format.
    - Platform transaction IDs use TXN-#### format.
    - Settlement IDs use SET-#### format.
    - Reconciliation month is March 2025 and month-end cutoff is 2025-03-31.
    - Settlements should normally occur within 1-2 days, but one known test case settles on 2025-04-01.
    """

    platform_transactions = [
        {
            "transaction_id": "TXN-1001",
            "customer_id": "CUST-01",
            "amount": Decimal("120.000999"),
            "currency": "USD",
            "timestamp": "2025-03-05T10:15:00",
        },
        {
            "transaction_id": "TXN-1002",
            "customer_id": "CUST-02",
            "amount": Decimal("75.500999"),
            "currency": "USD",
            "timestamp": "2025-03-12T14:22:00",
        },
        {
            "transaction_id": "TXN-1003",
            "customer_id": "CUST-03",
            "amount": Decimal("10.002000"),
            "currency": "USD",
            "timestamp": "2025-03-18T09:02:00",
        },
        {
            "transaction_id": "TXN-1004",
            "customer_id": "CUST-04",
            "amount": Decimal("240.000999"),
            "currency": "USD",
            "timestamp": "2025-03-31T23:55:00",
        },
        {
            "transaction_id": "TXN-1005",
            "customer_id": "CUST-05",
            "amount": Decimal("89.990999"),
            "currency": "USD",
            "timestamp": "2025-03-30T11:45:00",
        },
        {
            "transaction_id": "TXN-1006",
            "customer_id": "CUST-06",
            "amount": Decimal("51.120999"),
            "currency": "USD",
            "timestamp": "2025-03-22T16:10:00",
        },
    ]

    bank_settlements = [
        {
            "settlement_id": "SET-9001",
            "transaction_id": "TXN-1001",
            "settled_amount": Decimal("120.000000"),
            "settlement_date": "2025-03-06",
        },
        {
            "settlement_id": "SET-9002",
            "transaction_id": "TXN-1002",
            "settled_amount": Decimal("75.500000"),
            "settlement_date": "2025-03-13",
        },
        {
            "settlement_id": "SET-9003",
            "transaction_id": "TXN-1003",
            "settled_amount": Decimal("10.002000"),
            "settlement_date": "2025-03-19",
        },
        {
            "settlement_id": "SET-9004",
            "transaction_id": "TXN-1004",
            "settled_amount": Decimal("240.000000"),
            "settlement_date": "2025-04-01",
        },
        {
            "settlement_id": "SET-9005",
            "transaction_id": "TXN-1005",
            "settled_amount": Decimal("89.990000"),
            "settlement_date": "2025-03-31",
        },
        {
            "settlement_id": "SET-9006",
            "transaction_id": "TXN-1005",
            "settled_amount": Decimal("89.990000"),
            "settlement_date": "2025-03-31",
        },
        {
            "settlement_id": "SET-9008",
            "transaction_id": "TXN-1006",
            "settled_amount": Decimal("51.120000"),
            "settlement_date": "2025-03-23",
        },
        {
            "settlement_id": "SET-9007",
            "transaction_id": "RFD-404",
            "settled_amount": Decimal("-30.00"),
            "settlement_date": "2025-03-20",
        },
    ]

    platform_df = pd.DataFrame(platform_transactions)
    settlement_df = pd.DataFrame(bank_settlements)

    platform_df["timestamp"] = pd.to_datetime(platform_df["timestamp"])
    settlement_df["settlement_date"] = pd.to_datetime(settlement_df["settlement_date"]).dt.date

    return platform_df, settlement_df


def reconcile(
    platform_df: pd.DataFrame,
    settlement_df: pd.DataFrame,
    recon_month: str = "2025-03",
) -> ReconciliationResult:
    recon_period = pd.Period(recon_month, freq="M")
    month_end = recon_period.end_time.date()

    joined = platform_df.merge(
        settlement_df,
        on="transaction_id",
        how="outer",
        indicator=True,
        suffixes=("_platform", "_settlement"),
    )

    gap_records: list[dict[str, Any]] = []

    # Gap 1: transaction settled in following month.
    late_mask = (
        joined["transaction_id"].notna()
        & joined["_merge"].eq("both")
        & joined["timestamp"].notna()
        & (joined["timestamp"].dt.to_period("M") == recon_period)
        & (joined["settlement_date"] > month_end)
    )
    late_rows = joined.loc[late_mask]
    for _, row in late_rows.iterrows():
        gap_records.append(
            {
                "transaction_id": row["transaction_id"],
                "gap_type": "late_settlement_next_month",
                "reason": f"Transaction settled on {row['settlement_date']} after month-end {month_end}.",
                "gap_amount": Decimal(str(row["amount"])),
            }
        )

    # Gap 2: rounding difference visible at aggregate level.
    rounded_join = joined[
        joined["_merge"].eq("both")
        & joined["amount"].notna()
        & joined["settled_amount"].notna()
    ].copy()
    rounded_join["diff"] = rounded_join.apply(
        lambda r: Decimal(str(r["amount"])) - Decimal(str(r["settled_amount"])), axis=1
    )
    small_diff = rounded_join[
        rounded_join["diff"].abs().gt(Decimal("0"))
        & rounded_join["diff"].abs().lt(Decimal("0.001"))
    ]
    if not small_diff.empty:
        aggregate_diff = small_diff["diff"].sum()
        if abs(aggregate_diff) >= Decimal("0.005"):
            gap_records.append(
                {
                    "transaction_id": "MULTI-TXN",
                    "gap_type": "rounding_difference_aggregate",
                    "reason": "Small per-transaction precision drifts create a non-zero aggregate difference.",
                    "gap_amount": abs(aggregate_diff),
                }
            )

    # Gap 3: duplicate transaction in one dataset.
    settlement_dupes = settlement_df[settlement_df.duplicated("transaction_id", keep=False)]
    for transaction_id, group in settlement_dupes.groupby("transaction_id"):
        extra_entries = len(group) - 1
        if extra_entries > 0:
            sorted_group = group.sort_values("settlement_id")
            duplicate_total = sorted_group.iloc[1:]["settled_amount"].sum()
            gap_records.append(
                {
                    "transaction_id": transaction_id,
                    "gap_type": "duplicate_entry",
                    "reason": f"{extra_entries} extra settlement row(s) found for the same transaction_id.",
                    "gap_amount": abs(Decimal(str(duplicate_total))),
                }
            )

    # Gap 4: refund without matching platform transaction.
    orphan_refunds = settlement_df[
        (settlement_df["settled_amount"] < 0)
        & (~settlement_df["transaction_id"].isin(platform_df["transaction_id"]))
    ]
    for _, row in orphan_refunds.iterrows():
        gap_records.append(
            {
                "transaction_id": row["transaction_id"],
                "gap_type": "orphan_refund_no_original",
                "reason": "Negative settlement has no corresponding original platform transaction.",
                "gap_amount": abs(Decimal(str(row["settled_amount"]))),
            }
        )

    gaps_df = pd.DataFrame(gap_records)
    if gaps_df.empty:
        gaps_df = pd.DataFrame(columns=["transaction_id", "gap_type", "reason", "gap_amount"])

    flagged_ids = set(gaps_df[gaps_df["transaction_id"] != "MULTI-TXN"]["transaction_id"].tolist())

    matched_df = joined[
        joined["_merge"].eq("both")
        & ~joined["transaction_id"].isin(flagged_ids)
    ][
        [
            "transaction_id",
            "customer_id",
            "amount",
            "currency",
            "timestamp",
            "settlement_id",
            "settled_amount",
            "settlement_date",
        ]
    ].copy()

    unmatched_df = joined[
        joined["_merge"].ne("both") | joined["transaction_id"].isin(flagged_ids)
    ][
        [
            "transaction_id",
            "customer_id",
            "amount",
            "currency",
            "timestamp",
            "settlement_id",
            "settled_amount",
            "settlement_date",
            "_merge",
        ]
    ].copy()

    gap_reason_map: dict[str, str] = {}
    for _, row in gaps_df.iterrows():
        tx = row["transaction_id"]
        if tx == "MULTI-TXN":
            continue
        gap_reason_map[tx] = row["reason"]

    unmatched_df["exception_reason"] = unmatched_df["transaction_id"].map(gap_reason_map)
    unmatched_df["exception_reason"] = unmatched_df["exception_reason"].fillna(
        unmatched_df["_merge"].map(
            {
                "left_only": "Platform transaction has no settlement row.",
                "right_only": "Settlement row has no platform transaction.",
                "both": "Flagged by reconciliation rule.",
            }
        )
    )

    total_gap_amount = sum([Decimal(str(x)) for x in gaps_df["gap_amount"].tolist()], Decimal("0"))

    summary = {
        "total_transactions": int(platform_df["transaction_id"].nunique()),
        "total_settled_rows": int(settlement_df["settlement_id"].nunique()),
        "matched_rows": int(len(matched_df)),
        "unmatched_rows": int(len(unmatched_df)),
        "total_gap_amount": total_gap_amount,
    }

    return ReconciliationResult(
        summary=summary,
        matched=matched_df,
        unmatched=unmatched_df,
        gaps=gaps_df,
    )

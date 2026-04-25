from decimal import Decimal

from reconciliation import generate_test_data, reconcile


def test_detects_late_settlement_next_month() -> None:
    platform_df, settlement_df = generate_test_data()
    result = reconcile(platform_df, settlement_df, recon_month="2025-03")

    late = result.gaps[result.gaps["gap_type"] == "late_settlement_next_month"]
    assert len(late) == 1
    assert late.iloc[0]["transaction_id"] == "TXN-1004"


def test_detects_rounding_difference_aggregate() -> None:
    platform_df, settlement_df = generate_test_data()
    result = reconcile(platform_df, settlement_df, recon_month="2025-03")

    joined = platform_df.merge(settlement_df, on="transaction_id", how="inner")
    row_diffs = joined.apply(
        lambda r: abs(Decimal(str(r["amount"])) - Decimal(str(r["settled_amount"]))), axis=1
    )

    rounding = result.gaps[result.gaps["gap_type"] == "rounding_difference_aggregate"]
    assert len(rounding) == 1
    assert row_diffs.max() <= Decimal("0.001")
    assert Decimal(str(rounding.iloc[0]["gap_amount"])) >= Decimal("0.005")


def test_detects_duplicate_entry() -> None:
    platform_df, settlement_df = generate_test_data()
    result = reconcile(platform_df, settlement_df, recon_month="2025-03")

    duplicates = result.gaps[result.gaps["gap_type"] == "duplicate_entry"]
    assert len(duplicates) == 1
    assert duplicates.iloc[0]["transaction_id"] == "TXN-1005"


def test_detects_orphan_refund_no_original() -> None:
    platform_df, settlement_df = generate_test_data()
    result = reconcile(platform_df, settlement_df, recon_month="2025-03")

    refunds = result.gaps[result.gaps["gap_type"] == "orphan_refund_no_original"]
    assert len(refunds) == 1
    assert refunds.iloc[0]["transaction_id"] == "RFD-404"

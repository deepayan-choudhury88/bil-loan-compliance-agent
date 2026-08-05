"""Run sample collateral suggestions for first 10 Rule-3 failures from loans.csv.

Run:
    python -m retrieval.test_sample
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterator, List

from retrieval.retriever import get_company_context
from retrieval.suggestion_agent import suggest_asset

LOANS_CSV_PATH = Path("data/loans.csv")
MAX_FAILURE_SAMPLES = 10


def iter_rule3_failures(csv_path: Path) -> Iterator[Dict[str, str]]:
    """Yield rows where asset_value < 0.5 * loan_value."""
    with csv_path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            try:
                asset_value = float(row["asset_value"])
                loan_value = float(row["loan_value"])
            except (KeyError, TypeError, ValueError):
                continue

            if asset_value < 0.5 * loan_value:
                yield row


def format_report(loan: Dict[str, str], suggestion: Dict[str, object]) -> str:
    """Render a readable suggestion report for one loan."""
    suggested_asset = suggestion.get("suggested_asset") if suggestion.get("status") == "success" else "N/A"
    reason = suggestion.get("reason", "")

    return "\n".join(
        [
            f"Loan ID: {loan.get('loan_id', '')}",
            f"Company: {loan.get('company_name', '')}",
            f"Current Asset: {loan.get('asset_description', '')}",
            f"Loan Value: {loan.get('loan_value', '')} {loan.get('loan_currency', '')}",
            f"Suggested Asset: {suggested_asset}",
            f"Reason: {reason}",
            "-" * 72,
        ]
    )


def main() -> None:
    if not LOANS_CSV_PATH.exists():
        raise FileNotFoundError(f"CSV file not found: {LOANS_CSV_PATH}")

    failures: List[Dict[str, str]] = []
    for row in iter_rule3_failures(LOANS_CSV_PATH):
        failures.append(row)
        if len(failures) >= MAX_FAILURE_SAMPLES:
            break

    if not failures:
        print("No Rule 3 failures found in dataset.")
        return

    for loan in failures:
        company_name = loan.get("company_name", "")
        current_asset = loan.get("asset_description", "")

        try:
            loan_value = float(loan.get("loan_value", "0"))
        except ValueError:
            loan_value = 0.0

        try:
            current_asset_value = float(loan.get("asset_value", "0"))
        except ValueError:
            current_asset_value = 0.0

        # Retrieve context once and reuse it for suggestion generation.
        context = get_company_context(company_name)

        suggestion = suggest_asset(
            company_name=company_name,
            loan_value=loan_value,
            current_asset=current_asset,
            current_asset_value=current_asset_value,
            retrieved_context=context,
        )
        print(format_report(loan, suggestion))


if __name__ == "__main__":
    main()

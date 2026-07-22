from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class QueryTarget:
    customer_name: str
    customer_key: str
    receive_dates: list[str]


def normalize_customer_name(name: str) -> str:
    text = str(name or "")
    text = text.replace("\u3000", " ").strip()
    text = " ".join(text.split())
    return text


def build_query_targets(
    excel_path: Path,
    date_field: str,
    customer_field: str,
    date_format: str,
) -> list[QueryTarget]:
    df = pd.read_excel(excel_path)

    if date_field not in df.columns or customer_field not in df.columns:
        missing = [
            field
            for field in (date_field, customer_field)
            if field not in df.columns
        ]
        raise ValueError(f"Missing required columns: {missing}")

    working = df[[date_field, customer_field]].copy()
    working[customer_field] = working[customer_field].fillna("").map(normalize_customer_name)
    working = working[working[customer_field] != ""]

    parsed_dates = pd.to_datetime(working[date_field], errors="coerce")
    working[date_field] = parsed_dates.dt.strftime(date_format).fillna("")

    working["customer_key"] = working[customer_field]

    grouped = working.groupby("customer_key", as_index=False, sort=False).agg(
        customer_name=(customer_field, "first"),
        receive_dates=(date_field, lambda s: sorted(set(v for v in s if v))),
    )

    targets: list[QueryTarget] = []
    for _, row in grouped.iterrows():
        targets.append(
            QueryTarget(
                customer_name=row["customer_name"],
                customer_key=row["customer_key"],
                receive_dates=list(row["receive_dates"]),
            )
        )

    return targets

from __future__ import annotations

from pathlib import Path
import re
import json

import pandas as pd


ROC_DATE_PATTERN = re.compile(r"^(\d{2,3})[./-](\d{1,2})[./-](\d{1,2})$")
ILLEGAL_EXCEL_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
EXCEL_CELL_CHAR_LIMIT = 32767
TARGET_CASE_KEYWORDS = [
    "支付命令",
    "本票裁定",
    "清償借款",
    "本票裁定強制執行",
    "清償債務",
    "返還借款",
    "請求返還借款",
]

DETAIL_COLUMNS = [
    "receive_date_earliest",
    "customer_name",
    "query_status",
    "judgment_id",
    "judgment_date",
    "case_type",
    "full_text",
]

REVISED_COLUMNS = [
    "pre_examine_id",
    "pre_examine_no",
    "receive_date",
    "current_status_desc",
    "bus_name2",
    "customer_type",
    "customer_id_no",
    "customer_name",
    "company_or_not",
    "match_flag",
]


def roc_to_ad_date_str(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    match = ROC_DATE_PATTERN.match(text)
    if match:
        roc_year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        ad_year = roc_year + 1911
        try:
            dt = pd.Timestamp(year=ad_year, month=month, day=day)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return ""

    dt = pd.to_datetime(text, errors="coerce")
    if pd.isna(dt):
        return ""
    return dt.strftime("%Y-%m-%d")


def earliest_receive_date(receive_dates: list[str]) -> str:
    if not receive_dates:
        return ""

    parsed = pd.to_datetime(pd.Series(receive_dates), errors="coerce").dropna()
    if parsed.empty:
        return ""

    return parsed.min().strftime("%Y-%m-%d")


def sanitize_excel_text(value: object) -> str:
    text = str(value or "")
    text = ILLEGAL_EXCEL_CHAR_RE.sub("", text)
    if len(text) > EXCEL_CELL_CHAR_LIMIT:
        text = text[:EXCEL_CELL_CHAR_LIMIT]
    return text


def build_detail_df_from_json(json_path: Path) -> pd.DataFrame:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    records = payload.get("records", [])

    rows: list[dict[str, str]] = []
    for record in records:
        earliest = earliest_receive_date(record.get("receive_dates", []))
        customer_name = sanitize_excel_text(record.get("customer_name", ""))
        query_status = sanitize_excel_text(record.get("query_status", ""))
        judgments = record.get("judgments", [])

        if not judgments:
            rows.append(
                {
                    "receive_date_earliest": earliest,
                    "customer_name": customer_name,
                    "query_status": query_status,
                    "judgment_id": "",
                    "judgment_date": "",
                    "case_type": "",
                    "full_text": "",
                }
            )
            continue

        for judgment in judgments:
            rows.append(
                {
                    "receive_date_earliest": earliest,
                    "customer_name": customer_name,
                    "query_status": query_status,
                    "judgment_id": sanitize_excel_text(judgment.get("judgment_id", "")),
                    "judgment_date": sanitize_excel_text(judgment.get("judgment_date", "")),
                    "case_type": sanitize_excel_text(judgment.get("case_type", "")),
                    "full_text": sanitize_excel_text(judgment.get("full_text", "")),
                }
            )

    return pd.DataFrame(rows, columns=DETAIL_COLUMNS)


def resolve_master_path(project_root: Path) -> Path:
    parent_master = project_root.parent / "SCC_設備業退緩議_僅公司_2301至2606.xlsx"
    local_master = project_root / "data/input/SCC_設備業退緩議_僅公司_2301至2606.xlsx"

    if parent_master.exists():
        return parent_master
    if local_master.exists():
        return local_master
    raise FileNotFoundError("Master Excel not found in parent folder or data/input folder")


def build_workbook() -> Path:
    project_root = Path(__file__).resolve().parent
    json_path = project_root / "data/output/judgment_results_batch.json"
    master_path = resolve_master_path(project_root)
    output_path = project_root / "data/output/judgment_results_batch_revised.xlsx"

    detail_df = build_detail_df_from_json(json_path)
    master_df = pd.read_excel(master_path)

    # 1) Convert judgment_date from ROC date to AD date while keeping column name unchanged.
    detail_df["judgment_date"] = detail_df["judgment_date"].map(roc_to_ad_date_str)

    # 2) Build df_revised from selected case types and merge with master by customer_name.
    case_type_series = detail_df["case_type"].fillna("").astype(str)
    case_mask = case_type_series.apply(
        lambda x: any(keyword in x for keyword in TARGET_CASE_KEYWORDS)
    )
    filtered_detail_df = detail_df.loc[case_mask].copy()

    master_df["receive_date"] = pd.to_datetime(master_df["receive_date"], errors="coerce")
    filtered_detail_df["judgment_date_dt"] = pd.to_datetime(
        filtered_detail_df["judgment_date"], errors="coerce"
    )

    df_revised = master_df.merge(
        filtered_detail_df[
            [
                "customer_name",
                "query_status",
                "judgment_id",
                "judgment_date",
                "judgment_date_dt",
                "case_type",
                "full_text",
            ]
        ],
        on="customer_name",
        how="left",
    )

    condition = (
        (df_revised["query_status"] == "FOUND")
        & df_revised["receive_date"].notna()
        & df_revised["judgment_date_dt"].notna()
        & (df_revised["receive_date"] <= df_revised["judgment_date_dt"])
    )
    df_revised["match_flag"] = condition.astype(int)

    df_revised["receive_date"] = df_revised["receive_date"].dt.strftime("%Y-%m-%d")
    df_revised = df_revised.drop(columns=["judgment_date_dt"])
    df_revised = df_revised[REVISED_COLUMNS]
    df_revised.sort_values(by=["pre_examine_no", "customer_type", "match_flag"], ascending=[True, True, False], inplace=True)
    df_revised.drop_duplicates(subset=["pre_examine_no", "customer_type"], keep = "first", inplace=True)

    # 3) Export two sheets into one Excel workbook.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_revised.to_excel(writer, sheet_name="df_revised", index=False)
        detail_df.to_excel(writer, sheet_name="法學輸出明細", index=False)

    return output_path


if __name__ == "__main__":
    path = build_workbook()
    print(f"Revised workbook exported: {path}")

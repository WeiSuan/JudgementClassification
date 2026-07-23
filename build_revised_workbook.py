from __future__ import annotations

import argparse
from pathlib import Path
import unicodedata
import re
import json
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

import pandas as pd


ROC_DATE_PATTERN = re.compile(r"^(\d{2,3})[./-](\d{1,2})[./-](\d{1,2})$")
ILLEGAL_EXCEL_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
FULLWIDTH_PUNCT_RE = re.compile(r"[，。！？；：、（）［］【】｛｝「」『』《》〈〉〔〕．～…—－／＼｜＂＇｀﹏]")
EXCEL_CELL_CHAR_LIMIT = 32767

OLLAMA_API_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:3b"

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
    "judgment_date_dt",
    "judgment_date",
    "case_type",
    "full_text",
    "full_text_revised",
    "party_a",
    "party_b",
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
    "full_text_revised",
    "party_a",
    "party_b",
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


def remove_fullwidth_punctuation(value: object) -> str:
    text = sanitize_excel_text(value)
    return FULLWIDTH_PUNCT_RE.sub("", text)


def parse_revised_full_text(value: object, window_size: int = 100) -> str:
    text = remove_fullwidth_punctuation(value)
    cleaned_text = "".join(
        ch for ch in text if not (ch.isspace() or unicodedata.category(ch).startswith("P"))
    )

    marker = "裁判字號"
    marker_index = cleaned_text.find(marker)
    if marker_index == -1:
        return ""

    start_index = marker_index + len(marker)
    return cleaned_text[start_index : start_index + window_size]


def extract_json_object(text: str) -> dict[str, object]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}

    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}

    return payload if isinstance(payload, dict) else {}


def parse_party_ab_with_ollama(text: str, model: str = OLLAMA_MODEL) -> tuple[str, str]:
    source_text = remove_fullwidth_punctuation(text).strip()
    if not source_text:
        return "", ""

    prompt = (
        "請從下列法院裁判文字中，辨識兩個角色："
        "A = 受請求者/遭訴求者，常見於被告、債務人、相對人；"
        "B = 請求者/訴求者，常見於原告、債權人、聲請人。"
        "只輸出 JSON，不要輸出說明文字。JSON 格式如下："
        '{"party_a":"...","party_b":"..."}。'
        "若某一方無法判定，欄位填空字串。請保留原文出現順序，"
        "多個名稱以「、」串接。裁判文字如下：\n\n"
        f"{source_text}"
    )

    request_body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0,
                "num_predict": 256,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")

    request = Request(
        OLLAMA_API_URL,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Ollama API call failed: {exc}") from exc

    raw_text = str(payload.get("response", "")).strip()
    parsed = extract_json_object(raw_text)
    party_a = sanitize_excel_text(parsed.get("party_a", ""))
    party_b = sanitize_excel_text(parsed.get("party_b", ""))
    return party_a, party_b


def enrich_party_columns(detail_df: pd.DataFrame, progress_every: int = 50) -> pd.DataFrame:
    cache: dict[str, tuple[str, str]] = {}
    party_a_values: list[str] = []
    party_b_values: list[str] = []

    total = len(detail_df)
    for idx, row in enumerate(detail_df.itertuples(index=False), start=1):
        text = str(getattr(row, "full_text_revised", "") or "").strip()
        customer_name = str(getattr(row, "customer_name", "") or "")

        if text:
            if text not in cache:
                cache[text] = parse_party_ab_with_ollama(text)
            party_a, party_b = cache[text]
        else:
            party_a, party_b = "", ""

        party_a_values.append(party_a)
        party_b_values.append(party_b)

        if progress_every > 0 and idx % progress_every == 0:
            print(f"[party-parse] {idx}/{total} customer={customer_name}")

    result_df = detail_df.copy()
    result_df["party_a"] = party_a_values
    result_df["party_b"] = party_b_values
    return result_df


def apply_detail_filter(
    detail_df: pd.DataFrame,
    limit: int | None = None,
    customers: list[str] | None = None,
) -> pd.DataFrame:
    working_df = detail_df.copy()

    if customers:
        customer_set = {name.strip() for name in customers if name.strip()}
        if customer_set:
            working_df = working_df[working_df["customer_name"].isin(customer_set)].copy()

    if limit is not None:
        working_df = working_df.head(limit).copy()

    return working_df


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


def build_workbook(
    limit: int | None = None,
    customers: list[str] | None = None,
    output_suffix: str = "",
    progress_every: int = 50,
) -> Path:
    project_root = Path(__file__).resolve().parent
    json_path = project_root / "data/output/judgment_results_batch.json"
    master_path = resolve_master_path(project_root)
    output_name = "judgment_results_batch_revised"
    if output_suffix.strip():
        output_name = f"{output_name}_{output_suffix.strip()}"
    output_path = project_root / f"data/output/{output_name}.xlsx"

    detail_df = build_detail_df_from_json(json_path)
    detail_df = apply_detail_filter(detail_df, limit=limit, customers=customers)
    if detail_df.empty:
        raise ValueError("No rows left after applying filters; please adjust --limit or --customer")

    master_df = pd.read_excel(master_path)

    # 1) Convert judgment_date from ROC date to AD date while keeping column name unchanged.
    detail_df["judgment_date"] = detail_df["judgment_date"].map(roc_to_ad_date_str)
    detail_df["full_text_revised"] = detail_df["full_text"].map(
        lambda value: parse_revised_full_text(value, window_size=200)
    )

    detail_df = enrich_party_columns(detail_df, progress_every=progress_every)

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
    filtered_detail_df = filtered_detail_df[DETAIL_COLUMNS].copy()

    df_revised = master_df.merge(
        filtered_detail_df[
            [
                "customer_name",
                "query_status",
                "judgment_id",
                "judgment_date",
                "judgment_date_dt",
                "case_type",
                "full_text_revised",
                "party_a",
                "party_b",
            ]
        ],
        on="customer_name",
        how="left",
    )

    condition = (
        (df_revised["query_status"] == "FOUND")
        & df_revised["receive_date"].notna()
        & df_revised["judgment_date"].notna()
        & (df_revised["receive_date"] <= df_revised["judgment_date"])
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Only process first N detail rows")
    parser.add_argument(
        "--customer",
        action="append",
        default=None,
        help="Filter by customer_name; can be passed multiple times",
    )
    parser.add_argument(
        "--output-suffix",
        type=str,
        default="",
        help="Suffix for output filename (e.g. quicktest)",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=50,
        help="Print progress every N detail rows while parsing parties",
    )
    args = parser.parse_args()

    path = build_workbook(
        limit=args.limit,
        customers=args.customer,
        output_suffix=args.output_suffix,
        progress_every=args.progress_every,
    )
    print(f"Revised workbook exported: {path}")

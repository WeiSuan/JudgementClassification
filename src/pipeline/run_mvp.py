from __future__ import annotations

import json
from pathlib import Path

import yaml

from src.crawler.judicial_client import CrawlerConfig, JudicialClient
from src.preprocess.excel_pipeline import build_query_targets
from src.schemas.models import CustomerRecord, OutputMeta, OutputPayload


def load_settings(settings_path: Path) -> dict:
    with settings_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def run(settings_path: Path) -> Path:
    settings = load_settings(settings_path)

    input_cfg = settings["input"]
    crawler_cfg = settings["crawler"]
    output_cfg = settings["output"]
    mvp_cfg = settings.get("mvp", {})

    project_root = settings_path.parent.parent
    excel_path = project_root / input_cfg["file_path"]
    output_path = project_root / output_cfg["path"]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    targets = build_query_targets(
        excel_path=excel_path,
        date_field=input_cfg["date_field"],
        customer_field=input_cfg["customer_field"],
        date_format=input_cfg["date_format"],
    )

    if not targets:
        payload = OutputPayload(
            meta=OutputMeta.now(source_file=excel_path.name, site=crawler_cfg["base_url"]),
            records=[],
        )
        output_path.write_text(
            json.dumps(payload.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_path

    # MVP: prefer explicit test customer, fallback to first unique customer.
    test_customer_name = str(mvp_cfg.get("test_customer_name", "")).strip()
    if test_customer_name:
        target = next(
            (item for item in targets if item.customer_name == test_customer_name),
            targets[0],
        )
    else:
        target = targets[0]

    client = JudicialClient(
        CrawlerConfig(
            base_url=crawler_cfg["base_url"],
            headless=bool(crawler_cfg["headless"]),
            timeout_ms=int(crawler_cfg["timeout_ms"]),
            detail_timeout_ms=int(crawler_cfg.get("detail_timeout_ms", 10000)),
        )
    )

    status, note, judgments = client.query_customer(target.customer_name)

    record = CustomerRecord(
        receive_dates=target.receive_dates,
        customer_name=target.customer_name,
        customer_key=target.customer_key,
        query_status=status,
        query_note=note,
        judgments=judgments,
    )

    payload = OutputPayload(
        meta=OutputMeta.now(source_file=excel_path.name, site=crawler_cfg["base_url"]),
        records=[record],
    )

    output_path.write_text(
        json.dumps(payload.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


if __name__ == "__main__":
    result_path = run(Path("config/settings.yaml"))
    print(f"JSON exported: {result_path}")

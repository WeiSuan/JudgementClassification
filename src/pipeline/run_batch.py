from __future__ import annotations

import json
import time
from pathlib import Path

import yaml

from src.crawler.judicial_client import CrawlerConfig, JudicialClient
from src.preprocess.excel_pipeline import build_query_targets
from src.schemas.models import CustomerRecord, OutputMeta, OutputPayload


def load_settings(settings_path: Path) -> dict:
    with settings_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def _write_payload(output_path: Path, payload: OutputPayload) -> None:
    output_path.write_text(
        json.dumps(payload.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run(settings_path: Path) -> Path:
    settings = load_settings(settings_path)

    input_cfg = settings["input"]
    crawler_cfg = settings["crawler"]
    batch_cfg = settings.get("batch", {})

    project_root = settings_path.parent.parent
    excel_path = project_root / input_cfg["file_path"]
    output_path = project_root / batch_cfg.get("output_path", "data/output/judgment_results_batch.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    targets = build_query_targets(
        excel_path=excel_path,
        date_field=input_cfg["date_field"],
        customer_field=input_cfg["customer_field"],
        date_format=input_cfg["date_format"],
    )

    resume = bool(batch_cfg.get("resume", True))
    payload: OutputPayload
    if resume and output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        payload = OutputPayload.model_validate(existing)
        payload.meta = OutputMeta.now(source_file=excel_path.name, site=crawler_cfg["base_url"])
    else:
        payload = OutputPayload(
            meta=OutputMeta.now(source_file=excel_path.name, site=crawler_cfg["base_url"]),
            records=[],
        )
        _write_payload(output_path, payload)

    if not targets:
        return output_path

    request_interval = float(batch_cfg.get("request_interval_seconds", crawler_cfg.get("request_interval_seconds", 1)))
    max_retries = int(batch_cfg.get("max_retries", crawler_cfg.get("max_retries", 2)))

    client = JudicialClient(
        CrawlerConfig(
            base_url=crawler_cfg["base_url"],
            headless=bool(crawler_cfg["headless"]),
            timeout_ms=int(crawler_cfg["timeout_ms"]),
            detail_timeout_ms=int(crawler_cfg.get("detail_timeout_ms", 10000)),
        )
    )

    processed_keys = {record.customer_key for record in payload.records}
    pending_targets = [target for target in targets if target.customer_key not in processed_keys]

    total = len(targets)
    start = len(processed_keys)

    if pending_targets:
        print(f"Resume from {start}/{total}, pending {len(pending_targets)}")

    for offset, target in enumerate(pending_targets, start=1):
        idx = start + offset
        status = "ERROR"
        note = ""
        judgments = []

        for attempt in range(1, max_retries + 1):
            status, note, judgments = client.query_customer(target.customer_name)
            if status in {"FOUND", "NO_DATA"}:
                break
            if attempt < max_retries:
                time.sleep(max(request_interval, 1.0))

        record = CustomerRecord(
            receive_dates=target.receive_dates,
            customer_name=target.customer_name,
            customer_key=target.customer_key,
            query_status=status,
            query_note=note,
            judgments=judgments,
        )

        payload.records.append(record)
        _write_payload(output_path, payload)

        print(f"[{idx}/{total}] {target.customer_name} -> {status} ({len(judgments)} judgments)")
        time.sleep(max(request_interval, 0.2))

    return output_path


if __name__ == "__main__":
    result_path = run(Path("config/settings.yaml"))
    print(f"Batch JSON exported: {result_path}")

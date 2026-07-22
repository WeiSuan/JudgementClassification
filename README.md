# Judgment Crawler Project Scaffold

## Goal
Build a Python-based crawler pipeline for judicial judgment lookup:
1. Read Excel input and extract `receive_date` and `customer_name`.
2. Query https://judgment.judicial.gov.tw/FJUD/default.aspx by customer name.
3. Return structured results and export JSON.

## Current Status
This repository contains an executable **MVP pipeline**:
- Read Excel and extract `receive_date` / `customer_name`
- Normalize and de-duplicate customer names before query
- Query judicial website with Playwright (MVP: one target customer)
- Export JSON result

## Suggested Structure
- `src/preprocess`: Excel parsing and de-duplication pipeline.
- `src/crawler`: Playwright crawling and data extraction.
- `src/schemas`: Data contract models.
- `src/pipeline`: End-to-end orchestration.
- `data/input`: Source Excel files.
- `data/output`: JSON outputs.
- `data/logs`: Runtime logs.
- `config`: Runtime configuration files.
- `docs`: Requirements, architecture, and output schema references.

## Bootstrap
1. Create virtual environment
   - PowerShell:
     - `python -m venv .venv`
2. Activate virtual environment
   - PowerShell:
     - `.\\.venv\\Scripts\\Activate.ps1`
3. Install dependencies
   - `pip install -r requirements.txt`
4. Install Playwright browser runtime
   - `playwright install chromium`

## Run MVP
- Default test target is configured in `config/settings.yaml`:
   - `mvp.test_customer_name: 麗展能源有限公司`
- Run:
   - `python run_mvp.py`
- Output file:
   - `data/output/judgment_results_mvp.json`

## Run Full Batch (Deduplicated)
- This mode queries all deduplicated customer names from Excel.
- Run:
   - `python run_batch.py`
- Output file:
   - `data/output/judgment_results_batch.json`
- Runtime controls in `config/settings.yaml`:
   - `batch.request_interval_seconds`
   - `batch.max_retries`

## Input Data
Place source Excel under `data/input/`.
Expected primary file name:
- `SCC_設備業退緩議_僅公司_2301至2606.xlsx`

## MVP Test Case
Use first customer name for trial query:
- `麗展能源有限公司`

## Output
See `docs/json_output_template.json` for proposed JSON structure.

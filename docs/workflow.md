# Workflow Plan (No Implementation Yet)

## Stage A: Input Preparation
- Confirm source Excel exists under `data/input/`.
- Validate required columns:
  - `receive_date`
  - `customer_name`

## Stage B: Preprocess
- Convert `receive_date` into normalized date format.
- Normalize customer names and de-duplicate list.
- Keep mapping from original row ids to de-duplicated customer key.

## Stage C: Crawler (Playwright)
- Open default page: https://judgment.judicial.gov.tw/FJUD/default.aspx
- Input customer name and submit search.
- Capture result summary:
  - `裁判字號`
  - `裁判日期`
  - `裁判案由`
- Open each matched judgment and capture detail text.

## Stage D: Export
- If no match, set status `NO_DATA` and note `查無資料`.
- If match exists, store all matched judgments under same customer.
- Export JSON according to `docs/json_output_template.json`.

## MVP Test
- First trial customer: `麗展能源有限公司`

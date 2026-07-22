# Input Field Specification

## Required Columns
- `receive_date`
  - Meaning: 進件日
  - Type: date
  - Normalize target format: `YYYY-MM-DD`

- `customer_name`
  - Meaning: 客戶名稱
  - Type: string
  - Must be normalized before de-duplication

## Preprocess Rules (Recommended)
1. Drop rows where `customer_name` is empty.
2. Trim spaces and normalize whitespace.
3. De-duplicate by normalized `customer_name`.
4. Preserve original row index for traceability.

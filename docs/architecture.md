# Architecture Draft (Scaffold Phase)

## End-to-End Flow
1. Excel input loading from `data/input/`.
2. Field extraction:
   - `receive_date` (date)
   - `customer_name` (string)
3. Data cleaning and de-duplication before crawling.
4. Query judicial website per unique customer.
5. Parse search result rows.
6. Parse judgment detail page content.
7. Merge outputs into JSON file.

## Modules
- `src/preprocess`: schema check, field mapping, normalization, de-dup.
- `src/crawler`: Playwright page automation and extraction.
- `src/schemas`: output contract and validation.
- `src/pipeline`: run sequencing and checkpointing.

## De-duplication Strategy
Primary objective: reduce repeated lookups when source contains duplicate customers.

Recommended strategy:
1. Normalize `customer_name`:
   - trim leading/trailing spaces
   - collapse repeated spaces
   - convert full-width spaces to half-width spaces
2. Create `customer_key` from normalized name.
3. Group by `customer_key` and aggregate all related `receive_date` values.
4. Crawl once per `customer_key`, then map same result to all original rows.

## Retry and Stability
- Retry transient failures for fixed attempts.
- Save intermediate checkpoints (future implementation) to avoid repeated work.

# Playwright MCP Setup Notes

## Purpose
Use Playwright with MCP-enabled workflow for robust browser automation.

## Baseline Dependencies
- Python package: `playwright`
- Browser runtime: Chromium via `playwright install chromium`

## Suggested Execution Profile
- Start with `headless=false` for selector debugging.
- Switch to `headless=true` in production.
- Keep request interval and retry in config.

## Future MCP Integration Notes
If using an MCP server for Playwright control, keep these configurable:
- browser type (chromium)
- timeout
- locale
- user agent
- proxy (if needed)

No executable crawler code is included in this phase.

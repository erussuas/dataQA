# EnergyCAP Emissions Export QA Workbench — v11 Enriched Object Resolution

This version enriches the correction register after QA generation using Report-03 and Report-19 matches.

## Improvements

- Backfills site/account/meter/commodity fields from matching master and usage records.
- Adds `record_grain`.
- Uses “Multiple / not applicable” instead of blanks for site-level or aggregate issues.
- Keeps `object_resolution_status` and `object_resolution_note`.

## Deploy

Upload only:

- `app.py`
- `requirements.txt`

# EnergyCAP Emissions Export QA Workbench — v9 Record-Focused UI

This version makes the EnergyCAP record needing attention explicit in the UI.

## Key UI changes

- The correction register now prioritizes:
  - `energycap_object_type`
  - `energycap_record_to_review`
  - `site_name`
  - `account_number`
  - `meter_name`
  - `meter_code`
  - `commodity`
  - `issue`
  - `recommended_energycap_fix`
- Executive Readiness tab includes “Top EnergyCAP records to review.”
- Site Readiness tab includes an “Issues grouped by site” view.

## Deploy

Upload only:

- `app.py`
- `requirements.txt`

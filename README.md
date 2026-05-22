# EnergyCAP Pre-Export QA App — v2

Streamlit app to ingest EnergyCAP Reports 03, 19, 13, 21, and 26 and produce a record-level correction workbench before exporting energy utility usage to an emissions calculation tool.

## What changed in v2

- The app does not analyze automatically.
- All five files must be uploaded before the `Run QA` button is enabled.
- The app produces detailed record-level exceptions, not only summary counts.
- Each issue includes a correction target: Site, Account, Meter, Commodity, Month, likely EnergyCAP area to review, and suggested correction action.
- Exception downloads are available as CSV.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

Upload these files to GitHub and set `app.py` as the main file.

## Important note

EnergyCAP report exports vary by tenant and configuration. The parser uses flexible column detection, but column mappings should be validated with your actual export formats before production use.

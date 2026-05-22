# EnergyCAP Emissions Export QA Workbench — v8 Key Fix

Single-file Streamlit app.

## Fix in v8

Fixes a Streamlit session-state key collision caused by using `r26` both as a file uploader widget key and as an internal dataframe key.

## Deploy

Upload only:

- `app.py`
- `requirements.txt`

Then run:

```bash
streamlit run app.py
```

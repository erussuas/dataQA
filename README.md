# EnergyCAP Pre-Export QA App

Streamlit app to ingest EnergyCAP Reports 03, 19, 13, 21, and 26 and run pre-emissions-export QA.

## Purpose

The app helps identify, categorize, quantify, and summarize data issues before EnergyCAP usage data is exported to a downstream emissions calculation tool.

## Reports supported

- Report-03: Setup report for accounts, vendors, cost centers, meters, and sites
- Report-19: Monthly Utility Use and Cost
- Report-13: Bill Analysis
- Report-21: Monthly Comparison
- Report-26: Use and Cost Summary

## How to run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## How to deploy on Streamlit Community Cloud

1. Create a GitHub repository.
2. Upload all files in this package.
3. In Streamlit Community Cloud, select the repo.
4. Set the main file path to `app.py`.
5. Deploy.

## Notes

EnergyCAP exports can vary by configuration. The app uses flexible column detection, but you should confirm column mappings in the app after upload.

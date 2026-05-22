# EnergyCAP Emissions Export QA Workbench — v7 Single File

This version removes the separate `energycap_qa.py` module to avoid import/deployment mismatch errors on Streamlit Cloud.

## Main file

Use:

```bash
streamlit run app.py
```

## Purpose

The app creates an EnergyCAP object-level correction register before EnergyCAP energy utility usage is exported to a site-level emissions calculation tool.

The correction register is organized by EnergyCAP object, not Excel row:

- Site
- Account
- Meter
- Account-Meter relationship
- Site-Account-Meter-Commodity relationship
- Site-Commodity monthly coverage
- Bill / Usage record
- Aggregate rollup / report filter issue

## Required reports

- Report-03
- Report-19
- Report-13
- Report-21
- Report-26

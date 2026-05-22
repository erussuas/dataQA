# EnergyCAP Emissions Export QA Workbench — v6

Purpose-built Streamlit app for pre-export QA before EnergyCAP utility usage data feeds a site-level emissions calculation tool.

## Original intent

The app answers:

> Can I trust EnergyCAP energy utility usage data to calculate emissions at the site level?

It does **not** treat Excel rows as the correction object. It creates a register of **EnergyCAP records / objects** that need attention:

- Site
- Account
- Meter
- Account-Meter relationship
- Site-Account-Meter-Commodity relationship
- Bill / usage record
- Site-Commodity monthly coverage
- Aggregate rollup / report filter issue

## Reports used

- Report-03: master EnergyCAP setup / hierarchy
- Report-19: monthly utility usage fact table
- Report-13: bill anomaly support
- Report-21: monthly variance support
- Report-26: aggregate reconciliation support

## How to run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy

Upload all files to GitHub and deploy `app.py` in Streamlit Community Cloud.

## Key outputs

- Emissions export readiness score
- EnergyCAP correction register by EnergyCAP object
- Materiality by MWh / Dth
- Site-level emissions readiness
- Hierarchy reconciliation
- Aggregate reconciliation

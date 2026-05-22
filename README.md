# EnergyCAP Pre-Export QA App — v4 dtype fix

Fixes the pandas dtype error in v3 where text values like `Electricity` or `Natural Gas`
could not be inserted into columns initialized as numeric/NaN.

## Main fixes

- Text columns are explicitly initialized as object/string-safe columns.
- Commodity inference assignment is now dtype-safe.
- Usage standardization handles missing columns more safely.
- Keeps the v3 fast architecture.

Run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

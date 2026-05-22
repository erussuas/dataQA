# EnergyCAP Pre-Export QA App — v3 Fast

This version fixes the v2 performance issue and the `raw_record_preview` crash.

## Main fixes

- Removed slow row-by-row raw-record aggregation.
- Avoids turning every row of Reports 13/21/26 into a correction-register item.
- Adds configurable caps for review records.
- Keeps detailed record-level exceptions for actionable setup and usage issues from Reports 03 and 19.
- Keeps Reports 13, 21, and 26 as supporting review inputs.
- The app waits until all 5 reports are uploaded and the user clicks **Run QA**.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

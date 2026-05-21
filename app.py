
import io

import pandas as pd
import plotly.express as px
import streamlit as st

from energycap_qa import (
    build_master,
    build_usage,
    choose_largest_sheet,
    qa_from_reports,
    read_excel_flexible,
    score_qa,
)

st.set_page_config(page_title="EnergyCAP Pre-Export QA", layout="wide")

st.title("EnergyCAP Pre-Export QA for Emissions Reporting")
st.caption("Ingest EnergyCAP Reports 03, 19, 13, 21, and 26 to identify data issues before exporting utility usage to an emissions tool.")

with st.sidebar:
    st.header("Upload EnergyCAP Reports")
    file03 = st.file_uploader("Report-03 — Setup / master export", type=["xlsx", "xls"], key="r03")
    file19 = st.file_uploader("Report-19 — Monthly Utility Use and Cost", type=["xlsx", "xls"], key="r19")
    file13 = st.file_uploader("Report-13 — Bill Analysis", type=["xlsx", "xls"], key="r13")
    file21 = st.file_uploader("Report-21 — Monthly Comparison", type=["xlsx", "xls"], key="r21")
    file26 = st.file_uploader("Report-26 — Use and Cost Summary", type=["xlsx", "xls"], key="r26")
    st.divider()
    st.write("Minimum recommended input: Report-03 and Report-19.")

def load_uploaded(file):
    if not file:
        return None, {}
    sheets = read_excel_flexible(file)
    return choose_largest_sheet(sheets), sheets

r03, sheets03 = load_uploaded(file03)
r19, sheets19 = load_uploaded(file19)
r13, sheets13 = load_uploaded(file13)
r21, sheets21 = load_uploaded(file21)
r26, sheets26 = load_uploaded(file26)

if r03 is None or r19 is None:
    st.info("Upload at least Report-03 and Report-19 to run the core QA.")
    st.stop()

master = build_master(r03)
usage = build_usage(r19)
issues = qa_from_reports(master, usage, r13, r21, r26)
score = score_qa(issues)

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Overall QA Score", f"{score}/100")
kpi2.metric("QA Rules Triggered", len(issues[issues["occurrences"] > 0]))
kpi3.metric("Impacted MWh", f"{issues['impacted_mwh'].sum():,.1f}")
kpi4.metric("Impacted Dth", f"{issues['impacted_dth'].sum():,.1f}")

st.divider()

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Executive Summary",
    "Exception Register",
    "Master Data Review",
    "Usage Review",
    "Export Files"
])

with tab1:
    st.subheader("QA Summary")
    active = issues[issues["occurrences"] > 0].copy()

    if active.empty:
        st.success("No QA exceptions detected by the current rules.")
    else:
        by_cat = active.groupby("category", as_index=False).agg(
            occurrences=("occurrences", "sum"),
            impacted_mwh=("impacted_mwh", "sum"),
            impacted_dth=("impacted_dth", "sum"),
        )
        fig = px.bar(by_cat, x="category", y="occurrences", title="Occurrences by QA Category")
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(by_cat.sort_values("occurrences", ascending=False), use_container_width=True)

    st.subheader("Readiness interpretation")
    if score >= 90:
        st.success("Green: likely ready for controlled export, subject to review of high-severity exceptions.")
    elif score >= 75:
        st.warning("Yellow: export may be possible, but exceptions should be reviewed and documented.")
    else:
        st.error("Red: not recommended for emissions export until material issues are resolved.")

with tab2:
    st.subheader("Exception Register")
    st.dataframe(issues.sort_values(["severity", "occurrences"], ascending=[True, False]), use_container_width=True)

    st.download_button(
        "Download Exception Register CSV",
        issues.to_csv(index=False).encode("utf-8"),
        file_name="energycap_qa_exception_register.csv",
        mime="text/csv",
    )

with tab3:
    st.subheader("Report-03 Master Data")
    st.write("Detected master fields from Report-03.")
    st.dataframe(master.head(1000), use_container_width=True)

    st.subheader("Master Data Completeness")
    completeness = pd.DataFrame({
        "field": master.columns,
        "missing_count": [master[c].isna().sum() for c in master.columns],
        "missing_pct": [master[c].isna().mean() for c in master.columns],
    }).sort_values("missing_pct", ascending=False)
    st.dataframe(completeness, use_container_width=True)

with tab4:
    st.subheader("Report-19 Usage Data")
    st.dataframe(usage.head(1000), use_container_width=True)

    st.subheader("Usage by Standard Unit")
    unit_sum = usage.groupby("std_unit", dropna=False, as_index=False)["usage_std"].sum()
    st.dataframe(unit_sum, use_container_width=True)

with tab5:
    st.subheader("Download Normalized QA Inputs")
    st.download_button(
        "Download normalized master CSV",
        master.to_csv(index=False).encode("utf-8"),
        file_name="normalized_report03_master.csv",
        mime="text/csv",
    )
    st.download_button(
        "Download normalized usage CSV",
        usage.to_csv(index=False).encode("utf-8"),
        file_name="normalized_report19_usage.csv",
        mime="text/csv",
    )

st.caption("Version 0.1 MVP. EnergyCAP report formats vary; validate mappings and calculations before production use.")

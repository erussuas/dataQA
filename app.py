import pandas as pd
import plotly.express as px
import streamlit as st

from energycap_qa import (
    build_generic_report,
    build_master,
    build_usage,
    choose_largest_sheet,
    create_record_level_issues,
    read_excel_flexible,
    score_qa,
    summarize_issues,
)

st.set_page_config(page_title="EnergyCAP Pre-Export QA", layout="wide")

st.title("EnergyCAP Pre-Export QA Correction Workbench")
st.caption("Upload Reports 03, 19, 13, 21, and 26. The app waits for all files, then produces record-level exceptions to correct in EnergyCAP.")

with st.sidebar:
    st.header("1) Upload required reports")
    file03 = st.file_uploader("Required: Report-03 — Setup / master export", type=["xlsx", "xls"], key="r03")
    file19 = st.file_uploader("Required: Report-19 — Monthly Utility Use and Cost", type=["xlsx", "xls"], key="r19")
    file13 = st.file_uploader("Required: Report-13 — Bill Analysis", type=["xlsx", "xls"], key="r13")
    file21 = st.file_uploader("Required: Report-21 — Monthly Comparison", type=["xlsx", "xls"], key="r21")
    file26 = st.file_uploader("Required: Report-26 — Use and Cost Summary", type=["xlsx", "xls"], key="r26")

    all_files = all([file03, file19, file13, file21, file26])
    st.divider()
    st.header("2) Run QA")
    if not all_files:
        st.warning("Upload all five reports to enable QA.")
    run_qa = st.button("Run QA", type="primary", disabled=not all_files)

if not all_files:
    st.info("The app will not analyze anything until all five files are uploaded and you click **Run QA**.")
    uploaded_count = sum(bool(x) for x in [file03, file19, file13, file21, file26])
    st.progress(uploaded_count / 5, text=f"{uploaded_count}/5 reports uploaded")
    st.stop()

if not run_qa and "issue_detail" not in st.session_state:
    st.success("All five files are uploaded. Click **Run QA** in the sidebar to start the analysis.")
    st.stop()


@st.cache_data(show_spinner=False)
def load_uploaded(file):
    sheets = read_excel_flexible(file)
    return choose_largest_sheet(sheets), list(sheets.keys())


if run_qa:
    with st.spinner("Running EnergyCAP QA and building record-level correction register..."):
        r03, sheets03 = load_uploaded(file03)
        r19, sheets19 = load_uploaded(file19)
        r13, sheets13 = load_uploaded(file13)
        r21, sheets21 = load_uploaded(file21)
        r26, sheets26 = load_uploaded(file26)

        master = build_master(r03)
        usage = build_usage(r19)
        r13_generic = build_generic_report(r13, "Report-13")
        r21_generic = build_generic_report(r21, "Report-21")
        r26_generic = build_generic_report(r26, "Report-26")

        issue_detail = create_record_level_issues(master, usage, r13_generic, r21_generic, r26_generic)
        issue_summary = summarize_issues(issue_detail)
        score = score_qa(issue_detail)

        st.session_state["master"] = master
        st.session_state["usage"] = usage
        st.session_state["issue_detail"] = issue_detail
        st.session_state["issue_summary"] = issue_summary
        st.session_state["score"] = score
        st.session_state["sheet_info"] = {
            "Report-03": sheets03,
            "Report-19": sheets19,
            "Report-13": sheets13,
            "Report-21": sheets21,
            "Report-26": sheets26,
        }

master = st.session_state["master"]
usage = st.session_state["usage"]
issue_detail = st.session_state["issue_detail"]
issue_summary = st.session_state["issue_summary"]
score = st.session_state["score"]

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
kpi1.metric("Overall QA Score", f"{score}/100")
kpi2.metric("Record-Level Issues", f"{len(issue_detail):,}")
kpi3.metric("High Severity", f"{(issue_detail['severity'] == 'High').sum():,}" if not issue_detail.empty else "0")
kpi4.metric("Impacted MWh", f"{issue_detail['impacted_mwh'].sum():,.1f}" if not issue_detail.empty else "0.0")
kpi5.metric("Impacted Dth", f"{issue_detail['impacted_dth'].sum():,.1f}" if not issue_detail.empty else "0.0")

st.divider()

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Executive Summary",
    "Correction Register",
    "EnergyCAP To-Do List",
    "Master Data Review",
    "Usage Review",
    "Downloads"
])

with tab1:
    st.subheader("QA Summary")
    if issue_detail.empty:
        st.success("No issues detected by the current rules.")
    else:
        c1, c2 = st.columns([1, 1])
        with c1:
            by_cat = issue_detail.groupby("category", as_index=False).size().rename(columns={"size": "issues"})
            fig = px.bar(by_cat.sort_values("issues", ascending=False), x="category", y="issues", title="Issues by Category")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            by_sev = issue_detail.groupby("severity", as_index=False).size().rename(columns={"size": "issues"})
            fig = px.pie(by_sev, names="severity", values="issues", title="Issues by Severity")
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(issue_summary, use_container_width=True)

    st.subheader("Readiness interpretation")
    if score >= 90:
        st.success("Green: likely ready for controlled export after review of high-severity items.")
    elif score >= 75:
        st.warning("Yellow: exceptions should be reviewed and documented before export.")
    else:
        st.error("Red: not recommended for emissions export until material issues are corrected.")

with tab2:
    st.subheader("Record-Level Correction Register")
    st.write("Use this table to identify the specific EnergyCAP records that likely need attention.")

    if issue_detail.empty:
        st.success("No record-level exceptions found.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            sev_vals = sorted(issue_detail["severity"].dropna().unique())
            sev = st.multiselect("Severity", sev_vals, default=sev_vals)
        with col2:
            cat_vals = sorted(issue_detail["category"].dropna().unique())
            cat = st.multiselect("Category", cat_vals, default=cat_vals)
        with col3:
            src_vals = sorted(issue_detail["source_report"].dropna().unique())
            source = st.multiselect("Source report", src_vals, default=src_vals)

        filtered = issue_detail[
            issue_detail["severity"].isin(sev)
            & issue_detail["category"].isin(cat)
            & issue_detail["source_report"].isin(source)
        ].copy()

        search = st.text_input("Search site, account, meter, rule, or suggested action")
        if search:
            mask = filtered.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
            filtered = filtered[mask]

        st.dataframe(filtered, use_container_width=True, height=600)
        st.download_button(
            "Download filtered correction register CSV",
            filtered.to_csv(index=False).encode("utf-8"),
            file_name="energycap_record_level_correction_register_filtered.csv",
            mime="text/csv",
        )

with tab3:
    st.subheader("EnergyCAP To-Do List")
    st.write("Grouped by likely EnergyCAP area and suggested correction action.")

    if issue_detail.empty:
        st.success("No correction tasks generated.")
    else:
        todo = (
            issue_detail
            .groupby(["likely_energycap_area", "suggested_correction_action", "severity"], dropna=False)
            .agg(
                records=("issue_id", "count"),
                impacted_mwh=("impacted_mwh", "sum"),
                impacted_dth=("impacted_dth", "sum"),
            )
            .reset_index()
            .sort_values(["severity", "records"], ascending=[True, False])
        )
        st.dataframe(todo, use_container_width=True, height=500)

        st.subheader("Top correction keys")
        top_keys = (
            issue_detail
            .groupby(["correction_key"], dropna=False)
            .agg(
                records=("issue_id", "count"),
                high_severity=("severity", lambda x: (x == "High").sum()),
                impacted_mwh=("impacted_mwh", "sum"),
                impacted_dth=("impacted_dth", "sum"),
            )
            .reset_index()
            .sort_values(["high_severity", "records"], ascending=False)
            .head(100)
        )
        st.dataframe(top_keys, use_container_width=True, height=400)

with tab4:
    st.subheader("Normalized Report-03 Master Data")
    st.dataframe(master, use_container_width=True, height=500)

    st.subheader("Master Data Completeness")
    completeness = pd.DataFrame({
        "field": master.columns,
        "missing_count": [master[c].isna().sum() for c in master.columns],
        "missing_pct": [master[c].isna().mean() for c in master.columns],
    }).sort_values("missing_pct", ascending=False)
    st.dataframe(completeness, use_container_width=True)

with tab5:
    st.subheader("Normalized Report-19 Usage Data")
    st.dataframe(usage, use_container_width=True, height=500)

    st.subheader("Usage by Standard Unit")
    if "std_unit" in usage:
        unit_sum = usage.groupby("std_unit", dropna=False, as_index=False)["usage_std"].sum()
        st.dataframe(unit_sum, use_container_width=True)

with tab6:
    st.subheader("Download QA Outputs")
    st.download_button(
        "Download full record-level correction register",
        issue_detail.to_csv(index=False).encode("utf-8"),
        file_name="energycap_record_level_correction_register.csv",
        mime="text/csv",
    )
    st.download_button(
        "Download summary by rule",
        issue_summary.to_csv(index=False).encode("utf-8"),
        file_name="energycap_qa_summary_by_rule.csv",
        mime="text/csv",
    )
    st.download_button(
        "Download normalized Report-03 master",
        master.to_csv(index=False).encode("utf-8"),
        file_name="normalized_report03_master.csv",
        mime="text/csv",
    )
    st.download_button(
        "Download normalized Report-19 usage",
        usage.to_csv(index=False).encode("utf-8"),
        file_name="normalized_report19_usage.csv",
        mime="text/csv",
    )

st.caption("EnergyCAP QA App v2. Validate column mappings and rule logic against your EnergyCAP tenant before production use.")

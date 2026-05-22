
import pandas as pd
import plotly.express as px
import streamlit as st

from energycap_qa import (
    build_master,
    build_usage,
    choose_largest_sheet,
    create_record_level_issues,
    read_excel_flexible,
    score_qa,
    summarize_issues,
    summarize_supporting_report,
)

st.set_page_config(page_title="EnergyCAP Pre-Export QA", layout="wide")

st.title("EnergyCAP Pre-Export QA Correction Workbench")
st.caption("Fast v3: waits for all files, then produces actionable record-level exceptions without expanding every supporting report row.")

with st.sidebar:
    st.header("1) Upload required reports")
    file03 = st.file_uploader("Required: Report-03 — Setup / master export", type=["xlsx", "xls"], key="r03")
    file19 = st.file_uploader("Required: Report-19 — Monthly Utility Use and Cost", type=["xlsx", "xls"], key="r19")
    file13 = st.file_uploader("Required: Report-13 — Bill Analysis", type=["xlsx", "xls"], key="r13")
    file21 = st.file_uploader("Required: Report-21 — Monthly Comparison", type=["xlsx", "xls"], key="r21")
    file26 = st.file_uploader("Required: Report-26 — Use and Cost Summary", type=["xlsx", "xls"], key="r26")

    all_files = all([file03, file19, file13, file21, file26])
    st.divider()
    st.header("2) Performance settings")
    max_support_rows = st.slider("Sample rows from Reports 13/21/26", 50, 1000, 200, 50)
    max_detail_per_rule = st.slider("Max detailed exceptions per rule", 250, 5000, 1500, 250)
    st.divider()
    run_qa = st.button("Run QA", type="primary", disabled=not all_files)

if not all_files:
    st.info("The app will not analyze anything until all five files are uploaded and you click **Run QA**.")
    uploaded_count = sum(bool(x) for x in [file03, file19, file13, file21, file26])
    st.progress(uploaded_count / 5, text=f"{uploaded_count}/5 reports uploaded")
    st.stop()

if not run_qa and "issue_detail" not in st.session_state:
    st.success("All five files are uploaded. Click **Run QA** in the sidebar to start.")
    st.stop()

@st.cache_data(show_spinner=False)
def load_uploaded(file):
    sheets = read_excel_flexible(file)
    return choose_largest_sheet(sheets), list(sheets.keys())

if run_qa:
    with st.spinner("Running optimized QA..."):
        r03, sheets03 = load_uploaded(file03)
        r19, sheets19 = load_uploaded(file19)
        r13, sheets13 = load_uploaded(file13)
        r21, sheets21 = load_uploaded(file21)
        r26, sheets26 = load_uploaded(file26)

        master = build_master(r03)
        usage = build_usage(r19)
        r13_sample = summarize_supporting_report(r13, "Report-13", max_support_rows)
        r21_sample = summarize_supporting_report(r21, "Report-21", max_support_rows)
        r26_sample = summarize_supporting_report(r26, "Report-26", max_support_rows)

        issue_detail = create_record_level_issues(
            master, usage, r13_sample, r21_sample, r26_sample, max_detail_per_rule=max_detail_per_rule
        )
        issue_summary = summarize_issues(issue_detail)
        score = score_qa(issue_detail)

        st.session_state["master"] = master
        st.session_state["usage"] = usage
        st.session_state["issue_detail"] = issue_detail
        st.session_state["issue_summary"] = issue_summary
        st.session_state["score"] = score
        st.session_state["support_samples"] = {
            "Report-13": r13_sample,
            "Report-21": r21_sample,
            "Report-26": r26_sample,
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
    "Executive Summary", "Correction Register", "EnergyCAP To-Do List",
    "Master Data Review", "Usage Review", "Downloads"
])

with tab1:
    st.subheader("QA Summary")
    if issue_detail.empty:
        st.success("No issues detected by the current rules.")
    else:
        c1, c2 = st.columns([1, 1])
        with c1:
            by_cat = issue_detail.groupby("category", as_index=False).size().rename(columns={"size": "issues"})
            st.plotly_chart(px.bar(by_cat.sort_values("issues", ascending=False), x="category", y="issues", title="Issues by Category"), use_container_width=True)
        with c2:
            by_sev = issue_detail.groupby("severity", as_index=False).size().rename(columns={"size": "issues"})
            st.plotly_chart(px.pie(by_sev, names="severity", values="issues", title="Issues by Severity"), use_container_width=True)
        st.dataframe(issue_summary, use_container_width=True)

with tab2:
    st.subheader("Record-Level Correction Register")
    if issue_detail.empty:
        st.success("No record-level exceptions found.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            sev = st.multiselect("Severity", sorted(issue_detail["severity"].dropna().unique()), default=sorted(issue_detail["severity"].dropna().unique()))
        with col2:
            cat = st.multiselect("Category", sorted(issue_detail["category"].dropna().unique()), default=sorted(issue_detail["category"].dropna().unique()))
        with col3:
            source = st.multiselect("Source report", sorted(issue_detail["source_report"].dropna().unique()), default=sorted(issue_detail["source_report"].dropna().unique()))

        filtered = issue_detail[
            issue_detail["severity"].isin(sev)
            & issue_detail["category"].isin(cat)
            & issue_detail["source_report"].isin(source)
        ].copy()

        search = st.text_input("Search site, account, meter, rule, or action")
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
    if issue_detail.empty:
        st.success("No correction tasks generated.")
    else:
        todo = (
            issue_detail.groupby(["likely_energycap_area", "suggested_correction_action", "severity"], dropna=False)
            .agg(records=("issue_id", "count"), impacted_mwh=("impacted_mwh", "sum"), impacted_dth=("impacted_dth", "sum"))
            .reset_index()
            .sort_values(["severity", "records"], ascending=[True, False])
        )
        st.dataframe(todo, use_container_width=True, height=500)

with tab4:
    st.subheader("Normalized Report-03 Master Data")
    st.dataframe(master, use_container_width=True, height=500)
    completeness = pd.DataFrame({
        "field": master.columns,
        "missing_count": [master[c].isna().sum() for c in master.columns],
        "missing_pct": [master[c].isna().mean() for c in master.columns],
    }).sort_values("missing_pct", ascending=False)
    st.subheader("Master Data Completeness")
    st.dataframe(completeness, use_container_width=True)

with tab5:
    st.subheader("Normalized Report-19 Usage Data")
    st.dataframe(usage, use_container_width=True, height=500)
    if "std_unit" in usage:
        st.subheader("Usage by Standard Unit")
        st.dataframe(usage.groupby("std_unit", dropna=False, as_index=False)["usage_std"].sum(), use_container_width=True)

with tab6:
    st.subheader("Download QA Outputs")
    st.download_button("Download full correction register", issue_detail.to_csv(index=False).encode("utf-8"), "energycap_record_level_correction_register.csv", "text/csv")
    st.download_button("Download summary by rule", issue_summary.to_csv(index=False).encode("utf-8"), "energycap_qa_summary_by_rule.csv", "text/csv")
    st.download_button("Download normalized Report-03 master", master.to_csv(index=False).encode("utf-8"), "normalized_report03_master.csv", "text/csv")
    st.download_button("Download normalized Report-19 usage", usage.to_csv(index=False).encode("utf-8"), "normalized_report19_usage.csv", "text/csv")

st.caption("EnergyCAP QA App v3 Fast. Report 13/21/26 records are sampled for review to keep the app responsive.")


import pandas as pd
import plotly.express as px
import streamlit as st

from energycap_qa import (
    choose_largest_sheet,
    normalize_report03,
    normalize_support_report,
    normalize_usage_report,
    read_excel_flexible,
    build_energycap_object_register,
    summarize_register,
    site_readiness,
    readiness_score,
)

st.set_page_config(page_title="EnergyCAP Emissions Export QA", layout="wide")

st.title("EnergyCAP Emissions Export QA Workbench")
st.caption("Purpose: verify whether EnergyCAP energy-utility usage can be trusted for site-level emissions calculations.")

with st.sidebar:
    st.header("1) Upload EnergyCAP reports")
    file03 = st.file_uploader("Report-03 — Setup / hierarchy master", type=["xlsx", "xls"], key="r03")
    file19 = st.file_uploader("Report-19 — Monthly Utility Use and Cost", type=["xlsx", "xls"], key="r19")
    file13 = st.file_uploader("Report-13 — Bill Analysis", type=["xlsx", "xls"], key="r13")
    file21 = st.file_uploader("Report-21 — Monthly Comparison", type=["xlsx", "xls"], key="r21")
    file26 = st.file_uploader("Report-26 — Use and Cost Summary", type=["xlsx", "xls"], key="r26")

    all_files = all([file03, file19, file13, file21, file26])
    st.divider()
    st.header("2) QA settings")
    max_support_rows = st.slider("Sample rows from Reports 13/21/26", 50, 3000, 500, 50)
    max_objects_per_rule = st.slider("Max EnergyCAP objects per rule", 250, 10000, 3000, 250)
    recon_tolerance_pct = st.slider("Report-26 vs Report-19 tolerance %", 0.1, 10.0, 1.0, 0.1)
    run_qa = st.button("Run emissions export QA", type="primary", disabled=not all_files)

if not all_files:
    st.info("Upload all five reports. The app will not run until all files are uploaded and you click **Run emissions export QA**.")
    uploaded_count = sum(bool(x) for x in [file03, file19, file13, file21, file26])
    st.progress(uploaded_count / 5, text=f"{uploaded_count}/5 reports uploaded")
    st.stop()

if not run_qa and "register" not in st.session_state:
    st.success("All five reports are uploaded. Click **Run emissions export QA**.")
    st.stop()

@st.cache_data(show_spinner=False)
def load_uploaded(file):
    sheets = read_excel_flexible(file)
    return choose_largest_sheet(sheets), list(sheets.keys())

if run_qa:
    with st.spinner("Building EnergyCAP object register and emissions readiness assessment..."):
        r03_raw, _ = load_uploaded(file03)
        r19_raw, _ = load_uploaded(file19)
        r13_raw, _ = load_uploaded(file13)
        r21_raw, _ = load_uploaded(file21)
        r26_raw, _ = load_uploaded(file26)

        master, map03 = normalize_report03(r03_raw)
        usage, map19 = normalize_usage_report(r19_raw, "Report-19")
        r13, map13 = normalize_support_report(r13_raw, "Report-13", max_support_rows)
        r21, map21 = normalize_support_report(r21_raw, "Report-21", max_support_rows)
        r26, map26 = normalize_support_report(r26_raw, "Report-26", max_support_rows)

        register = build_energycap_object_register(
            master, usage, r13, r21, r26,
            recon_tolerance_pct=recon_tolerance_pct,
            max_objects_per_rule=max_objects_per_rule
        )
        summary = summarize_register(register)
        sites = site_readiness(master, usage, register)
        score = readiness_score(register, usage)
        mapping = pd.concat([map03, map19, map13, map21, map26], ignore_index=True)

        st.session_state["master"] = master
        st.session_state["usage"] = usage
        st.session_state["r26"] = r26
        st.session_state["register"] = register
        st.session_state["summary"] = summary
        st.session_state["sites"] = sites
        st.session_state["score"] = score
        st.session_state["mapping"] = mapping

master = st.session_state["master"]
usage = st.session_state["usage"]
r26 = st.session_state["r26"]
register = st.session_state["register"]
summary = st.session_state["summary"]
sites = st.session_state["sites"]
score = st.session_state["score"]
mapping = st.session_state["mapping"]

total_tco2e = usage["estimated_tco2e_exposure"].abs().sum() if "estimated_tco2e_exposure" in usage else 0
impacted_tco2e = register["estimated_tco2e_exposure"].abs().sum() if not register.empty else 0

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Export readiness score", f"{score}/100")
k2.metric("EnergyCAP records to review", f"{len(register):,}")
k3.metric("High severity records", f"{(register['severity'] == 'High').sum():,}" if not register.empty else "0")
k4.metric("Impacted MWh", f"{register['impacted_mwh'].sum():,.1f}" if not register.empty else "0.0")
k5.metric("Impacted Dth", f"{register['impacted_dth'].sum():,.1f}" if not register.empty else "0.0")

if score >= 90:
    st.success("Recommendation: likely ready for controlled emissions export after resolving/documenting any remaining high-priority items.")
elif score >= 75:
    st.warning("Recommendation: conditional export only. Review the EnergyCAP correction register before using the data for emissions reporting.")
else:
    st.error("Recommendation: do not export for emissions calculation until material EnergyCAP records are corrected.")

st.divider()

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Executive Readiness",
    "EnergyCAP Correction Register",
    "Site Readiness",
    "Hierarchy & Rollup Reconciliation",
    "Column Mapping",
    "Downloads",
])

with tab1:
    st.subheader("Emissions export readiness summary")
    if register.empty:
        st.success("No EnergyCAP object-level issues detected by current rules.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            by_type = register.groupby("energycap_object_type", as_index=False).agg(records=("register_id", "count"))
            st.plotly_chart(px.bar(by_type.sort_values("records", ascending=False), x="energycap_object_type", y="records", title="Records to review by EnergyCAP object type"), use_container_width=True)
        with c2:
            by_domain = register.groupby("qa_domain", as_index=False).agg(estimated_tco2e_exposure=("estimated_tco2e_exposure", "sum"))
            st.plotly_chart(px.bar(by_domain.sort_values("estimated_tco2e_exposure", ascending=False), x="qa_domain", y="estimated_tco2e_exposure", title="Estimated tCO₂e exposure by QA domain"), use_container_width=True)
        st.dataframe(summary, use_container_width=True, height=350)

    st.caption("Estimated tCO₂e exposure uses placeholder materiality factors only to prioritize QA. It is not an official emissions calculation.")

with tab2:
    st.subheader("EnergyCAP record correction register")
    st.write("This register is organized by the EnergyCAP object that needs attention — not by Excel row.")

    if register.empty:
        st.success("No EnergyCAP records to review.")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            sev = st.multiselect("Severity", sorted(register["severity"].dropna().unique()), default=sorted(register["severity"].dropna().unique()))
        with c2:
            obj = st.multiselect("EnergyCAP object type", sorted(register["energycap_object_type"].dropna().unique()), default=sorted(register["energycap_object_type"].dropna().unique()))
        with c3:
            domain = st.multiselect("QA domain", sorted(register["qa_domain"].dropna().unique()), default=sorted(register["qa_domain"].dropna().unique()))

        filtered = register[
            register["severity"].isin(sev)
            & register["energycap_object_type"].isin(obj)
            & register["qa_domain"].isin(domain)
        ].copy()

        search = st.text_input("Search site, account, meter, commodity, issue, evidence, or recommended fix")
        if search:
            mask = filtered.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
            filtered = filtered[mask]

        st.dataframe(filtered, use_container_width=True, height=650)
        st.download_button(
            "Download filtered EnergyCAP correction register",
            filtered.to_csv(index=False).encode("utf-8"),
            "energycap_object_correction_register_filtered.csv",
            "text/csv",
        )

with tab3:
    st.subheader("Site-level emissions readiness")
    st.write("This view shows whether each site appears ready for site-level emissions calculation.")
    st.dataframe(sites, use_container_width=True, height=600)

with tab4:
    st.subheader("Hierarchy and rollup reconciliation")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Report-03 master hierarchy counts**")
        st.dataframe(pd.DataFrame({
            "EnergyCAP level": ["Sites", "Accounts", "Account-Meter relationships", "Full Site-Account-Meter-Commodity relationships"],
            "Count": [
                master["site_key"].replace("", pd.NA).dropna().nunique(),
                master["account_key"].replace("", pd.NA).dropna().nunique(),
                master["account_meter_key"].replace(" | ", pd.NA).dropna().nunique(),
                master["full_rel_key"].replace(" |  |  | ", pd.NA).dropna().nunique(),
            ],
        }), use_container_width=True)
    with c2:
        st.markdown("**Report-19 usage relationship counts**")
        st.dataframe(pd.DataFrame({
            "EnergyCAP level": ["Sites with usage", "Accounts with usage", "Account-Meter relationships with usage", "Full relationships with usage", "Site/Commodity/Month facts"],
            "Count": [
                usage["site_key"].replace("", pd.NA).dropna().nunique(),
                usage["account_key"].replace("", pd.NA).dropna().nunique(),
                usage["account_meter_key"].replace(" | ", pd.NA).dropna().nunique(),
                usage["full_rel_key"].replace(" |  |  | ", pd.NA).dropna().nunique(),
                usage[["site_key", "commodity_key", "report_month"]].drop_duplicates().shape[0],
            ],
        }), use_container_width=True)

    st.markdown("**Report-19 usage by site/commodity/unit**")
    agg = usage.dropna(subset=["usage_std"]).groupby(["site_name", "commodity", "std_unit"], dropna=False)["usage_std"].sum().reset_index()
    st.dataframe(agg.sort_values("usage_std", ascending=False), use_container_width=True, height=400)

with tab5:
    st.subheader("Detected source-column mapping")
    st.write("This is diagnostic only. Missing mappings are not treated as EnergyCAP data issues unless they prevent reconciliation.")
    st.dataframe(mapping, use_container_width=True, height=600)

with tab6:
    st.subheader("Downloads")
    st.download_button("Download EnergyCAP object correction register", register.to_csv(index=False).encode("utf-8"), "energycap_object_correction_register.csv", "text/csv")
    st.download_button("Download readiness summary", summary.to_csv(index=False).encode("utf-8"), "energycap_readiness_summary.csv", "text/csv")
    st.download_button("Download site readiness", sites.to_csv(index=False).encode("utf-8"), "energycap_site_readiness.csv", "text/csv")
    st.download_button("Download normalized Report-03 master", master.to_csv(index=False).encode("utf-8"), "normalized_report03_master.csv", "text/csv")
    st.download_button("Download normalized Report-19 usage", usage.to_csv(index=False).encode("utf-8"), "normalized_report19_usage.csv", "text/csv")
    st.download_button("Download detected column mapping", mapping.to_csv(index=False).encode("utf-8"), "detected_column_mapping.csv", "text/csv")

st.caption("EnergyCAP Emissions Export QA Workbench v6. The correction register is object-based: it points to EnergyCAP records to review/fix.")

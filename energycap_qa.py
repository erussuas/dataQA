import re
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ELECTRICITY_UNITS = {
    "kwh": 0.001, "kw h": 0.001, "kilowatt-hour": 0.001,
    "kilowatt hour": 0.001, "kilowatt hours": 0.001, "mwh": 1.0,
}
GAS_UNITS = {
    "therm": 0.1, "therms": 0.1, "dth": 1.0, "dekatherm": 1.0,
    "dekatherms": 1.0, "mmbtu": 1.0, "btu": 0.000001,
    "ccf": 0.1037, "mcf": 1.037,
}


def clean_col(c: str) -> str:
    c = str(c).strip().replace("\n", " ")
    return re.sub(r"\s+", " ", c)


def normalize_key(c: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean_col(c).lower())


def read_excel_flexible(uploaded_file) -> Dict[str, pd.DataFrame]:
    xls = pd.ExcelFile(uploaded_file)
    out = {}
    for sheet in xls.sheet_names:
        try:
            df = pd.read_excel(uploaded_file, sheet_name=sheet)
            df.columns = [clean_col(c) for c in df.columns]
            df = df.dropna(how="all")
            if len(df) > 0 and len(df.columns) > 0:
                out[sheet] = df
        except Exception:
            continue
    return out


def choose_largest_sheet(sheets: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    if not sheets:
        return pd.DataFrame()
    return max(sheets.values(), key=lambda d: d.shape[0] * max(d.shape[1], 1)).copy()


def find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    if df is None or df.empty:
        return None
    normalized = {normalize_key(c): c for c in df.columns}
    for cand in candidates:
        key = normalize_key(cand)
        if key in normalized:
            return normalized[key]
    for cand in candidates:
        key = normalize_key(cand)
        for nk, original in normalized.items():
            if key and (key in nk or nk in key):
                return original
    return None


def numeric_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(
        s.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("(", "-", regex=False)
        .str.replace(")", "", regex=False),
        errors="coerce",
    )


def date_series(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def infer_commodity(row_or_value) -> str:
    text = str(row_or_value).lower()
    if any(x in text for x in ["electric", "power", "kwh", "mwh"]):
        return "Electricity"
    if any(x in text for x in ["natural gas", "gas", "therm", "dth", "mmbtu", "dekatherm"]):
        return "Natural Gas"
    return "Unknown"


def standardize_usage(value, unit, commodity):
    if pd.isna(value):
        return np.nan, None
    unit_key = str(unit).strip().lower() if unit is not None else ""
    commodity_key = str(commodity).lower()
    if "electric" in commodity_key:
        factor = ELECTRICITY_UNITS.get(unit_key)
        return (float(value) * factor, "MWh") if factor is not None else (np.nan, "MWh")
    if "gas" in commodity_key:
        factor = GAS_UNITS.get(unit_key)
        return (float(value) * factor, "Dth") if factor is not None else (np.nan, "Dth")
    if unit_key in ELECTRICITY_UNITS:
        return float(value) * ELECTRICITY_UNITS[unit_key], "MWh"
    if unit_key in GAS_UNITS:
        return float(value) * GAS_UNITS[unit_key], "Dth"
    return np.nan, None


def build_master(report03: pd.DataFrame) -> pd.DataFrame:
    df = report03.copy()
    cols = {
        "site_name": find_col(df, ["Building Name", "Site Name", "Place Name", "Site"]),
        "site_code": find_col(df, ["Building Code", "Site Code", "Place Code"]),
        "site_address": find_col(df, ["Building Address", "Site Address", "Address"]),
        "country": find_col(df, ["Building Country", "Site Country", "Country"]),
        "state": find_col(df, ["Building State", "Site State", "State", "Province"]),
        "site_status": find_col(df, ["Site Open/Closed", "Building Open/Closed", "Open/Closed", "Site Status"]),
        "site_open_date": find_col(df, ["Site Open Date", "Building Open Date", "Open Date"]),
        "site_close_date": find_col(df, ["Site Close Date", "Building Close Date", "Close Date"]),
        "account_name": find_col(df, ["Account Name"]),
        "account_number": find_col(df, ["Account Number", "Acct Number"]),
        "account_status": find_col(df, ["Account Status"]),
        "account_close_date": find_col(df, ["Account Close Date"]),
        "service_dates": find_col(df, ["Service Dates"]),
        "vendor": find_col(df, ["Vendor", "Vendor Name", "Utility"]),
        "commodity": find_col(df, ["Commodity"]),
        "meter_name": find_col(df, ["Meter Name"]),
        "meter_code": find_col(df, ["Meter Code"]),
        "meter_status": find_col(df, ["Meter Status"]),
        "meter_serial": find_col(df, ["Serial Number", "Meter Serial Number"]),
        "acct_meter_begin": find_col(df, ["Account-Meter Begin Date", "Acct-Meter Begin Date", "Account Meter Begin Date"]),
        "acct_meter_end": find_col(df, ["Account-Meter End Date", "Acct-Meter End Date", "Account Meter End Date"]),
        "primary_use": find_col(df, ["Primary Use"]),
        "floor_area": find_col(df, ["Current Floor Area", "Floor Area"]),
        "weather_station": find_col(df, ["Weather Station"]),
        "legal_entity": find_col(df, ["Legal Entity"]),
        "cost_center": find_col(df, ["Cost Center", "Cost Center Name"]),
        "gl_record": find_col(df, ["General Ledger Record", "GL Record", "GL Code"]),
    }
    out = pd.DataFrame()
    out["source_report"] = "Report-03"
    out["source_row"] = np.arange(2, len(df) + 2)
    for name, col in cols.items():
        out[name] = df[col] if col else np.nan
    for d in ["site_open_date", "site_close_date", "account_close_date", "acct_meter_begin", "acct_meter_end"]:
        out[d] = date_series(out[d])
    out["commodity"] = out["commodity"].fillna("").replace("", np.nan)
    out["commodity"] = out["commodity"].fillna(out.apply(lambda r: infer_commodity(" ".join(map(str, r.values))), axis=1))
    out["correction_key"] = out["site_name"].fillna("").astype(str) + " | " + out["account_number"].fillna("").astype(str) + " | " + out["meter_code"].fillna(out["meter_name"]).fillna("").astype(str)
    return out


def build_usage(report19: pd.DataFrame) -> pd.DataFrame:
    df = report19.copy()
    cols = {
        "site_name": find_col(df, ["Building Name", "Site Name", "Place Name", "Site"]),
        "account_number": find_col(df, ["Account Number", "Acct Number", "Account"]),
        "meter_name": find_col(df, ["Meter Name", "Meter"]),
        "meter_code": find_col(df, ["Meter Code"]),
        "commodity": find_col(df, ["Commodity"]),
        "usage": find_col(df, ["Use", "Usage", "Consumption", "Actual Use"]),
        "unit": find_col(df, ["Use Unit", "Usage Unit", "Unit", "UOM"]),
        "cost": find_col(df, ["Cost", "Total Cost", "Spend"]),
        "month": find_col(df, ["Month", "Billing Period", "Period", "Date"]),
        "service_start": find_col(df, ["Service Start", "Start Date", "Service Begin"]),
        "service_end": find_col(df, ["Service End", "End Date", "Service Through"]),
        "invoice": find_col(df, ["Invoice Number", "Invoice", "Bill Number"]),
        "vendor": find_col(df, ["Vendor", "Utility", "Vendor Name"]),
    }
    out = pd.DataFrame()
    out["source_report"] = "Report-19"
    out["source_row"] = np.arange(2, len(df) + 2)
    for name, col in cols.items():
        out[name] = df[col] if col else np.nan
    out["usage"] = numeric_series(out["usage"])
    out["cost"] = numeric_series(out["cost"])
    for d in ["month", "service_start", "service_end"]:
        out[d] = date_series(out[d])
    out["commodity"] = out["commodity"].fillna(out.apply(lambda r: infer_commodity(" ".join(map(str, r.values))), axis=1))
    std = out.apply(lambda r: standardize_usage(r["usage"], r["unit"], r["commodity"]), axis=1)
    out["usage_std"] = [x[0] for x in std]
    out["std_unit"] = [x[1] for x in std]
    out["report_month"] = out["month"].dt.to_period("M").astype(str).replace("NaT", "")
    out["correction_key"] = out["site_name"].fillna("").astype(str) + " | " + out["account_number"].fillna("").astype(str) + " | " + out["meter_code"].fillna(out["meter_name"]).fillna("").astype(str)
    return out


def build_generic_report(df: pd.DataFrame, report_name: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    site = find_col(out, ["Building Name", "Site Name", "Place Name", "Site"])
    account = find_col(out, ["Account Number", "Acct Number", "Account"])
    meter = find_col(out, ["Meter Name", "Meter", "Meter Code"])
    commodity = find_col(out, ["Commodity"])
    use = find_col(out, ["Use", "Usage", "Consumption", "Actual Use"])
    unit = find_col(out, ["Use Unit", "Usage Unit", "Unit", "UOM"])
    cost = find_col(out, ["Cost", "Total Cost", "Spend"])
    month = find_col(out, ["Month", "Billing Period", "Period", "Date"])
    normalized = pd.DataFrame({
        "source_report": report_name,
        "source_row": np.arange(2, len(out) + 2),
        "site_name": out[site] if site else np.nan,
        "account_number": out[account] if account else np.nan,
        "meter_name": out[meter] if meter else np.nan,
        "commodity": out[commodity] if commodity else np.nan,
        "usage": numeric_series(out[use]) if use else np.nan,
        "unit": out[unit] if unit else np.nan,
        "cost": numeric_series(out[cost]) if cost else np.nan,
        "month": date_series(out[month]) if month else pd.NaT,
    })
    normalized["commodity"] = normalized["commodity"].fillna(normalized.apply(lambda r: infer_commodity(" ".join(map(str, r.values))), axis=1))
    std = normalized.apply(lambda r: standardize_usage(r["usage"], r["unit"], r["commodity"]), axis=1)
    normalized["usage_std"] = [x[0] for x in std]
    normalized["std_unit"] = [x[1] for x in std]
    normalized["report_month"] = normalized["month"].dt.to_period("M").astype(str).replace("NaT", "")
    normalized["raw_record_preview"] = out.astype(str).agg(" | ".join, axis=1).str.slice(0, 600)
    return normalized


def impact_by_unit(row):
    std_unit = str(row.get("std_unit", ""))
    usage_std = row.get("usage_std", np.nan)
    if pd.isna(usage_std):
        return 0.0, 0.0
    if std_unit == "MWh":
        return float(abs(usage_std)), 0.0
    if std_unit == "Dth":
        return 0.0, float(abs(usage_std))
    return 0.0, 0.0


def make_issue(row, rule, category, severity, description, correction_area, suggested_action, impacted_mwh=0.0, impacted_dth=0.0, likely_field=""):
    return {
        "rule": rule, "category": category, "severity": severity, "description": description,
        "source_report": row.get("source_report", ""), "source_row": row.get("source_row", ""),
        "site_name": row.get("site_name", ""), "site_code": row.get("site_code", ""),
        "account_number": row.get("account_number", ""), "account_name": row.get("account_name", ""),
        "meter_name": row.get("meter_name", ""), "meter_code": row.get("meter_code", ""),
        "commodity": row.get("commodity", ""), "vendor": row.get("vendor", ""),
        "month": row.get("report_month", "") or (row.get("month", "") if pd.notna(row.get("month", pd.NaT)) else ""),
        "usage": row.get("usage", np.nan), "unit": row.get("unit", ""),
        "usage_std": row.get("usage_std", np.nan), "std_unit": row.get("std_unit", ""),
        "impacted_mwh": impacted_mwh, "impacted_dth": impacted_dth,
        "likely_energycap_area": correction_area, "likely_field_to_review": likely_field,
        "suggested_correction_action": suggested_action,
        "correction_key": row.get("correction_key", ""),
    }


def create_record_level_issues(master, usage, r13_generic, r21_generic, r26_generic):
    issues = []
    if master is not None and not master.empty:
        checks = [
            ("MISSING_SITE_NAME", "Site attribution", "High", "Report-03 row does not have a site/building name.", "Sites and Meters", "Add or correct the site/building assignment for this account/meter row.", "Building Name / Site Name", master["site_name"].isna() | master["site_name"].astype(str).str.strip().eq("")),
            ("MISSING_COUNTRY", "Emissions metadata", "High", "Site is missing country; emissions factors may not be assignable.", "Sites and Meters", "Populate country on the site/building record.", "Building Country / Country", master["country"].isna() | master["country"].astype(str).str.strip().eq("")),
            ("MISSING_COMMODITY_MASTER", "Commodity setup", "High", "Account/meter row is missing commodity.", "Accounts or Meters", "Populate or correct the commodity on the account/meter setup.", "Commodity", master["commodity"].isna() | master["commodity"].astype(str).str.strip().eq("") | master["commodity"].astype(str).str.lower().eq("unknown")),
            ("ACCOUNT_WITHOUT_METER", "Meter structure", "Medium", "Account row does not show a meter name or meter code.", "Meters", "Confirm whether the account should be linked to a meter; add/correct meter relationship if needed.", "Meter Name / Meter Code", (master["meter_name"].isna() | master["meter_name"].astype(str).str.strip().eq("")) & (master["meter_code"].isna() | master["meter_code"].astype(str).str.strip().eq(""))),
            ("MISSING_ACCOUNT_METER_BEGIN_DATE", "Account lifecycle", "Medium", "Account-meter relationship has no begin date.", "Account-Meter relationship", "Add the account-meter begin/effective date to support historical attribution.", "Account-Meter Begin Date", master["acct_meter_begin"].isna()),
        ]
        mask = master["account_status"].astype(str).str.lower().str.contains("active", na=False) & master["site_status"].astype(str).str.lower().str.contains("closed|inactive", na=False)
        checks.append(("ACTIVE_ACCOUNT_ON_CLOSED_SITE", "Account lifecycle", "High", "Account appears active while the associated site is closed/inactive.", "Accounts / Sites and Meters", "Confirm whether the account should be closed, moved to an active site, or whether the site status is wrong.", "Account Status / Site Open-Closed", mask))
        for rule, cat, sev, desc, area, action, field, mask in checks:
            for _, row in master[mask.fillna(False)].iterrows():
                issues.append(make_issue(row, rule, cat, sev, desc, area, action, 0.0, 0.0, field))
        dup_mask = master.duplicated(subset=[c for c in ["site_name", "account_number", "meter_code", "commodity"] if c in master.columns], keep=False)
        for _, row in master[dup_mask.fillna(False)].iterrows():
            issues.append(make_issue(row, "DUPLICATE_MASTER_RELATIONSHIP", "Meter structure", "Medium", "Duplicate site/account/meter/commodity relationship appears in Report-03.", "Accounts / Meters", "Review duplicate account-meter-site relationship rows and remove or correct duplicate setup if inappropriate.", 0.0, 0.0, "Site / Account / Meter relationship"))

    if usage is not None and not usage.empty:
        usage_checks = [
            ("USAGE_WITHOUT_SITE", "Site attribution", "High", "Usage row does not have a site name.", "Bill / Account / Site assignment", "Correct the account or meter site assignment so usage rolls to the correct site.", "Site Name", usage["site_name"].isna() | usage["site_name"].astype(str).str.strip().eq("")),
            ("MISSING_USAGE_VALUE", "Billing integrity", "High", "Usage row has no numeric usage value.", "Bill Entry", "Review the bill record and enter/correct the usage value.", "Use / Usage", usage["usage"].isna()),
            ("UNSTANDARDIZED_USAGE_UNIT", "Unit harmonization", "High", "Usage unit could not be converted to MWh or Dth.", "Bill Entry / Meter Setup", "Correct the usage unit or commodity so the record can be standardized.", "Use Unit / Commodity", usage["usage"].notna() & usage["usage_std"].isna()),
            ("MISSING_COMMODITY_USAGE", "Commodity setup", "High", "Usage row has missing or unknown commodity.", "Bill Entry / Account Setup", "Correct the commodity associated with the bill/account/meter.", "Commodity", usage["commodity"].isna() | usage["commodity"].astype(str).str.lower().eq("unknown")),
        ]
        for rule, cat, sev, desc, area, action, field, mask in usage_checks:
            for _, row in usage[mask.fillna(False)].iterrows():
                mwh, dth = impact_by_unit(row)
                issues.append(make_issue(row, rule, cat, sev, desc, area, action, mwh, dth, field))
        dup_subset = [c for c in ["site_name", "account_number", "meter_name", "commodity", "month", "usage", "cost"] if c in usage.columns]
        if dup_subset:
            dup_mask = usage.duplicated(subset=dup_subset, keep=False)
            for _, row in usage[dup_mask.fillna(False)].iterrows():
                mwh, dth = impact_by_unit(row)
                issues.append(make_issue(row, "POTENTIAL_DUPLICATE_USAGE_ROW", "Duplicate bills", "High", "Potential duplicate usage row based on matching site/account/meter/commodity/month/usage/cost.", "Bills / Batch Import", "Review whether this bill was imported twice, manually entered in addition to a feed, or reissued as a corrected invoice.", mwh, dth, "Invoice / Billing Period / Usage"))
        if master is not None and not master.empty:
            master_sites = set(master["site_name"].dropna().astype(str).str.strip())
            unknown_site_mask = ~usage["site_name"].fillna("").astype(str).str.strip().isin(master_sites)
            unknown_site_mask = unknown_site_mask & usage["site_name"].notna() & ~usage["site_name"].astype(str).str.strip().eq("")
            for _, row in usage[unknown_site_mask].iterrows():
                mwh, dth = impact_by_unit(row)
                issues.append(make_issue(row, "USAGE_SITE_NOT_IN_REPORT03_MASTER", "Site attribution", "High", "Usage site in Report-19 was not found in Report-03 master setup.", "Sites and Meters / Account Mapping", "Check for site naming mismatch, inactive/missing site, or account mapped to an unexpected site.", mwh, dth, "Site Name / Building Name"))
        temp = usage.dropna(subset=["month"]).copy()
        if not temp.empty:
            temp["period"] = temp["month"].dt.to_period("M")
            coverage = temp.groupby(["site_name", "commodity"], dropna=False)["period"].nunique().reset_index(name="months_present")
            for _, r in coverage[coverage["months_present"] < 12].iterrows():
                row = {"source_report": "Report-19", "source_row": "", "site_name": r.get("site_name", ""), "commodity": r.get("commodity", ""), "report_month": "", "correction_key": f"{r.get('site_name','')} |  | "}
                issues.append(make_issue(row, "INCOMPLETE_12_MONTH_COVERAGE", "Completeness", "Medium", f"Site/commodity has only {int(r['months_present'])} month(s) present in the Report-19 extract.", "Bills / Missing Bills", "Check for missing bills, late bills, closed accounts, or incorrect report date filters.", 0.0, 0.0, "Billing Period / Missing Bills"))

    # Bring in source records from exception/variance/reconciliation reports so users can act on them.
    for generic, report_name, rule, category, severity, desc, area, action, cap in [
        (r13_generic, "Report-13", "REPORT13_BILL_ANALYSIS_RECORD", "Billing integrity", "Medium", "Record appears in Report-13 Bill Analysis and should be reviewed as a bill/outlier issue.", "Bill Analysis / Bill Entry", "Open the referenced account/meter/bill in EnergyCAP and validate use, cost, demand, dates, and units.", 10000),
        (r21_generic, "Report-21", "REPORT21_MONTHLY_VARIANCE_RECORD", "Variance", "Medium", "Record appears in Report-21 Monthly Comparison and should be reviewed for abnormal variance.", "Monthly Comparison / Bill History", "Review current year vs. base year usage/cost variance and determine whether setup, missing bills, or operational changes explain it.", 10000),
        (r26_generic, "Report-26", "REPORT26_RECONCILIATION_RECORD", "Reconciliation", "Low", "Record from Report-26 available for reconciliation against Report-19 and Report-03.", "Use and Cost Summary", "Use this row to reconcile site/account/commodity totals and investigate mismatches.", 3000),
    ]:
        if generic is not None and not generic.empty:
            for _, row in generic.head(cap).iterrows():
                mwh, dth = impact_by_unit(row)
                issues.append(make_issue(row, rule, category, severity, desc, area, action, mwh, dth, "Report output row"))

    out = pd.DataFrame(issues)
    if out.empty:
        return out
    out.insert(0, "issue_number", range(1, len(out) + 1))
    out["issue_id"] = out.apply(lambda r: f"{r['rule']}-{int(r['issue_number']):06d}", axis=1)
    preferred_order = ["issue_id", "severity", "category", "rule", "description", "source_report", "source_row", "site_name", "site_code", "account_number", "account_name", "meter_name", "meter_code", "commodity", "vendor", "month", "usage", "unit", "usage_std", "std_unit", "impacted_mwh", "impacted_dth", "likely_energycap_area", "likely_field_to_review", "suggested_correction_action", "correction_key"]
    return out[[c for c in preferred_order if c in out.columns]]


def summarize_issues(issue_detail: pd.DataFrame) -> pd.DataFrame:
    if issue_detail is None or issue_detail.empty:
        return pd.DataFrame(columns=["category", "severity", "rule", "occurrences", "impacted_mwh", "impacted_dth"])
    return issue_detail.groupby(["category", "severity", "rule"], dropna=False).agg(occurrences=("issue_id", "count"), impacted_mwh=("impacted_mwh", "sum"), impacted_dth=("impacted_dth", "sum")).reset_index().sort_values(["severity", "occurrences"], ascending=[True, False])


def score_qa(issue_detail: pd.DataFrame) -> int:
    if issue_detail is None or issue_detail.empty:
        return 100
    weights = {"High": 5, "Medium": 2, "Low": 0.5}
    grouped = issue_detail.groupby("severity").size().to_dict()
    penalty = sum(np.log1p(count) * weights.get(sev, 1) * 4 for sev, count in grouped.items())
    return int(max(0, round(100 - penalty)))

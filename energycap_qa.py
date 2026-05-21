
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


ELECTRICITY_UNITS = {
    "kwh": 0.001,
    "mwh": 1.0,
    "kw h": 0.001,
    "kilowatt-hour": 0.001,
    "kilowatt hours": 0.001,
}

GAS_UNITS = {
    "therm": 0.1,
    "therms": 0.1,
    "dth": 1.0,
    "dekatherm": 1.0,
    "dekatherms": 1.0,
    "mmbtu": 1.0,
    "btu": 0.000001,
    "ccf": 0.1037,
    "mcf": 1.037,
}


def clean_col(c: str) -> str:
    c = str(c).strip().replace("\n", " ")
    c = re.sub(r"\s+", " ", c)
    return c


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
        s.astype(str).str.replace(",", "", regex=False).str.replace("$", "", regex=False),
        errors="coerce",
    )


def date_series(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def infer_commodity(row_or_value) -> str:
    text = str(row_or_value).lower()
    if any(x in text for x in ["electric", "power", "kwh", "mwh"]):
        return "Electricity"
    if any(x in text for x in ["gas", "therm", "dth", "mmbtu", "dekatherm"]):
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
        "site_name": find_col(df, ["Building Name", "Site Name", "Place Name"]),
        "site_code": find_col(df, ["Building Code", "Site Code", "Place Code"]),
        "site_address": find_col(df, ["Building Address", "Address"]),
        "country": find_col(df, ["Building Country", "Country"]),
        "site_status": find_col(df, ["Site Open/Closed", "Building Open/Closed", "Open/Closed"]),
        "site_open_date": find_col(df, ["Site Open Date", "Building Open Date", "Open Date"]),
        "site_close_date": find_col(df, ["Site Close Date", "Building Close Date", "Close Date"]),
        "account_name": find_col(df, ["Account Name"]),
        "account_number": find_col(df, ["Account Number", "Acct Number"]),
        "account_status": find_col(df, ["Account Status", "Status"]),
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
    }

    out = pd.DataFrame()
    for name, col in cols.items():
        out[name] = df[col] if col else np.nan

    for d in ["site_open_date", "site_close_date", "account_close_date", "acct_meter_begin", "acct_meter_end"]:
        out[d] = date_series(out[d])

    out["commodity"] = out["commodity"].fillna("").replace("", np.nan)
    out["commodity"] = out["commodity"].fillna(out.apply(lambda r: infer_commodity(" ".join(map(str, r.values))), axis=1))

    return out


def build_usage(report19: pd.DataFrame) -> pd.DataFrame:
    df = report19.copy()
    cols = {
        "site_name": find_col(df, ["Building Name", "Site Name", "Place Name", "Site"]),
        "account_number": find_col(df, ["Account Number", "Acct Number", "Account"]),
        "meter_name": find_col(df, ["Meter Name", "Meter"]),
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
    return out


def qa_from_reports(master: pd.DataFrame, usage: pd.DataFrame, report13=None, report21=None, report26=None) -> pd.DataFrame:
    issues = []

    def add(rule, category, severity, description, records, mwh=np.nan, dth=np.nan):
        issues.append({
            "rule": rule,
            "category": category,
            "severity": severity,
            "description": description,
            "occurrences": int(records) if pd.notna(records) else 0,
            "impacted_mwh": float(mwh) if pd.notna(mwh) else 0.0,
            "impacted_dth": float(dth) if pd.notna(dth) else 0.0,
        })

    if master is not None and not master.empty:
        add("MISSING_SITE_NAME", "Site attribution", "High", "Rows in Report-03 without a site/building name.", master["site_name"].isna().sum())
        add("MISSING_COUNTRY", "Emissions metadata", "High", "Sites missing country, which may block emissions factor assignment.", master["country"].isna().sum())
        add("MISSING_COMMODITY_MASTER", "Commodity setup", "Medium", "Account/meter rows missing commodity in Report-03.", master["commodity"].isna().sum())
        active_acct_closed_site = master[
            master["account_status"].astype(str).str.lower().str.contains("active", na=False)
            & master["site_status"].astype(str).str.lower().str.contains("closed|inactive", na=False)
        ]
        add("ACTIVE_ACCOUNT_ON_CLOSED_SITE", "Account lifecycle", "High", "Active accounts associated with closed/inactive sites.", len(active_acct_closed_site))

        no_meter = master["meter_name"].isna() & master["meter_code"].isna()
        add("ACCOUNT_WITHOUT_METER", "Meter structure", "Medium", "Account rows without meter name/code.", no_meter.sum())

        dup_meters = master.dropna(subset=["meter_code"]).duplicated(subset=["site_name", "account_number", "meter_code", "commodity"], keep=False)
        add("DUPLICATE_MASTER_RELATIONSHIP", "Meter structure", "Medium", "Duplicate site/account/meter/commodity relationship rows in Report-03.", dup_meters.sum())

        missing_dates = master["acct_meter_begin"].isna()
        add("MISSING_ACCOUNT_METER_BEGIN_DATE", "Account lifecycle", "Medium", "Account-meter relationship rows missing begin date.", missing_dates.sum())

    if usage is not None and not usage.empty:
        mwh_total = usage.loc[usage["std_unit"].eq("MWh"), "usage_std"].sum(skipna=True)
        dth_total = usage.loc[usage["std_unit"].eq("Dth"), "usage_std"].sum(skipna=True)

        missing_std = usage["usage"].notna() & usage["usage_std"].isna()
        add("UNSTANDARDIZED_USAGE_UNIT", "Unit harmonization", "High", "Usage rows that could not be converted to MWh or Dth.", missing_std.sum())

        missing_site_usage = usage["site_name"].isna().sum()
        add("USAGE_WITHOUT_SITE", "Site attribution", "High", "Usage rows missing site name in Report-19.", missing_site_usage)

        dup_cols = [c for c in ["site_name", "account_number", "meter_name", "commodity", "month", "usage", "cost"] if c in usage.columns]
        if dup_cols:
            dup_rows = usage.duplicated(subset=dup_cols, keep=False)
            add("POTENTIAL_DUPLICATE_USAGE_ROWS", "Duplicate bills", "High", "Potential duplicate usage rows in Report-19.", dup_rows.sum(),
                usage.loc[dup_rows & usage["std_unit"].eq("MWh"), "usage_std"].sum(skipna=True),
                usage.loc[dup_rows & usage["std_unit"].eq("Dth"), "usage_std"].sum(skipna=True))

        if "month" in usage.columns:
            monthly = usage.dropna(subset=["month"]).copy()
            monthly["report_month"] = monthly["month"].dt.to_period("M").astype(str)
            key = ["site_name", "commodity"]
            counts = monthly.groupby(key)["report_month"].nunique().reset_index(name="months_present")
            incomplete = counts[counts["months_present"] < 12] if not counts.empty else counts
            add("INCOMPLETE_12_MONTH_COVERAGE", "Completeness", "Medium", "Site/commodity combinations with fewer than 12 months present.", len(incomplete))

        if master is not None and not master.empty and "site_name" in usage.columns:
            master_sites = set(master["site_name"].dropna().astype(str))
            usage_unknown = usage[~usage["site_name"].astype(str).isin(master_sites)]
            add("USAGE_SITE_NOT_IN_MASTER", "Site attribution", "High", "Report-19 usage site not found in Report-03 master.", len(usage_unknown),
                usage_unknown.loc[usage_unknown["std_unit"].eq("MWh"), "usage_std"].sum(skipna=True),
                usage_unknown.loc[usage_unknown["std_unit"].eq("Dth"), "usage_std"].sum(skipna=True))

    if report13 is not None and not report13.empty:
        add("REPORT13_OUTLIER_ROWS", "Billing integrity", "Medium", "Rows present in Report-13 bill analysis/outlier report.", len(report13))

    if report21 is not None and not report21.empty:
        add("REPORT21_VARIANCE_ROWS", "Variance", "Medium", "Rows present in Report-21 monthly comparison report for variance review.", len(report21))

    if report26 is not None and not report26.empty:
        add("REPORT26_RECON_ROWS", "Reconciliation", "Low", "Rows present in Report-26 use and cost summary for reconciliation.", len(report26))

    return pd.DataFrame(issues)


def score_qa(issues: pd.DataFrame) -> int:
    if issues is None or issues.empty:
        return 100
    weights = {"High": 5, "Medium": 2, "Low": 1}
    penalty = 0
    for _, r in issues.iterrows():
        penalty += min(25, np.log1p(r["occurrences"]) * weights.get(r["severity"], 1))
    return int(max(0, round(100 - penalty)))

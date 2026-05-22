
import re
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


# -----------------------------
# Constants
# -----------------------------

ELECTRICITY_UNITS = {
    "kwh": 0.001,
    "kw h": 0.001,
    "kilowatt-hour": 0.001,
    "kilowatt hour": 0.001,
    "kilowatt hours": 0.001,
    "mwh": 1.0,
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

# Placeholder factors for QA materiality only. Not official emissions calculations.
DEFAULT_ELECTRICITY_TCO2E_PER_MWH = 0.40
DEFAULT_GAS_TCO2E_PER_DTH = 0.0053


# -----------------------------
# Utility helpers
# -----------------------------

def clean_col(c: str) -> str:
    c = str(c).strip().replace("\n", " ")
    return re.sub(r"\s+", " ", c)


def normalize_key(c: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean_col(c).lower())


def norm_text_value(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    s = re.sub(r"\s+", " ", s)
    if s.lower() in {"nan", "none", "nat"}:
        return ""
    return s


def norm_key_value(x) -> str:
    return norm_text_value(x).lower()


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


def numeric_series(s, index=None) -> pd.Series:
    if isinstance(s, pd.Series):
        raw = s
    else:
        raw = pd.Series(s, index=index)

    return pd.to_numeric(
        raw.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("(", "-", regex=False)
        .str.replace(")", "", regex=False)
        .str.replace("%", "", regex=False),
        errors="coerce",
    )


def date_series(s, index=None) -> pd.Series:
    if isinstance(s, pd.Series):
        return pd.to_datetime(s, errors="coerce")
    return pd.Series(pd.NaT, index=index)


def text_series(df, col):
    if col and col in df.columns:
        return df[col].map(norm_text_value).astype("object")
    return pd.Series("", index=df.index, dtype="object")


def infer_commodity(value) -> str:
    text = str(value).lower()
    if any(x in text for x in ["electric", "power", "kwh", "mwh"]):
        return "Electricity"
    if any(x in text for x in ["natural gas", "gas", "therm", "dth", "mmbtu", "dekatherm"]):
        return "Natural Gas"
    return ""


def standardize_usage_vectorized(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in ["unit", "commodity"]:
        if c not in out.columns:
            out[c] = ""
    if "usage" not in out.columns:
        out["usage"] = np.nan

    unit = out["unit"].fillna("").astype(str).str.strip().str.lower()
    commodity = out["commodity"].fillna("").astype(str).str.lower()

    out["usage_std"] = np.nan
    out["std_unit"] = pd.Series("", index=out.index, dtype="object")

    elec_factor = unit.map(ELECTRICITY_UNITS)
    gas_factor = unit.map(GAS_UNITS)

    elec_mask = commodity.str.contains("electric", na=False) | elec_factor.notna()
    gas_mask = (commodity.str.contains("gas", na=False) | gas_factor.notna()) & ~elec_mask

    out.loc[elec_mask, "usage_std"] = (
        out.loc[elec_mask, "usage"].astype(float) * elec_factor.loc[elec_mask].astype(float)
    )
    out.loc[elec_mask, "std_unit"] = "MWh"

    out.loc[gas_mask, "usage_std"] = (
        out.loc[gas_mask, "usage"].astype(float) * gas_factor.loc[gas_mask].astype(float)
    )
    out.loc[gas_mask, "std_unit"] = "Dth"

    out["estimated_tco2e_exposure"] = 0.0
    out.loc[out["std_unit"].eq("MWh"), "estimated_tco2e_exposure"] = (
        out.loc[out["std_unit"].eq("MWh"), "usage_std"].abs() * DEFAULT_ELECTRICITY_TCO2E_PER_MWH
    )
    out.loc[out["std_unit"].eq("Dth"), "estimated_tco2e_exposure"] = (
        out.loc[out["std_unit"].eq("Dth"), "usage_std"].abs() * DEFAULT_GAS_TCO2E_PER_DTH
    )

    return out


def make_rel_keys(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in ["site_name", "account_number", "meter_code", "meter_name", "commodity"]:
        if c not in out.columns:
            out[c] = ""

    meter_part = out["meter_code"].where(out["meter_code"].astype(str).str.strip().ne(""), out["meter_name"])

    out["site_key"] = out["site_name"].map(norm_key_value)
    out["account_key"] = out["account_number"].map(norm_key_value)
    out["meter_key"] = meter_part.map(norm_key_value)
    out["commodity_key"] = out["commodity"].map(norm_key_value)

    out["site_account_key"] = out["site_key"] + " | " + out["account_key"]
    out["account_meter_key"] = out["account_key"] + " | " + out["meter_key"]
    out["full_rel_key"] = (
        out["site_key"] + " | " + out["account_key"] + " | " + out["meter_key"] + " | " + out["commodity_key"]
    )
    out["site_commodity_key"] = out["site_key"] + " | " + out["commodity_key"]

    return out


# -----------------------------
# Column detection
# -----------------------------

def detect_columns_report03(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    return {
        "site_name": find_col(df, ["Building Name", "Site Name", "Place Name", "Site", "Building"]),
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
        "vendor": find_col(df, ["Vendor", "Vendor Name", "Utility"]),
        "commodity": find_col(df, ["Commodity"]),
        "meter_name": find_col(df, ["Meter Name"]),
        "meter_code": find_col(df, ["Meter Code"]),
        "meter_status": find_col(df, ["Meter Status"]),
        "acct_meter_begin": find_col(df, ["Account-Meter Begin Date", "Acct-Meter Begin Date", "Account Meter Begin Date"]),
        "acct_meter_end": find_col(df, ["Account-Meter End Date", "Acct-Meter End Date", "Account Meter End Date"]),
    }


def detect_columns_usage(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    return {
        "site_name": find_col(df, ["Building Name", "Site Name", "Place Name", "Site", "Building"]),
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


# -----------------------------
# Normalizers
# -----------------------------

def normalize_report03(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    cols = detect_columns_report03(df)
    out = pd.DataFrame(index=df.index)
    out["source_report"] = "Report-03"
    out["source_row"] = np.arange(2, len(df) + 2)

    text_cols = [
        "site_name", "site_code", "site_address", "country", "state", "site_status",
        "account_name", "account_number", "account_status", "vendor", "commodity",
        "meter_name", "meter_code", "meter_status",
    ]

    for c in text_cols:
        out[c] = text_series(df, cols.get(c))

    for c in ["site_open_date", "site_close_date", "account_close_date", "acct_meter_begin", "acct_meter_end"]:
        out[c] = date_series(df[cols[c]], df.index) if cols.get(c) else pd.Series(pd.NaT, index=df.index)

    missing_comm = out["commodity"].str.strip().eq("")
    if missing_comm.any():
        combined = out["account_name"] + " " + out["meter_name"] + " " + out["vendor"]
        out.loc[missing_comm, "commodity"] = combined.loc[missing_comm].map(infer_commodity).astype("object").values

    out = make_rel_keys(out)

    out["site_record"] = np.where(
        out["site_code"].ne(""),
        out["site_name"] + " [" + out["site_code"] + "]",
        out["site_name"],
    )
    out["account_record"] = np.where(
        out["account_name"].ne(""),
        out["account_name"] + " / " + out["account_number"],
        out["account_number"],
    )
    meter_display = out["meter_code"].where(out["meter_code"].ne(""), out["meter_name"])
    out["meter_record"] = meter_display
    out["account_meter_record"] = out["account_record"] + " → " + out["meter_record"]
    out["hierarchy_record"] = (
        out["site_record"] + " → " + out["account_record"] + " → " + out["meter_record"] + " → " + out["commodity"]
    )

    mapping = pd.DataFrame({
        "source_report": "Report-03",
        "normalized_field": list(cols.keys()),
        "detected_source_column": [cols[k] or "" for k in cols],
        "mapping_use": ["reconciliation key / EnergyCAP object identity"] * len(cols),
    })

    return out.reset_index(drop=True), mapping


def normalize_usage_report(df: pd.DataFrame, report_name: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    cols = detect_columns_usage(df)
    out = pd.DataFrame(index=df.index)
    out["source_report"] = report_name
    out["source_row"] = np.arange(2, len(df) + 2)

    for c in ["site_name", "account_number", "meter_name", "meter_code", "commodity", "unit", "invoice", "vendor"]:
        out[c] = text_series(df, cols.get(c))

    out["usage"] = numeric_series(df[cols["usage"]], df.index) if cols.get("usage") else pd.Series(np.nan, index=df.index)
    out["cost"] = numeric_series(df[cols["cost"]], df.index) if cols.get("cost") else pd.Series(np.nan, index=df.index)

    for c in ["month", "service_start", "service_end"]:
        out[c] = date_series(df[cols[c]], df.index) if cols.get(c) else pd.Series(pd.NaT, index=df.index)

    missing_comm = out["commodity"].str.strip().eq("")
    if missing_comm.any():
        combined = out["site_name"] + " " + out["account_number"] + " " + out["meter_name"] + " " + out["unit"]
        out.loc[missing_comm, "commodity"] = combined.loc[missing_comm].map(infer_commodity).astype("object").values

    out = standardize_usage_vectorized(out)
    out["report_month"] = out["month"].dt.to_period("M").astype(str).replace("NaT", "")
    out = make_rel_keys(out)

    out["site_record"] = out["site_name"]
    out["account_record"] = out["account_number"]
    meter_display = out["meter_code"].where(out["meter_code"].ne(""), out["meter_name"])
    out["meter_record"] = meter_display
    out["account_meter_record"] = out["account_record"] + " → " + out["meter_record"]
    out["bill_usage_record"] = (
        "Account " + out["account_number"] + " | Meter " + out["meter_record"] + " | "
        + out["commodity"] + " | " + out["report_month"] + " | Invoice " + out["invoice"]
    )

    mapping = pd.DataFrame({
        "source_report": report_name,
        "normalized_field": list(cols.keys()),
        "detected_source_column": [cols[k] or "" for k in cols],
        "mapping_use": ["usage fact / emissions export reconciliation"] * len(cols),
    })

    return out.reset_index(drop=True), mapping


def normalize_support_report(df: pd.DataFrame, report_name: str, max_rows: int = 1000) -> Tuple[pd.DataFrame, pd.DataFrame]:
    sample = df.head(max_rows).copy()
    normalized, mapping = normalize_usage_report(sample, report_name)
    normalized["source_total_rows"] = len(df)
    return normalized, mapping


# -----------------------------
# Register builders
# -----------------------------

def materiality_from_rows(rows: pd.DataFrame) -> Tuple[float, float, float]:
    if rows is None or rows.empty or "usage_std" not in rows:
        return 0.0, 0.0, 0.0

    mwh = rows.loc[rows["std_unit"].eq("MWh"), "usage_std"].abs().sum(skipna=True)
    dth = rows.loc[rows["std_unit"].eq("Dth"), "usage_std"].abs().sum(skipna=True)

    if "estimated_tco2e_exposure" in rows.columns:
        tco2e = rows["estimated_tco2e_exposure"].abs().sum(skipna=True)
    else:
        tco2e = 0.0

    return float(mwh), float(dth), float(tco2e)


def month_span(series: pd.Series) -> str:
    vals = sorted([v for v in series.dropna().astype(str).unique() if v and v != "NaT"])
    if not vals:
        return ""
    if len(vals) <= 6:
        return ", ".join(vals)
    return f"{vals[0]} to {vals[-1]} ({len(vals)} months/records)"


def add_object_issue(
    issues: list,
    *,
    energycap_object_type: str,
    energycap_record: str,
    severity: str,
    qa_domain: str,
    issue: str,
    why_it_matters: str,
    source_reports: str,
    site_name: str = "",
    account_number: str = "",
    meter_name: str = "",
    meter_code: str = "",
    commodity: str = "",
    months_impacted: str = "",
    impacted_mwh: float = 0.0,
    impacted_dth: float = 0.0,
    estimated_tco2e_exposure: float = 0.0,
    recommended_energycap_fix: str = "",
    evidence: str = "",
):
    issues.append({
        "energycap_object_type": energycap_object_type,
        "energycap_record_to_review": energycap_record,
        "severity": severity,
        "qa_domain": qa_domain,
        "issue": issue,
        "why_it_matters_for_emissions_export": why_it_matters,
        "source_reports": source_reports,
        "site_name": site_name,
        "account_number": account_number,
        "meter_name": meter_name,
        "meter_code": meter_code,
        "commodity": commodity,
        "months_impacted": months_impacted,
        "impacted_mwh": impacted_mwh,
        "impacted_dth": impacted_dth,
        "estimated_tco2e_exposure": estimated_tco2e_exposure,
        "recommended_energycap_fix": recommended_energycap_fix,
        "evidence": evidence,
    })


def build_energycap_object_register(
    master: pd.DataFrame,
    usage: pd.DataFrame,
    r13: pd.DataFrame,
    r21: pd.DataFrame,
    r26: pd.DataFrame,
    recon_tolerance_pct: float = 1.0,
    max_objects_per_rule: int = 3000,
) -> pd.DataFrame:
    issues = []

    master_sites = set(master.loc[master["site_key"].ne(""), "site_key"])
    master_accounts = set(master.loc[master["account_key"].ne(""), "account_key"])
    master_account_meter = set(master.loc[(master["account_key"].ne("")) & (master["meter_key"].ne("")), "account_meter_key"])
    master_full = set(master.loc[master["full_rel_key"].str.replace(" | ", "", regex=False).str.strip().ne(""), "full_rel_key"])
    master_site_comm = set(master.loc[(master["site_key"].ne("")) & (master["commodity_key"].ne("")), "site_commodity_key"])

    # Site in usage but not master.
    mask = usage["site_key"].ne("") & ~usage["site_key"].isin(master_sites)
    for (site_key, site_name), rows in list(usage[mask].groupby(["site_key", "site_name"], dropna=False))[:max_objects_per_rule]:
        mwh, dth, tco2e = materiality_from_rows(rows)
        add_object_issue(
            issues,
            energycap_object_type="Site",
            energycap_record=site_name or site_key,
            severity="High",
            qa_domain="Hierarchy reconciliation",
            issue="Usage exists for a site that is not present in the Report-03 EnergyCAP master hierarchy.",
            why_it_matters="Usage may be excluded from site-level emissions, mapped to an unintended site, or fail downstream site matching.",
            source_reports="Report-19 vs Report-03",
            site_name=site_name,
            months_impacted=month_span(rows["report_month"]),
            impacted_mwh=mwh,
            impacted_dth=dth,
            estimated_tco2e_exposure=tco2e,
            recommended_energycap_fix="Review the EnergyCAP site/building record and Report-03 export scope. Correct site naming, topmost filters, or site assignment.",
            evidence=f"site_key={site_key}; usage_rows={len(rows)}",
        )

    # Account in usage but not master.
    mask = usage["account_key"].ne("") & ~usage["account_key"].isin(master_accounts)
    for (account_key, account_number), rows in list(usage[mask].groupby(["account_key", "account_number"], dropna=False))[:max_objects_per_rule]:
        mwh, dth, tco2e = materiality_from_rows(rows)
        add_object_issue(
            issues,
            energycap_object_type="Account",
            energycap_record=account_number or account_key,
            severity="High",
            qa_domain="Hierarchy reconciliation",
            issue="Usage exists for an account that is not present in Report-03 master setup.",
            why_it_matters="The emissions export may include consumption that cannot be tied back to a governed account/site/meter structure.",
            source_reports="Report-19 vs Report-03",
            site_name=", ".join(rows["site_name"].dropna().astype(str).unique()[:3]),
            account_number=account_number,
            commodity=", ".join(rows["commodity"].dropna().astype(str).unique()[:3]),
            months_impacted=month_span(rows["report_month"]),
            impacted_mwh=mwh,
            impacted_dth=dth,
            estimated_tco2e_exposure=tco2e,
            recommended_energycap_fix="Confirm the account exists, is in scope, and is linked to the correct site/meter in EnergyCAP. Confirm Report-03 and Report-19 used the same topmost/date/filter scope.",
            evidence=f"account_key={account_key}; usage_rows={len(rows)}",
        )

    # Account-meter relation in usage but not master.
    mask = usage["account_key"].ne("") & usage["meter_key"].ne("") & ~usage["account_meter_key"].isin(master_account_meter)
    grouped = usage[mask].groupby(["account_meter_key", "account_number", "meter_name", "meter_code"], dropna=False)
    for (am_key, acct, meter_name, meter_code), rows in list(grouped)[:max_objects_per_rule]:
        mwh, dth, tco2e = materiality_from_rows(rows)
        add_object_issue(
            issues,
            energycap_object_type="Account-Meter relationship",
            energycap_record=f"{acct} → {meter_code or meter_name}",
            severity="High",
            qa_domain="Hierarchy reconciliation",
            issue="Report-19 usage is tied to an account-meter relationship that is not present in Report-03.",
            why_it_matters="Usage may be attached to the wrong meter, missing effective dates, or misattributed in site-level emissions.",
            source_reports="Report-19 vs Report-03",
            site_name=", ".join(rows["site_name"].dropna().astype(str).unique()[:3]),
            account_number=acct,
            meter_name=meter_name,
            meter_code=meter_code,
            commodity=", ".join(rows["commodity"].dropna().astype(str).unique()[:3]),
            months_impacted=month_span(rows["report_month"]),
            impacted_mwh=mwh,
            impacted_dth=dth,
            estimated_tco2e_exposure=tco2e,
            recommended_energycap_fix="Review account-meter relationship, meter code/name, and effective dates in EnergyCAP.",
            evidence=f"account_meter_key={am_key}; usage_rows={len(rows)}",
        )

    # Full hierarchy relation mismatch.
    mask = (
        usage["full_rel_key"].str.replace(" | ", "", regex=False).str.strip().ne("")
        & ~usage["full_rel_key"].isin(master_full)
    )
    grouped = usage[mask].groupby(["full_rel_key", "site_name", "account_number", "meter_name", "meter_code", "commodity"], dropna=False)
    for (full_key, site, acct, meter_name, meter_code, commodity), rows in list(grouped)[:max_objects_per_rule]:
        mwh, dth, tco2e = materiality_from_rows(rows)
        add_object_issue(
            issues,
            energycap_object_type="Site-Account-Meter-Commodity relationship",
            energycap_record=f"{site} → {acct} → {meter_code or meter_name} → {commodity}",
            severity="Medium",
            qa_domain="Hierarchy reconciliation",
            issue="The full usage relationship does not match the Report-03 master relationship.",
            why_it_matters="Even if the account/meter exists, commodity or site mapping may be inconsistent, affecting site-level emissions attribution.",
            source_reports="Report-19 vs Report-03",
            site_name=site,
            account_number=acct,
            meter_name=meter_name,
            meter_code=meter_code,
            commodity=commodity,
            months_impacted=month_span(rows["report_month"]),
            impacted_mwh=mwh,
            impacted_dth=dth,
            estimated_tco2e_exposure=tco2e,
            recommended_energycap_fix="Review the site, account, meter, and commodity combination in EnergyCAP. Confirm commodity assignment and site rollup.",
            evidence=f"full_rel_key={full_key}; usage_rows={len(rows)}",
        )

    # Site-commodity relation in usage but not master.
    mask = (
        usage["site_commodity_key"].str.replace(" | ", "", regex=False).str.strip().ne("")
        & ~usage["site_commodity_key"].isin(master_site_comm)
    )
    grouped = usage[mask].groupby(["site_commodity_key", "site_name", "commodity"], dropna=False)
    for (sc_key, site, commodity), rows in list(grouped)[:max_objects_per_rule]:
        mwh, dth, tco2e = materiality_from_rows(rows)
        add_object_issue(
            issues,
            energycap_object_type="Site-Commodity relationship",
            energycap_record=f"{site} → {commodity}",
            severity="Medium",
            qa_domain="Commodity reconciliation",
            issue="Usage exists for a site/commodity combination not configured in the master hierarchy.",
            why_it_matters="The emissions tool may not know how to classify or factor the commodity for that site.",
            source_reports="Report-19 vs Report-03",
            site_name=site,
            commodity=commodity,
            months_impacted=month_span(rows["report_month"]),
            impacted_mwh=mwh,
            impacted_dth=dth,
            estimated_tco2e_exposure=tco2e,
            recommended_energycap_fix="Check commodity assigned to account/meter and whether the site should have this commodity in scope.",
            evidence=f"site_commodity_key={sc_key}; usage_rows={len(rows)}",
        )

    # Active master accounts with no usage.
    active_mask = ~master["account_status"].str.lower().str.contains("inactive|closed", na=False)
    candidates = master[active_mask & master["account_key"].ne("")]
    usage_accounts = set(usage.loc[usage["account_key"].ne(""), "account_key"])
    missing_usage = candidates[~candidates["account_key"].isin(usage_accounts)]
    for (account_key, account_record), rows in list(missing_usage.groupby(["account_key", "account_record"], dropna=False))[:max_objects_per_rule]:
        r = rows.iloc[0]
        add_object_issue(
            issues,
            energycap_object_type="Account",
            energycap_record=account_record or account_key,
            severity="Medium",
            qa_domain="Usage completeness",
            issue="Active account in Report-03 has no corresponding usage in Report-19.",
            why_it_matters="An active account without usage may indicate missing bills or export filters excluding consumption from emissions.",
            source_reports="Report-03 vs Report-19",
            site_name=r.get("site_name", ""),
            account_number=r.get("account_number", ""),
            meter_name=r.get("meter_name", ""),
            meter_code=r.get("meter_code", ""),
            commodity=r.get("commodity", ""),
            recommended_energycap_fix="Check missing bills, account close status, report date range, and Report-19 filters.",
            evidence=f"account_key={account_key}; master_rows={len(rows)}",
        )

    # Missing geography for used sites.
    usage_site_keys = set(usage.loc[usage["site_key"].ne(""), "site_key"])
    used_sites = master[master["site_key"].isin(usage_site_keys)]
    missing_geo = used_sites[(used_sites["country"].str.strip().eq("")) | (used_sites["site_name"].str.strip().eq(""))]
    for (site_key, site_record), rows in list(missing_geo.groupby(["site_key", "site_record"], dropna=False))[:max_objects_per_rule]:
        related_usage = usage[usage["site_key"].eq(site_key)]
        mwh, dth, tco2e = materiality_from_rows(related_usage)
        r = rows.iloc[0]
        add_object_issue(
            issues,
            energycap_object_type="Site",
            energycap_record=site_record or site_key,
            severity="High",
            qa_domain="Emissions readiness",
            issue="Site with energy usage is missing required geography/name metadata.",
            why_it_matters="Location-based emissions factors require geography; missing site identity/geography can prevent correct emissions calculation.",
            source_reports="Report-03 + Report-19",
            site_name=r.get("site_name", ""),
            commodity=", ".join(related_usage["commodity"].dropna().astype(str).unique()[:3]),
            months_impacted=month_span(related_usage["report_month"]),
            impacted_mwh=mwh,
            impacted_dth=dth,
            estimated_tco2e_exposure=tco2e,
            recommended_energycap_fix="Populate site/building name and country/state/province in EnergyCAP.",
            evidence=f"site_key={site_key}; country='{r.get('country','')}'",
        )

    # Unconvertible units.
    mask = usage["usage"].notna() & (usage["usage_std"].isna() | usage["std_unit"].str.strip().eq(""))
    grouped = usage[mask].groupby(["account_key", "meter_key", "commodity", "unit"], dropna=False)
    for (acct_key, meter_key, commodity, unit), rows in list(grouped)[:max_objects_per_rule]:
        r = rows.iloc[0]
        add_object_issue(
            issues,
            energycap_object_type="Bill / Usage record",
            energycap_record=f"Account {r.get('account_number','')} | Meter {r.get('meter_code') or r.get('meter_name','')} | {commodity} | unit {unit}",
            severity="High",
            qa_domain="Emissions readiness",
            issue="Usage exists but cannot be converted to harmonized emissions units.",
            why_it_matters="The downstream emissions tool needs harmonized MWh for electricity and Dth for natural gas.",
            source_reports="Report-19",
            site_name=", ".join(rows["site_name"].dropna().astype(str).unique()[:3]),
            account_number=r.get("account_number", ""),
            meter_name=r.get("meter_name", ""),
            meter_code=r.get("meter_code", ""),
            commodity=commodity,
            months_impacted=month_span(rows["report_month"]),
            recommended_energycap_fix="Correct the commodity and usage unit on the meter/bill setup or add required conversion logic.",
            evidence=f"unit={unit}; commodity={commodity}; usage_rows={len(rows)}",
        )

    # Missing monthly coverage.
    u_month = usage[usage["report_month"].ne("") & usage["site_key"].ne("") & usage["commodity_key"].ne("")]
    if not u_month.empty:
        all_months = sorted(u_month["report_month"].unique())
        expected_n = len(all_months)
        if expected_n > 1:
            coverage = (
                u_month.groupby(["site_key", "site_name", "commodity_key", "commodity"], dropna=False)
                .agg(months_present=("report_month", "nunique"))
                .reset_index()
            )
            incomplete = coverage[coverage["months_present"] < expected_n]
            for _, r in incomplete.head(max_objects_per_rule).iterrows():
                related = u_month[(u_month["site_key"].eq(r["site_key"])) & (u_month["commodity_key"].eq(r["commodity_key"]))]
                mwh, dth, tco2e = materiality_from_rows(related)
                add_object_issue(
                    issues,
                    energycap_object_type="Site-Commodity monthly coverage",
                    energycap_record=f"{r['site_name']} → {r['commodity']}",
                    severity="Medium",
                    qa_domain="Usage completeness",
                    issue=f"Site/commodity has {int(r['months_present'])} of {expected_n} months in Report-19.",
                    why_it_matters="Missing months may understate annual site-level emissions.",
                    source_reports="Report-19",
                    site_name=r["site_name"],
                    commodity=r["commodity"],
                    months_impacted=f"{int(r['months_present'])}/{expected_n} months present",
                    impacted_mwh=mwh,
                    impacted_dth=dth,
                    estimated_tco2e_exposure=tco2e,
                    recommended_energycap_fix="Check missing bills, late invoices, account open/close status, and report date filters.",
                    evidence=f"Expected months in extract={expected_n}; present={int(r['months_present'])}",
                )

    # Duplicate usage facts.
    dup_cols = ["site_key", "account_key", "meter_key", "commodity_key", "report_month", "usage", "unit"]
    dup = usage.duplicated(subset=dup_cols, keep=False)
    grouped = usage[dup].groupby(dup_cols, dropna=False)
    for _, rows in list(grouped)[:max_objects_per_rule]:
        r = rows.iloc[0]
        mwh, dth, tco2e = materiality_from_rows(rows)
        add_object_issue(
            issues,
            energycap_object_type="Bill / Usage record",
            energycap_record=f"Account {r.get('account_number','')} | Meter {r.get('meter_code') or r.get('meter_name','')} | {r.get('commodity','')} | {r.get('report_month','')}",
            severity="High",
            qa_domain="Usage completeness",
            issue="Potential duplicate usage fact at the same site/account/meter/commodity/month/usage/unit grain.",
            why_it_matters="Duplicate usage will overstate site-level emissions.",
            source_reports="Report-19",
            site_name=r.get("site_name", ""),
            account_number=r.get("account_number", ""),
            meter_name=r.get("meter_name", ""),
            meter_code=r.get("meter_code", ""),
            commodity=r.get("commodity", ""),
            months_impacted=r.get("report_month", ""),
            impacted_mwh=mwh,
            impacted_dth=dth,
            estimated_tco2e_exposure=tco2e,
            recommended_energycap_fix="Review bill history and import batches for duplicate or corrected invoices.",
            evidence=f"duplicate_count={len(rows)}",
        )

    # Report-26 aggregate mismatch.
    if r26 is not None and not r26.empty and "usage_std" in r26.columns:
        r19_agg = (
            usage.dropna(subset=["usage_std"])
            .groupby(["site_key", "site_name", "commodity_key", "commodity", "std_unit"], dropna=False)["usage_std"]
            .sum()
            .reset_index(name="report19_usage_std")
        )
        r26_agg = (
            r26.dropna(subset=["usage_std"])
            .groupby(["site_key", "commodity_key", "std_unit"], dropna=False)["usage_std"]
            .sum()
            .reset_index(name="report26_usage_std")
        )

        cmp = r19_agg.merge(r26_agg, on=["site_key", "commodity_key", "std_unit"], how="outer")
        cmp["report19_usage_std"] = cmp["report19_usage_std"].fillna(0)
        cmp["report26_usage_std"] = cmp["report26_usage_std"].fillna(0)
        cmp["site_name"] = cmp["site_name"].fillna(cmp["site_key"])
        cmp["commodity"] = cmp["commodity"].fillna(cmp["commodity_key"])
        cmp["diff"] = cmp["report19_usage_std"] - cmp["report26_usage_std"]
        cmp["denom"] = cmp[["report19_usage_std", "report26_usage_std"]].abs().max(axis=1).replace(0, np.nan)
        cmp["diff_pct"] = (cmp["diff"].abs() / cmp["denom"]) * 100

        bad = cmp[cmp["diff_pct"].fillna(0) > recon_tolerance_pct]
        for _, r in bad.head(max_objects_per_rule).iterrows():
            unit = r["std_unit"]
            mwh = abs(r["diff"]) if unit == "MWh" else 0.0
            dth = abs(r["diff"]) if unit == "Dth" else 0.0
            tco2e = mwh * DEFAULT_ELECTRICITY_TCO2E_PER_MWH + dth * DEFAULT_GAS_TCO2E_PER_DTH

            add_object_issue(
                issues,
                energycap_object_type="Aggregate rollup / report filter",
                energycap_record=f"{r['site_name']} → {r['commodity']} → {unit}",
                severity="High",
                qa_domain="Rollup reconciliation",
                issue="Report-26 aggregate usage does not reconcile to Report-19 usage at site/commodity/unit level.",
                why_it_matters="The emissions export may not align with EnergyCAP rollups, indicating filter, chargeback, data type, or aggregation issues.",
                source_reports="Report-26 vs Report-19",
                site_name=r["site_name"],
                commodity=r["commodity"],
                impacted_mwh=float(mwh),
                impacted_dth=float(dth),
                estimated_tco2e_exposure=float(tco2e),
                recommended_energycap_fix="Confirm Report-19 and Report-26 were run with identical data type, date range, bill-source, void-bill, commodity, and topmost filters. Review chargebacks and aggregation settings.",
                evidence=f"Report19={r['report19_usage_std']}; Report26={r['report26_usage_std']}; diff={r['diff']}; diff_pct={r['diff_pct']:.2f}%",
            )

    # Report-13 bill anomaly support.
    if r13 is not None and not r13.empty:
        grouped = r13.groupby(["account_key", "meter_key", "commodity_key"], dropna=False)
        for _, rows in list(grouped)[:max_objects_per_rule]:
            r = rows.iloc[0]
            mwh, dth, tco2e = materiality_from_rows(rows)
            add_object_issue(
                issues,
                energycap_object_type="Bill / Usage record",
                energycap_record=f"Account {r.get('account_number','')} | Meter {r.get('meter_code') or r.get('meter_name','')} | {r.get('commodity','')}",
                severity="Medium",
                qa_domain="Bill anomaly",
                issue="Bill/account/meter appears in Report-13 Bill Analysis and should be reviewed.",
                why_it_matters="Outlier bills can materially distort emissions if usage, dates, demand, or units are wrong.",
                source_reports="Report-13",
                site_name=", ".join(rows["site_name"].dropna().astype(str).unique()[:3]),
                account_number=r.get("account_number", ""),
                meter_name=r.get("meter_name", ""),
                meter_code=r.get("meter_code", ""),
                commodity=r.get("commodity", ""),
                months_impacted=month_span(rows.get("report_month", pd.Series(dtype=str))),
                impacted_mwh=mwh,
                impacted_dth=dth,
                estimated_tco2e_exposure=tco2e,
                recommended_energycap_fix="Open the affected bill/account/meter in EnergyCAP and validate usage, cost, demand, service dates, and units.",
                evidence=f"Report-13 sampled rows={len(rows)}",
            )

    # Report-21 variance support.
    if r21 is not None and not r21.empty:
        grouped = r21.groupby(["site_key", "commodity_key"], dropna=False)
        for _, rows in list(grouped)[:max_objects_per_rule]:
            r = rows.iloc[0]
            mwh, dth, tco2e = materiality_from_rows(rows)
            add_object_issue(
                issues,
                energycap_object_type="Site-Commodity variance",
                energycap_record=f"{r.get('site_name','')} → {r.get('commodity','')}",
                severity="Low",
                qa_domain="Variance review",
                issue="Site/commodity appears in Report-21 Monthly Comparison review sample.",
                why_it_matters="Large year-over-year variances can indicate missing bills, account moves, meter changes, or true operational changes that should be explained before emissions export.",
                source_reports="Report-21",
                site_name=r.get("site_name", ""),
                commodity=r.get("commodity", ""),
                months_impacted=month_span(rows.get("report_month", pd.Series(dtype=str))),
                impacted_mwh=mwh,
                impacted_dth=dth,
                estimated_tco2e_exposure=tco2e,
                recommended_energycap_fix="Review the site/commodity in EnergyCAP Monthly Comparison and document whether the variance is explained or requires correction.",
                evidence=f"Report-21 sampled rows={len(rows)}",
            )

    out = pd.DataFrame(issues)
    if out.empty:
        return out

    out.insert(0, "register_id", [f"ECAP-QA-{i:06d}" for i in range(1, len(out) + 1)])

    severity_order = {"High": 0, "Medium": 1, "Low": 2}
    out["_severity_order"] = out["severity"].map(severity_order).fillna(9)
    out = (
        out.sort_values(
            by=["_severity_order", "estimated_tco2e_exposure", "impacted_mwh", "impacted_dth"],
            ascending=[True, False, False, False],
        )
        .drop(columns=["_severity_order"])
        .reset_index(drop=True)
    )

    return out


def summarize_register(register: pd.DataFrame) -> pd.DataFrame:
    if register is None or register.empty:
        return pd.DataFrame(columns=[
            "energycap_object_type", "severity", "qa_domain", "records",
            "impacted_mwh", "impacted_dth", "estimated_tco2e_exposure"
        ])

    return (
        register.groupby(["energycap_object_type", "severity", "qa_domain"], dropna=False)
        .agg(
            records=("register_id", "count"),
            impacted_mwh=("impacted_mwh", "sum"),
            impacted_dth=("impacted_dth", "sum"),
            estimated_tco2e_exposure=("estimated_tco2e_exposure", "sum"),
        )
        .reset_index()
    )


def site_readiness(master: pd.DataFrame, usage: pd.DataFrame, register: pd.DataFrame) -> pd.DataFrame:
    if usage is None or usage.empty:
        return pd.DataFrame()

    usage_agg = (
        usage.dropna(subset=["usage_std"])
        .groupby(["site_key", "site_name"], dropna=False)
        .agg(
            total_mwh=("usage_std", lambda s: s[usage.loc[s.index, "std_unit"].eq("MWh")].sum()),
            total_dth=("usage_std", lambda s: s[usage.loc[s.index, "std_unit"].eq("Dth")].sum()),
            estimated_tco2e=("estimated_tco2e_exposure", "sum"),
            commodities=("commodity", lambda s: ", ".join(sorted(set([x for x in s.astype(str) if x])))),
            months=("report_month", lambda s: len(set([x for x in s.astype(str) if x and x != "NaT"]))),
        )
        .reset_index()
    )

    if register is None or register.empty:
        usage_agg["open_qa_items"] = 0
        usage_agg["high_severity_items"] = 0
        usage_agg["readiness"] = "Ready"
        return usage_agg

    reg = (
        register.groupby("site_name", dropna=False)
        .agg(
            open_qa_items=("register_id", "count"),
            high_severity_items=("severity", lambda s: (s == "High").sum()),
            impacted_tco2e=("estimated_tco2e_exposure", "sum"),
        )
        .reset_index()
    )

    out = usage_agg.merge(reg, on="site_name", how="left")
    for c in ["open_qa_items", "high_severity_items", "impacted_tco2e"]:
        out[c] = out[c].fillna(0)

    out["readiness"] = np.where(
        out["high_severity_items"] > 0,
        "Not ready",
        np.where(out["open_qa_items"] > 0, "Conditional", "Ready"),
    )

    return out.sort_values(["readiness", "impacted_tco2e"], ascending=[False, False])


def readiness_score(register: pd.DataFrame, usage: pd.DataFrame) -> int:
    if register is None or register.empty:
        return 100

    total_tco2e = usage.get("estimated_tco2e_exposure", pd.Series([0])).abs().sum()
    impacted_tco2e = register.loc[
        register["severity"].isin(["High", "Medium"]),
        "estimated_tco2e_exposure"
    ].abs().sum()

    materiality_penalty = 0 if total_tco2e == 0 else min(45, (impacted_tco2e / total_tco2e) * 100)
    counts = register.groupby("severity").size().to_dict()
    count_penalty = (
        np.log1p(counts.get("High", 0)) * 9
        + np.log1p(counts.get("Medium", 0)) * 4
        + np.log1p(counts.get("Low", 0)) * 1
    )

    return int(max(0, round(100 - materiality_penalty - count_penalty)))


# -----------------------------
# Streamlit UI
# -----------------------------

st.set_page_config(page_title="EnergyCAP Emissions Export QA", layout="wide")

st.title("EnergyCAP Emissions Export QA Workbench")
st.caption("Purpose: verify whether EnergyCAP energy-utility usage can be trusted for site-level emissions calculations.")

with st.sidebar:
    st.header("1) Upload EnergyCAP reports")
    file03 = st.file_uploader("Report-03 — Setup / hierarchy master", type=["xlsx", "xls"], key="upload_r03")
    file19 = st.file_uploader("Report-19 — Monthly Utility Use and Cost", type=["xlsx", "xls"], key="upload_r19")
    file13 = st.file_uploader("Report-13 — Bill Analysis", type=["xlsx", "xls"], key="upload_r13")
    file21 = st.file_uploader("Report-21 — Monthly Comparison", type=["xlsx", "xls"], key="upload_r21")
    file26 = st.file_uploader("Report-26 — Use and Cost Summary", type=["xlsx", "xls"], key="upload_r26")

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

if not run_qa and "qa_register" not in st.session_state:
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
            master,
            usage,
            r13,
            r21,
            r26,
            recon_tolerance_pct=recon_tolerance_pct,
            max_objects_per_rule=max_objects_per_rule,
        )

        summary = summarize_register(register)
        sites = site_readiness(master, usage, register)
        score = readiness_score(register, usage)
        mapping = pd.concat([map03, map19, map13, map21, map26], ignore_index=True)

        st.session_state["qa_master"] = master
        st.session_state["qa_usage"] = usage
        st.session_state["qa_r26"] = r26
        st.session_state["qa_register"] = register
        st.session_state["qa_summary"] = summary
        st.session_state["qa_sites"] = sites
        st.session_state["qa_score"] = score
        st.session_state["qa_mapping"] = mapping

master = st.session_state["qa_master"]
usage = st.session_state["qa_usage"]
r26 = st.session_state["qa_r26"]
register = st.session_state["qa_register"]
summary = st.session_state["qa_summary"]
sites = st.session_state["qa_sites"]
score = st.session_state["qa_score"]
mapping = st.session_state["qa_mapping"]

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
            st.plotly_chart(
                px.bar(
                    by_type.sort_values("records", ascending=False),
                    x="energycap_object_type",
                    y="records",
                    title="Records to review by EnergyCAP object type",
                ),
                use_container_width=True,
            )

        with c2:
            by_domain = register.groupby("qa_domain", as_index=False).agg(
                estimated_tco2e_exposure=("estimated_tco2e_exposure", "sum")
            )
            st.plotly_chart(
                px.bar(
                    by_domain.sort_values("estimated_tco2e_exposure", ascending=False),
                    x="qa_domain",
                    y="estimated_tco2e_exposure",
                    title="Estimated tCO₂e exposure by QA domain",
                ),
                use_container_width=True,
            )

        st.dataframe(summary, use_container_width=True, height=350)

        st.markdown("### Top EnergyCAP records to review")
        top_cols = [
            "severity",
            "energycap_object_type",
            "energycap_record_to_review",
            "site_name",
            "account_number",
            "meter_name",
            "meter_code",
            "commodity",
            "issue",
            "recommended_energycap_fix",
            "estimated_tco2e_exposure",
        ]
        top_cols = [c for c in top_cols if c in register.columns]
        st.dataframe(register[top_cols].head(25), use_container_width=True, height=400)

    st.caption("Estimated tCO₂e exposure uses placeholder materiality factors only to prioritize QA. It is not an official emissions calculation.")

with tab2:
    st.subheader("EnergyCAP record correction register")
    st.write("This register is organized by the EnergyCAP object that needs attention — not by Excel row.")

    if register.empty:
        st.success("No EnergyCAP records to review.")
    else:
        c1, c2, c3 = st.columns(3)

        with c1:
            sev = st.multiselect(
                "Severity",
                sorted(register["severity"].dropna().unique()),
                default=sorted(register["severity"].dropna().unique()),
            )

        with c2:
            obj = st.multiselect(
                "EnergyCAP object type",
                sorted(register["energycap_object_type"].dropna().unique()),
                default=sorted(register["energycap_object_type"].dropna().unique()),
            )

        with c3:
            domain = st.multiselect(
                "QA domain",
                sorted(register["qa_domain"].dropna().unique()),
                default=sorted(register["qa_domain"].dropna().unique()),
            )

        filtered = register[
            register["severity"].isin(sev)
            & register["energycap_object_type"].isin(obj)
            & register["qa_domain"].isin(domain)
        ].copy()

        search = st.text_input("Search site, account, meter, commodity, issue, evidence, or recommended fix")
        if search:
            mask = filtered.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
            filtered = filtered[mask]

        priority_cols = [
            "severity",
            "energycap_object_type",
            "energycap_record_to_review",
            "site_name",
            "account_number",
            "meter_name",
            "meter_code",
            "commodity",
            "months_impacted",
            "issue",
            "recommended_energycap_fix",
            "impacted_mwh",
            "impacted_dth",
            "estimated_tco2e_exposure",
            "evidence",
            "source_reports",
            "register_id",
        ]
        display_cols = [c for c in priority_cols if c in filtered.columns]
        st.markdown("### EnergyCAP records to review/fix")
        st.caption("Start with the columns `energycap_object_type` and `energycap_record_to_review`. These identify the EnergyCAP record to open or investigate.")
        st.dataframe(filtered[display_cols], use_container_width=True, height=650)

        st.download_button(
            "Download filtered EnergyCAP correction register",
            filtered.to_csv(index=False).encode("utf-8"),
            "energycap_object_correction_register_filtered.csv",
            "text/csv",
        )

with tab3:
    st.subheader("Site-level emissions readiness")
    st.write("This view shows whether each site appears ready for site-level emissions calculation.")
    site_cols = [
        "readiness",
        "site_name",
        "commodities",
        "months",
        "open_qa_items",
        "high_severity_items",
        "total_mwh",
        "total_dth",
        "estimated_tco2e",
        "impacted_tco2e",
    ]
    site_display_cols = [c for c in site_cols if c in sites.columns]
    st.dataframe(sites[site_display_cols], use_container_width=True, height=600)

    if not register.empty:
        st.markdown("### Issues grouped by site")
        site_issue_summary = (
            register.groupby(["site_name", "energycap_object_type", "severity"], dropna=False)
            .agg(
                records=("register_id", "count"),
                impacted_mwh=("impacted_mwh", "sum"),
                impacted_dth=("impacted_dth", "sum"),
                estimated_tco2e_exposure=("estimated_tco2e_exposure", "sum"),
            )
            .reset_index()
            .sort_values(["severity", "records"], ascending=[True, False])
        )
        st.dataframe(site_issue_summary, use_container_width=True, height=450)

with tab4:
    st.subheader("Hierarchy and rollup reconciliation")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Report-03 master hierarchy counts**")
        st.dataframe(
            pd.DataFrame({
                "EnergyCAP level": [
                    "Sites",
                    "Accounts",
                    "Account-Meter relationships",
                    "Full Site-Account-Meter-Commodity relationships",
                ],
                "Count": [
                    master["site_key"].replace("", pd.NA).dropna().nunique(),
                    master["account_key"].replace("", pd.NA).dropna().nunique(),
                    master["account_meter_key"].replace(" | ", pd.NA).dropna().nunique(),
                    master["full_rel_key"].replace(" |  |  | ", pd.NA).dropna().nunique(),
                ],
            }),
            use_container_width=True,
        )

    with c2:
        st.markdown("**Report-19 usage relationship counts**")
        st.dataframe(
            pd.DataFrame({
                "EnergyCAP level": [
                    "Sites with usage",
                    "Accounts with usage",
                    "Account-Meter relationships with usage",
                    "Full relationships with usage",
                    "Site/Commodity/Month facts",
                ],
                "Count": [
                    usage["site_key"].replace("", pd.NA).dropna().nunique(),
                    usage["account_key"].replace("", pd.NA).dropna().nunique(),
                    usage["account_meter_key"].replace(" | ", pd.NA).dropna().nunique(),
                    usage["full_rel_key"].replace(" |  |  | ", pd.NA).dropna().nunique(),
                    usage[["site_key", "commodity_key", "report_month"]].drop_duplicates().shape[0],
                ],
            }),
            use_container_width=True,
        )

    st.markdown("**Report-19 usage by site/commodity/unit**")
    agg = (
        usage.dropna(subset=["usage_std"])
        .groupby(["site_name", "commodity", "std_unit"], dropna=False)["usage_std"]
        .sum()
        .reset_index()
    )
    st.dataframe(agg.sort_values("usage_std", ascending=False), use_container_width=True, height=400)

with tab5:
    st.subheader("Detected source-column mapping")
    st.write("This is diagnostic only. Missing mappings are not treated as EnergyCAP data issues unless they prevent reconciliation.")
    st.dataframe(mapping, use_container_width=True, height=600)

with tab6:
    st.subheader("Downloads")
    st.download_button(
        "Download EnergyCAP object correction register",
        register.to_csv(index=False).encode("utf-8"),
        "energycap_object_correction_register.csv",
        "text/csv",
    )
    st.download_button(
        "Download readiness summary",
        summary.to_csv(index=False).encode("utf-8"),
        "energycap_readiness_summary.csv",
        "text/csv",
    )
    st.download_button(
        "Download site readiness",
        sites.to_csv(index=False).encode("utf-8"),
        "energycap_site_readiness.csv",
        "text/csv",
    )
    st.download_button(
        "Download normalized Report-03 master",
        master.to_csv(index=False).encode("utf-8"),
        "normalized_report03_master.csv",
        "text/csv",
    )
    st.download_button(
        "Download normalized Report-19 usage",
        usage.to_csv(index=False).encode("utf-8"),
        "normalized_report19_usage.csv",
        "text/csv",
    )
    st.download_button(
        "Download detected column mapping",
        mapping.to_csv(index=False).encode("utf-8"),
        "detected_column_mapping.csv",
        "text/csv",
    )

st.caption("EnergyCAP Emissions Export QA Workbench v9 record-focused. The correction register points to EnergyCAP objects to review/fix.")

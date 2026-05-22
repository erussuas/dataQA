import re
from io import BytesIO
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

ELEC = {"kwh":0.001,"mwh":1.0,"kilowatt hour":0.001,"kilowatt hours":0.001,"kw h":0.001}
GAS = {"therm":0.1,"therms":0.1,"dth":1.0,"dekatherm":1.0,"dekatherms":1.0,"mmbtu":1.0,"ccf":0.1037,"mcf":1.037}
REPORT_TYPES = ["Report-03","Report-19","Report-13","Report-21","Report-26","Ignore"]

def clean_col(c): return re.sub(r"\s+"," ",str(c).strip().replace("\n"," "))
def disp(x):
    if pd.isna(x): return ""
    s=re.sub(r"\s+"," ",str(x).strip())
    return "" if s.lower() in {"nan","none","nat"} else s
def key(x): return disp(x).lower()
def ckey(c): return re.sub(r"[^a-z0-9]+","",str(c).lower())
def num(s):
    return pd.to_numeric(s.astype(str).str.replace(",","",regex=False).str.replace("$","",regex=False).str.replace("(","-",regex=False).str.replace(")","",regex=False).str.replace("%","",regex=False),errors="coerce")
def infer_comm(t):
    t=str(t).lower()
    if any(x in t for x in ["electric","electricity","power","kwh","mwh"]): return "Electricity"
    if any(x in t for x in ["natural gas"," gas","therm","dth","mmbtu","dekatherm"]): return "Natural Gas"
    return ""
def find_col(df,cands):
    if df is None or df.empty: return ""
    m={ckey(c):c for c in df.columns}
    for cand in cands:
        k=ckey(cand)
        if k in m: return m[k]
    for cand in cands:
        k=ckey(cand)
        for kk,c in m.items():
            if k and (k in kk or kk in k): return c
    return ""

@st.cache_data(show_spinner=False)
def load_excel(name,b):
    xls=pd.ExcelFile(BytesIO(b)); sheets={}
    for sh in xls.sheet_names:
        try:
            df=pd.read_excel(BytesIO(b),sheet_name=sh)
            df.columns=[clean_col(c) for c in df.columns]
            df=df.dropna(how="all")
            if len(df)>0 and len(df.columns)>0: sheets[sh]=df
        except Exception: pass
    if not sheets: return pd.DataFrame(), []
    return max(sheets.values(), key=lambda d:d.shape[0]*max(1,d.shape[1])).copy(), list(sheets.keys())

def detect_report(name,df):
    txt=(name+" "+" ".join(df.columns)).lower(); s={r:0 for r in REPORT_TYPES if r!="Ignore"}
    if any(x in txt for x in ["report-03","report 03","setup","accounts, vendors"]): s["Report-03"]+=80
    if "building" in txt and "account" in txt and "meter" in txt: s["Report-03"]+=25
    if any(x in txt for x in ["report-19","report 19","monthly utility use"]): s["Report-19"]+=80
    if ("usage" in txt or " use" in txt) and ("month" in txt or "period" in txt): s["Report-19"]+=20
    if any(x in txt for x in ["report-13","report 13","bill analysis","outlier"]): s["Report-13"]+=90
    if any(x in txt for x in ["report-21","report 21","monthly comparison","variance"]): s["Report-21"]+=90
    if any(x in txt for x in ["report-26","report 26","use and cost summary"]): s["Report-26"]+=90
    best=max(s,key=s.get); conf=min(s[best],100)
    return (best,conf) if conf>=30 else ("Ignore",conf)

def sel(label,df,cands,k,req=False):
    opts=[""]+list(df.columns); detected=find_col(df,cands); idx=opts.index(detected) if detected in opts else 0
    return st.selectbox(label+(" *" if req else ""),opts,index=idx,key=k)

def standardize(df):
    out=df.copy(); unit=out["unit"].fillna("").astype(str).str.lower().str.strip(); comm=out["commodity"].fillna("").astype(str).str.lower()
    out["usage_std"]=np.nan; out["std_unit"]=""
    ef=unit.map(ELEC); gf=unit.map(GAS)
    em=comm.str.contains("electric",na=False)|ef.notna(); gm=(comm.str.contains("gas",na=False)|gf.notna()) & ~em
    out.loc[em,"usage_std"]=out.loc[em,"usage"]*ef.loc[em].astype(float); out.loc[em,"std_unit"]="MWh"
    out.loc[gm,"usage_std"]=out.loc[gm,"usage"]*gf.loc[gm].astype(float); out.loc[gm,"std_unit"]="Dth"
    out["estimated_tco2e_exposure"]=0.0
    out.loc[out["std_unit"].eq("MWh"),"estimated_tco2e_exposure"]=out.loc[out["std_unit"].eq("MWh"),"usage_std"].abs()*0.40
    out.loc[out["std_unit"].eq("Dth"),"estimated_tco2e_exposure"]=out.loc[out["std_unit"].eq("Dth"),"usage_std"].abs()*0.0053
    return out

def add_keys(df):
    out=df.copy()
    for c in ["site_name","account_number","meter_name","meter_code","commodity"]:
        if c not in out: out[c]=""
    md=out["meter_code"].where(out["meter_code"].astype(str).str.strip().ne(""),out["meter_name"]); out["meter_display"]=md
    out["site_key"]=out["site_name"].map(key); out["account_key"]=out["account_number"].map(key); out["meter_key"]=md.map(key); out["commodity_key"]=out["commodity"].map(key)
    out["site_account_key"]=out["site_key"]+"|"+out["account_key"]; out["account_meter_key"]=out["account_key"]+"|"+out["meter_key"]
    out["site_commodity_key"]=out["site_key"]+"|"+out["commodity_key"]; out["full_key"]=out["site_key"]+"|"+out["account_key"]+"|"+out["meter_key"]+"|"+out["commodity_key"]
    return out

def norm_master(df,m):
    out=pd.DataFrame(index=df.index); out["source_report"]="Report-03"; out["source_row"]=np.arange(2,len(df)+2)
    for f in ["site_name","site_code","account_number","account_name","meter_name","meter_code","commodity","country","state","account_status","site_status","vendor"]:
        col=m.get(f,""); out[f]=df[col].map(disp) if col and col in df.columns else ""
    miss=out["commodity"].eq("")
    out.loc[miss,"commodity"]=(out.loc[miss,"account_name"]+" "+out.loc[miss,"meter_name"]+" "+out.loc[miss,"account_number"]+" "+out.loc[miss,"vendor"]).map(infer_comm)
    out=add_keys(out); out["energycap_full_record"]=out["site_name"]+" → "+out["account_number"]+" → "+out["meter_display"]+" → "+out["commodity"]
    return out.drop_duplicates().reset_index(drop=True)

def norm_usage(df,m,src):
    out=pd.DataFrame(index=df.index); out["source_report"]=src; out["source_row"]=np.arange(2,len(df)+2)
    for f in ["site_name","account_number","meter_name","meter_code","commodity","unit","invoice","vendor"]:
        col=m.get(f,""); out[f]=df[col].map(disp) if col and col in df.columns else ""
    uc=m.get("usage",""); out["usage"]=num(df[uc]) if uc and uc in df.columns else np.nan
    mc=m.get("month",""); out["month"]=pd.to_datetime(df[mc],errors="coerce") if mc and mc in df.columns else pd.NaT
    out["report_month"]=out["month"].dt.to_period("M").astype(str).replace("NaT","")
    miss=out["commodity"].eq("")
    out.loc[miss,"commodity"]=(out.loc[miss,"site_name"]+" "+out.loc[miss,"account_number"]+" "+out.loc[miss,"meter_name"]+" "+out.loc[miss,"unit"]+" "+out.loc[miss,"vendor"]).map(infer_comm)
    out=standardize(out); out=add_keys(out); return out.reset_index(drop=True)

def norm_support(df,base_map,src,cap):
    if df is None or df.empty: return pd.DataFrame()
    df2=df.head(cap).copy(); m={}
    for k,v in base_map.items(): m[k]=v if v in df2.columns else find_col(df2,[v,k.replace("_"," "),k])
    return norm_usage(df2,m,src)

def first_nonblank(s):
    for x in s:
        y=disp(x)
        if y: return y
    return ""

def mat(rows):
    if rows is None or rows.empty: return 0.0,0.0,0.0
    mwh=rows.loc[rows["std_unit"].eq("MWh"),"usage_std"].abs().sum(skipna=True) if "std_unit" in rows else 0.0
    dth=rows.loc[rows["std_unit"].eq("Dth"),"usage_std"].abs().sum(skipna=True) if "std_unit" in rows else 0.0
    co2=rows["estimated_tco2e_exposure"].abs().sum(skipna=True) if "estimated_tco2e_exposure" in rows else 0.0
    return float(mwh),float(dth),float(co2)

def months(rows):
    if rows is None or rows.empty or "report_month" not in rows: return ""
    vals=sorted([v for v in rows["report_month"].dropna().astype(str).unique() if v and v!="NaT"])
    return ", ".join(vals) if len(vals)<=6 else f"{vals[0]} to {vals[-1]} ({len(vals)} months/records)" if vals else ""

def add_row(lst,typ,severity,obj,grain,site,acct,meter_name,meter_code,comm,domain,issue,fix,evidence,sources,rows=None):
    mwh,dth,co2=mat(rows) if rows is not None else (0,0,0)
    if grain in ["Site","Site-Commodity","Rollup"]:
        acct=acct or "Multiple / not applicable"; meter_name=meter_name or "Multiple / not applicable"
    meter=disp(meter_code) or disp(meter_name)
    parts=[disp(site)]
    if grain not in ["Site","Site-Commodity","Rollup"]: parts += [disp(acct), disp(meter)]
    if comm: parts.append(disp(comm))
    if grain=="Rollup": parts.append("Aggregate rollup")
    lst.append({"register_type":typ,"severity":severity,"energycap_object_type":obj,"record_grain":grain,"energycap_record_to_review":" → ".join([p for p in parts if p]),"site_name":site,"account_number":acct,"meter_name":meter_name,"meter_code":meter_code,"commodity":comm,"months_impacted":months(rows) if rows is not None else "","qa_domain":domain,"issue":issue,"recommended_energycap_fix_or_review":fix,"impacted_mwh":mwh,"impacted_dth":dth,"estimated_tco2e_exposure":co2,"source_reports":sources,"evidence":evidence})

def build_registers(master,usage,r13,r21,r26,tol,max_items):
    corr=[]; risk=[]
    ms=set(master.loc[master.site_key.ne(""),"site_key"]); ma=set(master.loc[master.account_key.ne(""),"account_key"]); mam=set(master.loc[master.account_meter_key.ne("|"),"account_meter_key"]); mf=set(master.loc[master.full_key.str.replace("|","",regex=False).ne(""),"full_key"]); msc=set(master.loc[master.site_commodity_key.ne("|"),"site_commodity_key"])
    bad=usage[usage.site_key.ne("") & ~usage.site_key.isin(ms)]
    for (sk,s),rows in list(bad.groupby(["site_key","site_name"],dropna=False))[:max_items]: add_row(corr,"Correction","High","Site","Site",s,"","","",", ".join(sorted(set(rows.commodity.astype(str)))[:3]),"Hierarchy reconciliation","Usage exists for a site not found in Report-03 master hierarchy.","Review site/building setup, site naming, and Report-03 scope/filtering.",f"site_key={sk}; usage_rows={len(rows)}","Report-19 vs Report-03",rows)
    bad=usage[usage.account_key.ne("") & ~usage.account_key.isin(ma)]
    for (ak,a),rows in list(bad.groupby(["account_key","account_number"],dropna=False))[:max_items]: add_row(corr,"Correction","High","Account","Account",first_nonblank(rows.site_name),a,"Multiple / review account","",", ".join(sorted(set(rows.commodity.astype(str)))[:3]),"Hierarchy reconciliation","Usage exists for an account not found in Report-03 master setup.","Confirm account exists and is linked to the correct site/meter in EnergyCAP. Confirm matching report scope.",f"account_key={ak}; usage_rows={len(rows)}","Report-19 vs Report-03",rows)
    bad=usage[usage.account_key.ne("") & usage.meter_key.ne("") & ~usage.account_meter_key.isin(mam)]
    for (am,a,mn,mc),rows in list(bad.groupby(["account_meter_key","account_number","meter_name","meter_code"],dropna=False))[:max_items]: add_row(corr,"Correction","High","Account-Meter relationship","Account-Meter",first_nonblank(rows.site_name),a,mn,mc,", ".join(sorted(set(rows.commodity.astype(str)))[:3]),"Hierarchy reconciliation","Usage is tied to an account-meter relationship not present in Report-03.","Review account-meter relationship, meter identifier, and effective dating in EnergyCAP.",f"account_meter_key={am}; usage_rows={len(rows)}","Report-19 vs Report-03",rows)
    bad=usage[usage.full_key.str.replace("|","",regex=False).ne("") & ~usage.full_key.isin(mf)]
    for (fk,s,a,mn,mc,cm),rows in list(bad.groupby(["full_key","site_name","account_number","meter_name","meter_code","commodity"],dropna=False))[:max_items]: add_row(corr,"Correction","Medium","Site-Account-Meter-Commodity relationship","Full hierarchy",s,a,mn,mc,cm,"Hierarchy reconciliation","Full site-account-meter-commodity relationship in usage does not match Report-03.","Review site assignment, account, meter, and commodity setup in EnergyCAP.",f"full_key={fk}; usage_rows={len(rows)}","Report-19 vs Report-03",rows)
    bad=usage[usage.site_commodity_key.str.replace("|","",regex=False).ne("") & ~usage.site_commodity_key.isin(msc)]
    for (sc,s,cm),rows in list(bad.groupby(["site_commodity_key","site_name","commodity"],dropna=False))[:max_items]: add_row(corr,"Correction","Medium","Site-Commodity relationship","Site-Commodity",s,"","","",cm,"Commodity reconciliation","Usage exists for a site/commodity combination not configured in Report-03.","Check commodity assigned to account/meter and whether this commodity should exist for the site.",f"site_commodity_key={sc}; usage_rows={len(rows)}","Report-19 vs Report-03",rows)
    active=master[master.account_key.ne("")]
    if "account_status" in active: active=active[~active.account_status.str.lower().str.contains("inactive|closed",na=False)]
    ua=set(usage.loc[usage.account_key.ne(""),"account_key"]); missing=active[~active.account_key.isin(ua)]
    for (ak,a),rows in list(missing.groupby(["account_key","account_number"],dropna=False))[:max_items]:
        r=rows.iloc[0]; add_row(corr,"Correction","Medium","Account","Account",r.site_name,a,r.meter_name,r.meter_code,r.commodity,"Usage completeness","Active account in Report-03 has no corresponding usage in Report-19.","Check missing bills, date range/filtering, or whether the account should be inactive/closed.",f"account_key={ak}; master_rows={len(rows)}","Report-03 vs Report-19")
    geo=master[master.site_key.isin(set(usage.loc[usage.site_key.ne(""),"site_key"]))]; missgeo=geo[geo.country.str.strip().eq("") | geo.site_name.str.strip().eq("")]
    for (sk,s),rows in list(missgeo.groupby(["site_key","site_name"],dropna=False))[:max_items]:
        rel=usage[usage.site_key.eq(sk)]; add_row(corr,"Correction","High","Site","Site",s,"","","",", ".join(sorted(set(rel.commodity.astype(str)))[:3]),"Emissions readiness","Site with energy usage is missing site name or country/geography metadata.","Populate site name and country/state/province in EnergyCAP.",f"site_key={sk}; country='{first_nonblank(rows.country)}'","Report-03 + Report-19",rel)
    bad=usage[usage.usage.notna() & (usage.usage_std.isna() | usage.std_unit.eq(""))]
    for (a,mk,u,cm),rows in list(bad.groupby(["account_number","meter_key","unit","commodity"],dropna=False))[:max_items]: add_row(corr,"Correction","High","Bill / Usage record","Bill / Usage",first_nonblank(rows.site_name),a,first_nonblank(rows.meter_name),first_nonblank(rows.meter_code),cm,"Emissions readiness","Usage exists but cannot be converted to MWh or Dth.","Correct commodity and usage unit setup or add supported conversion logic.",f"unit={u}; commodity={cm}; usage_rows={len(rows)}","Report-19",rows)
    dup_cols=["site_key","account_key","meter_key","commodity_key","report_month","usage","unit"]; dup=usage.duplicated(subset=dup_cols,keep=False)
    for _,rows in list(usage[dup].groupby(dup_cols,dropna=False))[:max_items]:
        r=rows.iloc[0]; add_row(corr,"Correction","High","Bill / Usage record","Bill / Usage",r.site_name,r.account_number,r.meter_name,r.meter_code,r.commodity,"Usage completeness","Potential duplicate usage fact at site/account/meter/commodity/month/usage/unit grain.","Review bill history/import batches for duplicate or corrected invoices.",f"duplicate_count={len(rows)}","Report-19",rows)
    um=usage[usage.report_month.ne("") & usage.site_key.ne("") & usage.commodity_key.ne("")]
    if not um.empty:
        allm=sorted(um.report_month.unique()); exp=len(allm)
        if exp>1:
            cov=um.groupby(["site_key","site_name","commodity_key","commodity"],dropna=False).report_month.nunique().reset_index(name="months_present")
            for _,r in cov[cov.months_present<exp].head(max_items).iterrows():
                rel=um[(um.site_key.eq(r.site_key)) & (um.commodity_key.eq(r.commodity_key))]; add_row(corr,"Correction","Medium","Site-Commodity monthly coverage","Site-Commodity",r.site_name,"","","",r.commodity,"Usage completeness",f"Site/commodity has {int(r.months_present)} of {exp} months present in Report-19.","Check missing bills, late invoices, account open/close status, and date filters.",f"present={int(r.months_present)}; expected={exp}","Report-19",rel)
    if r26 is not None and not r26.empty and "usage_std" in r26:
        a19=usage.dropna(subset=["usage_std"]).groupby(["site_key","site_name","commodity_key","commodity","std_unit"],dropna=False).usage_std.sum().reset_index(name="r19")
        a26=r26.dropna(subset=["usage_std"]).groupby(["site_key","site_name","commodity_key","commodity","std_unit"],dropna=False).usage_std.sum().reset_index(name="r26")
        cmp=a19.merge(a26,on=["site_key","commodity_key","std_unit"],how="outer",suffixes=("_19","_26")); cmp["r19"]=cmp.r19.fillna(0); cmp["r26"]=cmp.r26.fillna(0); cmp["site_name"]=cmp.site_name_19.fillna(cmp.site_name_26).fillna(cmp.site_key); cmp["commodity"]=cmp.commodity_19.fillna(cmp.commodity_26).fillna(cmp.commodity_key); cmp["diff"]=cmp.r19-cmp.r26; cmp["denom"]=cmp[["r19","r26"]].abs().max(axis=1).replace(0,np.nan); cmp["diff_pct"]=(cmp["diff"].abs()/cmp["denom"])*100
        for _,r in cmp[cmp.diff_pct.fillna(0)>tol].head(max_items).iterrows():
            unit=r.std_unit; mwh=abs(r.diff) if unit=="MWh" else 0; dth=abs(r.diff) if unit=="Dth" else 0; co2=mwh*0.40+dth*0.0053; rows=pd.DataFrame({"usage_std":[mwh or dth],"std_unit":[unit],"estimated_tco2e_exposure":[co2]}); add_row(corr,"Correction","High","Aggregate rollup / report filter","Rollup",r.site_name,"","","",r.commodity,"Rollup reconciliation","Report-26 aggregate usage does not reconcile to Report-19 at site/commodity/unit level.","Confirm Report-19 and Report-26 used identical data type, date range, commodity, topmost, bill-source, chargeback, and void-bill filters.",f"Report19={r.r19}; Report26={r.r26}; diff_pct={r.diff_pct:.2f}%","Report-26 vs Report-19",rows)
    # Risks
    multi=usage[usage.site_key.ne("") & usage.meter_key.ne("") & usage.commodity_key.ne("")]
    for _,rows in list(multi.groupby(["site_key","site_name","meter_key","meter_display","commodity_key","commodity","report_month"],dropna=False))[:max_items]:
        if rows.account_key.nunique()>1:
            r=rows.iloc[0]; add_row(risk,"Risk","Review","Potential supply/distribution overlap","Site-Account-Meter",r.site_name,"Multiple accounts",r.meter_display,"",r.commodity,"Double-counting risk","Multiple accounts carry usage for the same site/meter/commodity/month.","Review whether these are separate supply and distribution accounts. Ensure usage is counted once.",f"accounts={', '.join(sorted(set(rows.account_number.astype(str))))}; month={r.report_month}","Report-19",rows)
    for _,rows in list(multi.groupby(["site_key","site_name","account_key","account_number","commodity_key","commodity","report_month"],dropna=False))[:max_items]:
        if rows.meter_key.nunique()>1:
            r=rows.iloc[0]; add_row(risk,"Risk","Review","Multiple meters on same account","Site-Account-Meter",r.site_name,r.account_number,"Multiple meters","",r.commodity,"Double-counting risk","Multiple meters appear on the same account/commodity/month.","Review whether meters are distinct loads, parent/child meters, or submeters included in a master meter.",f"meters={', '.join(sorted(set(rows.meter_display.astype(str))))}; month={r.report_month}","Report-19",rows)
    neg=usage[usage.usage.notna() & (usage.usage<0)]
    for _,rows in list(neg.groupby(["site_name","account_number","meter_display","commodity"],dropna=False))[:max_items]:
        r=rows.iloc[0]; add_row(risk,"Risk","Review","Negative usage / credit","Bill / Usage",r.site_name,r.account_number,r.meter_name,r.meter_code,r.commodity,"Calculation risk","Negative usage detected.","Review whether this is a correction, net metering/export, billing reversal, or data error. Confirm emissions treatment.",f"negative_rows={len(rows)}","Report-19",rows)
    active=master[master.site_key.ne("") & master.commodity_key.ne("") & master.account_key.ne("")]
    for _,rows in list(active.groupby(["site_key","site_name","commodity_key","commodity"],dropna=False))[:max_items]:
        if rows.account_key.nunique()>1:
            r=rows.iloc[0]; add_row(risk,"Risk","Review","Multiple accounts for same site/commodity","Site-Account",r.site_name,"Multiple accounts","Multiple / review","",r.commodity,"Configuration risk","Multiple accounts are configured for the same site and commodity.","Review whether accounts are distinct loads, sequential changes, supply/delivery split, or duplicates.",f"accounts={', '.join(sorted(set(rows.account_number.astype(str)))[:10])}","Report-03")
    if r13 is not None and not r13.empty:
        for _,rows in list(r13.groupby(["site_name","account_number","meter_display","commodity"],dropna=False))[:max_items]:
            r=rows.iloc[0]; add_row(risk,"Risk","Review","Bill anomaly","Bill / Usage",r.site_name,r.account_number,r.meter_name,r.meter_code,r.commodity,"Bill anomaly","Record appears in Report-13 Bill Analysis.","Review usage, cost, demand, service dates, and units for the affected bill/account/meter.",f"Report-13 rows={len(rows)}","Report-13",rows)
    if r21 is not None and not r21.empty:
        for _,rows in list(r21.groupby(["site_name","commodity"],dropna=False))[:max_items]:
            r=rows.iloc[0]; add_row(risk,"Risk","Review","Variance review","Site-Commodity",r.site_name,"","","",r.commodity,"Variance risk","Site/commodity appears in Report-21 variance review sample.","Review whether variance is explained by operations, missing bills, account moves, meter changes, or setup changes.",f"Report-21 rows={len(rows)}","Report-21",rows)
    corr=pd.DataFrame(corr); risk=pd.DataFrame(risk)
    for df,pfx in [(corr,"CORR"),(risk,"RISK")]:
        if not df.empty:
            df.insert(0,"register_id",[f"{pfx}-{i:06d}" for i in range(1,len(df)+1)]); order={"High":0,"Medium":1,"Low":2,"Review":3}; df["_sev"]=df.severity.map(order).fillna(9); df.sort_values(["_sev","estimated_tco2e_exposure"],ascending=[True,False],inplace=True); df.drop(columns="_sev",inplace=True); df.reset_index(drop=True,inplace=True)
    return corr,risk

def site_ready(usage,corr,risk):
    if usage.empty: return pd.DataFrame()
    agg=usage.dropna(subset=["usage_std"]).groupby("site_name",dropna=False).agg(total_mwh=("usage_std",lambda s:s[usage.loc[s.index,"std_unit"].eq("MWh")].sum()),total_dth=("usage_std",lambda s:s[usage.loc[s.index,"std_unit"].eq("Dth")].sum()),estimated_tco2e=("estimated_tco2e_exposure","sum"),commodities=("commodity",lambda s:", ".join(sorted(set(x for x in s.astype(str) if x)))),months=("report_month",lambda s:len(set(x for x in s.astype(str) if x and x!="NaT")))).reset_index()
    cc=corr.groupby("site_name",dropna=False).agg(correction_items=("register_id","count"),high_correction_items=("severity",lambda s:(s=="High").sum()),correction_tco2e=("estimated_tco2e_exposure","sum")).reset_index() if not corr.empty else pd.DataFrame(columns=["site_name","correction_items","high_correction_items","correction_tco2e"])
    rr=risk.groupby("site_name",dropna=False).agg(risk_items=("register_id","count"),risk_tco2e=("estimated_tco2e_exposure","sum")).reset_index() if not risk.empty else pd.DataFrame(columns=["site_name","risk_items","risk_tco2e"])
    out=agg.merge(cc,on="site_name",how="left").merge(rr,on="site_name",how="left")
    for c in ["correction_items","high_correction_items","correction_tco2e","risk_items","risk_tco2e"]: out[c]=out[c].fillna(0)
    out["readiness"]=np.where(out.high_correction_items>0,"Blocked",np.where(out.correction_items>0,"Conditional",np.where(out.risk_items>0,"Review","Ready")))
    return out

def score(corr,risk,usage):
    if corr.empty and risk.empty: return 100
    total=usage.estimated_tco2e_exposure.abs().sum() if "estimated_tco2e_exposure" in usage else 0; impacted=corr.estimated_tco2e_exposure.abs().sum() if not corr.empty else 0
    matpen=0 if total==0 else min(50,(impacted/total)*100); high=(corr.severity=="High").sum() if not corr.empty else 0; med=(corr.severity=="Medium").sum() if not corr.empty else 0
    return int(max(0,round(100-matpen-np.log1p(high)*10-np.log1p(med)*4-np.log1p(len(risk))*1)))

st.set_page_config(page_title="EnergyCAP Emissions QA v13",layout="wide")
st.title("EnergyCAP Emissions Export QA Workbench")
st.caption("v13: bulk upload → report detection → manual mapping → correction register + risk review register.")
uploaded=st.file_uploader("Upload all EnergyCAP Excel reports together",type=["xlsx","xls"],accept_multiple_files=True)
if not uploaded:
    st.info("Upload your EnergyCAP Excel reports to begin."); st.stop()
loaded=[]
for f in uploaded:
    df,sheets=load_excel(f.name,f.getvalue()); det,conf=detect_report(f.name,df); loaded.append({"file":f.name,"df":df,"det":det,"conf":conf})
st.subheader("Step 1 — Confirm report identification")
assign={}; rows=[]
for i,it in enumerate(loaded):
    c1,c2,c3,c4=st.columns([3,2,1,2])
    c1.write(it["file"]); idx=REPORT_TYPES.index(it["det"]) if it["det"] in REPORT_TYPES else 5; typ=c2.selectbox("Report type",REPORT_TYPES,index=idx,key=f"rt{i}",label_visibility="collapsed"); c3.write(f"{it['conf']}%"); c4.write(f"{len(it['df']):,} rows / {len(it['df'].columns):,} cols")
    if typ!="Ignore": assign[typ]=it["df"]
    rows.append({"file":it["file"],"type":typ,"confidence":it["conf"],"rows":len(it["df"]),"cols":len(it["df"].columns)})
with st.expander("Confirmed file table",False): st.dataframe(pd.DataFrame(rows),use_container_width=True)
if "Report-03" not in assign or "Report-19" not in assign:
    st.warning("Report-03 and Report-19 are required minimum inputs."); st.stop()
r03_raw=assign["Report-03"]; r19_raw=assign["Report-19"]; r13_raw=assign.get("Report-13",pd.DataFrame()); r21_raw=assign.get("Report-21",pd.DataFrame()); r26_raw=assign.get("Report-26",pd.DataFrame())
st.divider(); st.subheader("Step 2 — Confirm key column mapping")
with st.expander("Report-03 master hierarchy mapping",True):
    a,b,c=st.columns(3)
    with a:
        m03_site=sel("Site / building name",r03_raw,["Building Name","Site Name","Place Name","Site"],"m03_site",True); m03_site_code=sel("Site code",r03_raw,["Building Code","Site Code","Place Code"],"m03_site_code"); m03_country=sel("Country",r03_raw,["Building Country","Country","Site Country"],"m03_country"); m03_state=sel("State/province",r03_raw,["Building State","State","Province"],"m03_state")
    with b:
        m03_acct=sel("Account number",r03_raw,["Account Number","Acct Number"],"m03_acct",True); m03_acct_name=sel("Account name",r03_raw,["Account Name"],"m03_acct_name"); m03_acct_status=sel("Account status",r03_raw,["Account Status","Status"],"m03_acct_status"); m03_vendor=sel("Vendor",r03_raw,["Vendor","Vendor Name","Utility"],"m03_vendor")
    with c:
        m03_meter=sel("Meter name",r03_raw,["Meter Name","Meter"],"m03_meter"); m03_meter_code=sel("Meter code",r03_raw,["Meter Code"],"m03_meter_code"); m03_comm=sel("Commodity",r03_raw,["Commodity"],"m03_comm",True)
with st.expander("Report-19 usage mapping",True):
    a,b,c=st.columns(3)
    with a:
        m19_site=sel("Site / building name",r19_raw,["Building Name","Site Name","Place Name","Site"],"m19_site",True); m19_acct=sel("Account number",r19_raw,["Account Number","Acct Number","Account"],"m19_acct",True); m19_meter=sel("Meter name",r19_raw,["Meter Name","Meter"],"m19_meter"); m19_meter_code=sel("Meter code",r19_raw,["Meter Code"],"m19_meter_code")
    with b:
        m19_comm=sel("Commodity",r19_raw,["Commodity"],"m19_comm",True); m19_month=sel("Month / period",r19_raw,["Month","Billing Period","Period","Date"],"m19_month",True); m19_invoice=sel("Invoice number",r19_raw,["Invoice Number","Invoice","Bill Number"],"m19_invoice")
    with c:
        m19_usage=sel("Usage",r19_raw,["Use","Usage","Consumption","Actual Use"],"m19_usage",True); m19_unit=sel("Usage unit",r19_raw,["Use Unit","Usage Unit","Unit","UOM"],"m19_unit",True); m19_vendor=sel("Vendor",r19_raw,["Vendor","Vendor Name","Utility"],"m19_vendor")
if not all([m03_site,m03_acct,m03_comm,m19_site,m19_acct,m19_comm,m19_month,m19_usage,m19_unit]):
    st.warning("Please select all required fields marked with *."); st.stop()
st.sidebar.header("Run settings"); support_rows=st.sidebar.slider("Rows sampled from Reports 13/21/26",50,5000,500,50); max_items=st.sidebar.slider("Max records per QA rule",100,10000,3000,100); tolerance=st.sidebar.slider("Report-26 vs Report-19 tolerance %",0.1,10.0,1.0,0.1); run=st.sidebar.button("Run emissions export QA",type="primary")
if not run and "corr_v13" not in st.session_state:
    st.success("Files and mappings are ready. Click Run emissions export QA in the sidebar."); st.stop()
if run:
    m03={"site_name":m03_site,"site_code":m03_site_code,"country":m03_country,"state":m03_state,"account_number":m03_acct,"account_name":m03_acct_name,"account_status":m03_acct_status,"meter_name":m03_meter,"meter_code":m03_meter_code,"commodity":m03_comm,"vendor":m03_vendor}
    m19={"site_name":m19_site,"account_number":m19_acct,"meter_name":m19_meter,"meter_code":m19_meter_code,"commodity":m19_comm,"month":m19_month,"usage":m19_usage,"unit":m19_unit,"invoice":m19_invoice,"vendor":m19_vendor}
    with st.spinner("Building EnergyCAP correction and risk registers..."):
        master=norm_master(r03_raw,m03); usage=norm_usage(r19_raw,m19,"Report-19"); r13=norm_support(r13_raw,m19,"Report-13",support_rows) if not r13_raw.empty else pd.DataFrame(); r21=norm_support(r21_raw,m19,"Report-21",support_rows) if not r21_raw.empty else pd.DataFrame(); r26=norm_support(r26_raw,m19,"Report-26",support_rows) if not r26_raw.empty else pd.DataFrame(); corr,risk=build_registers(master,usage,r13,r21,r26,tolerance,max_items); sites=site_ready(usage,corr,risk); sc=score(corr,risk,usage); mapping=pd.DataFrame([{"report":"Report-03","field":k,"column":v} for k,v in m03.items()]+[{"report":"Report-19","field":k,"column":v} for k,v in m19.items()])
        st.session_state.update({"corr_v13":corr,"risk_v13":risk,"sites_v13":sites,"score_v13":sc,"master_v13":master,"usage_v13":usage,"mapping_v13":mapping})
corr=st.session_state["corr_v13"]; risk=st.session_state["risk_v13"]; sites=st.session_state["sites_v13"]; sc=st.session_state["score_v13"]; master=st.session_state["master_v13"]; usage=st.session_state["usage_v13"]; mapping=st.session_state["mapping_v13"]
st.divider(); k1,k2,k3,k4,k5=st.columns(5); k1.metric("Readiness score",f"{sc}/100"); k2.metric("Correction records",f"{len(corr):,}"); k3.metric("Risk records",f"{len(risk):,}"); k4.metric("Impacted MWh",f"{corr.impacted_mwh.sum():,.1f}" if not corr.empty else "0.0"); k5.metric("Impacted Dth",f"{corr.impacted_dth.sum():,.1f}" if not corr.empty else "0.0")
if sc>=90 and corr.empty: st.success("Ready: no correction records detected. Review risk flags before final export approval.")
elif sc>=75: st.warning("Conditional: review correction and risk registers before emissions export.")
else: st.error("Blocked: material correction items should be resolved before emissions export.")
t1,t2,t3,t4,t5,t6=st.tabs(["Correction Register","Risk Review Register","Site Readiness","Summary","Normalized Data","Downloads"])
cols=["severity","energycap_object_type","record_grain","energycap_record_to_review","site_name","account_number","meter_name","meter_code","commodity","months_impacted","qa_domain","issue","recommended_energycap_fix_or_review","impacted_mwh","impacted_dth","estimated_tco2e_exposure","source_reports","evidence"]
with t1:
    st.subheader("Correction Register — records to fix in EnergyCAP")
    st.success("No correction records detected.") if corr.empty else st.dataframe(corr[[c for c in cols if c in corr]],use_container_width=True,height=700)
with t2:
    st.subheader("Risk Review Register — records to review before export")
    st.write("These are not necessarily wrong, but they can create emissions-data risk such as double counting or inconsistent treatment.")
    st.success("No risk records detected.") if risk.empty else st.dataframe(risk[[c for c in cols if c in risk]],use_container_width=True,height=700)
with t3: st.subheader("Site readiness"); st.dataframe(sites,use_container_width=True,height=650)
with t4:
    st.subheader("Summary"); a,b=st.columns(2)
    with a:
        if not corr.empty: st.plotly_chart(px.bar(corr.groupby("qa_domain",as_index=False).agg(records=("register_id","count")),x="qa_domain",y="records",title="Correction records by QA domain"),use_container_width=True)
        else: st.info("No correction records.")
    with b:
        if not risk.empty: st.plotly_chart(px.bar(risk.groupby("qa_domain",as_index=False).agg(records=("register_id","count")),x="qa_domain",y="records",title="Risk records by QA domain"),use_container_width=True)
        else: st.info("No risk records.")
with t5:
    st.subheader("Normalized Data"); st.markdown("**Confirmed mapping**"); st.dataframe(mapping,use_container_width=True); st.markdown("**Report-03 normalized hierarchy preview**"); st.dataframe(master.head(1000),use_container_width=True,height=350); st.markdown("**Report-19 normalized usage preview**"); st.dataframe(usage.head(1000),use_container_width=True,height=350)
with t6:
    st.subheader("Downloads"); st.download_button("Download Correction Register",corr.to_csv(index=False).encode("utf-8"),"energycap_correction_register.csv","text/csv"); st.download_button("Download Risk Review Register",risk.to_csv(index=False).encode("utf-8"),"energycap_risk_review_register.csv","text/csv"); st.download_button("Download Site Readiness",sites.to_csv(index=False).encode("utf-8"),"energycap_site_readiness.csv","text/csv"); st.download_button("Download Normalized Report-03",master.to_csv(index=False).encode("utf-8"),"normalized_report03_master.csv","text/csv"); st.download_button("Download Normalized Report-19",usage.to_csv(index=False).encode("utf-8"),"normalized_report19_usage.csv","text/csv"); st.download_button("Download Confirmed Mapping",mapping.to_csv(index=False).encode("utf-8"),"confirmed_column_mapping.csv","text/csv")
st.caption("EnergyCAP Emissions Export QA Workbench v13 — bulk upload + object-level correction and risk registers.")

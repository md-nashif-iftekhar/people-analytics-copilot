"""Shared utilities for all analytics routers."""
import pandas as pd
from pathlib import Path
from fastapi import HTTPException

UPLOAD_DIR = Path("uploads")


def load_csv(filename: str, required_cols: list[str] = None) -> pd.DataFrame:
    """Load a CSV from the uploads folder with optional column validation."""
    path = UPLOAD_DIR / filename
    if not path.exists():
        raise HTTPException(
            404,
            f"Dataset '{filename}' not found. Upload it first via POST /api/upload"
        )
    df = pd.read_csv(path)
    if required_cols:
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            raise HTTPException(
                422,
                f"Dataset '{filename}' is missing required columns: {missing}. "
                f"Found: {list(df.columns)}"
            )
    return df


def df_info(df: pd.DataFrame) -> dict:
    """Return basic info about a dataframe."""
    return {
        "rows": len(df),
        "columns": list(df.columns),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "missing": df.isnull().sum().to_dict(),
    }


def corr_matrix(df: pd.DataFrame, target: str = None) -> dict:
    """Return correlation matrix (optionally sorted by target column)."""
    num = df.select_dtypes(include="number")
    corr = num.corr().round(3)
    if target and target in corr:
        sorted_cols = corr[target].abs().sort_values(ascending=False).index.tolist()
        corr = corr.loc[sorted_cols, sorted_cols]
    return corr.to_dict()


def generate_insights() -> dict:
    """Generate natural-language findings from available datasets in uploads/.

    Returns a dict with keys: findings (list) and total (int).
    """
    import numpy as np

    findings = []

    tv_path = UPLOAD_DIR / "fau_clinic_turnover_data.csv"
    if tv_path.exists():
        df = pd.read_csv(tv_path)
        # overall turnover rate
        if 'left' in df.columns:
            rate = round(df['left'].mean() * 100, 1)
            findings.append({"icon": "↺", "color": "red",
                "text": f"{rate}% of employees left — across {len(df):,} records."})
        if 'job_role' in df.columns and 'left' in df.columns:
            by_role = (df.groupby('job_role')['left'].mean() * 100).round(1)
            if len(by_role):
                top_role = by_role.idxmax()
                findings.append({"icon": "⚠", "color": "amber",
                    "text": f"{top_role.replace('_', ' ')} shows the highest turnover at {by_role.max()}%."})
        if 'satisfaction_level' in df.columns and 'left' in df.columns:
            ls = round(df[df['left']==1]['satisfaction_level'].mean(), 2)
            ss = round(df[df['left']==0]['satisfaction_level'].mean(), 2)
            if ss:
                findings.append({"icon": "◈", "color": "blue",
                    "text": f"Employees who left averaged {ls} satisfaction vs {ss} for those who stayed — a {round((ss-ls)/ss*100,1)}% gap."})
        if 'average_montly_hours' in df.columns and 'left' in df.columns:
            lh = round(df[df['left']==1]['average_montly_hours'].mean(), 0)
            sh = round(df[df['left']==0]['average_montly_hours'].mean(), 0)
            if lh and sh and lh > sh:
                findings.append({"icon": "⏱", "color": "amber",
                    "text": f"Leavers worked {int(lh-sh)} more hours/month on average ({int(lh)}h vs {int(sh)}h for those who stayed)."})
        if 'salary' in df.columns and 'left' in df.columns:
            low_rate = round(df[df['salary']=='low']['left'].mean() * 100, 1)
            high_rate = round(df[df['salary']=='high']['left'].mean() * 100, 1)
            findings.append({"icon": "◇", "color": "green",
                "text": f"Low-salary employees leave at {low_rate}% vs {high_rate}% for high-salary — a {round(low_rate-high_rate,1)}pt difference."})

    wb_path = UPLOAD_DIR / "fau_clinic_employee_wellbeing.csv"
    if wb_path.exists():
        df = pd.read_csv(wb_path)
        if 'DAILY_STRESS' in df.columns and 'WORK_LIFE_BALANCE_SCORE' in df.columns:
            stress_wlb = df.groupby('DAILY_STRESS')['WORK_LIFE_BALANCE_SCORE'].mean().round(1)
            if not stress_wlb.empty:
                hi = stress_wlb.index.max(); lo = stress_wlb.index.min()
                findings.append({"icon": "◇", "color": "purple",
                    "text": f"High-stress employees (level {hi}) average a WLB score of {stress_wlb[hi]:.0f} vs {stress_wlb[lo]:.0f} for low-stress (level {lo})."})
        if 'GENDER' in df.columns and 'DAILY_STRESS' in df.columns:
            gs = df.groupby('GENDER')['DAILY_STRESS'].mean().round(2)
            if len(gs) >= 2:
                higher = gs.idxmax(); lower = gs.idxmin()
                findings.append({"icon": "◎", "color": "blue",
                    "text": f"{higher} employees report higher average daily stress ({gs[higher]} vs {gs[lower]} for {lower})."})
        if 'SLEEP_HOURS' in df.columns and 'WORK_LIFE_BALANCE_SCORE' in df.columns:
            sleep_wlb = df.groupby('SLEEP_HOURS')['WORK_LIFE_BALANCE_SCORE'].mean()
            if not sleep_wlb.empty:
                best_sleep = sleep_wlb.idxmax()
                findings.append({"icon": "◈", "color": "green",
                    "text": f"Employees sleeping {best_sleep}h/night report the highest average WLB score ({sleep_wlb[best_sleep]:.0f})."})

    rec_path = UPLOAD_DIR / "fau_clinic_recruitment.csv"
    if rec_path.exists():
        df = pd.read_csv(rec_path)
        if 'hired' in df.columns:
            hired = df['hired'].map({'TRUE': 1, 'FALSE': 0, True: 1, False: 0})
            hire_rate = round(hired.mean() * 100, 1)
            findings.append({"icon": "⬡", "color": "blue",
                "text": f"Overall hire rate is {hire_rate}% across {len(df):,} applicants."})
        if 'gender' in df.columns and 'hired' in df.columns:
            gr = df.groupby('gender').apply(lambda x: x['hired'].map({'TRUE':1,'FALSE':0,True:1,False:0}).mean() * 100).round(1)
            if len(gr) >= 2:
                findings.append({"icon": "◎", "color": "amber",
                    "text": f"Hire rate by gender: {' vs '.join(f'{g}: {v}%' for g,v in gr.items())}."})

    return {"findings": findings, "total": len(findings)}

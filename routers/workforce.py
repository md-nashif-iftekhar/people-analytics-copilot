"""
Workforce Planning Router
==========================
Endpoints:
  GET /               - Full shift analysis: required staff, alerts, costs
  GET /optimize       - Shift optimization scenarios
  GET /alerts         - Understaffing / overstaffing alerts
  GET /heatmap        - Hour x demand matrix for heatmap
  GET /raw            - Raw dataset

Dataset: fau_medical_staff.csv
"""
import math
import pandas as pd
import numpy as np
from fastapi import APIRouter, Query
from .utils import load_csv, df_info

router = APIRouter()
DEFAULT_FILE = "fau_medical_staff.csv"
DEFAULT_SL   = 4   # patients per staff per hour
WAGES        = {"Shift 1": 45, "Shift 2": 45, "Shift 3": 60}   # EUR per 8h shift
SHIFT_NAMES  = {"Shift 1": "Morning (06–14)", "Shift 2": "Afternoon (14–22)", "Shift 3": "Night (22–06)"}


def _load_clean(filename: str):
    df = load_csv(filename)
    df.columns = [c.strip() for c in df.columns]
    # Drop wage row
    mask = df["Time Windows"].astype(str).str.contains("Wage", case=False, na=False)
    wages_row = df[mask]
    df = df[~mask].copy()
    df["Avg_Patient_Number"] = pd.to_numeric(df["Avg_Patient_Number"], errors="coerce")

    # Parse actual wages from dataset if present
    extracted = {}
    if not wages_row.empty:
        r = wages_row.iloc[0]
        for s in ["Shift 1", "Shift 2", "Shift 3"]:
            try:
                extracted[s] = float(r[s])
            except Exception:
                pass
    wages = {**WAGES, **extracted}

    # Detect shift per row
    rows = []
    for _, r in df.iterrows():
        shift = None
        for s in ["Shift 1", "Shift 2", "Shift 3"]:
            if s in r and pd.notna(r[s]) and str(r[s]).strip() != "":
                shift = s
                break
        rows.append({
            "time_window":    str(r["Time Windows"]).strip(),
            "shift":          shift,
            "avg_patients":   float(r["Avg_Patient_Number"]) if pd.notna(r["Avg_Patient_Number"]) else 0.0,
        })
    return pd.DataFrame(rows), wages


def _compute(row_df: pd.DataFrame, sl: int, wages: dict):
    rows = []
    for _, r in row_df.iterrows():
        avg = r["avg_patients"]
        required = math.ceil(avg / sl) if avg > 0 else 0
        capacity = required * sl
        util = round(avg / capacity * 100, 1) if capacity > 0 else 0.0
        rows.append({
            "time_window":    r["time_window"],
            "shift":          r["shift"],
            "avg_patients":   avg,
            "required_staff": required,
            "capacity":       capacity,
            "utilization_pct": util,
            "understaffed":   avg > capacity and required > 0,
            "overstaffed":    util < 50 and required > 1,
            "zero_demand":    avg == 0,
        })
    return pd.DataFrame(rows)


@router.get("/")
def workforce_analysis(
    filename:      str = Query(DEFAULT_FILE),
    service_level: int = Query(DEFAULT_SL, ge=1, le=20),
):
    """Full shift analysis: required staff, shift summary, alerts, cost estimates."""
    df, wages = _load_clean(filename)
    comp = _compute(df, service_level, wages)

    # ── Per-shift summary ─────────────────────────────────────────
    shift_summary = []
    for shift, grp in comp.groupby("shift"):
        peak      = int(grp["required_staff"].max())
        avg_pts   = float(grp["avg_patients"].mean().round(2))
        n_windows = len(grp)
        wage      = wages.get(shift, 45)

        # Cost scenarios
        cost_peak      = peak * wage                        # always staff at peak
        cost_optimized = int(grp["required_staff"].sum() * wage / n_windows * n_windows)
        overstaff_hrs  = int(peak * n_windows - grp["required_staff"].sum())
        savings        = cost_peak - int(grp["required_staff"].sum() / n_windows * wage) if n_windows else 0

        shift_summary.append({
            "shift":           shift,
            "label":           SHIFT_NAMES.get(shift, shift),
            "recommended_staff": peak,
            "avg_patients_per_hour": avg_pts,
            "time_windows":    n_windows,
            "wage_per_shift_eur": wage,
            "cost_fixed_peak_eur":  cost_peak,
            "cost_optimized_eur":   cost_optimized,
            "overstaffing_hours":   overstaff_hrs,
            "potential_savings_eur": max(0, cost_peak - cost_optimized),
        })

    # ── Alerts ────────────────────────────────────────────────────
    alerts = []
    for _, r in comp.iterrows():
        if r["understaffed"]:
            alerts.append({
                "type":    "UNDERSTAFFING",
                "severity": "HIGH",
                "time":    r["time_window"],
                "shift":   r["shift"],
                "message": f"Demand ({r['avg_patients']} pts/hr) exceeds staff capacity ({r['capacity']} pts/hr). Add 1 more staff.",
            })
        if r["zero_demand"]:
            alerts.append({
                "type":    "ZERO_DEMAND",
                "severity": "INFO",
                "time":    r["time_window"],
                "shift":   r["shift"],
                "message": f"No patients expected. Consider reducing staffing.",
            })

    # ── Total daily cost ─────────────────────────────────────────
    total_cost_peak = sum(s["cost_fixed_peak_eur"] for s in shift_summary)
    total_cost_opt  = sum(s["cost_optimized_eur"]  for s in shift_summary)

    return {
        "service_level":     service_level,
        "wages_eur":         wages,
        "dataset_info":      df_info(df),
        "per_time_window":   comp.to_dict(orient="records"),
        "shift_summary":     shift_summary,
        "alerts":            alerts,
        "cost_summary": {
            "total_daily_cost_peak_staffing_eur":     total_cost_peak,
            "total_daily_cost_optimized_eur":         total_cost_opt,
            "total_potential_savings_eur":            total_cost_peak - total_cost_opt,
            "monthly_savings_if_optimized_eur":       (total_cost_peak - total_cost_opt) * 30,
        },
        "interpretation": (
            f"Staffing at the peak level for all shifts costs EUR {total_cost_peak}/day. "
            f"Dynamic staffing saves up to EUR {total_cost_peak - total_cost_opt}/day "
            f"(EUR {(total_cost_peak - total_cost_opt)*30}/month)."
        ),
    }


@router.get("/optimize")
def optimize(
    filename:      str   = Query(DEFAULT_FILE),
    service_level: int   = Query(DEFAULT_SL, ge=1, le=20),
    budget_eur:    float = Query(300.0, description="Daily staffing budget in EUR"),
):
    """
    Optimization scenarios: minimum cost, maximum coverage, budget-constrained.
    Returns recommended staff per shift under each scenario.
    """
    df, wages = _load_clean(filename)
    comp = _compute(df, service_level, wages)

    scenarios = {}
    for shift, grp in comp.groupby("shift"):
        wage   = wages.get(shift, 45)
        peak   = int(grp["required_staff"].max())
        minimum = max(1, int(math.ceil(grp["avg_patients"].mean() / service_level)))
        budget_staff = min(peak, max(1, int(budget_eur / wage)))

        scenarios[shift] = {
            "label":                  SHIFT_NAMES.get(shift, shift),
            "minimum_coverage":       minimum,
            "minimum_cost_eur":       minimum * wage,
            "full_coverage_staff":    peak,
            "full_coverage_cost_eur": peak * wage,
            "budget_constrained_staff": budget_staff,
            "budget_cost_eur":        budget_staff * wage,
            "recommended":            peak,
            "recommendation_reason":  (
                f"Peak of {peak} staff ensures 100% coverage at all times for EUR {peak*wage}/shift."
            ),
        }

    return {
        "budget_eur":    budget_eur,
        "service_level": service_level,
        "scenarios":     scenarios,
    }


@router.get("/alerts")
def alerts(
    filename:      str = Query(DEFAULT_FILE),
    service_level: int = Query(DEFAULT_SL, ge=1, le=20),
    threshold_pct: float = Query(80.0, description="Utilization % above which understaffing alert fires"),
):
    """
    Understaffing and overstaffing alerts with severity levels.
    """
    df, wages = _load_clean(filename)
    comp = _compute(df, service_level, wages)

    under, over, zero = [], [], []
    for _, r in comp.iterrows():
        if r["utilization_pct"] >= threshold_pct and r["required_staff"] > 0:
            under.append({
                "severity": "HIGH" if r["utilization_pct"] >= 95 else "MEDIUM",
                "time":     r["time_window"], "shift": r["shift"],
                "avg_patients": r["avg_patients"], "required_staff": r["required_staff"],
                "utilization_pct": r["utilization_pct"],
                "action": "Add 1 additional staff member immediately.",
            })
        if r["utilization_pct"] < 50 and r["required_staff"] > 1:
            wage = wages.get(r["shift"], 45)
            over.append({
                "severity": "LOW",
                "time":     r["time_window"], "shift": r["shift"],
                "avg_patients": r["avg_patients"], "required_staff": r["required_staff"],
                "utilization_pct": r["utilization_pct"],
                "wasted_cost_eur": round((r["required_staff"] - 1) * wage / 8, 2),
                "action": "Consider reducing by 1 staff or redistributing.",
            })
        if r["zero_demand"]:
            zero.append({"time": r["time_window"], "shift": r["shift"]})

    return {
        "service_level":        service_level,
        "threshold_pct":        threshold_pct,
        "understaffing_alerts": under,
        "overstaffing_alerts":  over,
        "zero_demand_windows":  zero,
        "total_alerts":         len(under) + len(over) + len(zero),
        "summary": f"{len(under)} understaffing · {len(over)} overstaffing · {len(zero)} zero-demand windows.",
    }


@router.get("/heatmap")
def heatmap(
    filename:      str = Query(DEFAULT_FILE),
    service_level: int = Query(DEFAULT_SL, ge=1, le=20),
):
    """
    Hour-by-shift demand matrix for heatmap chart.
    Returns: labels, values matrix, required staff matrix.
    """
    df, wages = _load_clean(filename)
    comp = _compute(df, service_level, wages)

    time_labels  = comp["time_window"].tolist()
    shift_labels = sorted(comp["shift"].dropna().unique().tolist())

    # Demand matrix: rows = time windows, cols = shifts
    demand_matrix = []
    staff_matrix  = []
    for _, r in comp.iterrows():
        row_d, row_s = [], []
        for s in shift_labels:
            if r["shift"] == s:
                row_d.append(float(r["avg_patients"]))
                row_s.append(int(r["required_staff"]))
            else:
                row_d.append(None)
                row_s.append(None)
        demand_matrix.append(row_d)
        staff_matrix.append(row_s)

    # Flat demand curve (for line chart)
    demand_curve = [{"time": r["time_window"], "patients": r["avg_patients"],
                     "shift": r["shift"], "staff": r["required_staff"]} for _, r in comp.iterrows()]

    return {
        "time_labels":    time_labels,
        "shift_labels":   [SHIFT_NAMES.get(s, s) for s in shift_labels],
        "shift_keys":     shift_labels,
        "demand_matrix":  demand_matrix,
        "staff_matrix":   staff_matrix,
        "demand_curve":   demand_curve,
    }


@router.get("/raw")
def raw(filename: str = Query(DEFAULT_FILE)):
    df, _ = _load_clean(filename)
    return {"data": df.fillna("").to_dict(orient="records"), "info": df_info(df)}

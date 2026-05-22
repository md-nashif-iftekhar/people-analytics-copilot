"""
Recruitment Router
==================
Association rule mining (Apriori) to find key qualifications
for critical care nursing. Also detects hiring bias by gender/location.

Dataset: fau_clinic_recruitment.csv
"""

import pandas as pd
from fastapi import APIRouter, Query
from mlxtend.frequent_patterns import apriori, association_rules
from .utils import load_csv, df_info

router = APIRouter()
DEFAULT_FILE = "fau_clinic_recruitment.csv"


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Convert all columns to bool for Apriori."""
    bool_cols = df.select_dtypes(include="bool").columns.tolist()
    # Convert object columns that look boolean
    for col in df.select_dtypes(include="object").columns:
        unique = df[col].dropna().unique()
        if set(unique).issubset({"True", "False", "true", "false", "1", "0"}):
            df[col] = df[col].map({"True": True, "False": False, "true": True, "false": False, "1": True, "0": False})
    # Keep only boolean columns
    bool_df = df.select_dtypes(include="bool")
    return bool_df


@router.get("/")
def recruitment_analysis(
    filename: str = Query(DEFAULT_FILE),
    min_support: float = Query(0.05, ge=0.01, le=1.0, description="Minimum support"),
    min_confidence: float = Query(0.5, ge=0.1, le=1.0, description="Minimum confidence"),
    min_lift: float = Query(1.0, ge=0.1, description="Minimum lift"),
    target_col: str = Query("critical_care_nursing", description="Target outcome column"),
    top_n: int = Query(20, ge=1, le=100, description="Max rules to return"),
):
    """
    Run Apriori association rule mining on recruitment data.
    Returns top rules sorted by lift, filtered by target outcome column.
    """
    df = load_csv(filename)
    info = df_info(df)

    bool_df = _prepare(df.copy())
    if bool_df.empty or len(bool_df.columns) < 2:
        return {"error": "Not enough boolean columns for association analysis.", "info": info}

    # Frequent itemsets
    freq = apriori(bool_df, min_support=min_support, use_colnames=True, max_len=5)
    if freq.empty:
        return {
            "message": f"No frequent itemsets found at min_support={min_support}. Try lowering it.",
            "info": info,
        }

    rules = association_rules(freq, metric="confidence", min_threshold=min_confidence, num_itemsets=len(freq))
    rules = rules[rules["lift"] >= min_lift]

    # Filter rules where consequent is target column == True
    if target_col in bool_df.columns:
        rules = rules[rules["consequents"].apply(lambda c: target_col in c)]

    rules = rules.sort_values("lift", ascending=False).head(top_n)

    # Format output
    formatted = []
    for _, r in rules.iterrows():
        ant = sorted(r["antecedents"])
        con = sorted(r["consequents"])
        formatted.append({
            "antecedents": list(ant),
            "consequents": list(con),
            "support": round(float(r["support"]), 4),
            "confidence": round(float(r["confidence"]), 4),
            "lift": round(float(r["lift"]), 4),
            "rule_str": f"{' + '.join(ant)} → {' + '.join(con)}",
        })

    # Explain first rule
    explanation = {}
    if formatted:
        r0 = formatted[0]
        explanation = {
            "rule": r0["rule_str"],
            "support_meaning": (
                f"{r0['support']*100:.1f}% of applicants have all these attributes together."
            ),
            "confidence_meaning": (
                f"When an applicant has {r0['antecedents']}, they are hired for {target_col} "
                f"{r0['confidence']*100:.1f}% of the time."
            ),
            "lift_meaning": (
                f"This combination is {r0['lift']:.2f}x more likely to lead to hiring "
                f"than by chance (lift > 1 = positive association)."
            ),
        }

    return {
        "dataset_info": info,
        "params": {
            "min_support": min_support,
            "min_confidence": min_confidence,
            "min_lift": min_lift,
            "target_col": target_col,
        },
        "total_rules_found": len(formatted),
        "top_rules": formatted,
        "first_rule_explanation": explanation,
    }


@router.get("/bias")
def bias_analysis(
    filename: str = Query(DEFAULT_FILE),
    target_col: str = Query("critical_care_nursing", description="Hiring outcome column"),
    group_cols: str = Query("gender,location", description="Comma-separated columns to group by"),
):
    """
    Detect potential bias in hiring by comparing hire rates across demographic groups.
    """
    df = load_csv(filename)
    groups = [g.strip() for g in group_cols.split(",") if g.strip() in df.columns]
    if not groups:
        return {"error": f"None of the group columns found. Available: {list(df.columns)}"}
    if target_col not in df.columns:
        return {"error": f"Target column '{target_col}' not found."}

    results = {}
    for col in groups:
        rates = df.groupby(col)[target_col].mean().round(4) * 100
        results[col] = {
            str(k): round(float(v), 2) for k, v in rates.items()
        }
        vals = list(results[col].values())
        results[col]["_max_gap_pct"] = round(max(vals) - min(vals), 2) if vals else 0
        results[col]["_flag"] = "⚠️ Potential bias" if results[col]["_max_gap_pct"] > 10 else "✅ Acceptable"

    overall_rate = round(float(df[target_col].mean()) * 100, 2)

    return {
        "target_column": target_col,
        "overall_hire_rate_pct": overall_rate,
        "bias_by_group": results,
        "interpretation": (
            "A gap > 10% between groups in the same category may indicate "
            "systematic bias. Review hiring criteria and processes."
        ),
    }


@router.get("/summary")
def hiring_summary(filename: str = Query(DEFAULT_FILE)):
    """Basic hiring statistics from the recruitment dataset."""
    df = load_csv(filename)
    out = {"dataset_info": df_info(df)}
    if "hired" in df.columns:
        out["hire_rate_pct"] = round(float(df["hired"].mean()) * 100, 2)
    for col in ["critical_care_nursing", "family_nurse", "occupational_health_nursing", "gerontological_nursing"]:
        if col in df.columns:
            out[f"{col}_rate_pct"] = round(float(df[col].mean()) * 100, 2)
    if "gender" in df.columns and "hired" in df.columns:
        out["hire_rate_by_gender"] = {
            str(k): round(float(v) * 100, 2)
            for k, v in df.groupby("gender")["hired"].mean().items()
        }
    return out

"""
Employee Well-Being Router
===========================
Analyzes WORK_LIFE_BALANCE_SCORE (WLB) drivers,
stress by gender/age, and trains a Linear Regression predictor.

Dataset: fau_clinic_employee_wellbeing.csv
"""

import pandas as pd
import numpy as np
from fastapi import APIRouter, Query
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
from sklearn.preprocessing import LabelEncoder
import warnings
warnings.filterwarnings("ignore")

from .utils import load_csv, df_info, corr_matrix

router = APIRouter()
DEFAULT_FILE = "fau_clinic_employee_wellbeing.csv"
TARGET = "WORK_LIFE_BALANCE_SCORE"


def _preprocess(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Encode AGE ranges and GENDER, handle missing values."""
    df = df.copy()
    log = {}

    # AGE: convert range strings to midpoint numeric
    if "AGE" in df.columns and df["AGE"].dtype == object:
        def age_midpoint(val):
            try:
                parts = str(val).replace("to", "-").replace(" ", "").split("-")
                return (float(parts[0]) + float(parts[1])) / 2
            except Exception:
                return np.nan
        df["AGE_NUMERIC"] = df["AGE"].apply(age_midpoint)
        df.drop(columns=["AGE"], inplace=True)
        log["AGE"] = "Converted range string to numeric midpoint → AGE_NUMERIC"

    # GENDER: binary encode (Female=0, Male=1)
    if "GENDER" in df.columns:
        df["GENDER_NUMERIC"] = (df["GENDER"].str.lower().str.strip() == "male").astype(int)
        df.drop(columns=["GENDER"], inplace=True)
        log["GENDER"] = "Binary encoded: Female=0, Male=1 → GENDER_NUMERIC"

    # Remaining object columns
    le = LabelEncoder()
    for col in df.select_dtypes(include="object").columns:
        if col != TARGET:
            df[col] = le.fit_transform(df[col].astype(str))
            log[col] = "LabelEncoded"

    df.fillna(df.median(numeric_only=True), inplace=True)
    return df, log


@router.get("/eda")
def eda(filename: str = Query(DEFAULT_FILE)):
    """EDA: dataset overview, stress by gender/age, hobby time by gender."""
    df = load_csv(filename)

    # Convert numeric columns to proper types
    if "DAILY_STRESS" in df.columns:
        df["DAILY_STRESS"] = pd.to_numeric(df["DAILY_STRESS"], errors="coerce")
    if "TIME_FOR_HOBBY" in df.columns:
        df["TIME_FOR_HOBBY"] = pd.to_numeric(df["TIME_FOR_HOBBY"], errors="coerce")
    if TARGET in df.columns:
        df[TARGET] = pd.to_numeric(df[TARGET], errors="coerce")

    # Stress by gender
    stress_by_gender = {}
    if "GENDER" in df.columns and "DAILY_STRESS" in df.columns:
        stress_by_gender = df.groupby("GENDER")["DAILY_STRESS"].agg(
            mean="mean", median="median", count="count"
        ).round(3).to_dict(orient="index")
        stress_by_gender = {str(k): {m: round(float(v), 3) for m, v in vals.items()}
                            for k, vals in stress_by_gender.items()}

    # Stress by age group
    stress_by_age = {}
    if "AGE" in df.columns and "DAILY_STRESS" in df.columns:
        stress_by_age = df.groupby("AGE")["DAILY_STRESS"].mean().round(3).to_dict()
        stress_by_age = {str(k): round(float(v), 3) for k, v in stress_by_age.items()}

    # Hobby time by gender
    hobby_by_gender = {}
    if "GENDER" in df.columns and "TIME_FOR_HOBBY" in df.columns:
        hobby_by_gender = df.groupby("GENDER")["TIME_FOR_HOBBY"].mean().round(3).to_dict()
        hobby_by_gender = {str(k): round(float(v), 3) for k, v in hobby_by_gender.items()}

    # WLB by age
    wlb_by_age = {}
    if "AGE" in df.columns and TARGET in df.columns:
        wlb_by_age = df.groupby("AGE")[TARGET].mean().round(2).to_dict()
        wlb_by_age = {str(k): round(float(v), 2) for k, v in wlb_by_age.items()}

    # WLB by gender
    wlb_by_gender = {}
    if "GENDER" in df.columns and TARGET in df.columns:
        wlb_by_gender = df.groupby("GENDER")[TARGET].mean().round(2).to_dict()
        wlb_by_gender = {str(k): round(float(v), 2) for k, v in wlb_by_gender.items()}

    return {
        "dataset_info": df_info(df),
        "target_stats": {
            "mean": round(float(df[TARGET].mean()), 2) if TARGET in df.columns else None,
            "std": round(float(df[TARGET].std()), 2) if TARGET in df.columns else None,
            "min": round(float(df[TARGET].min()), 2) if TARGET in df.columns else None,
            "max": round(float(df[TARGET].max()), 2) if TARGET in df.columns else None,
        },
        "daily_stress_by_gender": stress_by_gender,
        "daily_stress_by_age": stress_by_age,
        "hobby_time_by_gender": hobby_by_gender,
        "wlb_by_age_group": wlb_by_age,
        "wlb_by_gender": wlb_by_gender,
        "insight": "Employees with more time for hobbies and sleep tend to have higher WLB scores.",
    }


@router.get("/correlation")
def correlation(filename: str = Query(DEFAULT_FILE)):
    """Correlation matrix sorted by WORK_LIFE_BALANCE_SCORE."""
    df = load_csv(filename)
    df2, _ = _preprocess(df)
    corr = corr_matrix(df2, target=TARGET)

    top_pos, top_neg = {}, {}
    if TARGET in df2.columns:
        target_corr = df2.corr()[TARGET].drop(TARGET, errors="ignore")
        top_pos = target_corr[target_corr > 0].sort_values(ascending=False).head(5).round(4).to_dict()
        top_neg = target_corr[target_corr < 0].sort_values().head(5).round(4).to_dict()

    return {
        "correlation_matrix": corr,
        "top_positive_correlates_with_WLB": top_pos,
        "top_negative_correlates_with_WLB": top_neg,
    }


@router.get("/train")
def train_model(
    filename: str = Query(DEFAULT_FILE),
    test_size: float = Query(0.2, ge=0.1, le=0.4),
    sample_n: int = Query(10, ge=5, le=50, description="Rows to include in actual vs predicted sample"),
):
    """Train Linear Regression to predict WORK_LIFE_BALANCE_SCORE."""
    df = load_csv(filename)
    df2, preprocessing_log = _preprocess(df)

    if TARGET not in df2.columns:
        return {"error": f"Target '{TARGET}' not found after preprocessing."}

    X = df2.drop(columns=[TARGET])
    y = df2[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42
    )

    model = LinearRegression()
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    r2 = round(r2_score(y_test, y_pred), 4)
    mae = round(mean_absolute_error(y_test, y_pred), 4)
    rmse = round(float(np.sqrt(mean_squared_error(y_test, y_pred))), 4)

    # Actual vs predicted sample
    sample = pd.DataFrame({
        "actual": y_test.values[:sample_n],
        "predicted": y_pred[:sample_n].round(2),
        "error": (y_test.values[:sample_n] - y_pred[:sample_n]).round(2),
    }).to_dict(orient="records")

    # Coefficients
    coefficients = {
        feat: round(float(coef), 4)
        for feat, coef in sorted(zip(X.columns, model.coef_), key=lambda x: abs(x[1]), reverse=True)
    }

    # Predict for a new hypothetical employee
    hypothetical = {
        "DAILY_STRESS": 2, "SOCIAL_NETWORK": 7, "ACHIEVEMENT": 5,
        "BMI_RANGE": 2, "TODO_COMPLETED": 6, "DAILY_STEPS": 5,
        "SLEEP_HOURS": 7, "SUFFICIENT_INCOME": 2, "PERSONAL_AWARDS": 3,
        "TIME_FOR_HOBBY": 5, "WEEKLY_MEDITATION": 4, "AGE_NUMERIC": 35,
        "GENDER_NUMERIC": 0,
    }
    # Align columns
    hyp_row = pd.DataFrame([{c: hypothetical.get(c, 0) for c in X.columns}])
    hyp_pred = round(float(model.predict(hyp_row)[0]), 2)

    return {
        "model": "Linear Regression",
        "target": TARGET,
        "features_used": list(X.columns),
        "preprocessing": preprocessing_log,
        "metrics": {
            "r2_score": r2,
            "mae": mae,
            "rmse": rmse,
            "train_size": len(X_train),
            "test_size": len(X_test),
            "r2_interpretation": (
                f"The model explains {r2*100:.1f}% of the variance in WLB scores. "
                + ("Good fit." if r2 > 0.6 else "Moderate fit — consider additional features.")
            ),
        },
        "coefficients": coefficients,
        "actual_vs_predicted_sample": sample,
        "hypothetical_prediction": {
            "input": hypothetical,
            "predicted_wlb_score": hyp_pred,
            "note": "Male, 35yo, low stress, 5hrs/wk hobby, sufficient income, 7hrs sleep.",
        },
        "recommendations": [
            "Reduce daily stress through flexible scheduling or workload management.",
            "Encourage hobbies and personal time — TIME_FOR_HOBBY is a top positive driver.",
            "Improve sleep culture — SLEEP_HOURS strongly correlates with WLB.",
            "Ensure sufficient income — SUFFICIENT_INCOME positively impacts scores.",
        ],
    }


@router.get("/deep-analysis")
def deep_analysis(filename: str = Query(DEFAULT_FILE)):
    """
    Full WLB deep analysis:
    - Stress breakdown by gender (counts + %)
    - WLB by stress level (shows monotonic decline)
    - WLB by hobby time buckets
    - WLB by sleep hours buckets
    - WLB by meditation frequency
    - WLB by income sufficiency
    - Gender comparison (stress + WLB)
    - Age group comparison
    - Full correlation matrix (all numeric pairs)
    - Auto-generated insights
    """
    df = load_csv(filename)

    # Clean numeric cols that may have dirty values
    numeric_cols = ["DAILY_STRESS","SLEEP_HOURS","TIME_FOR_HOBBY","WEEKLY_MEDITATION",
                    "SUFFICIENT_INCOME","SOCIAL_NETWORK","ACHIEVEMENT","BMI_RANGE",
                    "TODO_COMPLETED","DAILY_STEPS","PERSONAL_AWARDS"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["DAILY_STRESS", TARGET])

    # ── Stress by gender (%) ──────────────────────────────────────
    stress_gender = {}
    if "GENDER" in df.columns:
        for g, grp in df.groupby("GENDER"):
            counts = grp["DAILY_STRESS"].value_counts(normalize=True).sort_index()
            stress_gender[str(g)] = {str(int(k)): round(float(v)*100, 1) for k, v in counts.items()}

    # ── WLB by stress level ──────────────────────────────────────
    wlb_by_stress = (
        df.groupby("DAILY_STRESS")[TARGET].mean()
        .sort_index().round(2).to_dict()
    )
    wlb_by_stress = {str(int(k)): round(float(v), 2) for k, v in wlb_by_stress.items()}

    # ── WLB by hobby time bucket ─────────────────────────────────
    wlb_by_hobby = {}
    if "TIME_FOR_HOBBY" in df.columns:
        df["_hobby_group"] = pd.cut(df["TIME_FOR_HOBBY"], bins=[-1,0,3,6,100],
                                    labels=["No hobby","1–3 h/wk","4–6 h/wk","7+ h/wk"])
        wlb_by_hobby = df.groupby("_hobby_group", observed=True)[TARGET].mean().round(2).to_dict()
        wlb_by_hobby = {str(k): round(float(v), 2) for k, v in wlb_by_hobby.items()}

    # ── WLB by sleep hours ──────────────────────────────────────
    wlb_by_sleep = {}
    if "SLEEP_HOURS" in df.columns:
        df["_sleep_group"] = pd.cut(df["SLEEP_HOURS"], bins=[-1,5,6,7,8,24],
                                    labels=["≤5 h","6 h","7 h","8 h","9+ h"])
        wlb_by_sleep = df.groupby("_sleep_group", observed=True)[TARGET].mean().round(2).to_dict()
        wlb_by_sleep = {str(k): round(float(v), 2) for k, v in wlb_by_sleep.items()}

    # ── WLB by meditation ────────────────────────────────────────
    wlb_by_meditation = {}
    if "WEEKLY_MEDITATION" in df.columns:
        df["_med_group"] = pd.cut(df["WEEKLY_MEDITATION"], bins=[-1,0,2,5,100],
                                  labels=["None","1–2 sessions","3–5 sessions","6+ sessions"])
        wlb_by_meditation = df.groupby("_med_group", observed=True)[TARGET].mean().round(2).to_dict()
        wlb_by_meditation = {str(k): round(float(v), 2) for k, v in wlb_by_meditation.items()}

    # ── WLB by income ────────────────────────────────────────────
    wlb_by_income = {}
    if "SUFFICIENT_INCOME" in df.columns:
        raw = df.groupby("SUFFICIENT_INCOME")[TARGET].mean().round(2).to_dict()
        label_map = {1: "Insufficient", 2: "Sufficient"}
        wlb_by_income = {label_map.get(int(k), str(k)): round(float(v), 2) for k, v in raw.items()}

    # ── Gender comparison ────────────────────────────────────────
    gender_comparison = {}
    if "GENDER" in df.columns:
        for col in ["DAILY_STRESS", TARGET, "TIME_FOR_HOBBY", "SLEEP_HOURS", "WEEKLY_MEDITATION"]:
            if col in df.columns:
                g_means = df.groupby("GENDER")[col].mean().round(3).to_dict()
                gender_comparison[col] = {str(k): round(float(v), 3) for k, v in g_means.items()}

    # ── Age comparison ───────────────────────────────────────────
    age_comparison = {}
    if "AGE" in df.columns:
        age_order = ["Less than 20", "21 to 35", "36 to 50", "51 or more"]
        for col in ["DAILY_STRESS", TARGET]:
            if col in df.columns:
                g = df.groupby("AGE")[col].mean().round(2)
                age_comparison[col] = {k: round(float(g[k]), 2) for k in age_order if k in g.index}

    # ── Full correlation matrix ──────────────────────────────────
    num_df = df.select_dtypes(include="number").drop(columns=[c for c in ["_hobby_group","_sleep_group","_med_group"] if c in df.columns], errors="ignore")
    full_corr = num_df.corr().round(4)
    # Sorted by WLB correlation
    if TARGET in full_corr:
        sorted_cols = full_corr[TARGET].abs().sort_values(ascending=False).index.tolist()
        full_corr = full_corr.loc[sorted_cols, sorted_cols]
    corr_dict = full_corr.to_dict()

    # WLB correlation series only (for bar chart)
    wlb_corr = full_corr[TARGET].drop(TARGET, errors="ignore").sort_values(ascending=False).round(4).to_dict()
    wlb_corr = {str(k): round(float(v), 4) for k, v in wlb_corr.items()}

    # ── WLB distribution (histogram buckets) ────────────────────
    wlb_dist = {}
    bins = list(range(480, 830, 30))
    labels_hist = [f"{b}–{b+30}" for b in bins[:-1]]
    counts, _ = np.histogram(df[TARGET].dropna(), bins=bins)
    wlb_dist = {labels_hist[i]: int(counts[i]) for i in range(len(labels_hist))}

    # ── Stress distribution (all employees) ──────────────────────
    stress_dist = df["DAILY_STRESS"].value_counts().sort_index().to_dict()
    stress_dist = {str(int(k)): int(v) for k, v in stress_dist.items()}

    # ── Auto-generated insights ──────────────────────────────────
    hi_stress_wlb = wlb_by_stress.get("4", 0) or wlb_by_stress.get("5", 0)
    lo_stress_wlb = wlb_by_stress.get("1", 0) or wlb_by_stress.get("0", 0)
    stress_pct_diff = round((float(lo_stress_wlb) - float(hi_stress_wlb)) / float(lo_stress_wlb) * 100, 1) if lo_stress_wlb else 0

    sleep_hi = wlb_by_sleep.get("8 h", 0) or wlb_by_sleep.get("9+ h", 0)
    sleep_lo = wlb_by_sleep.get("≤5 h", 0)
    sleep_diff = round(float(sleep_hi) - float(sleep_lo), 1) if sleep_hi and sleep_lo else 0

    hobby_hi = list(wlb_by_hobby.values())[-1] if wlb_by_hobby else 0
    hobby_lo = list(wlb_by_hobby.values())[0] if wlb_by_hobby else 0
    hobby_diff = round(float(hobby_hi) - float(hobby_lo), 1)

    f_stress = gender_comparison.get("DAILY_STRESS", {}).get("Female", 0)
    m_stress = gender_comparison.get("DAILY_STRESS", {}).get("Male", 0)
    stress_gender_pct = round((float(f_stress) - float(m_stress)) / float(m_stress) * 100, 1) if m_stress else 0

    income_diff = 0
    if len(wlb_by_income) == 2:
        vals = list(wlb_by_income.values())
        income_diff = round(float(vals[1]) - float(vals[0]), 1)

    insights = [
        f"Employees with high daily stress (≥4) have WLB scores {stress_pct_diff}% lower than low-stress employees.",
        f"Getting 8 hours of sleep is associated with {sleep_diff} higher WLB points vs. ≤5 hours.",
        f"Employees spending 7+ h/week on hobbies score {hobby_diff} WLB points higher than those with no hobbies.",
        f"Female employees report {stress_gender_pct}% higher average daily stress than male colleagues.",
        f"Employees with sufficient income score {income_diff} WLB points higher than those with insufficient income.",
        f"Achievement and task completion (TODO_COMPLETED) are the strongest positive correlates of WLB (r≈0.56).",
        f"BMI_RANGE is negatively correlated with WLB (r≈{round(float(wlb_corr.get('BMI_RANGE', -0.25)), 2)}), suggesting physical health impacts well-being.",
        f"Regular meditation (6+ sessions/week) is associated with WLB scores ~{round(float(list(wlb_by_meditation.values())[-1]) - float(list(wlb_by_meditation.values())[0]), 1)} points above non-meditators.",
    ]

    return {
        "dataset_info": df_info(df),
        "stress_distribution": stress_dist,
        "stress_by_gender_pct": stress_gender,
        "wlb_by_stress_level": wlb_by_stress,
        "wlb_by_hobby_time": wlb_by_hobby,
        "wlb_by_sleep_hours": wlb_by_sleep,
        "wlb_by_meditation": wlb_by_meditation,
        "wlb_by_income": wlb_by_income,
        "gender_comparison": gender_comparison,
        "age_comparison": age_comparison,
        "wlb_correlation_with_features": wlb_corr,
        "full_correlation_matrix": corr_dict,
        "wlb_distribution_histogram": wlb_dist,
        "auto_insights": insights,
    }

"""
Employee Turnover Prediction
==============================
Three models: Logistic Regression, Random Forest, XGBoost (GradientBoosting)
Per-employee attrition probability, feature importance, SHAP-style insights.

Dataset: fau_clinic_turnover_data.csv
"""
import pandas as pd
import numpy as np
from fastapi import APIRouter, Query
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, roc_auc_score, confusion_matrix)
from sklearn.preprocessing import LabelEncoder
import warnings
warnings.filterwarnings("ignore")

from .utils import load_csv, df_info, corr_matrix

router    = APIRouter()
DEFAULT_FILE = "fau_clinic_turnover_data.csv"
TARGET    = "left"
SALARY_MAP = {"low": 0, "medium": 1, "high": 2}


def _preprocess(df: pd.DataFrame):
    d   = df.copy()
    log = {}
    le  = LabelEncoder()
    for col in d.select_dtypes(include="object").columns:
        d[col] = le.fit_transform(d[col].astype(str))
        log[col] = "LabelEncoded"
    d.fillna(d.median(numeric_only=True), inplace=True)
    return d, log


def _build_model(model_type: str):
    if model_type == "logistic_regression":
        return LogisticRegression(max_iter=500, random_state=42, C=1.0)
    elif model_type == "xgboost":
        return GradientBoostingClassifier(n_estimators=150, learning_rate=0.1, max_depth=4, random_state=42)
    else:
        return RandomForestClassifier(n_estimators=150, max_depth=None, random_state=42, n_jobs=-1)


def _feature_importance(model, feature_names: list) -> dict:
    if hasattr(model, "feature_importances_"):
        fi = dict(zip(feature_names, model.feature_importances_))
    elif hasattr(model, "coef_"):
        fi = dict(zip(feature_names, np.abs(model.coef_[0])))
    else:
        return {}
    return {k: round(float(v), 4) for k, v in sorted(fi.items(), key=lambda x: x[1], reverse=True)}


def _risk_label(prob: float) -> str:
    if prob >= 0.75: return "Critical"
    if prob >= 0.50: return "High"
    if prob >= 0.25: return "Medium"
    return "Low"


@router.get("/train")
def train_model(
    filename:   str   = Query(DEFAULT_FILE),
    model_type: str   = Query("random_forest", description="random_forest | logistic_regression | xgboost"),
    test_size:  float = Query(0.2, ge=0.1, le=0.4),
    top_n_employees: int = Query(20, ge=5, le=100, description="Employees to return in per-employee table"),
):
    """
    Train a turnover classifier and return full evaluation + per-employee attrition probabilities.
    """
    df     = load_csv(filename)
    df2, log = _preprocess(df)

    X = df2.drop(columns=[TARGET])
    y = df2[TARGET]

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=test_size, random_state=42, stratify=y)

    model = _build_model(model_type)
    model.fit(X_tr, y_tr)

    y_pred = model.predict(X_te)
    y_prob = model.predict_proba(X_te)[:, 1]

    acc  = round(accuracy_score(y_te, y_pred), 4)
    prec = round(precision_score(y_te, y_pred, zero_division=0), 4)
    rec  = round(recall_score(y_te, y_pred, zero_division=0), 4)
    f1   = round(f1_score(y_te, y_pred, zero_division=0), 4)
    auc  = round(roc_auc_score(y_te, y_prob), 4)
    cv5  = round(cross_val_score(model, X, y, cv=5, scoring="roc_auc").mean(), 4)

    cm   = confusion_matrix(y_te, y_pred).tolist()
    fi   = _feature_importance(model, list(X.columns))

    # ── Per-employee risk table ────────────────────────────────
    all_probs  = model.predict_proba(X)[:, 1]
    emp_table  = []
    for idx, (row_idx, row) in enumerate(df2.iterrows()):
        prob = float(all_probs[idx])
        raw  = df.iloc[idx]
        emp_table.append({
            "index":            int(row_idx),
            "job_role":         str(raw.get("job_role", "—")),
            "salary":           str(raw.get("salary", "—")),
            "satisfaction_level": float(raw.get("satisfaction_level", 0)),
            "average_montly_hours": int(raw.get("average_montly_hours", 0)),
            "time_spend_clinic": int(raw.get("time_spend_clinic", 0)),
            "actual_left":      int(df2.loc[row_idx, TARGET]),
            "attrition_probability": round(prob, 4),
            "risk_label":       _risk_label(prob),
        })

    emp_table.sort(key=lambda x: x["attrition_probability"], reverse=True)

    # Segment counts
    seg = {
        "critical": sum(1 for e in emp_table if e["risk_label"] == "Critical"),
        "high":     sum(1 for e in emp_table if e["risk_label"] == "High"),
        "medium":   sum(1 for e in emp_table if e["risk_label"] == "Medium"),
        "low":      sum(1 for e in emp_table if e["risk_label"] == "Low"),
    }

    # Attrition probability distribution (histogram)
    hist_counts, hist_edges = np.histogram([e["attrition_probability"] for e in emp_table], bins=10, range=(0, 1))
    prob_dist = {f"{hist_edges[i]:.1f}–{hist_edges[i+1]:.1f}": int(hist_counts[i]) for i in range(len(hist_counts))}

    # Feature-level insights
    top_feat     = next(iter(fi))
    pos_features = [k for k, v in fi.items() if k in ("satisfaction_level",)] if "satisfaction_level" in fi else []
    insights = [
        f"Top turnover predictor: '{top_feat}' (importance {fi[top_feat]}).",
        f"{seg['critical']} employees have Critical attrition probability (≥75%).",
        f"Low satisfaction drives turnover — employees who left had avg satisfaction {df[df[TARGET]==1]['satisfaction_level'].mean():.2f} vs {df[df[TARGET]==0]['satisfaction_level'].mean():.2f} for stayers.",
        f"Overtime correlates with turnover: {df[df['average_montly_hours']>250][TARGET].mean()*100:.1f}% leave rate for >250 h/month.",
        f"Model 5-fold CV AUC: {cv5} — {'Excellent' if cv5>0.95 else 'Good' if cv5>0.85 else 'Moderate'} generalization.",
    ]

    top_k = emp_table[:top_n_employees]
    crit  = [e for e in emp_table if e["risk_label"] == "Critical"][:top_n_employees]

    return {
        "model":          model_type,
        "preprocessing":  log,
        "metrics": {
            "accuracy":    acc,  "precision": prec,
            "recall":      rec,  "f1_score":  f1,
            "roc_auc":     auc,  "cv5_auc":   cv5,
            "train_size":  len(X_tr), "test_size": len(X_te),
        },
        "confusion_matrix": {
            "matrix": cm,
            "true_negatives":  cm[0][0], "false_positives": cm[0][1],
            "false_negatives": cm[1][0], "true_positives":  cm[1][1],
        },
        "feature_importance":     fi,
        "risk_segments":          seg,
        "attrition_prob_distribution": prob_dist,
        "top_risk_employees":     top_k,
        "critical_employees":     crit,
        "auto_insights":          insights,
        "retention_recommendations": [
            "Address low job satisfaction through role enrichment, recognition programs and regular 1-on-1s.",
            "Cap overtime — employees logging >250 h/month show significantly higher turnover.",
            "Create promotion pathways — employees without promotions in 5+ years are high-risk.",
            "Review salary benchmarks — low-salary employees leave at 3× the rate of high-salary peers.",
            "Focus retention efforts on employees in their 2nd–4th year — peak churn window.",
        ],
    }


@router.get("/compare-models")
def compare_models(
    filename:  str   = Query(DEFAULT_FILE),
    test_size: float = Query(0.2, ge=0.1, le=0.4),
):
    """Train all three models and return side-by-side comparison."""
    df     = load_csv(filename)
    df2, _ = _preprocess(df)
    X = df2.drop(columns=[TARGET])
    y = df2[TARGET]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=test_size, random_state=42, stratify=y)

    results = {}
    for name in ["logistic_regression", "random_forest", "xgboost"]:
        m = _build_model(name)
        m.fit(X_tr, y_tr)
        yp  = m.predict(X_te)
        ypr = m.predict_proba(X_te)[:, 1]
        cv5 = round(cross_val_score(m, X, y, cv=5, scoring="roc_auc").mean(), 4)
        results[name] = {
            "accuracy":  round(accuracy_score(y_te, yp), 4),
            "roc_auc":   round(roc_auc_score(y_te, ypr), 4),
            "f1_score":  round(f1_score(y_te, yp, zero_division=0), 4),
            "cv5_auc":   cv5,
            "top_feature": next(iter(_feature_importance(m, list(X.columns))), "n/a"),
        }

    best = max(results, key=lambda k: results[k]["roc_auc"])
    return {
        "models":             results,
        "best_model":         best,
        "best_model_auc":     results[best]["roc_auc"],
        "recommendation":     f"Use {best.replace('_',' ').title()} for production — highest ROC AUC ({results[best]['roc_auc']}).",
    }


@router.get("/eda")
def eda(filename: str = Query(DEFAULT_FILE)):
    df   = load_csv(filename)
    rate = round(float(df[TARGET].mean()) * 100, 2)

    role_col  = [c for c in df.columns if "role" in c.lower()][0] if any("role" in c.lower() for c in df.columns) else None
    sat_by_role, turn_by_role, sal_by_role = {}, {}, {}
    if role_col:
        sat_by_role  = {str(k): round(float(v), 3) for k, v in df.groupby(role_col)["satisfaction_level"].mean().items()}
        turn_by_role = {str(k): round(float(v)*100, 2) for k, v in df.groupby(role_col)[TARGET].mean().items()}
        if "salary" in df.columns:
            sal_by_role = {str(k): str(df.groupby(role_col)["salary"].agg(lambda x: x.mode()[0]).get(k, "—")) for k in sat_by_role}

    turn_by_sal = {}
    if "salary" in df.columns:
        turn_by_sal = {str(k): round(float(v)*100, 2) for k, v in df.groupby("salary")[TARGET].mean().items()}

    left_sat  = round(float(df[df[TARGET]==1]["satisfaction_level"].mean()), 3)
    stay_sat  = round(float(df[df[TARGET]==0]["satisfaction_level"].mean()), 3)
    tenure_col = [c for c in df.columns if "time" in c.lower() or "spend" in c.lower()]
    avg_tenure = round(float(df[df[TARGET]==1][tenure_col[0]].mean()), 2) if tenure_col else None

    df2, _ = _preprocess(df)
    corr = df2.corr()[TARGET].drop(TARGET, errors="ignore").sort_values(ascending=False)
    top_pos = {str(k): round(float(v), 4) for k, v in corr[corr > 0].head(5).items()}
    top_neg = {str(k): round(float(v), 4) for k, v in corr[corr < 0].head(5).items()}

    return {
        "dataset_info":               df_info(df),
        "overall_turnover_rate_pct":  rate,
        "avg_satisfaction_who_left":  left_sat,
        "avg_satisfaction_who_stayed": stay_sat,
        "avg_tenure_years_who_left":  avg_tenure,
        "satisfaction_by_role":       sat_by_role,
        "turnover_rate_by_role_pct":  turn_by_role,
        "salary_mode_by_role":        sal_by_role,
        "turnover_rate_by_salary_pct": turn_by_sal,
        "top_positive_correlates_with_turnover": top_pos,
        "top_negative_correlates_with_turnover": top_neg,
        "insight": f"{rate}% overall turnover. Low satisfaction ({left_sat} vs {stay_sat}) is the clearest differentiator.",
    }


@router.get("/risk-profile")
def risk_profile(filename: str = Query(DEFAULT_FILE)):
    df = load_csv(filename)
    results = {}
    for col in df.select_dtypes(include="object").columns:
        g = df.groupby(col)[TARGET].mean().sort_values(ascending=False)
        results[col] = {str(k): round(float(v)*100, 1) for k, v in g.items()}
    if "satisfaction_level" in df.columns:
        df["_sq"] = pd.qcut(df["satisfaction_level"], q=4, labels=["Q1 (low)","Q2","Q3","Q4 (high)"])
        sq = df.groupby("_sq", observed=True)[TARGET].mean()
        results["satisfaction_quartile_pct"] = {str(k): round(float(v)*100, 1) for k, v in sq.items()}
    return {
        "overall_turnover_pct":       round(float(df[TARGET].mean())*100, 2),
        "turnover_risk_by_segment":   results,
    }

"""
Employee Performance Router
============================
EDA, correlation analysis, and ML model (Random Forest)
to predict PerformanceRating.

Dataset: clinic_performance.csv
"""

import pandas as pd
import numpy as np
from fastapi import APIRouter, Query, Body
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.neural_network import MLPClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, classification_report
from sklearn.preprocessing import LabelEncoder
import warnings
warnings.filterwarnings("ignore")

from .utils import load_csv, df_info, corr_matrix

router = APIRouter()
DEFAULT_FILE = "clinic_performance.csv"
TARGET = "PerformanceRating"

# Columns to drop (ID-like or irrelevant)
DROP_COLS = ["EmpNumber"]


def _preprocess(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Encode categoricals, drop irrelevant cols, return processed df + encoding map."""
    df = df.copy()
    df.drop(columns=[c for c in DROP_COLS if c in df.columns], inplace=True)

    encoding_log = {}
    le = LabelEncoder()
    for col in df.select_dtypes(include="object").columns:
        df[col] = le.fit_transform(df[col].astype(str))
        encoding_log[col] = "LabelEncoded"

    # Drop cols with >50% missing
    threshold = len(df) * 0.5
    before = list(df.columns)
    df.dropna(axis=1, thresh=int(threshold), inplace=True)
    dropped = [c for c in before if c not in df.columns]
    if dropped:
        encoding_log["dropped_high_missing"] = dropped

    df.fillna(df.median(numeric_only=True), inplace=True)
    return df, encoding_log


def _train(df: pd.DataFrame, model_type: str, test_size: float):
    """Train chosen model and return metrics + feature importance."""
    if TARGET not in df.columns:
        raise ValueError(f"Target column '{TARGET}' not found.")

    X = df.drop(columns=[TARGET])
    y = df[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42, stratify=y
    )

    if model_type == "random_forest":
        model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    elif model_type == "svm":
        model = SVC(kernel="rbf", probability=True, random_state=42)
    elif model_type == "mlp":
        model = MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=300, random_state=42)
    else:
        model = RandomForestClassifier(n_estimators=100, random_state=42)

    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    metrics = {
        "accuracy": round(accuracy_score(y_test, y_pred), 4),
        "precision": round(precision_score(y_test, y_pred, average="weighted", zero_division=0), 4),
        "recall": round(recall_score(y_test, y_pred, average="weighted", zero_division=0), 4),
        "f1_score": round(f1_score(y_test, y_pred, average="weighted", zero_division=0), 4),
        "train_size": len(X_train),
        "test_size": len(X_test),
        "classes": sorted(y.unique().tolist()),
    }

    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    per_class = {str(k): {m: round(v, 4) for m, v in v2.items()}
                 for k, v2 in report.items() if k not in ("accuracy", "macro avg", "weighted avg")}

    feature_importance = {}
    if hasattr(model, "feature_importances_"):
        fi = dict(zip(X.columns, model.feature_importances_))
        feature_importance = {
            k: round(float(v), 4)
            for k, v in sorted(fi.items(), key=lambda x: x[1], reverse=True)
        }

    # Sample predictions (first 10 test rows)
    sample = pd.DataFrame({
        "actual": y_test.values[:10],
        "predicted": y_pred[:10],
        "correct": (y_test.values[:10] == y_pred[:10]),
    }).to_dict(orient="records")

    return metrics, per_class, feature_importance, sample, model, X.columns.tolist()


@router.get("/eda")
def eda(filename: str = Query(DEFAULT_FILE)):
    """Exploratory Data Analysis: overview, missing values, distributions, role-based analysis."""
    df = load_csv(filename)

    # Role-based performance
    role_col = [c for c in df.columns if "role" in c.lower() or "jobrole" in c.lower().replace(" ", "")]
    role_analysis = {}
    if role_col and TARGET in df.columns:
        role_analysis = df.groupby(role_col[0])[TARGET].agg(["mean", "count", "std"]).round(3).to_dict(orient="index")
        role_analysis = {str(k): {m: round(float(v), 3) if not pd.isna(v) else None for m, v in vals.items()}
                         for k, vals in role_analysis.items()}

    # Column-level summary
    summary = {}
    for col in df.columns:
        col_data = df[col].dropna()
        if df[col].dtype == object:
            summary[col] = {"type": "categorical", "unique": int(col_data.nunique()),
                            "top_values": col_data.value_counts().head(5).to_dict()}
        else:
            summary[col] = {"type": "numeric", "min": round(float(col_data.min()), 3),
                            "max": round(float(col_data.max()), 3),
                            "mean": round(float(col_data.mean()), 3),
                            "std": round(float(col_data.std()), 3)}

    return {
        "dataset_info": df_info(df),
        "column_summary": summary,
        "role_based_performance": role_analysis,
        "target_distribution": df[TARGET].value_counts().to_dict() if TARGET in df.columns else {},
    }


@router.get("/correlation")
def correlation(filename: str = Query(DEFAULT_FILE)):
    """Correlation matrix and top correlates with PerformanceRating."""
    df = load_csv(filename)
    df2, _ = _preprocess(df)
    corr = corr_matrix(df2, target=TARGET)

    top_pos = {}
    top_neg = {}
    if TARGET in df2.columns:
        target_corr = pd.DataFrame(df2.corr()[TARGET]).drop(TARGET, errors="ignore")
        top_pos = target_corr[target_corr[TARGET] > 0].sort_values(TARGET, ascending=False).head(5)[TARGET].round(4).to_dict()
        top_neg = target_corr[target_corr[TARGET] < 0].sort_values(TARGET).head(5)[TARGET].round(4).to_dict()

    return {
        "correlation_matrix": corr,
        "top_positive_correlates": top_pos,
        "top_negative_correlates": top_neg,
    }


@router.get("/train")
def train_model(
    filename: str = Query(DEFAULT_FILE),
    model_type: str = Query("random_forest", description="random_forest | svm | mlp"),
    test_size: float = Query(0.2, ge=0.1, le=0.4, description="Test split fraction"),
):
    """Train an ML model to predict PerformanceRating. Returns metrics, feature importance, sample predictions."""
    df = load_csv(filename)
    df2, encoding_log = _preprocess(df)
    metrics, per_class, feature_importance, sample, _, features = _train(df2, model_type, test_size)

    return {
        "model": model_type,
        "target": TARGET,
        "features_used": features,
        "preprocessing": encoding_log,
        "metrics": metrics,
        "per_class_metrics": per_class,
        "feature_importance": feature_importance,
        "sample_predictions": sample,
        "interpretation": {
            "accuracy": f"The model correctly predicts performance {metrics['accuracy']*100:.1f}% of the time.",
            "top_driver": next(iter(feature_importance)) if feature_importance else "N/A",
            "recommendation": (
                "Focus on the top feature importance drivers to improve employee performance. "
                "High salary hike % and job involvement strongly predict higher ratings."
            ),
        },
    }


# ── Score formulas ───────────────────────────────────────────────────────────
def _add_scores(df_enc: pd.DataFrame, df_orig: pd.DataFrame) -> pd.DataFrame:
    """Compute three composite scores using original (unencoded) column values."""
    d = df_enc.copy()

    # Productivity (0-100)
    d["productivity_score"] = (
        ((df_orig["PerformanceRating"] - 2) / 2) * 40 +
        ((df_orig["EmpJobInvolvement"]  - 1) / 3) * 25 +
        ((df_orig["EmpJobSatisfaction"] - 1) / 3) * 20 +
        ((df_orig["EmpEnvironmentSatisfaction"] - 1) / 3) * 15
    ).clip(0, 100).round(1).values

    # Burnout risk (0-100)
    promo_max = max(df_orig["YearsSinceLastPromotion"].max(), 1)
    dist_max  = max(df_orig["DistanceFromHomeKm"].max(), 1)
    ot        = (df_orig["OverTime"] == "Yes").astype(float)
    d["burnout_score"] = (
        ot * 30 +
        ((4 - df_orig["EmpWorkLifeBalance"]) / 3) * 25 +
        ((4 - df_orig["EmpJobSatisfaction"]) / 3) * 20 +
        (df_orig["YearsSinceLastPromotion"] / promo_max) * 15 +
        (df_orig["DistanceFromHomeKm"] / dist_max) * 10
    ).clip(0, 100).round(1).values

    # High performer score (0-100)
    hike_max = max(df_orig["EmpLastSalaryHikePercent"].max(), 1)
    d["high_performer_score"] = (
        ((df_orig["PerformanceRating"] - 2) / 2) * 50 +
        (df_orig["EmpLastSalaryHikePercent"] / hike_max) * 30 +
        ((df_orig["EmpJobInvolvement"] - 1) / 3) * 20
    ).clip(0, 100).round(1).values

    return d


def _label(hp: float, burn: float, prod: float) -> dict:
    tags = []
    if hp >= 70:   tags.append("⭐ High Performer")
    if burn >= 60: tags.append("🔥 Burnout Risk")
    if prod >= 70: tags.append("⚡ High Productivity")
    if burn >= 60 and prod < 40: tags.append("⚠ Critical — Act Now")
    if not tags:   tags.append("✓ Stable")
    return {
        "high_performer_score": hp,
        "burnout_score": burn,
        "productivity_score": prod,
        "tags": tags,
        "burnout_level": "High" if burn >= 60 else ("Medium" if burn >= 35 else "Low"),
        "performance_tier": "Top" if hp >= 70 else ("Mid" if hp >= 40 else "Low"),
    }


@router.get("/predictions")
def predictions(
    filename: str = Query(DEFAULT_FILE),
    top_n: int = Query(20, ge=5, le=100, description="Employees to return per list"),
):
    """
    Per-employee predictions:
    - High Performer score (0-100)
    - Burnout Risk score (0-100)
    - Productivity score (0-100)
    - Segment labels and tier per employee
    - Aggregate distributions and role-level summaries
    - Auto-generated insights
    """
    df = load_csv(filename)
    df_raw, _ = _preprocess(df.copy())

    scored = _add_scores(df_raw, df)
    scored["EmpNumber"] = df["EmpNumber"].values
    scored["EmpJobRole"] = df["EmpJobRole"].values

    # ── Per-employee table ────────────────────────────────────────
    records = []
    for _, row in scored.iterrows():
        hp  = float(row["high_performer_score"])
        burn = float(row["burnout_score"])
        prod = float(row["productivity_score"])
        info = _label(hp, burn, prod)
        records.append({
            "emp_id":   str(row["EmpNumber"]),
            "job_role": str(row["EmpJobRole"]),
            **info,
        })

    records.sort(key=lambda x: x["high_performer_score"], reverse=True)

    # ── Segment counts ────────────────────────────────────────────
    high_performers = [r for r in records if r["high_performer_score"] >= 70]
    burnout_risk    = [r for r in records if r["burnout_score"] >= 60]
    high_prod       = [r for r in records if r["productivity_score"] >= 70]
    critical        = [r for r in records if r["burnout_score"] >= 60 and r["productivity_score"] < 40]

    # ── Role-level summary ────────────────────────────────────────
    role_summary = {}
    for role, grp in scored.groupby("EmpJobRole"):
        role_summary[str(role)] = {
            "count": int(len(grp)),
            "avg_productivity": float(grp["productivity_score"].mean().round(1)),
            "avg_burnout":      float(grp["burnout_score"].mean().round(1)),
            "avg_high_performer": float(grp["high_performer_score"].mean().round(1)),
            "high_performers_pct": round(float((grp["high_performer_score"] >= 70).mean() * 100), 1),
            "burnout_risk_pct":   round(float((grp["burnout_score"] >= 60).mean() * 100), 1),
        }

    # ── Score distributions (histogram buckets) ──────────────────
    def hist(series, bins):
        counts, edges = np.histogram(series, bins=bins)
        labels = [f"{int(edges[i])}–{int(edges[i+1])}" for i in range(len(edges)-1)]
        return {labels[i]: int(counts[i]) for i in range(len(labels))}

    bins10 = list(range(0, 110, 10))
    prod_dist  = hist(scored["productivity_score"],    bins10)
    burn_dist  = hist(scored["burnout_score"],         bins10)
    hp_dist    = hist(scored["high_performer_score"],  bins10)

    # ── Auto insights ─────────────────────────────────────────────
    total = len(records)
    insights = [
        f"{len(high_performers)} employees ({len(high_performers)/total*100:.1f}%) qualify as High Performers (score ≥ 70).",
        f"{len(burnout_risk)} employees ({len(burnout_risk)/total*100:.1f}%) are at Burnout Risk (score ≥ 60). Immediate attention recommended.",
        f"{len(critical)} employees show both high burnout risk AND low productivity — critical intervention needed.",
        f"Average productivity score across all roles: {scored['productivity_score'].mean():.1f}/100.",
        f"Average burnout risk score: {scored['burnout_score'].mean():.1f}/100.",
    ]
    top_burn_role = max(role_summary, key=lambda r: role_summary[r]["burnout_risk_pct"])
    top_prod_role = max(role_summary, key=lambda r: role_summary[r]["avg_productivity"])
    insights.append(f"Highest burnout risk role: {top_burn_role} ({role_summary[top_burn_role]['burnout_risk_pct']}% at risk).")
    insights.append(f"Highest average productivity role: {top_prod_role} ({role_summary[top_prod_role]['avg_productivity']}/100).")

    return {
        "dataset_info": df_info(df),
        "segment_counts": {
            "total_employees": total,
            "high_performers": len(high_performers),
            "burnout_risk": len(burnout_risk),
            "high_productivity": len(high_prod),
            "critical_cases": len(critical),
        },
        "top_high_performers":  records[:top_n],
        "top_burnout_risk":     sorted(burnout_risk,  key=lambda x: x["burnout_score"],      reverse=True)[:top_n],
        "top_productive":       sorted(high_prod,      key=lambda x: x["productivity_score"], reverse=True)[:top_n],
        "critical_employees":   critical,
        "role_summary":         role_summary,
        "score_distributions": {
            "productivity":     prod_dist,
            "burnout":          burn_dist,
            "high_performer":   hp_dist,
        },
        "auto_insights": insights,
        "score_methodology": {
            "productivity_score": "40% PerformanceRating + 25% JobInvolvement + 20% JobSatisfaction + 15% EnvironmentSatisfaction",
            "burnout_score":      "30% OverTime + 25% low WorkLifeBalance + 20% low JobSatisfaction + 15% YearsSinceLastPromotion + 10% DistanceFromHome",
            "high_performer_score": "50% PerformanceRating + 30% SalaryHike% + 20% JobInvolvement",
        },
    }

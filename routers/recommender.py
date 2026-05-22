"""
Employee Recommender System
============================
Three recommendation modes:
  - onboarding_buddy : cosine similarity on hobbies/sport/team
  - mentor           : experience gap + shared interests
  - teammate         : team alignment + compatibility

Techniques: Cosine similarity, collaborative filtering, similarity matrix
"""
import pandas as pd
import numpy as np
from fastapi import APIRouter, Query, HTTPException
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import MultiLabelBinarizer
from .utils import load_csv, df_info

router = APIRouter()
DEFAULT_FILE = "fau_clinic_recommender_system.csv"

EXP_ORDER = {"Novice.": 1, "Advanced beginner.": 2, "Competent.": 3, "Proficient.": 4, "Expert.": 5}


def _tokenize(val):
    return [t.strip().lower() for t in str(val).split(",") if t.strip()]


def _build_matrix(df, w_hobbies=2.0, w_sports=1.5, w_teams=1.0):
    mlb = MultiLabelBinarizer()
    hobbies = pd.DataFrame(mlb.fit_transform(df["hobbies"].apply(_tokenize)), columns=[f"h_{c}" for c in mlb.classes_])
    sports  = pd.DataFrame(mlb.fit_transform(df["sports"].apply(_tokenize)),  columns=[f"s_{c}" for c in mlb.classes_])
    teams   = pd.get_dummies(df["teams"]).add_prefix("t_")
    exp     = df["previous_experience"].map(EXP_ORDER).fillna(0).values.reshape(-1, 1) / 5.0
    return np.hstack([hobbies.values * w_hobbies, sports.values * w_sports, teams.values * w_teams, exp * 0.5])


def _shared(a, b):
    out = {}
    for col in ["hobbies", "sports"]:
        common = sorted(set(_tokenize(a[col])) & set(_tokenize(b[col])))
        if common:
            out[col] = common
    if a["teams"] == b["teams"]:
        out["teams"] = [a["teams"]]
    return out


@router.get("/")
def recommend(
    filename: str = Query(DEFAULT_FILE),
    employee_id: str = Query("emp_050"),
    mode: str = Query("onboarding_buddy", description="onboarding_buddy | mentor | teammate"),
    top_n: int = Query(5, ge=1, le=20),
    weight_hobbies: float = Query(2.0),
    weight_sports:  float = Query(1.5),
    weight_teams:   float = Query(1.0),
):
    """Recommend colleagues using cosine similarity. Mode controls scoring strategy."""
    df = load_csv(filename)
    if employee_id not in df["id"].values:
        raise HTTPException(404, f"Employee '{employee_id}' not found.")

    mat = _build_matrix(df, weight_hobbies, weight_sports, weight_teams)
    sim = cosine_similarity(mat)
    t_idx = df[df["id"] == employee_id].index[0]
    t_row = df.iloc[t_idx]
    sims  = sim[t_idx]

    EXP_ORDER_local = EXP_ORDER
    results = []
    for i, row in df.iterrows():
        if row["id"] == employee_id:
            continue
        cos = float(sims[i])
        if mode == "mentor":
            t_exp = EXP_ORDER_local.get(t_row["previous_experience"], 0)
            c_exp = EXP_ORDER_local.get(row["previous_experience"], 0)
            gap   = c_exp - t_exp
            if gap <= 0:
                continue
            score = round(min(gap / 4, 1.0) * 40 + cos * 60, 2)
        elif mode == "teammate":
            same  = 1.0 if row["teams"] == t_row["teams"] else 0.0
            score = round(same * 30 + cos * 70, 2)
        else:
            score = round(cos * 100, 2)

        results.append({
            "employee_id":       str(row["id"]),
            "score":             score,
            "cosine_similarity": round(cos, 4),
            "profile":           {c: str(row[c]) for c in df.columns if c != "id"},
            "shared_attributes": _shared(t_row, row),
            "experience_level":  str(row["previous_experience"]),
            "same_team":         row["teams"] == t_row["teams"],
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    mode_labels = {
        "onboarding_buddy": "Most similar colleague by shared hobbies, sports and team — best social fit for onboarding.",
        "mentor": "More experienced employee with similar interests — guides professional growth.",
        "teammate": "Best collaborative match — team alignment plus personal compatibility.",
    }
    return {
        "mode": mode,
        "target_employee": {"id": employee_id, "profile": {c: str(t_row[c]) for c in df.columns if c != "id"}},
        "recommendations": results[:top_n],
        "mode_explanation": mode_labels.get(mode, ""),
        "dataset_info": df_info(df),
    }


@router.get("/similarity-matrix")
def similarity_matrix(filename: str = Query(DEFAULT_FILE)):
    """Full NxN cosine similarity matrix for heatmap rendering."""
    df  = load_csv(filename)
    mat = _build_matrix(df)
    sim = cosine_similarity(mat)
    return {
        "employee_ids":      df["id"].tolist(),
        "similarity_matrix": np.round(sim, 3).tolist(),
        "dataset_info":      df_info(df),
    }


@router.get("/team-clusters")
def team_clusters(filename: str = Query(DEFAULT_FILE)):
    """Team-based collaborative filtering: cohesion scores, bridge employees, recommended team for new hire."""
    df  = load_csv(filename)
    mat = _build_matrix(df)
    sim = cosine_similarity(mat)

    clusters = {}
    for team in sorted(df["teams"].unique()):
        idxs    = df[df["teams"] == team].index.tolist()
        members = df.loc[idxs, "id"].tolist()
        if len(idxs) > 1:
            sub = sim[np.ix_(idxs, idxs)].copy()
            np.fill_diagonal(sub, np.nan)
            intra = float(np.nanmean(sub))
        else:
            intra = 1.0
        other_idxs = df[df["teams"] != team].index.tolist()
        cross_mean  = sim[np.ix_(idxs, other_idxs)].mean(axis=1)
        bridge_emp  = df.iloc[idxs[int(np.argmax(cross_mean))]]["id"]
        exp_mix     = df.loc[idxs, "previous_experience"].value_counts().to_dict()
        clusters[team] = {
            "members":                      members,
            "count":                        len(members),
            "intra_team_avg_similarity":    round(intra, 3),
            "bridge_employee":              str(bridge_emp),
            "experience_mix":               {str(k): int(v) for k, v in exp_mix.items()},
        }

    best = max(clusters, key=lambda t: clusters[t]["intra_team_avg_similarity"])
    return {
        "teams":                         clusters,
        "recommended_team_for_new_hire": best,
        "rationale":                     "Team with highest intra-team similarity is most cohesive and ready to absorb a new member.",
    }


@router.get("/employees")
def list_employees(filename: str = Query(DEFAULT_FILE)):
    df = load_csv(filename)
    return {
        "employee_ids":     df["id"].tolist(),
        "total":            len(df),
        "teams":            sorted(df["teams"].unique().tolist()),
        "experience_levels": list(EXP_ORDER.keys()),
    }

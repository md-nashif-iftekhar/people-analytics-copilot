from fastapi import APIRouter, HTTPException, Query
from typing import List
import numpy as np

from .utils import load_csv

router = APIRouter()


def detect_burnout() -> dict:
    try:
        df = load_csv("fau_clinic_employee_wellbeing.csv")
    except Exception as e:
        return {"error": str(e)}
    out = {}
    # risk if DAILY_STRESS >=4 or (DAILY_STRESS>=3 and SLEEP_HOURS<=6)
    df['burnout_flag'] = ((df.get('DAILY_STRESS', 0) >= 4) | ((df.get('DAILY_STRESS', 0) >= 3) & (df.get('SLEEP_HOURS', 99) <= 6)))
    out['count'] = int(df['burnout_flag'].sum())
    # top groups by AGE
    if 'AGE' in df.columns:
        by_age = df[df['burnout_flag']].groupby('AGE').size().sort_values(ascending=False).head(5).to_dict()
        out['by_age'] = by_age
    if 'GENDER' in df.columns:
        out['by_gender'] = df[df['burnout_flag']].groupby('GENDER').size().to_dict()
    return out


def detect_quiet_quitting() -> dict:
    try:
        df = load_csv("clinic_performance.csv")
    except Exception as e:
        return {"error": str(e)}
    out = {}
    # Heuristic: low involvement (<=2), low satisfaction (<=2), low performance (<=3), no overtime
    cond = (df.get('EmpJobInvolvement', 0) <= 2) & (df.get('EmpJobSatisfaction', 0) <= 2) & (df.get('PerformanceRating', 0) <= 3) & (df.get('OverTime', '').fillna('No') == 'No')
    df_q = df[cond]
    out['count'] = int(len(df_q))
    out['examples'] = df_q[['EmpNumber','EmpJobRole','PerformanceRating','EmpJobSatisfaction','EmpJobInvolvement']].head(10).to_dict(orient='records') if not df_q.empty else []
    return out


def detect_turnover_risk() -> dict:
    # Train a simple logistic regression on turnover CSV and report top-risk roles and feature importance
    try:
        tr = load_csv("fau_clinic_turnover_data.csv")
    except Exception as e:
        return {"error": str(e)}
    out = {}
    if 'left' not in tr.columns:
        return {"error": "turnover dataset missing 'left' column"}
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import train_test_split
    except Exception as e:
        return {"error": f"sklearn required: {e}"}
    # basic numeric features
    num = tr.select_dtypes(include='number').copy()
    if num.empty:
        return {"error": "no numeric features to train on"}
    y = tr['left']
    X = num.fillna(0)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=1)
    clf = LogisticRegression(max_iter=200)
    clf.fit(X_train, y_train)
    probs = clf.predict_proba(X)[:, 1]
    tr = tr.assign(turnover_prob=probs)
    # top roles
    if 'job_role' in tr.columns:
        roles = tr.groupby('job_role')['turnover_prob'].mean().sort_values(ascending=False).head(8).round(3).to_dict()
        out['top_roles_by_risk'] = roles
    out['model_score_sample'] = float(clf.score(X_test, y_test))
    return out


def detect_productivity_decline() -> dict:
    try:
        df = load_csv("clinic_performance.csv")
    except Exception as e:
        return {"error": str(e)}
    out = {}
    if 'PerformanceRating' not in df.columns:
        return {"error": "performance dataset missing 'PerformanceRating'"}
    # flag employees whose rating is >=1 point below role mean
    if 'EmpJobRole' in df.columns:
        role_means = df.groupby('EmpJobRole')['PerformanceRating'].mean()
        df['role_mean'] = df['EmpJobRole'].map(role_means)
        df['prod_decline'] = df['role_mean'] - df['PerformanceRating'] >= 1
        out['count'] = int(df['prod_decline'].sum())
        out['examples'] = df[df['prod_decline']][['EmpNumber','EmpJobRole','PerformanceRating','role_mean']].head(10).to_dict(orient='records')
    else:
        out['error'] = 'EmpJobRole not available for grouping'
    return out


def detect_toxic_teams() -> dict:
    # teams with low satisfaction and high turnover
    out = {}
    try:
        wb = load_csv("fau_clinic_employee_wellbeing.csv")
        tr = load_csv("fau_clinic_turnover_data.csv")
    except Exception as e:
        return {"error": str(e)}
    if 'job_role' in tr.columns:
        role_turn = tr.groupby('job_role')['left'].mean().sort_values(ascending=False).head(8).to_dict()
    else:
        role_turn = {}
    # wellbeing: low WLB by job if JOB ROLE exists in other data? Attempt mapping via index clusters
    out['roles_high_turnover'] = role_turn
    # approximate toxic teams: roles with high turnover and low avg satisfaction in turnover dataset
    if 'job_role' in tr.columns and 'satisfaction_level' in tr.columns:
        score = tr.groupby('job_role')['satisfaction_level'].mean()
        tox = ((tr.groupby('job_role')['left'].mean() * 100).round(1)).sort_values(ascending=False).head(8).to_dict()
        out['toxic_candidates'] = tox
    return out


def detect_overworked_departments() -> dict:
    try:
        tr = load_csv("fau_clinic_turnover_data.csv")
    except Exception as e:
        return {"error": str(e)}
    out = {}
    if 'average_montly_hours' not in tr.columns:
        return {"error": "missing average_montly_hours"}
    overall = tr['average_montly_hours'].mean()
    by_role = tr.groupby('job_role')['average_montly_hours'].mean().sort_values(ascending=False)
    high = by_role[by_role > overall + 20].round(1).to_dict()
    out['overall_avg_hours'] = round(float(overall),1)
    out['overworked_roles'] = high
    return out


@router.get("/overview", tags=["Risk"])
def risk_overview():
    """Run all detectors and return a combined overview."""
    return {
        'burnout': detect_burnout(),
        'quiet_quitting': detect_quiet_quitting(),
        'turnover_risk': detect_turnover_risk(),
        'productivity_decline': detect_productivity_decline(),
        'toxic_teams': detect_toxic_teams(),
        'overworked': detect_overworked_departments(),
    }


@router.get("/employee", tags=["Risk"])
def employee_risk(emp: str = Query(...)):
    """Return risk profile for an employee id present in `clinic_performance.csv` (EmpNumber)."""
    try:
        df = load_csv('clinic_performance.csv')
    except Exception as e:
        raise HTTPException(404, str(e))
    row = df[df['EmpNumber'] == emp]
    if row.empty:
        raise HTTPException(404, f'Employee {emp} not found')
    r = row.iloc[0].to_dict()
    profile = {}
    # Quiet quitting heuristic
    profile['quiet_quitting_risk'] = bool((r.get('EmpJobInvolvement',0) <=2) and (r.get('EmpJobSatisfaction',0) <=2) and (r.get('PerformanceRating',0) <=3) and (r.get('OverTime','No')=='No'))
    # Productivity decline vs role mean
    if 'EmpJobRole' in df.columns:
        role_mean = df[df['EmpJobRole']==r.get('EmpJobRole', '')]['PerformanceRating'].mean()
        profile['productivity_decline'] = bool(role_mean - r.get('PerformanceRating',0) >= 1)
    # Attrition probability approximation using turnover model if available
    try:
        from sklearn.linear_model import LogisticRegression
        tr = load_csv('fau_clinic_turnover_data.csv')
        num = tr.select_dtypes(include='number').copy().fillna(0)
        if not num.empty:
            # train quickly
            clf = LogisticRegression(max_iter=200).fit(num, tr['left'])
            # attempt to map features from employee row
            common = [c for c in num.columns if c in row.columns]
            if common:
                x = np.array([row[c].values[0] for c in common], dtype=float).reshape(1,-1)
                prob = float(clf.predict_proba(x)[:,1])
                profile['turnover_probability'] = round(prob,3)
    except Exception:
        pass
    return {'employee': r, 'profile': profile}

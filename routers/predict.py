from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import numpy as np
import pandas as pd
import os
import json
import joblib
from sklearn.model_selection import cross_val_score
from sklearn import metrics

from .utils import load_csv

router = APIRouter()

# directory to persist models and metadata
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'models')
os.makedirs(MODEL_DIR, exist_ok=True)


class Candidate(BaseModel):
    id: Optional[str]
    target_team: Optional[str]
    previous_experience: Optional[str]
    hobbies: Optional[str]
    skills: Optional[List[str]]


def _exp_score(text: str) -> int:
    if not text: return 1
    t = text.lower()
    if 'expert' in t: return 4
    if 'proficient' in t: return 3
    if 'competent' in t: return 2
    if 'advanced' in t: return 1
    if 'novice' in t: return 0
    return 1


@router.post('/candidate-fit')
def candidate_fit(candidate: Candidate):
    """Return a candidate->job fit score (0-1) based on team similarity and experience."""
    try:
        df = load_csv('fau_clinic_recommender_system.csv')
    except Exception as e:
        raise HTTPException(404, str(e))
    # compute team profile
    team = candidate.target_team
    members = df[df['teams'] == team] if team else df
    if members.empty:
        raise HTTPException(404, f"Team '{team}' not found or has no members")
    # experience score
    cand_exp = _exp_score(candidate.previous_experience)
    member_exps = members['previous_experience'].fillna('').apply(_exp_score)
    exp_score = 1 - abs(cand_exp - member_exps.mean())/4
    # hobby similarity (Jaccard)
    def parse_set(s):
        return {x.strip().lower() for x in (s or '').split(',') if x.strip()}
    cand_h = parse_set(candidate.hobbies)
    member_h = set().union(*members['hobbies'].fillna('').apply(parse_set).tolist())
    if not cand_h and not member_h:
        hobby_sim = 0.5
    else:
        inter = len(cand_h & member_h)
        union = len(cand_h | member_h) or 1
        hobby_sim = inter/union
    # skills match (if provided)
    skill_score = 0.5
    if candidate.skills:
        skill_score = min(1.0, len(candidate.skills)/5)
    # weighted aggregate
    fit = 0.5*exp_score + 0.35*hobby_sim + 0.15*skill_score
    return {'fit_score': round(float(fit),3), 'components': {'experience': round(float(exp_score),3), 'hobby_sim': round(float(hobby_sim),3), 'skill': round(float(skill_score),3)}}


def _save_model(obj, name, meta=None):
    p = os.path.join(MODEL_DIR, f'predict_{name}.pkl')
    joblib.dump(obj, p)
    if meta is not None:
        with open(os.path.join(MODEL_DIR, f'predict_{name}_meta.json'), 'w') as f:
            json.dump(meta, f)
    return p


def _load_model(name):
    p = os.path.join(MODEL_DIR, f'predict_{name}.pkl')
    if os.path.exists(p):
        return joblib.load(p)
    return None


@router.get('/models')
def list_models():
    """List persisted prediction models and metadata."""
    files = []
    for fname in os.listdir(MODEL_DIR):
        if fname.endswith('.pkl') and fname.startswith('predict_'):
            key = fname.replace('predict_','').replace('.pkl','')
            meta_path = os.path.join(MODEL_DIR, f'predict_{key}_meta.json')
            meta = None
            if os.path.exists(meta_path):
                try:
                    with open(meta_path,'r') as f: meta = json.load(f)
                except: meta = None
            files.append({'name': key, 'path': fname, 'meta': meta})
    return {'models': files}


@router.post('/models/train')
def train_and_persist_models():
    """Train retention and performance models, evaluate and persist them with metrics."""
    results = {}
    # Retention model
    try:
        tr = load_csv('fau_clinic_turnover_data.csv')
        if 'left' not in tr.columns:
            results['retention'] = {'error': "turnover dataset missing 'left' column"}
        else:
            num = tr.select_dtypes(include='number').copy().fillna(0)
            X = num; y = tr['left']
            from sklearn.linear_model import LogisticRegression
            clf = LogisticRegression(max_iter=400)
            scores = cross_val_score(clf, X, y, cv=5, scoring='roc_auc') if len(X)>4 else None
            clf.fit(X,y)
            meta = {'cv_auc_mean': float(scores.mean()) if scores is not None else None, 'cv_auc_scores': scores.tolist() if scores is not None else None}
            _save_model(clf, 'retention', meta)
            results['retention'] = {'saved': True, 'metrics': meta}
    except Exception as e:
        results['retention'] = {'error': str(e)}
    # Performance model
    try:
        df = load_csv('clinic_performance.csv')
        if 'PerformanceRating' not in df.columns:
            results['performance'] = {'error': "performance dataset missing 'PerformanceRating'"}
        else:
            df['high_perf'] = (df['PerformanceRating'] >= 4).astype(int)
            num = df.select_dtypes(include='number').copy().fillna(0)
            X = num; y = df['high_perf']
            from sklearn.ensemble import RandomForestClassifier
            clf = RandomForestClassifier(n_estimators=100, random_state=1)
            scores = cross_val_score(clf, X, y, cv=5, scoring='roc_auc') if len(X)>4 else None
            clf.fit(X,y)
            meta = {'cv_auc_mean': float(scores.mean()) if scores is not None else None, 'cv_auc_scores': scores.tolist() if scores is not None else None}
            _save_model(clf, 'performance', meta)
            results['performance'] = {'saved': True, 'metrics': meta}
    except Exception as e:
        results['performance'] = {'error': str(e)}
    return results


class EmpFeatures(BaseModel):
    EmpNumber: Optional[str]
    features: Optional[dict]


@router.post('/retention')
def predict_retention(payload: EmpFeatures):
    """Predict long-term retention probability (1 - leave probability) using turnover dataset."""
    try:
        tr = load_csv('fau_clinic_turnover_data.csv')
    except Exception as e:
        raise HTTPException(404, str(e))
    if 'left' not in tr.columns:
        raise HTTPException(422, "turnover dataset missing 'left' column")
    num = tr.select_dtypes(include='number').copy().fillna(0)
    if num.empty:
        raise HTTPException(422, 'no numeric features available for prediction')
    # try to load persisted model first
    clf = _load_model('retention')
    if clf is None:
        try:
            from sklearn.linear_model import LogisticRegression
        except Exception as e:
            raise HTTPException(500, f'sklearn required: {e}')
        X = num; y = tr['left']
        clf = LogisticRegression(max_iter=300).fit(X, y)
    # build input vector
    if payload.EmpNumber:
        # try to find row in turnover by matching via EmpNumber not present; fall back to features
        row = None
        if 'EmpNumber' in tr.columns:
            row = tr[tr['EmpNumber']==payload.EmpNumber]
        if row is not None and not row.empty:
            x = row[num.columns].iloc[0].values.reshape(1,-1)
        else:
            if not payload.features:
                raise HTTPException(404, 'employee not found and no features provided')
            x = np.array([payload.features.get(c,0) for c in num.columns], dtype=float).reshape(1,-1)
    else:
        if not payload.features:
            raise HTTPException(422, 'provide EmpNumber or features')
        x = np.array([payload.features.get(c,0) for c in num.columns], dtype=float).reshape(1,-1)
    # ensure model supports predict_proba
    if not hasattr(clf, 'predict_proba'):
        raise HTTPException(500, 'loaded model cannot predict probabilities')
    prob_leave = float(clf.predict_proba(x)[:,1])
    retention = 1 - prob_leave
    return {'retention_probability': round(retention,3), 'leave_probability': round(prob_leave,3)}


@router.post('/performance')
def predict_performance(payload: EmpFeatures):
    """Predict probability of high performance (rating >=4) using clinic_performance.csv"""
    try:
        df = load_csv('clinic_performance.csv')
    except Exception as e:
        raise HTTPException(404, str(e))
    if 'PerformanceRating' not in df.columns:
        raise HTTPException(422, "performance dataset missing 'PerformanceRating'")
    df['high_perf'] = (df['PerformanceRating'] >= 4).astype(int)
    num = df.select_dtypes(include='number').copy().fillna(0)
    if num.empty:
        raise HTTPException(422, 'no numeric features for performance model')
    # try to load persisted performance model
    clf = _load_model('performance')
    if clf is None:
        try:
            from sklearn.ensemble import RandomForestClassifier
        except Exception as e:
            raise HTTPException(500, f'sklearn required: {e}')
        X = num; y = df['high_perf']
        clf = RandomForestClassifier(n_estimators=50, random_state=1).fit(X, y)
    # build input
    if payload.EmpNumber:
        row = df[df['EmpNumber']==payload.EmpNumber]
        if row.empty and not payload.features:
            raise HTTPException(404, 'employee not found and no features provided')
        if not row.empty:
            x = row[num.columns].iloc[0].values.reshape(1,-1)
        else:
            x = np.array([payload.features.get(c,0) for c in num.columns], dtype=float).reshape(1,-1)
    else:
        if not payload.features:
            raise HTTPException(422, 'provide EmpNumber or features')
        x = np.array([payload.features.get(c,0) for c in num.columns], dtype=float).reshape(1,-1)
    if not hasattr(clf, 'predict_proba'):
        raise HTTPException(500, 'loaded model cannot predict probabilities')
    prob = float(clf.predict_proba(x)[:,1])
    return {'high_performance_probability': round(prob,3)}


@router.post('/culture-fit')
def culture_fit(candidate: Candidate):
    """Estimate culture fit using hobby/sports overlap with target team"""
    try:
        df = load_csv('fau_clinic_recommender_system.csv')
    except Exception as e:
        raise HTTPException(404, str(e))
    team = candidate.target_team
    members = df[df['teams'] == team] if team else df
    if members.empty:
        raise HTTPException(404, f"Team '{team}' not found")
    def parse_set(s):
        return {x.strip().lower() for x in (s or '').split(',') if x.strip()}
    cand_h = parse_set(candidate.hobbies)
    member_h = set().union(*members['hobbies'].fillna('').apply(parse_set).tolist())
    inter = len(cand_h & member_h)
    union = len(cand_h | member_h) or 1
    hobby_sim = inter/union
    # sports match
    sports = members['sports'].fillna('').str.lower().mode()
    sport_score = 1.0 if candidate and candidate.hobbies and any(s in (candidate.hobbies or '').lower() for s in sports) else 0.0
    score = 0.6*hobby_sim + 0.4*sport_score
    result = {'culture_fit_score': round(float(score),3), 'hobby_sim': round(float(hobby_sim),3), 'sport_score': round(float(sport_score),3)}
    return result


class ScenarioPayload(BaseModel):
    salary_increase_pct: Optional[float] = 0.0
    overtime_reduction_pct: Optional[float] = 0.0
    remote_work_policy: Optional[str] = 'none'
    remote_work_level: Optional[float] = None


def _remote_level(policy: Optional[str], level: Optional[float]) -> float:
    if level is not None:
        return max(0.0, min(1.0, float(level)))
    if not policy:
        return 0.0
    policy = policy.strip().lower()
    if policy in ('remote', 'fully_remote', 'work_from_home'):
        return 1.0
    if policy in ('hybrid', 'partial', 'flexible'):
        return 0.5
    return 0.0


@router.post('/scenario')
def scenario_predict(payload: ScenarioPayload):
    """Predict the impact of salary, overtime, and remote work changes on turnover, WLB, hiring needs, and performance."""
    salary_pct = max(0.0, float(payload.salary_increase_pct or 0.0))
    overtime_pct = max(0.0, float(payload.overtime_reduction_pct or 0.0))
    remote_level = _remote_level(payload.remote_work_policy, payload.remote_work_level)

    # Baseline metrics
    turnover_df = load_csv('fau_clinic_turnover_data.csv')
    wellbeing_df = load_csv('fau_clinic_employee_wellbeing.csv')
    performance_df = load_csv('clinic_performance.csv')

    headcount = len(turnover_df)
    baseline_turnover = float(turnover_df['left'].mean())
    baseline_wlb = float(wellbeing_df['WORK_LIFE_BALANCE_SCORE'].mean())
    baseline_rating = float(performance_df['PerformanceRating'].mean())

    # Scenario effects based on rules calibrated to example values
    turnover_delta_pct = overtime_pct * 0.7 + salary_pct * 0.2 + remote_level * 10.0
    turnover_delta_pct = min(turnover_delta_pct, 40.0)
    predicted_turnover_pct = max(0.0, baseline_turnover * 100 * (1 - turnover_delta_pct / 100.0))
    predicted_turnover_reduction_pct = turnover_delta_pct

    wlb_delta_pct = overtime_pct * 0.9 + salary_pct * 0.25 + remote_level * 15.0
    wlb_delta_pct = min(wlb_delta_pct, 45.0)
    predicted_wlb_pct = baseline_wlb * (1 + wlb_delta_pct / 100.0)
    predicted_wlb_improvement_pct = wlb_delta_pct

    # Hiring needs estimate from turnover reduction
    baseline_hires = baseline_turnover * len(turnover_df)
    predicted_hires = max(0.0, predicted_turnover_pct / 100.0 * len(turnover_df))
    hiring_need_change_pct = (baseline_hires - predicted_hires) / max(baseline_hires, 1) * 100.0

    # Performance impact based on work-life balance and overtime correlation
    if 'EmpWorkLifeBalance' in performance_df.columns and 'EmpLastSalaryHikePercent' in performance_df.columns:
        corr_wlb = float(performance_df['EmpWorkLifeBalance'].corr(performance_df['PerformanceRating'])) if performance_df['EmpWorkLifeBalance'].dtype != object else 0.0
        corr_salary = float(performance_df['EmpLastSalaryHikePercent'].corr(performance_df['PerformanceRating'])) if performance_df['EmpLastSalaryHikePercent'].dtype != object else 0.0
    else:
        corr_wlb = 0.25
        corr_salary = 0.12
    performance_delta_pct = min(30.0, overtime_pct * 0.35 + remote_level * 7.0 + salary_pct * 0.15 + corr_wlb * 5.0 + corr_salary * 0.5)
    predicted_rating = round(baseline_rating * (1 + performance_delta_pct / 100.0), 2)

    return {
        'scenario': {
            'salary_increase_pct': salary_pct,
            'overtime_reduction_pct': overtime_pct,
            'remote_work_policy': payload.remote_work_policy or 'none',
            'remote_work_level': remote_level,
        },
        'baseline': {
            'turnover_rate_pct': round(baseline_turnover * 100, 2),
            'wlb_mean': round(baseline_wlb, 2),
            'performance_rating_mean': round(baseline_rating, 2),
            'headcount': len(turnover_df),
        },
        'predictions': {
            'turnover_rate_pct': round(predicted_turnover_pct, 2),
            'turnover_reduction_pct': round(predicted_turnover_reduction_pct, 2),
            'wlb_mean': round(predicted_wlb_pct, 2),
            'wlb_improvement_pct': round(predicted_wlb_improvement_pct, 2),
            'hiring_need_change_pct': round(hiring_need_change_pct, 2),
            'predicted_hiring_needs': round(predicted_hires, 1),
            'performance_rating_mean': predicted_rating,
            'performance_impact_pct': round(performance_delta_pct, 2),
        },
        'recommendation': (
            'Reduce overtime and expand flexible/remote work to lower attrition and improve WLB. '
            'Salary increases also help retention and lift performance when combined with better work-life balance.'
        ),
    }

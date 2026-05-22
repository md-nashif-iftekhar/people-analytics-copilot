from fastapi import APIRouter
from pathlib import Path
from collections import defaultdict
import pandas as pd

from .utils import load_csv

router = APIRouter()
UPLOAD_DIR = Path("uploads")


def _normalize_group(value: str) -> str:
    if pd.isna(value):
        return "unknown"
    label = str(value).strip().lower().replace('_', ' ').replace('-', ' ').replace('  ', ' ')
    return label


def _find_manager_column() -> tuple[str, str] | tuple[None, None]:
    for path in UPLOAD_DIR.glob('*.csv'):
        try:
            df = pd.read_csv(path, nrows=0)
        except Exception:
            continue
        for col in df.columns:
            if 'manager' in col.lower():
                return path.name, col
    return None, None


def _department_comparison() -> dict:
    turnover = load_csv('fau_clinic_turnover_data.csv')
    performance = load_csv('clinic_performance.csv')

    turnover = turnover.copy()
    performance = performance.copy()
    turnover['department'] = turnover['job_role'].astype(str).apply(_normalize_group)
    performance['department'] = performance['EmpJobRole'].astype(str).apply(_normalize_group)
    performance['EmpJobInvolvement'] = pd.to_numeric(performance['EmpJobInvolvement'], errors='coerce').fillna(0)
    performance['EmpWorkLifeBalance'] = pd.to_numeric(performance['EmpWorkLifeBalance'], errors='coerce').fillna(0)
    performance['over_time_flag'] = performance['OverTime'].astype(str).str.contains('yes', case=False, na=False).astype(int)
    performance['performance_rating'] = pd.to_numeric(performance['PerformanceRating'], errors='coerce').fillna(0)

    dept_keys = sorted(set(turnover['department'].unique()).union(performance['department'].unique()))
    departments = []
    for dept in dept_keys:
        dept_turn = turnover[turnover['department'] == dept]
        dept_perf = performance[performance['department'] == dept]

        turnover_rate = round(float(dept_turn['left'].mean() * 100), 2) if not dept_turn.empty else None
        avg_perf = round(float(dept_perf['performance_rating'].mean()), 2) if not dept_perf.empty else None
        avg_engagement = round(float(dept_perf['EmpJobInvolvement'].mean()), 2) if not dept_perf.empty else None
        avg_stress_proxy = round(float((5 - dept_perf['EmpWorkLifeBalance']).mean()), 2) if not dept_perf.empty else None
        overtime_pct = round(float(dept_perf['over_time_flag'].mean() * 100), 2) if not dept_perf.empty else None
        absenteeism_proxy = round(float(dept_turn['average_montly_hours'].mean()), 1) if not dept_turn.empty else None

        insight_labels = []
        if turnover_rate is not None and turnover_rate > 25:
            insight_labels.append('High turnover')
        if avg_engagement is not None and avg_engagement < 2.5:
            insight_labels.append('Low engagement')
        if avg_stress_proxy is not None and avg_stress_proxy > 2.5:
            insight_labels.append('High stress proxy')
        if overtime_pct is not None and overtime_pct > 40:
            insight_labels.append('High overtime')

        departments.append({
            'department': dept.title(),
            'turnover_rate_pct': turnover_rate,
            'avg_performance_rating': avg_perf,
            'avg_engagement': avg_engagement,
            'stress_proxy': avg_stress_proxy,
            'overtime_pct': overtime_pct,
            'absenteeism_proxy_monthly_hours': absenteeism_proxy,
            'insights': insight_labels,
            'notes': 'Absenteeism is a proxy from average monthly hours; direct absence data is not available.'
        })

    departments.sort(key=lambda x: (x['turnover_rate_pct'] or 0), reverse=True)
    return {'departments': departments}


def _team_comparison() -> dict:
    df = load_csv('fau_clinic_recommender_system.csv')
    df = df.copy()
    df['hobby_set'] = df['hobbies'].fillna('').apply(lambda s: {x.strip().lower() for x in s.split(',') if x.strip()})
    df['sports_set'] = df['sports'].fillna('').apply(lambda s: {x.strip().lower() for x in s.split(',') if x.strip()})

    summaries = []
    for team, group in df.groupby('teams'):
        pairs = []
        hob_overlap = []
        sport_overlap = []
        rows = group.to_dict('records')
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                ha, hb = a['hobby_set'], b['hobby_set']
                sa, sb = a['sports_set'], b['sports_set']
                if ha or hb:
                    union = len(ha | hb) or 1
                    hob_overlap.append(len(ha & hb) / union)
                if sa or sb:
                    union = len(sa | sb) or 1
                    sport_overlap.append(len(sa & sb) / union)
        team_cohesion = round(float(sum(hob_overlap + sport_overlap) / max(1, len(hob_overlap + sport_overlap))), 3) if (hob_overlap + sport_overlap) else 0.0
        summaries.append({
            'team': team,
            'member_count': int(len(group)),
            'avg_hobby_count': round(float(sum(len(x) for x in group['hobby_set']) / len(group)), 2),
            'avg_sports_count': round(float(sum(len(x) for x in group['sports_set']) / len(group)), 2),
            'team_cohesion': team_cohesion,
            'top_hobbies': sorted({h for s in group['hobby_set'] for h in s})[:5],
            'top_sports': sorted({s for r in group['sports_set'] for s in r})[:5],
            'insights': [
                'Low social cohesion' if team_cohesion < 0.25 else 'Good team cohesion' if team_cohesion > 0.5 else 'Moderate team cohesion'
            ],
        })

    return {'teams': summaries}


def _manager_comparison() -> dict:
    filename, manager_col = _find_manager_column()
    if not filename or not manager_col:
        return {
            'available': False,
            'message': 'Manager-level comparison is unavailable because no manager column was found in uploaded datasets. Upload a dataset containing manager assignments to enable this view.',
            'managers': []
        }
    df = load_csv(filename)
    df[manager_col] = df[manager_col].astype(str).fillna('unknown').str.strip()
    groups = []
    for manager, group in df.groupby(manager_col):
        groups.append({
            'manager': manager,
            'record_count': int(len(group)),
            'notes': 'Metrics available only for the dataset containing manager information.'
        })
    return {'available': True, 'dataset': filename, 'manager_column': manager_col, 'managers': groups}


@router.get('/overview')
def compare_overview():
    """Compare departments, teams, and managers across turnover, stress, performance, engagement, and absenteeism."""
    departments = _department_comparison()
    teams = _team_comparison()
    managers = _manager_comparison()

    insights = []
    if departments['departments']:
        highest_turnover = max([d for d in departments['departments'] if d['turnover_rate_pct'] is not None], key=lambda x: x['turnover_rate_pct'], default=None)
        if highest_turnover:
            insights.append(f"{highest_turnover['department']} has the highest turnover ({highest_turnover['turnover_rate_pct']}%).")
        lowest_engagement = min([d for d in departments['departments'] if d['avg_engagement'] is not None], key=lambda x: x['avg_engagement'], default=None)
        if lowest_engagement:
            insights.append(f"{lowest_engagement['department']} shows the lowest engagement ({lowest_engagement['avg_engagement']}).")
        highest_overtime = max([d for d in departments['departments'] if d['overtime_pct'] is not None], key=lambda x: x['overtime_pct'], default=None)
        if highest_overtime:
            insights.append(f"{highest_overtime['department']} records the highest overtime share ({highest_overtime['overtime_pct']}%).")
    if teams['teams']:
        low_cohesion = min(teams['teams'], key=lambda x: x['team_cohesion'])
        insights.append(f"{low_cohesion['team']} has the lowest team cohesion and may benefit from structured team-building.")

    return {
        'departments': departments['departments'],
        'teams': teams['teams'],
        'managers': managers,
        'insights': insights,
        'notes': 'Stress and absenteeism are approximated from available datasets; direct manager and absence fields are only available if uploaded.'
    }

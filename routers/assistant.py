from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import pandas as pd
import numpy as np

from .utils import load_csv, generate_insights
from .risk import detect_burnout, detect_turnover_risk, detect_overworked_departments
from .compare import _department_comparison

router = APIRouter()


class AssistantRequest(BaseModel):
    question: str


def _find_best_group_column(df: pd.DataFrame) -> str | None:
    for key in ['department', 'dept', 'job_role', 'EmpJobRole', 'JOB ROLE', 'JobRole']:
        if key in df.columns:
            return key
    for col in df.columns:
        if any(token in col.lower() for token in ['department', 'dept', 'job role', 'job_role', 'role']):
            return col
    return None


def _top_turnover_factors() -> str:
    try:
        df = load_csv('fau_clinic_turnover_data.csv')
    except HTTPException as exc:
        return f"Turnover analysis is unavailable: {exc.detail if hasattr(exc, 'detail') else str(exc)}"
    if 'left' not in df.columns:
        return "Turnover dataset does not contain the required 'left' column."

    rate = round(df['left'].mean() * 100, 1)
    reasons = []
    if 'satisfaction_level' in df.columns:
        left_sat = round(df[df['left'] == 1]['satisfaction_level'].mean(), 2)
        stay_sat = round(df[df['left'] == 0]['satisfaction_level'].mean(), 2)
        reasons.append(f"Employees who left have lower satisfaction ({left_sat}) than those who stayed ({stay_sat}).")
    if 'average_montly_hours' in df.columns:
        left_hours = round(df[df['left'] == 1]['average_montly_hours'].mean(), 0)
        stay_hours = round(df[df['left'] == 0]['average_montly_hours'].mean(), 0)
        if left_hours > stay_hours:
            reasons.append(f"Leavers worked about {int(left_hours - stay_hours)} more hours per month than stayed employees.")
    if 'salary' in df.columns:
        low_rate = round(df[df['salary'] == 'low']['left'].mean() * 100, 1)
        high_rate = round(df[df['salary'] == 'high']['left'].mean() * 100, 1)
        reasons.append(f"Turnover is higher among low-salary roles ({low_rate}% vs {high_rate}% for high salary).")
    by_role = None
    if 'job_role' in df.columns:
        by_role = df.groupby('job_role')['left'].mean().sort_values(ascending=False).head(3).multiply(100).round(1).to_dict()
    answer = [f"Current overall turnover is about {rate}%."] + reasons
    if by_role:
        answer.append("Highest turnover roles are: " + ", ".join(f"{role.replace('_', ' ')} ({score}%)" for role, score in by_role.items()) + ".")
    if not reasons:
        answer.append("This dataset shows turnover but not enough labeled factors to explain the change precisely.")
    return " ".join(answer)


def _burnout_risk_summary() -> str:
    result = detect_burnout()
    if 'error' in result:
        return f"Burnout risk analysis is unavailable: {result['error']}"
    count = result.get('count', 0)
    details = []
    if result.get('by_age'):
        top_age = sorted(result['by_age'].items(), key=lambda x: x[1], reverse=True)[0]
        details.append(f"Most affected age group: {top_age[0]} ({top_age[1]} employees).")
    if result.get('by_gender'):
        gender_counts = ', '.join(f"{g}: {v}" for g, v in result['by_gender'].items())
        details.append(f"Burnout flags by gender: {gender_counts}.")
    if not details:
        details.append("Burnout is identified through high stress or low sleep patterns.")
    return f"I found {count} employees flagged as burnout risk. {' '.join(details)}"


def _wlb_department_summary() -> str:
    try:
        wb = load_csv('fau_clinic_employee_wellbeing.csv')
    except HTTPException as exc:
        return f"Work-life balance analysis is unavailable: {exc.detail if hasattr(exc, 'detail') else str(exc)}"
    if 'WORK_LIFE_BALANCE_SCORE' not in wb.columns:
        return "The wellbeing dataset is missing the WORK_LIFE_BALANCE_SCORE column."
    group = _find_best_group_column(wb)
    if group:
        avg = wb.groupby(group)['WORK_LIFE_BALANCE_SCORE'].mean().sort_values().head(5).round(1).to_dict()
        if avg:
            rows = ", ".join(f"{grp}: {score}" for grp, score in avg.items())
            return f"Groups with the lowest work-life balance are: {rows}. These groups should be prioritized for WLB improvements."
    age = wb.groupby('AGE')['WORK_LIFE_BALANCE_SCORE'].mean().sort_values().head(3).round(1).to_dict()
    if age:
        rows = ", ".join(f"{grp}: {score}" for grp, score in age.items())
        return f"No department or job role field is available. The lowest WLB scores are by age bracket: {rows}."
    return "Work-life balance is measured, but the dataset does not include a clear department or role dimension."


def _staffing_shortage_projection() -> str:
    try:
        staffing = load_csv('fau_medical_staff.csv')
    except HTTPException as exc:
        fallback = f"Staffing shortage projections are unavailable: {exc.detail if hasattr(exc, 'detail') else str(exc)}"
        try:
            tr = load_csv('fau_clinic_turnover_data.csv')
            rate = round(tr['left'].mean() * 100, 1) if 'left' in tr.columns else None
            return fallback + (f" Turnover rate is {rate}% from the turnover dataset." if rate is not None else "")
        except HTTPException:
            return fallback

    if 'Avg_Patient_Number' not in staffing.columns:
        return "The workforce dataset does not contain the expected Avg_Patient_Number field for shortage projection."
    staffing['avg_patients'] = pd.to_numeric(staffing['Avg_Patient_Number'], errors='coerce').fillna(0)
    staffing['required_staff'] = staffing['avg_patients'].apply(lambda v: int(np.ceil(v / 4)) if v > 0 else 0)
    understaffed = int((staffing['avg_patients'] > staffing['required_staff'] * 4).sum())
    shortage_pct = round((understaffed / max(1, len(staffing))) * 100, 1)
    estimate = f"The current workforce plan shows {understaffed} understaffed time windows ({shortage_pct}% of windows)."
    try:
        tr = load_csv('fau_clinic_turnover_data.csv')
        if 'left' in tr.columns:
            quarter_risk = round(tr['left'].mean() * 100 * 0.25, 1)
            estimate += f" With a turnover rate of {round(tr['left'].mean() * 100,1)}%, next quarter may require roughly {quarter_risk}% more hires to maintain staffing."
    except HTTPException:
        pass
    return estimate


def _department_comparison_answer() -> str:
    try:
        overview = _department_comparison()
    except Exception as exc:
        return f"Department comparison is unavailable: {str(exc)}"
    if not overview['departments']:
        return "No department comparison data was generated."
    top = sorted([d for d in overview['departments'] if d['turnover_rate_pct'] is not None], key=lambda x: x['turnover_rate_pct'], reverse=True)[:3]
    top_rows = ", ".join(f"{d['department']} ({d['turnover_rate_pct']}%)" for d in top)
    return f"Top departments by turnover are: {top_rows}. Use the Compare view for more details."


def _fallback_answer() -> str:
    return (
        "I can answer questions about turnover trends, burnout risk, work-life balance, staffing shortages, and department comparisons. "
        "Try: 'Why is turnover increasing?', 'Which employees are burnout risks?', 'Show departments with poor work-life balance.', or 'Predict next quarter staffing shortages.'"
    )


@router.post('/query', tags=['Assistant'])
def chat_assistant(payload: AssistantRequest):
    question = payload.question.strip()
    if not question:
        raise HTTPException(400, 'Question is required.')
    text = question.lower()
    if 'turnover' in text and any(w in text for w in ['why', 'increasing', 'increase', 'rising', 'rise']):
        return {'question': question, 'answer': _top_turnover_factors(), 'intent': 'turnover_trend'}
    if 'burnout' in text or 'burn out' in text:
        return {'question': question, 'answer': _burnout_risk_summary(), 'intent': 'burnout_risk'}
    if 'work-life' in text or 'work life' in text or 'wlb' in text or 'life balance' in text:
        return {'question': question, 'answer': _wlb_department_summary(), 'intent': 'work_life_balance'}
    if 'staffing' in text or 'shortage' in text or 'next quarter' in text or 'hiring need' in text:
        return {'question': question, 'answer': _staffing_shortage_projection(), 'intent': 'staffing_shortage'}
    if 'department' in text and 'poor' in text:
        return {'question': question, 'answer': _wlb_department_summary(), 'intent': 'department_wlb'}
    if 'department' in text and 'compare' in text:
        return {'question': question, 'answer': _department_comparison_answer(), 'intent': 'department_compare'}
    if 'team' in text and 'compare' in text:
        return {'question': question, 'answer': _department_comparison_answer(), 'intent': 'team_compare'}
    if 'why' in text and 'turnover' in text:
        return {'question': question, 'answer': _top_turnover_factors(), 'intent': 'turnover_trend'}
    if 'predict' in text and 'staffing' in text:
        return {'question': question, 'answer': _staffing_shortage_projection(), 'intent': 'staffing_shortage'}
    if 'insights' in text or 'recommendation' in text or 'what should' in text:
        fallback = generate_insights()
        findings = fallback.get('findings', [])
        if findings:
            answer = ' '.join(item['text'] for item in findings[:4])
        else:
            answer = _fallback_answer()
        return {'question': question, 'answer': answer, 'intent': 'insights'}
    return {'question': question, 'answer': _fallback_answer(), 'intent': 'fallback'}

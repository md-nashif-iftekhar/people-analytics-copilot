from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from io import BytesIO
from typing import List
from datetime import datetime
import os

from .utils import generate_insights, df_info, load_csv

router = APIRouter()


def build_recommendations(findings: List[dict]) -> List[str]:
    """Convert findings into simple actionable recommendations."""
    recs = []
    for f in findings:
        text = f.get("text", "").lower()
        if "turnover" in text or "left" in text or "leavers" in text:
            recs.append("Investigate high-turnover roles; consider targeted retention programs and workload review.")
        if "satisfaction" in text or "satisfaction" in text:
            recs.append("Run targeted engagement surveys for low-satisfaction cohorts and design improvement plans.")
        if "stress" in text or "work_life_balance" in text or "wlb" in text:
            recs.append("Offer wellbeing interventions: flexible schedules, counselling, and workload adjustments.")
        if "hire rate" in text or "hire" in text:
            recs.append("Review recruitment funnel and bias checks; improve sourcing for low-converting groups.")
        if "sleep" in text:
            recs.append("Promote sleep hygiene and wellbeing programs to improve employee WLB.")
    # deduplicate while preserving order
    seen = set(); out = []
    for r in recs:
        if r not in seen:
            seen.add(r); out.append(r)
    if not out:
        out.append("No specific recommendations identified — run more analyses or upload richer datasets.")
    return out


REPORTS_DIR = os.path.join("uploads", "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


def _create_charts(findings: List[dict]) -> List[BytesIO]:
    """Create simple charts (matplotlib) based on CSVs and return list of PNG bytes buffers."""
    buffers = []
    try:
        import matplotlib.pyplot as plt
        from matplotlib.ticker import MaxNLocator
    except Exception:
        return buffers

    # Attempt a turnover by job_role bar chart
    try:
        df = load_csv("fau_clinic_turnover_data.csv")
        if "job_role" in df.columns and "left" in df.columns:
            by_role = (df.groupby("job_role")["left"].mean() * 100).sort_values(ascending=False).head(10)
            fig, ax = plt.subplots(figsize=(6, 3))
            by_role.plot(kind="bar", ax=ax, color="#2b8cbe")
            ax.set_ylabel("Turnover %")
            ax.set_xlabel("Job Role")
            ax.yaxis.set_major_locator(MaxNLocator(integer=True))
            plt.xticks(rotation=45, ha="right")
            buf = BytesIO()
            plt.tight_layout()
            fig.savefig(buf, format="png")
            plt.close(fig)
            buf.seek(0)
            buffers.append(buf)
    except Exception:
        pass

    # Attempt a hire rate pie chart
    try:
        df = load_csv("fau_clinic_recruitment.csv")
        if "hired" in df.columns:
            hired = df['hired'].map({'TRUE': 1, 'FALSE': 0, True: 1, False: 0}).fillna(0)
            vals = [hired.sum(), len(hired)-hired.sum()]
            labels = ["Hired", "Not Hired"]
            fig, ax = plt.subplots(figsize=(4, 3))
            ax.pie(vals, labels=labels, autopct="%1.1f%%", colors=["#4daf4a", "#e41a1c"])
            plt.tight_layout()
            buf = BytesIO()
            fig.savefig(buf, format="png")
            plt.close(fig)
            buf.seek(0)
            buffers.append(buf)
    except Exception:
        pass

    return buffers


def _save_pdf_to_file(findings: List[dict], recs: List[str], charts: List[BytesIO], filename: str) -> str:
    """Build PDF and save to uploads/reports/filename, return path."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader

    path = os.path.join(REPORTS_DIR, filename)
    c = canvas.Canvas(path, pagesize=letter)
    width, height = letter
    y = height - 72
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, y, "People Analytics Report")
    y -= 28
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, y, "Executive Summary")
    y -= 20
    c.setFont("Helvetica", 10)
    for f in findings[:8]:
        text = f.get("text", "")
        lines = text.split("\n")
        for line in lines:
            c.drawString(80, y, line[:95])
            y -= 14
            if y < 120:
                c.showPage(); y = height - 72
    y -= 6
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, y, "Recommendations")
    y -= 18
    c.setFont("Helvetica", 10)
    for r in recs:
        c.drawString(80, y, "- " + r[:110])
        y -= 14
        if y < 120:
            c.showPage(); y = height - 72

    # Add charts
    for buf in charts:
        if y < 300:
            c.showPage(); y = height - 72
        try:
            img = ImageReader(buf)
            c.drawImage(img, 72, y-220, width=460, height=220)
            y -= 240
        except Exception:
            pass

    c.showPage()
    c.save()
    return path


@router.get("/executive", tags=["Reports"])
def executive_summary():
    """Return a short executive summary (top findings + recommendations)."""
    insights = generate_insights()
    findings = insights.get("findings", [])
    top = findings[:4]
    summary_text = "\n".join([f"- {f.get('text')}" for f in top])
    recs = build_recommendations(findings)
    return JSONResponse({"summary": summary_text, "recommendations": recs, "total_findings": insights.get("total", 0)})


@router.get("/hr-report", tags=["Reports"])
def hr_report():
    """Return a structured HR report (dataset summaries + insights)."""
    report = {"datasets": {}, "insights": generate_insights()}
    # include basic df_info for known datasets if available
    files = [
        ("turnover", "fau_clinic_turnover_data.csv"),
        ("wellbeing", "fau_clinic_employee_wellbeing.csv"),
        ("recruitment", "fau_clinic_recruitment.csv"),
    ]
    for name, fname in files:
        try:
            df = load_csv(fname)
            report["datasets"][name] = df_info(df)
        except Exception as e:
            report["datasets"][name] = {"error": str(e)}
    return report


@router.get("/recommendations", tags=["Reports"])
def recommendations():
    """Return generated recommendations based on insights."""
    insights = generate_insights()
    recs = build_recommendations(insights.get("findings", []))
    return {"recommendations": recs}


@router.get("/pdf", tags=["Reports"])
def pdf_report():
    """Generate a simple PDF report combining the executive summary and recommendations."""
    insights = generate_insights()
    findings = insights.get("findings", [])
    recs = build_recommendations(findings)

    # generate PDF in-memory
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception as e:
        raise HTTPException(500, f"PDF generation dependency missing: {e}")

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 72
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, y, "Executive Summary")
    y -= 24
    c.setFont("Helvetica", 10)
    for f in findings[:6]:
        text = f.get("text", "")
        for line in text.split('\n'):
            c.drawString(80, y, line[:100])
            y -= 14
            if y < 72:
                c.showPage()
                y = height - 72
    y -= 8
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, y, "Recommendations")
    y -= 18
    c.setFont("Helvetica", 10)
    for r in recs:
        for line in r.split('\n'):
            c.drawString(80, y, line[:100])
            y -= 14
            if y < 72:
                c.showPage()
                y = height - 72
    c.showPage()
    c.save()
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=hr_report.pdf"})


@router.post("/generate", tags=["Reports"])
def generate_and_save_report() -> dict:
    """Generate a PDF report, save it under uploads/reports/, and return filename and path."""
    insights = generate_insights()
    findings = insights.get("findings", [])
    recs = build_recommendations(findings)
    charts = _create_charts(findings)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = f"people_report_{ts}.pdf"
    path = _save_pdf_to_file(findings, recs, charts, filename)
    return {"filename": filename, "path": path}


def generate_and_save_report_wrapper():
    """Wrapper used by scheduler where FastAPI internals may not be available."""
    try:
        generate_and_save_report()
    except Exception:
        pass


@router.get("/list", tags=["Reports"])
def list_reports():
    """List saved PDF reports in uploads/reports/"""
    files = []
    for f in sorted(os.listdir(REPORTS_DIR), reverse=True):
        if f.lower().endswith('.pdf'):
            full = os.path.join(REPORTS_DIR, f)
            files.append({"filename": f, "size": os.path.getsize(full), "path": full})
    return {"reports": files}


@router.get("/download", tags=["Reports"])
def download_report(filename: str = Query(...)):
    """Download a saved report by filename (query param `filename`)."""
    safe = os.path.basename(filename)
    full = os.path.join(REPORTS_DIR, safe)
    if not os.path.exists(full):
        raise HTTPException(404, "Report not found")
    return FileResponse(full, media_type='application/pdf', filename=safe)

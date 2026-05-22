"""
People Analytics Platform - FastAPI Backend
==========================================
Run with: uvicorn main:app --reload --port 8000
Docs at:  http://localhost:8000/docs
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
import shutil, os
from pathlib import Path

from routers import assistant, workforce, recruitment, recommender, performance, wellbeing, turnover, compare
from routers.utils import generate_insights
from routers import reports
from routers import risk
from routers import social
from routers import predict
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="People Analytics Platform",
    description="HR analytics backend: workforce planning, recruitment, recommender, performance, well-being, turnover",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (frontend)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Register routers
app.include_router(workforce.router,   prefix="/api/workforce",   tags=["Workforce Planning"])
app.include_router(recruitment.router, prefix="/api/recruitment", tags=["Recruitment"])
app.include_router(recommender.router, prefix="/api/recommender", tags=["Recommender"])
app.include_router(performance.router, prefix="/api/performance", tags=["Performance"])
app.include_router(wellbeing.router,   prefix="/api/wellbeing",   tags=["Well-Being"])
app.include_router(turnover.router,    prefix="/api/turnover",    tags=["Turnover"])
app.include_router(reports.router,     prefix="/api/reports",     tags=["Reports"])
app.include_router(risk.router,        prefix="/api/risk",        tags=["Risk"])
app.include_router(social.router,      prefix="/api/social",      tags=["Social"])
app.include_router(predict.router,     prefix="/api/predict",     tags=["Predict"])
app.include_router(compare.router,     prefix="/api/compare",     tags=["Compare"])
app.include_router(assistant.router,   prefix="/api/assistant",   tags=["Assistant"])


def _schedule_reports():
    """Start a background scheduler to generate reports periodically."""
    scheduler = BackgroundScheduler()
    # Example: run daily at 08:00 UTC. For testing you can change to '*/1 * * * *' style via CronTrigger.
    trigger = CronTrigger(hour="8", minute="0")
    # Scheduler job uses the wrapper to avoid FastAPI context issues
    scheduler.add_job(lambda: reports.generate_and_save_report_wrapper(), trigger, id="daily_report", replace_existing=True)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())
    return scheduler


@app.on_event("startup")
def startup_event():
    app.state.scheduler = _schedule_reports()


@app.on_event("shutdown")
def shutdown_event():
    sched = getattr(app.state, 'scheduler', None)
    if sched:
        sched.shutdown()


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root():
    html_path = Path("static/index.html")
    if html_path.exists():
        return html_path.read_text(encoding='utf-8')
    return "<h2>People Analytics API running. Visit <a href='/docs'>/docs</a> for the API explorer.</h2>"


@app.post("/api/upload", tags=["Data Upload"])
async def upload_dataset(file: UploadFile = File(...)):
    """Upload a CSV dataset. Auto-detects dataset type by filename or columns."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only CSV files are supported.")
    dest = UPLOAD_DIR / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    import pandas as pd
    df = pd.read_csv(dest, nrows=2)
    return {
        "filename": file.filename,
        "columns": list(df.columns),
        "message": f"Uploaded successfully to {dest}",
    }


@app.get("/api/datasets", tags=["Data Upload"])
def list_datasets():
    """List all available CSV datasets in the uploads folder."""
    import pandas as pd
    result = []
    for f in sorted(UPLOAD_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(f)
            result.append({
                "filename": f.name,
                "rows": len(df),
                "columns": len(df.columns),
                "column_names": list(df.columns),
            })
        except Exception as e:
            result.append({"filename": f.name, "error": str(e)})
    return result


@app.post("/api/manual-entry", tags=["Data Upload"])
async def manual_entry(request: Request):
    """Append a single manually-entered row to an existing dataset CSV."""
    import pandas as pd
    body = await request.json()
    dataset = body.pop("_dataset", None)
    file_map = {
        "turnover":    "fau_clinic_turnover_data.csv",
        "wellbeing":   "fau_clinic_employee_wellbeing.csv",
        "recruitment": "fau_clinic_recruitment.csv",
    }
    if dataset not in file_map:
        raise HTTPException(400, f"Unknown dataset: {dataset}")
    filepath = UPLOAD_DIR / file_map[dataset]
    if not filepath.exists():
        raise HTTPException(404, f"Dataset file not found: {file_map[dataset]}")
    df = pd.read_csv(filepath)
    new_row = {k: v for k, v in body.items() if v is not None and v != ""}
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(filepath, index=False)
    return {"message": "Row added successfully", "total_rows": len(df)}


@app.get("/api/insights", tags=["System"])
def get_insights():
    """Generate natural language findings from available datasets via utility."""
    return generate_insights()

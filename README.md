# People Analytics Platform — Python Backend

A production-ready FastAPI backend for HR analytics.  
Upload your CSV data and get instant ML-powered insights across 6 modules.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Place your CSV files in the uploads/ folder

# 3. Start the server
uvicorn main:app --reload --port 8000

# 4. Open the interactive API docs
open http://localhost:8000/docs
```

---

## Project Structure

```
people_analytics/
├── main.py                    # FastAPI app, upload & dataset endpoints
├── requirements.txt
├── uploads/                   # CSV datasets go here
│   ├── fau_medical_staff.csv
│   ├── fau_clinic_recruitment.csv
│   ├── fau_clinic_recommender_system.csv
│   ├── clinic_performance.csv
│   ├── fau_clinic_employee_wellbeing.csv
│   └── fau_clinic_turnover_data.csv
├── routers/
│   ├── utils.py               # Shared: load_csv, df_info, corr_matrix
│   ├── workforce.py           # Shift staffing optimizer
│   ├── recruitment.py         # Association rule mining + bias detection
│   ├── recommender.py         # Jaccard similarity recommender
│   ├── performance.py         # EDA + Random Forest / SVM / MLP
│   ├── wellbeing.py           # WLB analysis + Linear Regression
│   └── turnover.py            # Turnover EDA + classifier + risk profile
└── static/                    # Frontend files (optional)
```

---

## API Endpoints

### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/datasets` | List all uploaded datasets |
| POST | `/api/upload` | Upload a new CSV dataset |

### Workforce Planning
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/workforce/` | Optimal staffing per shift |
| GET | `/api/workforce/raw` | Raw dataset as JSON |

**Key parameters:**
- `filename` — CSV filename (default: `fau_medical_staff.csv`)
- `service_level` — max patients one staff handles per hour (default: 4)

---

### Recruitment
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/recruitment/` | Association rule mining |
| GET | `/api/recruitment/bias` | Hiring bias by gender/location |
| GET | `/api/recruitment/summary` | Hire rate statistics |

**Key parameters:**
- `min_support` — minimum rule support (default: 0.05)
- `min_confidence` — minimum confidence (default: 0.5)
- `min_lift` — minimum lift (default: 1.0)
- `target_col` — outcome column (default: `critical_care_nursing`)

---

### Employee Recommender
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/recommender/` | Top-N similar colleagues |
| GET | `/api/recommender/employees` | List all employee IDs |

**Key parameters:**
- `employee_id` — target employee (default: `emp_050`)
- `top_n` — number of recommendations (default: 3)
- `weight_hobbies`, `weight_sports`, `weight_teams`, `weight_experience` — similarity weights

---

### Employee Performance
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/performance/eda` | Exploratory data analysis |
| GET | `/api/performance/correlation` | Correlation matrix |
| GET | `/api/performance/train` | Train & evaluate ML model |

**Key parameters:**
- `model_type` — `random_forest` (default) | `svm` | `mlp`
- `test_size` — train/test split (default: 0.2)

---

### Well-Being
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/wellbeing/eda` | Stress by gender/age, WLB by group |
| GET | `/api/wellbeing/correlation` | Correlation with WLB score |
| GET | `/api/wellbeing/train` | Linear Regression + predictions |

---

### Turnover
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/turnover/eda` | Turnover rates, satisfaction, salary |
| GET | `/api/turnover/correlation` | Correlation with 'left' |
| GET | `/api/turnover/train` | Train turnover classifier |
| GET | `/api/turnover/risk-profile` | Segment-level risk analysis |

**Key parameters:**
- `model_type` — `random_forest` | `gradient_boosting` | `logistic_regression`

---

## Example Usage (Python)

```python
import requests

BASE = "http://localhost:8000"

# List datasets
print(requests.get(f"{BASE}/api/datasets").json())

# Workforce planning with custom service level
resp = requests.get(f"{BASE}/api/workforce/", params={"service_level": 5})
for shift in resp.json()["shift_summary"]:
    print(f"{shift['shift']}: {shift['recommended_staff']} staff")

# Association rules for recruitment
rules = requests.get(f"{BASE}/api/recruitment/", params={
    "min_support": 0.04, "min_confidence": 0.6, "target_col": "critical_care_nursing"
}).json()
for rule in rules["top_rules"][:3]:
    print(rule["rule_str"], "| lift:", rule["lift"])

# Recommender for a new employee
recs = requests.get(f"{BASE}/api/recommender/", params={"employee_id": "emp_050", "top_n": 3}).json()
for r in recs["recommendations"]:
    print(r["employee_id"], "similarity:", r["similarity_score"])

# Train performance model
perf = requests.get(f"{BASE}/api/performance/train", params={"model_type": "random_forest"}).json()
print("Accuracy:", perf["metrics"]["accuracy"])
print("Top feature:", list(perf["feature_importance"].keys())[0])

# WLB regression
wlb = requests.get(f"{BASE}/api/wellbeing/train").json()
print("R2 score:", wlb["metrics"]["r2_score"])
print("Hypothetical prediction:", wlb["hypothetical_prediction"]["predicted_wlb_score"])

# Turnover prediction
turnover = requests.get(f"{BASE}/api/turnover/train", params={"model_type": "random_forest"}).json()
print("Turnover AUC:", turnover["metrics"]["roc_auc"])
print("Why they leave:", turnover["why_employees_leave"])
```

---

## Bring Your Own Data

Any CSV with the right columns will work. The API auto-validates columns and returns clear error messages if columns are missing.

| Module | Required columns |
|--------|-----------------|
| Workforce | `Avg_Patient_Number`, shift columns |
| Recruitment | Boolean skill/outcome columns |
| Recommender | `id`, `hobbies`, `sports`, `teams` |
| Performance | `PerformanceRating` + numeric/categorical HR features |
| Well-Being | `WORK_LIFE_BALANCE_SCORE` + stress/lifestyle features |
| Turnover | `left` (0/1) + satisfaction, salary, role columns |

Upload via:
```bash
curl -X POST "http://localhost:8000/api/upload" \
     -H "accept: application/json" \
     -F "file=@my_hr_data.csv"
```

---

## ML Models Used

| Module | Algorithm | Metric |
|--------|-----------|--------|
| Performance | Random Forest / SVM / MLP | Accuracy, Precision, Recall, F1 |
| Well-Being | Linear Regression | R², MAE, RMSE |
| Turnover | Random Forest / Gradient Boosting / Logistic Regression | Accuracy, AUC-ROC, F1 |
| Recruitment | Apriori (association rules) | Support, Confidence, Lift |
| Recommender | Weighted Jaccard Similarity | Similarity score 0–1 |
| Workforce | Erlang-inspired service level | Staff count per shift |

---

## Results from Your Data

| Module | Key Result |
|--------|-----------|
| Workforce | Shift 1: 3 staff · Shift 2: 2 staff · Shift 3: 1 staff |
| Recruitment | 5 rules for critical care nursing (top lift: ~2.3) |
| Recommender | emp_050 best match: emp_001 (Jaccard ~0.80) |
| Performance | Random Forest accuracy: **91.3%** |
| Well-Being | Linear Regression R²: **0.854** |
| Turnover | Random Forest AUC: **0.996** |

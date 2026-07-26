# Backend — Fish Stress Detection

FastAPI backend handling data ingestion, storage, REST API, and alerting.

## Team Member
- **Taahira** — Backend, Database, Dashboard, Alerts

## Tech Stack
- FastAPI + Uvicorn (web framework)
- PostgreSQL + SQLAlchemy (database)
- MQTT (receive sensor data from ESP32)
- Streamlit (dashboard)
- Telegram Bot API (alerts)

# Fish Stress Detection — Backend
Real-time individual fish stress detection system.
---

## System overview
ESP32 sensors → MQTT broker → backend
↓
CV module (per-fish metrics) → REST API → PostgreSQL
↓
FSI computation
↓
Streamlit dashboard + Telegram alerts

## Fish Stress Index formula
**Per-fish behavioral score (0.0 – 1.0):**
score += surface_visits_weight (0.20) — gasping at surface
score += turning_frequency_weight (0.20) — erratic direction changes
score += avg_speed_weight (0.20) — thrashing or lethargy
score += motion_variability_weight(0.15) — inconsistent swimming
score += avg_acceleration_weight (0.15) — sudden bursts
score += bottom_dwelling_weight (0.05) — chronic lethargy
score += inactivity_pct_weight (0.05) — listlessness

**Stress levels:**
0.00 – 0.29 → NORMAL — healthy, no action needed
0.30 – 0.59 → WARNING — monitor closely
0.60 – 1.00 → CRITICAL — immediate intervention required

---

## Quick start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Fill in DATABASE_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# 3. Run migrations
alembic upgrade head

# 4. Start server
uvicorn app.main:app --reload --port 8000

# 5. Start dashboard
streamlit run app/dashboard/streamlit_app.py --server.port 8501
```

**API docs:** http://localhost:8000/docs  
**Dashboard:** http://localhost:8501

---

## API reference

### Auth
POST /api/v1/auth/login — get JWT token (form: username, password)
GET /api/v1/auth/me — current user info

| User | Password | Role |
|------|----------|------|
| taahira | backend2024 | admin |
| likhita | cv2024 | writer |
| yashwanth | hardware2024 | writer |
| viewer | view2024 | reader |

### Tanks
GET /api/v1/tanks/ — list all active tanks
POST /api/v1/tanks/ — register a tank
GET /api/v1/tanks/{tank_id} — get tank details
PATCH /api/v1/tanks/{tank_id} — update tank metadata
DELETE /api/v1/tanks/{tank_id} — deactivate tank
GET /api/v1/tanks/{tank_id}/dashboard — full dashboard payload

### Sensors
POST /api/v1/sensors/{tank_id}/readings — manual sensor ingestion
GET /api/v1/sensors/{tank_id}/latest — latest reading
GET /api/v1/sensors/{tank_id}/history?hours=N — history for charts
POST /api/v1/sensors/{tank_id}/behavior/batch — per-fish batch (Likhita)
GET /api/v1/sensors/{tank_id}/stress/current — current FSI
GET /api/v1/sensors/{tank_id}/stress/history — FSI history

### Alerts
GET /api/v1/alerts/{tank_id}?status=active — tank alerts
PATCH /api/v1/alerts/{id}/resolve — resolve alert
GET /api/v1/alerts/stats/summary — system-wide stats

---

## Integration — Likhita (CV module)

Send per-fish batch every 30 seconds:

```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/sensors/tank_01/behavior/batch",
    json={
        "tank_id":   "tank_01",
        "timestamp": "2026-07-23T12:30:00Z",
        "fish": [
            {
                "fish_id":           2,
                "avg_speed":         3.2,
                "avg_acceleration":  1.5,
                "turning_frequency": 6.0,
                "motion_variability":2.8,
                "surface_visits":    1,
                "bottom_dwelling":   12.0,
                "inactivity_pct":    15.0
            }
        ]
    }
)
result = response.json()
# result["results"] — list of {fish_id, stress_score, stress_level}
# result["tank_summary"] — {avg_stress, critical_fish, most_stressed_fish_id}
```

## Integration — Yashwanth (ESP32)

Publish to MQTT topic `fish_tank/tank_01/sensors` every 10 seconds:

```json
{
  "tank_id":     "tank_01",
  "temperature": 26.5,
  "ph":          7.2,
  "do_mg_l":     6.8,
  "ammonia":     null,
  "alerts":      [],
  "status":      "ok"
}
```

No changes needed to Yashwanth's code. Sensor data is automatically
used as environmental context for each fish analysis window.

---

## Project structure
backend/
├── app/
│ ├── api/
│ │ ├── auth.py JWT authentication
│ │ ├── tanks.py Tank management + dashboard endpoint
│ │ ├── sensors.py Sensor ingestion + per-fish batch
│ │ ├── alerts.py Alert management
│ │ └── health.py Health checks
│ ├── core/
│ │ ├── config.py Environment settings (.env)
│ │ ├── database.py Async SQLAlchemy engine
│ │ └── security.py JWT + bcrypt
│ ├── models/
│ │ └── models.py 6 database tables
│ ├── schemas/
│ │ └── schemas.py Pydantic request/response models
│ ├── services/
│ │ ├── mqtt_consumer.py MQTT background listener
│ │ ├── fsi_engine.py FSI + per-fish stress formula
│ │ └── alert_service.py Telegram + email notifications
│ ├── dashboard/
│ │ └── streamlit_app.py Live monitoring dashboard
│ └── main.py FastAPI app entry point
├── migrations/ Alembic database migrations
├── scripts/
│ ├── test_all_endpoints.py 20-test suite
│ └── simulate_full_pipeline.py Integration test
├── requirements.txt
├── .env.example
└── README.md

## Database tables

| Table | Purpose |
|-------|---------|
| `tanks` | Fish tank registry |
| `sensor_readings` | Water quality from ESP32 |
| `behavior_readings` | Legacy tank-level behavior |
| `stress_scores` | Tank-level FSI history |
| `alerts` | Threshold breach alerts |
| `fish_stress_records` | **Per-fish individual stress** (professor's requirement) |

## Running tests

```bash
# 20-endpoint test suite
python scripts/test_all_endpoints.py

# Full pipeline simulation (end-to-end)
python scripts/simulate_full_pipeline.py
```

## Days completed

| Day | Built |
|-----|-------|
| 1 | FastAPI scaffold, config, health endpoint |
| 2 | PostgreSQL + 5 tables, Alembic migrations |
| 3 | MQTT consumer, FSI engine, REST APIs |
| 4 | Alerts API, JWT auth, behavior endpoint, 20-test suite |
| 5 | Streamlit dashboard — FSI gauge, charts, alerts |
| 6 | Telegram alerts, email, resolution notices |
| 7 | Per-fish batch endpoint, pipeline simulation, PR |
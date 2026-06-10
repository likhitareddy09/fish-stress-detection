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

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set up environment
```bash
cp .env.example .env
# Edit .env with your actual values
```

### 3. Run the server
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### 4. Open API docs
Visit: http://localhost:8000/docs

## Project Structure
backend/
├── app/
│   ├── api/          # API route handlers
│   ├── core/         # Config and database setup
│   ├── models/       # Database table definitions
│   ├── schemas/      # Pydantic request/response models
│   ├── services/     # Business logic (MQTT, alerts)
│   ├── dashboard/    # Streamlit dashboard
│   └── main.py       # App entry point
├── tests/            # Unit tests
├── requirements.txt
├── .env.example
└── README.md

## API Endpoints (Day 1)
- `GET /` — Root, shows API info
- `GET /api/v1/health` — Health check
- `GET /api/v1/ping` — Ping/pong

More endpoints added each day.
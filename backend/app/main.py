from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.models import Tank, SensorReading, BehaviorReading, StressScore, Alert

from app.core.config import settings
from app.core.database import engine, Base
from app.api import health

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 50)
    print("  Fish Stress Detection Backend Starting...")
    print("=" * 50)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            print("  Database connected. All tables verified.")
    except Exception as e:
        print(f"  [WARNING] Database error: {e.__class__.__name__}: {e}")
        print("  Server starting without DB connection.")

    print("  Server ready at http://localhost:8000/docs")
    print("=" * 50)

    yield

    print("Server shutting down...")
    await engine.dispose()


app = FastAPI(
    title="Fish Stress Detection API",
    description="""
    Backend API for the Fish Stress Detection system.
    
    **Team:** Taahira (Backend), Likhita (AI/CV), Yashwanth (Hardware)
    
    **Features:**
    - Real-time sensor data ingestion via MQTT
    - Fish stress index computation
    - Historical data storage in PostgreSQL
    - Telegram and email alerts
    - REST API for dashboard
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Fish Stress Detection API",
        "status": "running",
        "docs": "http://localhost:8000/docs",
        "health": "http://localhost:8000/api/v1/health",
    }
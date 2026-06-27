import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine, Base
from app.api import health, tanks, sensors, alerts, auth
from app.models.models import Tank, SensorReading, BehaviorReading, StressScore, Alert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 55)
    print("  Fish Stress Detection Backend — Starting")
    print("=" * 55)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database: all tables verified.")
    except Exception as e:
        logger.warning(f"Database unavailable: {e.__class__.__name__}. Continuing without DB.")

    try:
        from app.services.mqtt_consumer import start_mqtt_consumer
        loop = asyncio.get_event_loop()
        start_mqtt_consumer(loop)
        logger.info("MQTT consumer: started, listening on fish_tank/#")
    except Exception as e:
        logger.warning(f"MQTT consumer failed to start: {e}. Is Mosquitto running?")

    print("=" * 55)
    print("  Server ready at http://localhost:8000")
    print("  API docs   at http://localhost:8000/docs")
    print("=" * 55)

    yield

    logger.info("Shutting down...")
    await engine.dispose()


app = FastAPI(
    title="Fish Stress Detection API",
    description="""
Backend for the Fish Stress Detection System.

**Team:** Taahira (Backend) · Likhita (AI/CV) · Yashwanth (Hardware)

**Features:**
- Tank management API
- Sensor ingestion API (MQTT + REST)
- FSI computation engine
- Alerts API
- JWT Authentication
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

app.include_router(health.router,  prefix="/api/v1",          tags=["Health"])
app.include_router(auth.router,    prefix="/api/v1/auth",      tags=["Auth"])
app.include_router(tanks.router,   prefix="/api/v1/tanks",     tags=["Tanks"])
app.include_router(sensors.router, prefix="/api/v1/sensors",   tags=["Sensors"])
app.include_router(alerts.router,  prefix="/api/v1/alerts",    tags=["Alerts"])


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Fish Stress Detection API",
        "status":  "running",
        "version": "1.0.0",
        "docs":    "http://localhost:8000/docs",
    }
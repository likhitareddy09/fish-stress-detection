from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models.models import Tank, SensorReading, BehaviorReading, StressScore
from app.schemas.schemas import (
    SensorReadingCreate, SensorReadingResponse, SensorHistoryResponse,
    BehaviorReadingCreate, BehaviorReadingResponse,
    StressScoreResponse,
    BehaviorIngestResponse,
)
from app.services.fsi_engine import compute_fsi

router = APIRouter()


# ── Sensor readings ───────────────────────────────────────────────────────────

@router.get("/{tank_id}/latest", response_model=SensorReadingResponse)
async def get_latest_sensor(tank_id: str, db: AsyncSession = Depends(get_db)):
    """Get the most recent sensor reading for a tank."""
    tank = await _get_tank_or_404(tank_id, db)
    result = await db.execute(
        select(SensorReading)
        .where(SensorReading.tank_id == tank.id)
        .order_by(desc(SensorReading.timestamp))
        .limit(1)
    )
    reading = result.scalar_one_or_none()
    if not reading:
        raise HTTPException(status_code=404, detail="No sensor readings found for this tank.")
    return reading


@router.get("/{tank_id}/history", response_model=SensorHistoryResponse)
async def get_sensor_history(
    tank_id: str,
    hours: int = Query(default=24, ge=1, le=168, description="How many hours of history to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get sensor reading history for charting in Streamlit.
    Default: last 24 hours. Max: 7 days (168 hours).
    """
    tank = await _get_tank_or_404(tank_id, db)
    since = datetime.utcnow() - timedelta(hours=hours)

    result = await db.execute(
        select(SensorReading)
        .where(SensorReading.tank_id == tank.id, SensorReading.timestamp >= since)
        .order_by(SensorReading.timestamp)
    )
    readings = result.scalars().all()

    return SensorHistoryResponse(
        tank_id=tank_id,
        readings=readings,
        count=len(readings),
    )


@router.post("/{tank_id}/readings", response_model=SensorReadingResponse, status_code=201)
async def ingest_sensor_reading(
    tank_id: str,
    data: SensorReadingCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Manually POST a sensor reading (used for testing without MQTT).
    In production, readings come in via the MQTT consumer automatically.
    """
    tank = await _get_tank_or_404(tank_id, db)

    reading = SensorReading(
        tank_id=tank.id,
        temperature=data.temperature,
        ph=data.ph,
        dissolved_o2=data.dissolved_o2,
        ammonia=data.ammonia,
        turbidity=data.turbidity,
    )
    db.add(reading)
    await db.flush()  # Get the reading ID before computing FSI

    # Compute and save FSI score immediately
    fsi_score, stress_level, wq_score = compute_fsi(
        temperature=data.temperature,
        ph=data.ph,
        dissolved_o2=data.dissolved_o2,
        ammonia=data.ammonia,
    )
    from app.models.models import StressScore
    score = StressScore(
        tank_id=tank.id,
        fsi_score=fsi_score,
        stress_level=stress_level,
        water_quality_score=wq_score,
        sensor_reading_id=reading.id,
    )
    db.add(score)
    await db.commit()
    await db.refresh(reading)
    return reading


# ── Behavior readings (sent by Likhita's CV module) ──────────────────────────

@router.post(
    "/{tank_id}/behavior",
    response_model=BehaviorIngestResponse,
    status_code=201,
    summary="Receive behavioral data from CV module",
    description="""
    Called by Likhita's CV module every 30 seconds with aggregated fish behavior metrics.
    
    The backend will:
    1. Save the behavior reading to the database
    2. Fetch the latest water quality reading from Yashwanth's sensors
    3. Compute the combined FSI = 0.60 × WQ + 0.40 × behavior
    4. Return the computed stress score so the CV module can log it
    
    **Do NOT send:** fish_id, behavior_score, stress_level — these are computed here.
    **DO send:** raw behavioral measurements as listed below.
    """,
)
async def ingest_behavior_reading(
    tank_id: str,
    data: BehaviorReadingCreate,
    db: AsyncSession = Depends(get_db),
):
    from app.schemas.schemas import BehaviorIngestResponse

    tank = await _get_tank_or_404(tank_id, db)

    # Save behavior reading
    behavior = BehaviorReading(
        tank_id=          tank.id,
        fish_count=       data.fish_count,
        avg_speed=        data.avg_speed,
        avg_acceleration= data.avg_acceleration,
        turning_frequency=data.turning_frequency,
        motion_variability=data.motion_variability,
        surface_visits=   data.surface_visits,
        bottom_dwelling=  data.bottom_dwelling,
        inactivity_pct=   data.inactivity_pct,
        schooling_density=data.schooling_density,
    )
    db.add(behavior)
    await db.flush()

    # Get latest water quality for combined FSI
    sensor_result = await db.execute(
        select(SensorReading)
        .where(SensorReading.tank_id == tank.id)
        .order_by(desc(SensorReading.timestamp))
        .limit(1)
    )
    latest_sensor = sensor_result.scalar_one_or_none()

    # Compute combined FSI
    fsi_score, stress_level, wq_score = compute_fsi(
        temperature=      latest_sensor.temperature   if latest_sensor else None,
        ph=               latest_sensor.ph            if latest_sensor else None,
        dissolved_o2=     latest_sensor.dissolved_o2  if latest_sensor else None,
        ammonia=          latest_sensor.ammonia        if latest_sensor else None,
        avg_speed=        data.avg_speed,
        turning_frequency=data.turning_frequency,
        surface_visits=   data.surface_visits,
        inactivity_pct=   data.inactivity_pct,
    )

    # Compute behavioral component separately for the response
    from app.services.fsi_engine import _normalize_behavior, BEH_WEIGHTS
    beh_score = None
    if any(v is not None for v in [data.avg_speed, data.turning_frequency,
                                    data.surface_visits, data.inactivity_pct]):
        beh_score = round(
            _normalize_behavior(
                data.avg_speed, data.turning_frequency,
                data.surface_visits, data.inactivity_pct
            ), 4
        )

    # Save stress score with both components
    score = StressScore(
        tank_id=             tank.id,
        fsi_score=           fsi_score,
        stress_level=        stress_level,
        water_quality_score= wq_score,
        behavioral_score=    beh_score,
        behavior_reading_id= behavior.id,
    )
    db.add(score)
    await db.commit()
    await db.refresh(behavior)

    level_messages = {
        "normal":   "All good — fish appear healthy.",
        "warning":  "Elevated stress detected. Monitor closely.",
        "critical": "CRITICAL stress — immediate attention required!",
    }

    return BehaviorIngestResponse(
        behavior_reading_id= behavior.id,
        tank_id=             tank_id,
        fish_count=          data.fish_count,
        timestamp=           behavior.timestamp,
        fsi_score=           fsi_score,
        stress_level=        stress_level,
        behavioral_score=    beh_score,
        water_quality_score= wq_score,
        message=             level_messages.get(stress_level.value, "Score computed."),
    )

# ── Stress scores ─────────────────────────────────────────────────────────────

@router.get("/{tank_id}/stress/current", response_model=StressScoreResponse)
async def get_current_stress(tank_id: str, db: AsyncSession = Depends(get_db)):
    """Get the most recent computed FSI score for a tank."""
    tank = await _get_tank_or_404(tank_id, db)
    result = await db.execute(
        select(StressScore)
        .where(StressScore.tank_id == tank.id)
        .order_by(desc(StressScore.computed_at))
        .limit(1)
    )
    score = result.scalar_one_or_none()
    if not score:
        raise HTTPException(status_code=404, detail="No stress scores computed yet.")
    return score


@router.get("/{tank_id}/stress/history", response_model=List[StressScoreResponse])
async def get_stress_history(
    tank_id: str,
    hours: int = Query(default=24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    """Get FSI score history for plotting the stress trend chart."""
    tank = await _get_tank_or_404(tank_id, db)
    since = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(StressScore)
        .where(StressScore.tank_id == tank.id, StressScore.computed_at >= since)
        .order_by(StressScore.computed_at)
    )
    return result.scalars().all()


# ── Helper ────────────────────────────────────────────────────────────────────

async def _get_tank_or_404(tank_id: str, db: AsyncSession) -> Tank:
    """Shared helper — look up tank by string ID or raise 404."""
    result = await db.execute(select(Tank).where(Tank.tank_id == tank_id))
    tank = result.scalar_one_or_none()
    if not tank:
        raise HTTPException(status_code=404, detail=f"Tank '{tank_id}' not found.")
    return tank
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

@router.post("/{tank_id}/behavior", response_model=BehaviorReadingResponse, status_code=201)
async def ingest_behavior_reading(
    tank_id: str,
    data: BehaviorReadingCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive behavioral features from Likhita's CV module.
    Called after each 30-second video analysis window.
    """
    tank = await _get_tank_or_404(tank_id, db)

    behavior = BehaviorReading(
        tank_id=tank.id,
        fish_count=data.fish_count,
        avg_speed=data.avg_speed,
        avg_acceleration=data.avg_acceleration,
        turning_frequency=data.turning_frequency,
        motion_variability=data.motion_variability,
        surface_visits=data.surface_visits,
        bottom_dwelling=data.bottom_dwelling,
        inactivity_pct=data.inactivity_pct,
        schooling_density=data.schooling_density,
    )
    db.add(behavior)
    await db.flush()

    # Update FSI with behavioral component if we have recent sensor data
    sensor_result = await db.execute(
        select(SensorReading)
        .where(SensorReading.tank_id == tank.id)
        .order_by(desc(SensorReading.timestamp))
        .limit(1)
    )
    latest_sensor = sensor_result.scalar_one_or_none()

    fsi_score, stress_level, wq_score = compute_fsi(
        temperature=latest_sensor.temperature if latest_sensor else None,
        ph=latest_sensor.ph if latest_sensor else None,
        dissolved_o2=latest_sensor.dissolved_o2 if latest_sensor else None,
        ammonia=latest_sensor.ammonia if latest_sensor else None,
        avg_speed=data.avg_speed,
        turning_frequency=data.turning_frequency,
        surface_visits=data.surface_visits,
        inactivity_pct=data.inactivity_pct,
    )

    from app.models.models import StressScore
    score = StressScore(
        tank_id=tank.id,
        fsi_score=fsi_score,
        stress_level=stress_level,
        water_quality_score=wq_score,
        behavior_reading_id=behavior.id,
    )
    db.add(score)
    await db.commit()
    await db.refresh(behavior)
    return behavior


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
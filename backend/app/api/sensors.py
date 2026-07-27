from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List
from datetime import datetime, timedelta
import logging
logger = logging.getLogger(__name__)

from app.core.database import get_db
from app.models.models import Tank, SensorReading, BehaviorReading, StressScore
from app.schemas.schemas import (
    SensorReadingCreate, SensorReadingResponse, SensorHistoryResponse,
    BehaviorReadingCreate, BehaviorReadingResponse,
    StressScoreResponse,
    BehaviorIngestResponse,
    FishBatchCreate, FishBatchResponse, FishStressResult,
)
from app.services.fsi_engine import compute_fsi, compute_fish_fsi

router = APIRouter()


@router.get("/{tank_id}/latest", response_model=SensorReadingResponse)
async def get_latest_sensor(tank_id: str, db: AsyncSession = Depends(get_db)):
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
    hours: int = Query(default=24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    tank = await _get_tank_or_404(tank_id, db)
    since = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(SensorReading)
        .where(SensorReading.tank_id == tank.id, SensorReading.timestamp >= since)
        .order_by(SensorReading.timestamp)
    )
    readings = result.scalars().all()
    return SensorHistoryResponse(tank_id=tank_id, readings=readings, count=len(readings))


@router.post("/{tank_id}/readings", response_model=SensorReadingResponse, status_code=201)
async def ingest_sensor_reading(
    tank_id: str,
    data: SensorReadingCreate,
    db: AsyncSession = Depends(get_db),
):
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
    await db.flush()

    fsi_score, stress_level, wq_score = compute_fsi(
        temperature=data.temperature,
        ph=data.ph,
        dissolved_o2=data.dissolved_o2,
        ammonia=data.ammonia,
    )
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
    # Fire Telegram alert if WARNING or CRITICAL
    from app.models.models import StressLevel as SL
    if stress_level in (SL.WARNING, SL.CRITICAL):
        import asyncio
        from app.services.alert_service import send_telegram_alert
        from app.services.fsi_engine import get_alert_types
        alert_types = get_alert_types(
            temperature=data.temperature,
            ph=data.ph,
            dissolved_o2=data.dissolved_o2,
            ammonia=data.ammonia,
        )
        asyncio.create_task(
            send_telegram_alert(tank_id, fsi_score, stress_level, alert_types)
        )

    await db.commit()
    await db.refresh(reading)
    return reading


@router.post(
    "/{tank_id}/behavior",
    response_model=BehaviorIngestResponse,
    status_code=201,
    summary="Receive behavioral data from CV module",
)
async def ingest_behavior_reading(
    tank_id: str,
    data: BehaviorReadingCreate,
    db: AsyncSession = Depends(get_db),
):
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

    from app.services.fsi_engine import _normalize_behavior
    beh_score = None
    if any(v is not None for v in [data.avg_speed, data.turning_frequency,
                                    data.surface_visits, data.inactivity_pct]):
        beh_score = round(
            _normalize_behavior(data.avg_speed, data.turning_frequency,
                                data.surface_visits, data.inactivity_pct), 4
        )

    score = StressScore(
        tank_id=tank.id,
        fsi_score=fsi_score,
        stress_level=stress_level,
        water_quality_score=wq_score,
        behavioral_score=beh_score,
        behavior_reading_id=behavior.id,
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
        behavior_reading_id=behavior.id,
        tank_id=tank_id,
        fish_count=data.fish_count,
        timestamp=behavior.timestamp,
        fsi_score=fsi_score,
        stress_level=stress_level,
        behavioral_score=beh_score,
        water_quality_score=wq_score,
        message=level_messages.get(stress_level.value, "Score computed."),
    )


@router.get("/{tank_id}/stress/current", response_model=StressScoreResponse)
async def get_current_stress(tank_id: str, db: AsyncSession = Depends(get_db)):
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
    tank = await _get_tank_or_404(tank_id, db)
    since = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(StressScore)
        .where(StressScore.tank_id == tank.id, StressScore.computed_at >= since)
        .order_by(StressScore.computed_at)
    )
    return result.scalars().all()

# ── Per-fish batch endpoint (professor's requirement) ────────────────────────

@router.post(
    "/{tank_id}/behavior/batch",
    response_model=FishBatchResponse,
    status_code=201,
    summary="Receive per-fish behavioral data from CV module",
    description="""
    Accepts an array of per-fish behavioral records from Likhita's CV module.
    
    For each fish the backend:
    1. Computes an individual stress score using behavioral metrics
    2. Stores the result in fish_stress_records table
    3. Associates the latest environmental sensor readings as context
    
    Returns individual stress scores + tank-level summary.
    
    Send this every 30 seconds after each analysis window.
    """,
)
async def ingest_fish_batch(
    tank_id: str,
    data: FishBatchCreate,
    db: AsyncSession = Depends(get_db),
):
    from app.models.models import FishStressRecord
    from datetime import datetime, timezone

    tank = await _get_tank_or_404(tank_id, db)

    # Fetch latest environmental context from Yashwanth's sensors
    sensor_result = await db.execute(
        select(SensorReading)
        .where(SensorReading.tank_id == tank.id)
        .order_by(desc(SensorReading.timestamp))
        .limit(1)
    )
    latest_sensor = sensor_result.scalar_one_or_none()

    # Parse analysis timestamp if provided
    analysis_ts = None
    if data.timestamp:
        try:
            analysis_ts = datetime.fromisoformat(data.timestamp.replace("Z", "+00:00"))
        except Exception:
            analysis_ts = datetime.now(timezone.utc)

    # Process each fish individually
    results = []
    critical_fish = []

    for fish_record in data.fish:
        stress_score, stress_level = compute_fish_fsi(
            avg_speed=          fish_record.avg_speed,
            avg_acceleration=   fish_record.avg_acceleration,
            turning_frequency=  fish_record.turning_frequency,
            motion_variability= fish_record.motion_variability,
            surface_visits=     fish_record.surface_visits,
            bottom_dwelling=    fish_record.bottom_dwelling,
            inactivity_pct=     fish_record.inactivity_pct,
        )

        # Save individual record to DB
        record = FishStressRecord(
            tank_id=            tank.id,
            fish_id=            fish_record.fish_id,
            avg_speed=          fish_record.avg_speed,
            avg_acceleration=   fish_record.avg_acceleration,
            turning_frequency=  fish_record.turning_frequency,
            motion_variability= fish_record.motion_variability,
            surface_visits=     fish_record.surface_visits,
            bottom_dwelling=    fish_record.bottom_dwelling,
            inactivity_pct=     fish_record.inactivity_pct,
            stress_score=       stress_score,
            stress_level=       stress_level,
            # Environmental context snapshot
            temperature_ctx=    latest_sensor.temperature  if latest_sensor else None,
            ph_ctx=             latest_sensor.ph           if latest_sensor else None,
            do_ctx=             latest_sensor.dissolved_o2 if latest_sensor else None,
            analysis_timestamp= analysis_ts,
        )
        db.add(record)

        results.append(FishStressResult(
            fish_id=       fish_record.fish_id,
            stress_score=  stress_score,
            stress_level=  stress_level,
            avg_speed=     fish_record.avg_speed,
            surface_visits=fish_record.surface_visits,
        ))

        from app.models.models import StressLevel as SL
        if stress_level == SL.CRITICAL:
            critical_fish.append(fish_record.fish_id)

    await db.commit()

    # Build tank-level summary
    scores = [r.stress_score for r in results]
    avg_stress = round(sum(scores) / len(scores), 4) if scores else 0.0
    most_stressed = max(results, key=lambda r: r.stress_score) if results else None

    # Fire Telegram alert if any fish is critical
    if critical_fish:
        from app.models.models import StressLevel as SL
        from app.services.alert_service import send_telegram_alert
        import asyncio
        asyncio.create_task(
            send_telegram_alert(
                tank_id=     tank_id,
                fsi=         max(scores),
                level=       SL.CRITICAL,
                alert_types= [f"FISH_{fid}_CRITICAL" for fid in critical_fish],
            )
        )

    logger.info(
        f"Batch processed: tank={tank_id} fish={len(results)} "
        f"avg_stress={avg_stress:.3f} critical={len(critical_fish)}"
    )

    return FishBatchResponse(
        tank_id=            tank_id,
        fish_count=         len(results),
        analysis_timestamp= data.timestamp,
        results=            results,
        tank_summary={
            "avg_stress":            avg_stress,
            "critical_fish":         len(critical_fish),
            "critical_fish_ids":     critical_fish,
            "most_stressed_fish_id": most_stressed.fish_id if most_stressed else None,
            "most_stressed_score":   most_stressed.stress_score if most_stressed else None,
        },
    )

@router.get("/{tank_id}/fish-stress/latest")
async def get_latest_fish_stress(
    tank_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get the most recent per-fish stress results.
    Called by the Streamlit dashboard to display the per-fish stress table.
    Returns all fish records from the latest analysis window.
    """
    from app.models.models import FishStressRecord

    tank = await _get_tank_or_404(tank_id, db)

    # Get the most recent analysis timestamp
    latest_ts_result = await db.execute(
        select(FishStressRecord.analysis_timestamp)
        .where(FishStressRecord.tank_id == tank.id)
        .order_by(desc(FishStressRecord.recorded_at))
        .limit(1)
    )
    latest_ts = latest_ts_result.scalar_one_or_none()

    if not latest_ts:
        # No fish stress records exist yet
        return {
            "tank_id":        tank_id,
            "fish":           [],
            "fish_count":     0,
            "critical_count": 0,
            "avg_stress":     0.0,
            "analysis_time":  None,
            "message":        "No fish stress data yet. Run Likhita's main.py first.",
        }

    # Get all fish records from that same analysis window
    records_result = await db.execute(
        select(FishStressRecord)
        .where(
            FishStressRecord.tank_id == tank.id,
            FishStressRecord.analysis_timestamp == latest_ts,
        )
        .order_by(FishStressRecord.stress_score.desc())
    )
    records = records_result.scalars().all()

    fish_list = [
        {
            "fish_id":       r.fish_id,
            "stress_score":  r.stress_score,
            "stress_level":  r.stress_level.value,
            "avg_speed":     r.avg_speed,
            "surface_visits":r.surface_visits,
            "inactivity_pct":r.inactivity_pct,
            "temperature_ctx": r.temperature_ctx,
            "ph_ctx":          r.ph_ctx,
            "do_ctx":          r.do_ctx,
        }
        for r in records
    ]

    critical = sum(1 for f in fish_list if f["stress_level"] == "critical")
    avg      = round(sum(f["stress_score"] for f in fish_list) / len(fish_list), 4) if fish_list else 0.0

    return {
        "tank_id":        tank_id,
        "analysis_time":  latest_ts.isoformat(),
        "fish":           fish_list,
        "fish_count":     len(fish_list),
        "critical_count": critical,
        "avg_stress":     avg,
    }


async def _get_tank_or_404(tank_id: str, db: AsyncSession) -> Tank:
    result = await db.execute(select(Tank).where(Tank.tank_id == tank_id))
    tank = result.scalar_one_or_none()
    if not tank:
        raise HTTPException(status_code=404, detail=f"Tank '{tank_id}' not found.")
    return tank
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models.models import Tank, SensorReading, StressScore, Alert, AlertStatus
from app.schemas.schemas import TankCreate, TankUpdate, TankResponse, DashboardSummary

router = APIRouter()


@router.get("/", response_model=List[TankResponse])
async def list_all_tanks(db: AsyncSession = Depends(get_db)):
    """Return all active tanks. Dashboard uses this to populate the tank selector."""
    result = await db.execute(
        select(Tank).where(Tank.is_active == True).order_by(Tank.created_at)
    )
    return result.scalars().all()


@router.post("/", response_model=TankResponse, status_code=status.HTTP_201_CREATED)
async def create_tank(tank: TankCreate, db: AsyncSession = Depends(get_db)):
    """Register a new fish tank. Usually called once during setup."""
    existing = await db.execute(select(Tank).where(Tank.tank_id == tank.tank_id))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tank with ID '{tank.tank_id}' already exists."
        )
    new_tank = Tank(**tank.model_dump())
    db.add(new_tank)
    await db.commit()
    await db.refresh(new_tank)
    return new_tank


@router.get("/{tank_id}", response_model=TankResponse)
async def get_tank(tank_id: str, db: AsyncSession = Depends(get_db)):
    """Get details of one tank by its string ID (e.g. 'tank_01')."""
    result = await db.execute(select(Tank).where(Tank.tank_id == tank_id))
    tank = result.scalar_one_or_none()
    if not tank:
        raise HTTPException(status_code=404, detail=f"Tank '{tank_id}' not found.")
    return tank


@router.patch("/{tank_id}", response_model=TankResponse)
async def update_tank(tank_id: str, updates: TankUpdate, db: AsyncSession = Depends(get_db)):
    """Update tank metadata (name, species, fish count, etc.)."""
    result = await db.execute(select(Tank).where(Tank.tank_id == tank_id))
    tank = result.scalar_one_or_none()
    if not tank:
        raise HTTPException(status_code=404, detail=f"Tank '{tank_id}' not found.")

    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tank, field, value)

    await db.commit()
    await db.refresh(tank)
    return tank


@router.delete("/{tank_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_tank(tank_id: str, db: AsyncSession = Depends(get_db)):
    """Soft-delete a tank (marks is_active=False, keeps all historical data)."""
    result = await db.execute(select(Tank).where(Tank.tank_id == tank_id))
    tank = result.scalar_one_or_none()
    if not tank:
        raise HTTPException(status_code=404, detail=f"Tank '{tank_id}' not found.")
    tank.is_active = False
    await db.commit()


@router.get("/{tank_id}/dashboard", response_model=DashboardSummary)
async def get_tank_dashboard(tank_id: str, db: AsyncSession = Depends(get_db)):
    """
    Single endpoint that returns EVERYTHING the Streamlit dashboard needs:
    - Tank info
    - Latest sensor reading
    - Current stress score
    - Active alerts from the last 24 hours

    Streamlit calls this every 10 seconds to refresh the dashboard.
    """
    result = await db.execute(select(Tank).where(Tank.tank_id == tank_id))
    tank = result.scalar_one_or_none()
    if not tank:
        raise HTTPException(status_code=404, detail=f"Tank '{tank_id}' not found.")

    # Latest sensor reading
    sensor_result = await db.execute(
        select(SensorReading)
        .where(SensorReading.tank_id == tank.id)
        .order_by(desc(SensorReading.timestamp))
        .limit(1)
    )
    latest_sensor = sensor_result.scalar_one_or_none()

    # Latest stress score
    stress_result = await db.execute(
        select(StressScore)
        .where(StressScore.tank_id == tank.id)
        .order_by(desc(StressScore.computed_at))
        .limit(1)
    )
    latest_stress = stress_result.scalar_one_or_none()

    # Active alerts (last 24 hours, unresolved only)
    since_24h = datetime.utcnow() - timedelta(hours=24)
    alerts_result = await db.execute(
        select(Alert)
        .where(
            Alert.tank_id == tank.id,
            Alert.status == AlertStatus.ACTIVE,
            Alert.created_at >= since_24h,
        )
        .order_by(desc(Alert.created_at))
        .limit(20)
    )
    active_alerts = alerts_result.scalars().all()

    # Readings count today
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    count_result = await db.execute(
        select(SensorReading)
        .where(SensorReading.tank_id == tank.id, SensorReading.timestamp >= today_start)
    )
    readings_today = len(count_result.scalars().all())

    return DashboardSummary(
        tank=tank,
        latest_sensor=latest_sensor,
        latest_stress=latest_stress,
        active_alerts=active_alerts,
        alert_count=len(active_alerts),
        readings_today=readings_today,
    )
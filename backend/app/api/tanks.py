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
    result = await db.execute(
        select(Tank).where(Tank.is_active == True).order_by(Tank.created_at)
    )
    return result.scalars().all()


@router.post("/", response_model=TankResponse, status_code=status.HTTP_201_CREATED)
async def create_tank(tank: TankCreate, db: AsyncSession = Depends(get_db)):
    """
    Register a new fish tank.
    If the tank_id already exists but was deactivated, it gets reactivated.
    """
    result = await db.execute(select(Tank).where(Tank.tank_id == tank.tank_id))
    existing = result.scalar_one_or_none()

    if existing:
        if existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tank with ID '{tank.tank_id}' already exists."
            )
        for field, value in tank.model_dump().items():
            setattr(existing, field, value)
        existing.is_active = True
        await db.commit()
        await db.refresh(existing)
        return existing

    new_tank = Tank(**tank.model_dump())
    db.add(new_tank)
    await db.commit()
    await db.refresh(new_tank)
    return new_tank


@router.get("/{tank_id}", response_model=TankResponse)
async def get_tank(tank_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tank).where(Tank.tank_id == tank_id))
    tank = result.scalar_one_or_none()
    if not tank:
        raise HTTPException(status_code=404, detail=f"Tank '{tank_id}' not found.")
    return tank


@router.patch("/{tank_id}", response_model=TankResponse)
async def update_tank(tank_id: str, updates: TankUpdate, db: AsyncSession = Depends(get_db)):
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
    result = await db.execute(select(Tank).where(Tank.tank_id == tank_id))
    tank = result.scalar_one_or_none()
    if not tank:
        raise HTTPException(status_code=404, detail=f"Tank '{tank_id}' not found.")
    tank.is_active = False
    await db.commit()


@router.get("/{tank_id}/dashboard", response_model=DashboardSummary)
async def get_tank_dashboard(tank_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tank).where(Tank.tank_id == tank_id))
    tank = result.scalar_one_or_none()
    if not tank:
        raise HTTPException(status_code=404, detail=f"Tank '{tank_id}' not found.")

    sensor_result = await db.execute(
        select(SensorReading)
        .where(SensorReading.tank_id == tank.id)
        .order_by(desc(SensorReading.timestamp))
        .limit(1)
    )
    latest_sensor = sensor_result.scalar_one_or_none()

    stress_result = await db.execute(
        select(StressScore)
        .where(StressScore.tank_id == tank.id)
        .order_by(desc(StressScore.computed_at))
        .limit(1)
    )
    latest_stress = stress_result.scalar_one_or_none()

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
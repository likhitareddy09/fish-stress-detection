from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from typing import List
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models.models import Alert, AlertStatus, Tank, StressLevel
import logging
logger = logging.getLogger(__name__)
from app.schemas.schemas import AlertResponse, AlertResolveRequest

router = APIRouter()


@router.get("/{tank_id}", response_model=List[AlertResponse])
async def get_tank_alerts(
    tank_id: str,
    status: str = Query(default="active", enum=["active", "resolved", "all"]),
    hours: int = Query(default=24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
):
    """
    Get alerts for a specific tank.
    Default: active alerts from last 24 hours.
    Streamlit dashboard calls this to show the alert panel.
    """
    result = await db.execute(select(Tank).where(Tank.tank_id == tank_id))
    tank = result.scalar_one_or_none()
    if not tank:
        raise HTTPException(status_code=404, detail=f"Tank '{tank_id}' not found.")

    since = datetime.utcnow() - timedelta(hours=hours)
    query = select(Alert).where(
        Alert.tank_id == tank.id,
        Alert.created_at >= since,
    ).order_by(desc(Alert.created_at))

    if status == "active":
        query = query.where(Alert.status == AlertStatus.ACTIVE)
    elif status == "resolved":
        query = query.where(Alert.status == AlertStatus.RESOLVED)

    alerts_result = await db.execute(query)
    return alerts_result.scalars().all()


@router.patch("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: int,
    body: AlertResolveRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Mark an alert as resolved.
    Sends a Telegram resolution notice automatically.
    """
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert  = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found.")
    if alert.status == AlertStatus.RESOLVED:
        raise HTTPException(status_code=400, detail="Alert is already resolved.")

    alert.status       = AlertStatus.RESOLVED
    alert.resolved_at  = datetime.utcnow()
    alert.resolved_note = body.note

    # Mark notification flags
    alert.telegram_sent = True

    await db.commit()
    await db.refresh(alert)

    # Send resolution notice to Telegram
    tank_result = await db.execute(
        select(Tank).where(Tank.id == alert.tank_id)
    )
    tank = tank_result.scalar_one_or_none()
    tank_id_str = tank.tank_id if tank else "unknown"

    try:
        from app.services.alert_service import send_telegram_resolution
        import asyncio
        asyncio.create_task(
            send_telegram_resolution(tank_id_str, alert_id, body.note)
        )
    except Exception as e:
        logger.warning(f"Could not send resolution notice: {e}")

    return alert


@router.get("/stats/summary")
async def get_alert_stats(
    hours: int = Query(default=24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
):
    """
    Summary statistics across all tanks.
    Used by dashboard header to show overall system health.
    """
    since = datetime.utcnow() - timedelta(hours=hours)

    total_result = await db.execute(
        select(func.count(Alert.id))
        .where(Alert.created_at >= since)
    )
    total = total_result.scalar()

    active_result = await db.execute(
        select(func.count(Alert.id))
        .where(Alert.created_at >= since, Alert.status == AlertStatus.ACTIVE)
    )
    active = active_result.scalar()

    critical_result = await db.execute(
        select(func.count(Alert.id))
        .where(
            Alert.created_at >= since,
            Alert.severity == StressLevel.CRITICAL,
            Alert.status == AlertStatus.ACTIVE,
        )
    )
    critical = critical_result.scalar()

    return {
        "period_hours":    hours,
        "total_alerts":    total,
        "active_alerts":   active,
        "resolved_alerts": total - active,
        "critical_active": critical,
        "system_status":   "critical" if critical > 0 else "warning" if active > 0 else "normal",
    }
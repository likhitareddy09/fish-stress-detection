import logging
from app.models.models import StressLevel

logger = logging.getLogger(__name__)


async def send_telegram_alert(
    tank_id: str,
    fsi: float,
    level: StressLevel,
    alert_types: list[str],
):
    """
    Placeholder — full Telegram implementation on Day 6.
    Logs the alert that would be sent.
    """
    emoji = {"normal": "✅", "warning": "⚠️", "critical": "🚨"}.get(level.value, "❓")
    alert_list = ", ".join(alert_types)
    logger.info(
        f"[ALERT PLACEHOLDER] {emoji} Tank {tank_id} | "
        f"FSI={fsi:.3f} | Level={level.value.upper()} | Alerts: {alert_list}"
    )
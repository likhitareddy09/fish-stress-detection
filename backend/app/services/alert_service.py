"""
Alert Service — Fish Stress Detection System
============================================
Handles all outbound notifications:
  - Telegram messages (primary alert channel)
  - Email via Gmail SMTP (secondary, optional)

Called automatically by mqtt_consumer.py when FSI crosses thresholds.
Can also be called directly for testing.
"""

import httpx
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from app.core.config import settings
from app.models.models import StressLevel

logger = logging.getLogger(__name__)


# ── Telegram alert ────────────────────────────────────────────────────────────

async def send_telegram_alert(
    tank_id: str,
    fsi: float,
    level: StressLevel,
    alert_types: list[str],
):
    """
    Send a Telegram message when stress level is WARNING or CRITICAL.

    Called from:
      - mqtt_consumer.py after processing each MQTT payload
      - sensors.py after ingesting a critical sensor reading via REST

    Args:
        tank_id:     e.g. "tank_01"
        fsi:         Fish Stress Index score, 0.0 – 1.0
        level:       StressLevel.WARNING or StressLevel.CRITICAL
        alert_types: list of strings e.g. ["HIGH_TEMP", "LOW_PH"]
    """
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        logger.warning(
            "Telegram not configured — skipping alert. "
            "Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env"
        )
        return

    emoji = {
        "normal":   "✅",
        "warning":  "⚠️",
        "critical": "🚨",
    }.get(level.value, "❓")

    fsi_bar   = _build_fsi_bar(fsi)
    now       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    alert_lines = (
        "\n".join(f"  • {_alert_label(a)}" for a in alert_types)
        if alert_types else "  • General stress detected"
    )

    message = (
        f"{emoji} *Fish Stress Alert*\n\n"
        f"🐟 Tank: `{tank_id}`\n"
        f"📊 Stress Level: *{level.value.upper()}*\n"
        f"📈 FSI Score: `{fsi:.3f}` / 1.000\n"
        f"`{fsi_bar}`\n\n"
        f"⚠️ *Alerts detected:*\n{alert_lines}\n\n"
        f"🔧 *Recommended action:*\n{_recommend_action(alert_types)}\n\n"
        f"🕐 Time: `{now}`\n"
        f"🖥 Dashboard: http://localhost:8501\n"
        f"📡 API: http://localhost:8000/docs"
    )

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json={
                "chat_id":    settings.TELEGRAM_CHAT_ID,
                "text":       message,
                "parse_mode": "Markdown",
            })

        if response.status_code == 200:
            logger.info(
                f"Telegram alert sent: tank={tank_id} "
                f"FSI={fsi:.3f} level={level.value}"
            )
        else:
            logger.error(
                f"Telegram API error: HTTP {response.status_code} "
                f"— {response.text[:300]}"
            )

    except httpx.TimeoutException:
        logger.error("Telegram alert timed out after 10 seconds")
    except httpx.ConnectError:
        logger.error("Telegram alert failed — no internet connection")
    except Exception as e:
        logger.error(f"Telegram alert unexpected error: {e}")


async def send_telegram_resolution(tank_id: str, alert_id: int, note: str = None):
    """
    Send a Telegram message when an alert is manually resolved.
    Called from alerts.py when someone clicks resolve on the dashboard.
    """
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = (
        f"✅ *Alert Resolved*\n\n"
        f"🐟 Tank: `{tank_id}`\n"
        f"🆔 Alert ID: `{alert_id}`\n"
        f"🕐 Resolved at: `{now}`\n"
    )
    if note:
        message += f"📝 Note: {note}"

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json={
                "chat_id":    settings.TELEGRAM_CHAT_ID,
                "text":       message,
                "parse_mode": "Markdown",
            })
        logger.info(f"Telegram resolution notice sent for alert {alert_id}")
    except Exception as e:
        logger.error(f"Telegram resolution notice failed: {e}")


# ── Email alert ───────────────────────────────────────────────────────────────

def send_email_alert(
    tank_id: str,
    fsi: float,
    level: StressLevel,
    alert_types: list[str],
):
    """
    Send an email alert via Gmail SMTP.

    Setup required (one time):
      1. Go to myaccount.google.com/apppasswords
      2. Generate an App Password for "Mail"
      3. Add to .env:
           ALERT_EMAIL=youremail@gmail.com
           EMAIL_PASSWORD=xxxx xxxx xxxx xxxx  (16-char app password)

    Note: Use Gmail App Password, NOT your regular Gmail password.
    Two-factor authentication must be enabled on your Google account.
    """
    if not settings.ALERT_EMAIL or not settings.EMAIL_PASSWORD:
        logger.warning(
            "Email not configured — skipping. "
            "Add ALERT_EMAIL and EMAIL_PASSWORD to .env"
        )
        return

    emoji   = {"normal": "✅", "warning": "⚠️", "critical": "🚨"}.get(level.value, "")
    subject = f"{emoji} [{level.value.upper()}] Fish Stress Alert — Tank {tank_id}"
    now     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    alert_lines = "\n".join(f"  - {_alert_label(a)}" for a in alert_types)
    action      = _recommend_action(alert_types)

    body = f"""
FISH STRESS DETECTION SYSTEM — ALERT NOTIFICATION
==================================================

Tank ID:      {tank_id}
Stress Level: {level.value.upper()}
FSI Score:    {fsi:.3f} / 1.000
Time:         {now}

FSI Bar: [{_build_fsi_bar(fsi)}]

TRIGGERED ALERTS:
{alert_lines if alert_lines else "  - General stress detected"}

RECOMMENDED ACTION:
{action}

LINKS:
  Dashboard:  http://localhost:8501
  API Docs:   http://localhost:8000/docs
  Alerts API: http://localhost:8000/api/v1/alerts/{tank_id}

--
Fish Stress Detection System
Automated alert — do not reply to this email.
    """.strip()

    msg            = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"]    = settings.ALERT_EMAIL
    msg["To"]      = settings.ALERT_EMAIL
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(settings.ALERT_EMAIL, settings.EMAIL_PASSWORD)
            server.sendmail(
                settings.ALERT_EMAIL,
                [settings.ALERT_EMAIL],
                msg.as_string()
            )
        logger.info(f"Email alert sent to {settings.ALERT_EMAIL} for tank {tank_id}")
    except smtplib.SMTPAuthenticationError:
        logger.error(
            "Email authentication failed. "
            "Use a Gmail App Password, not your regular password. "
            "Generate at: myaccount.google.com/apppasswords"
        )
    except smtplib.SMTPException as e:
        logger.error(f"Email SMTP error: {e}")
    except Exception as e:
        logger.error(f"Email unexpected error: {e}")


# ── Private helpers ───────────────────────────────────────────────────────────

def _build_fsi_bar(fsi: float) -> str:
    """Build an ASCII progress bar for the FSI score."""
    filled = int(round(fsi * 10))
    empty  = 10 - filled
    if fsi < 0.30:
        indicator = "NORMAL"
    elif fsi < 0.60:
        indicator = "WARNING"
    else:
        indicator = "CRITICAL"
    return f"{'█' * filled}{'░' * empty} {fsi:.1%} {indicator}"


def _alert_label(alert_type: str) -> str:
    """Convert alert type code to a human-readable label."""
    labels = {
        "HIGH_TEMP":     "Temperature too HIGH",
        "LOW_TEMP":      "Temperature too LOW",
        "HIGH_PH":       "pH level too HIGH",
        "LOW_PH":        "pH level too LOW",
        "LOW_DO":        "Dissolved oxygen CRITICALLY LOW",
        "HIGH_AMMONIA":  "Ammonia spike DETECTED",
        "STRESS_CRITICAL": "Fish stress CRITICAL",
        "STRESS_WARNING":  "Fish stress WARNING",
    }
    return labels.get(alert_type, alert_type.replace("_", " ").title())


def _recommend_action(alert_types: list[str]) -> str:
    """Return a recommended action string based on which alerts fired."""
    actions = []
    if "HIGH_TEMP" in alert_types:
        actions.append("  • Reduce water temperature — check heater/cooler")
    if "LOW_TEMP" in alert_types:
        actions.append("  • Increase water temperature — check heater")
    if "HIGH_PH" in alert_types:
        actions.append("  • Add pH-Down solution — retest in 30 minutes")
    if "LOW_PH" in alert_types:
        actions.append("  • Add pH-Up solution — retest in 30 minutes")
    if "LOW_DO" in alert_types:
        actions.append("  • Check aerator/air pump — increase surface agitation")
    if "HIGH_AMMONIA" in alert_types:
        actions.append("  • Perform 25% water change immediately")
    if not actions:
        actions.append("  • Monitor fish behavior closely")
        actions.append("  • Check all equipment is functioning normally")
    return "\n".join(actions)
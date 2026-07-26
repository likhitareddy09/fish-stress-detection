import paho.mqtt.client as mqtt
import asyncio
import json
import logging
import threading
from datetime import datetime
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.models import Tank, SensorReading, StressScore, Alert, AlertStatus
from app.services.fsi_engine import compute_fsi, get_alert_types

logger = logging.getLogger(__name__)

# ── Topic structure (must match Yashwanth's ESP32 code exactly) ──────────────
# fish_tank/{tank_id}/sensors  → full JSON payload (temp, pH, DO, alerts)
# fish_tank/{tank_id}/status   → "online" or "offline"
SENSOR_TOPIC_SUFFIX = "/sensors"
STATUS_TOPIC_SUFFIX = "/status"


# ── MQTT callbacks ────────────────────────────────────────────────────────────

def on_connect(client: mqtt.Client, userdata, flags, rc: int):
    """Called when MQTT connection is established."""
    if rc == 0:
        logger.info("MQTT consumer connected to broker.")
        # Subscribe to ALL fish_tank topics
        client.subscribe("fish_tank/#", qos=1)
        logger.info("Subscribed to: fish_tank/#")
    else:
        error_codes = {
            1: "Incorrect protocol version",
            2: "Invalid client ID",
            3: "Broker unavailable",
            4: "Bad username/password",
            5: "Not authorized",
        }
        logger.error(f"MQTT connection failed: {error_codes.get(rc, f'Unknown error {rc}')}")


def on_disconnect(client: mqtt.Client, userdata, rc: int):
    """Called when MQTT disconnects — paho auto-reconnects if loop_forever is used."""
    if rc != 0:
        logger.warning(f"Unexpected MQTT disconnect (rc={rc}). Will attempt reconnect...")


def on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
    """
    Called for every MQTT message received.
    Runs in the paho thread — we dispatch DB work to the asyncio event loop.
    """
    topic = msg.topic
    payload_str = msg.payload.decode("utf-8", errors="replace")

    logger.debug(f"MQTT message: {topic} → {payload_str[:120]}")

    # Only process the main sensor topic
    if topic.endswith(SENSOR_TOPIC_SUFFIX):
        # Run the async processing in the background asyncio loop
        loop = userdata.get("loop")
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(
                _process_sensor_payload(topic, payload_str),
                loop
            )
        else:
            logger.error("No asyncio event loop available for DB operations.")

    elif topic.endswith(STATUS_TOPIC_SUFFIX):
        tank_id = _extract_tank_id(topic)
        logger.info(f"ESP32 status update: {tank_id} → {payload_str}")


# ── Core processing logic ─────────────────────────────────────────────────────

async def _process_sensor_payload(topic: str, payload_str: str):
    """
    Parse MQTT JSON from ESP32, save to DB, compute FSI, create alerts.
    This is the heart of Day 3.
    """
    # Step 1: Parse JSON
    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError as e:
        logger.error(f"Bad JSON on topic {topic}: {e} | Raw: {payload_str[:200]}")
        return

    # Step 2: Extract fields (matches Yashwanth's ESP32 payload format)
    tank_id_str  = payload.get("tank_id", _extract_tank_id(topic))
    temperature  = payload.get("temperature")
    ph = payload.get("ph") or payload.get("pH")
    dissolved_o2 = payload.get("do_mg_l")       # Yashwanth uses "do_mg_l"
    ammonia      = payload.get("ammonia")
    esp32_alerts = payload.get("alerts", [])    # Alerts already computed on ESP32

    logger.info(
        f"Processing [{tank_id_str}]: "
        f"temp={temperature}°C  pH={ph}  DO={dissolved_o2}mg/L"
    )

    async with AsyncSessionLocal() as db:
        try:
            # Step 3: Get or auto-create the tank
            tank = await _get_or_create_tank(db, tank_id_str)

            # Step 4: Save sensor reading
            reading = SensorReading(
                tank_id=tank.id,
                temperature=temperature,
                ph=ph,
                dissolved_o2=dissolved_o2,
                ammonia=ammonia,
                raw_payload=payload_str,
            )
            db.add(reading)
            await db.flush()  # Need reading.id for FK in StressScore

            # Step 5: Compute FSI
            fsi_score, stress_level, wq_score = compute_fsi(
                temperature=temperature,
                ph=ph,
                dissolved_o2=dissolved_o2,
                ammonia=ammonia,
            )

            # Step 6: Save stress score
            score = StressScore(
                tank_id=tank.id,
                fsi_score=fsi_score,
                stress_level=stress_level,
                water_quality_score=wq_score,
                sensor_reading_id=reading.id,
            )
            db.add(score)

            # Step 7: Create alert records for any threshold breaches
            alert_types = get_alert_types(temperature, ph, dissolved_o2, ammonia)
            # Merge with alerts already detected by ESP32
            all_alerts = list(set(alert_types + esp32_alerts))

            for alert_type in all_alerts:
                alert = Alert(
                    tank_id=tank.id,
                    alert_type=alert_type,
                    severity=stress_level,
                    message=_build_alert_message(tank_id_str, alert_type, temperature, ph, dissolved_o2, fsi_score),
                    triggered_value=_get_triggered_value(alert_type, temperature, ph, dissolved_o2, ammonia),
                    threshold_value=_get_threshold_value(alert_type),
                    status=AlertStatus.ACTIVE,
                )
                db.add(alert)

            await db.commit()
            logger.info(
                f"Saved [{tank_id_str}]: FSI={fsi_score:.3f} ({stress_level.value}) "
                f"| {len(all_alerts)} alert(s)"
            )

            # Step 8: Send Telegram notification for WARNING or CRITICAL
            from app.models.models import StressLevel
            if stress_level in (StressLevel.WARNING, StressLevel.CRITICAL) and all_alerts:
                from app.services.alert_service import send_telegram_alert
                asyncio.create_task(
                    send_telegram_alert(tank_id_str, fsi_score, stress_level, all_alerts)
                )

        except Exception as e:
            logger.exception(f"Error processing payload for {tank_id_str}: {e}")
            await db.rollback()


async def _get_or_create_tank(db, tank_id_str: str) -> Tank:
    """
    Look up tank by string ID. If it doesn't exist yet, auto-create it.
    This way the system works even before the tank is manually registered.
    """
    result = await db.execute(select(Tank).where(Tank.tank_id == tank_id_str))
    tank = result.scalar_one_or_none()
    if not tank:
        tank = Tank(
            tank_id=tank_id_str,
            name=f"Auto-created: {tank_id_str}",
        )
        db.add(tank)
        await db.flush()
        logger.info(f"Auto-created tank: {tank_id_str}")
    return tank


def _extract_tank_id(topic: str) -> str:
    """Extract tank_id from topic like 'fish_tank/tank_01/sensors' → 'tank_01'."""
    parts = topic.split("/")
    return parts[1] if len(parts) >= 2 else "unknown"


def _build_alert_message(tank_id, alert_type, temp, ph, do2, fsi) -> str:
    messages = {
        "HIGH_TEMP": f"Temperature too high: {temp}°C (limit: 30°C)",
        "LOW_TEMP":  f"Temperature too low: {temp}°C (limit: 18°C)",
        "HIGH_PH":   f"pH too high: {ph} (limit: 8.5)",
        "LOW_PH":    f"pH too low: {ph} (limit: 6.0)",
        "LOW_DO":    f"Dissolved oxygen critical: {do2} mg/L (limit: 4.0 mg/L)",
        "HIGH_AMMONIA": f"Ammonia spike detected",
    }
    base = messages.get(alert_type, f"Anomaly detected: {alert_type}")
    return f"Tank {tank_id} — {base}. FSI={fsi:.2f}"


def _get_triggered_value(alert_type, temp, ph, do2, ammonia):
    mapping = {
        "HIGH_TEMP": temp, "LOW_TEMP": temp,
        "HIGH_PH": ph,     "LOW_PH": ph,
        "LOW_DO": do2,
        "HIGH_AMMONIA": ammonia,
    }
    return mapping.get(alert_type)


def _get_threshold_value(alert_type):
    thresholds = {
        "HIGH_TEMP": 30.0, "LOW_TEMP": 18.0,
        "HIGH_PH": 8.5,    "LOW_PH": 6.0,
        "LOW_DO": 4.0,     "HIGH_AMMONIA": 0.02,
    }
    return thresholds.get(alert_type)


# ── Public function called by main.py on startup ──────────────────────────────

def start_mqtt_consumer(loop: asyncio.AbstractEventLoop):
    """
    Start the MQTT consumer in a background thread.
    Passes the asyncio event loop so async DB operations work from the paho thread.
    """
    def _run():
        client = mqtt.Client(
            client_id="fish_stress_backend",
            userdata={"loop": loop},
        )
        client.on_connect    = on_connect
        client.on_disconnect = on_disconnect
        client.on_message    = on_message

        logger.info(f"Connecting to MQTT broker: {settings.MQTT_BROKER_IP}:{settings.MQTT_PORT}")

        try:
            client.connect(settings.MQTT_BROKER_IP, settings.MQTT_PORT, keepalive=60)
            client.loop_forever()   # Blocks this thread; auto-reconnects on disconnect
        except Exception as e:
            logger.error(f"MQTT consumer failed to start: {e}")

    thread = threading.Thread(target=_run, name="mqtt-consumer", daemon=True)
    thread.start()
    logger.info("MQTT consumer thread started.")
    return thread
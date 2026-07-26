from sqlalchemy import (
    Column, Integer, String, Float, DateTime,
    Boolean, ForeignKey, Text, Enum as SAEnum, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.core.database import Base


# ── Enums ────────────────────────────────────────────────────────────────────

class StressLevel(str, enum.Enum):
    NORMAL   = "normal"
    WARNING  = "warning"
    CRITICAL = "critical"

class AlertStatus(str, enum.Enum):
    ACTIVE   = "active"
    RESOLVED = "resolved"


# ── Tank ─────────────────────────────────────────────────────────────────────

class Tank(Base):
    """
    Represents a physical fish tank being monitored.
    One tank → many sensor readings, alerts, stress scores.
    """
    __tablename__ = "tanks"

    id           = Column(Integer, primary_key=True, index=True)
    tank_id      = Column(String(50), unique=True, nullable=False, index=True)
    name         = Column(String(100), nullable=False, default="Unnamed Tank")
    location     = Column(String(200))
    fish_species = Column(String(100))
    fish_count   = Column(Integer, default=0)
    volume_liters= Column(Float)
    is_active    = Column(Boolean, default=True, nullable=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    sensor_readings  = relationship("SensorReading",  back_populates="tank", cascade="all, delete-orphan")
    behavior_readings= relationship("BehaviorReading", back_populates="tank", cascade="all, delete-orphan")
    stress_scores    = relationship("StressScore",    back_populates="tank", cascade="all, delete-orphan")
    alerts           = relationship("Alert",          back_populates="tank", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Tank id={self.tank_id} name={self.name}>"


# ── SensorReading ─────────────────────────────────────────────────────────────

class SensorReading(Base):
    """
    Water quality sensor data received from Yashwanth's ESP32 via MQTT.
    Stored every time ESP32 publishes a reading (every ~10 seconds).
    """
    __tablename__ = "sensor_readings"

    id           = Column(Integer, primary_key=True, index=True)
    tank_id      = Column(Integer, ForeignKey("tanks.id", ondelete="CASCADE"), nullable=False)

    # Core water quality parameters
    temperature  = Column(Float)          # Celsius — ideal: 24-28°C
    ph           = Column(Float)          # pH units — ideal: 6.5-8.0
    dissolved_o2 = Column(Float)          # mg/L    — ideal: >5 mg/L
    ammonia      = Column(Float)          # ppm     — ideal: <0.02 ppm
    turbidity    = Column(Float)          # NTU     — optional sensor

    # Metadata
    timestamp    = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    raw_payload  = Column(Text)           # Full JSON from MQTT — stored for debugging

    tank = relationship("Tank", back_populates="sensor_readings")

    __table_args__ = (
        Index("ix_sensor_readings_tank_timestamp", "tank_id", "timestamp"),
    )

    def __repr__(self):
        return f"<SensorReading tank={self.tank_id} temp={self.temperature} ph={self.ph}>"


# ── BehaviorReading ───────────────────────────────────────────────────────────

class BehaviorReading(Base):
    """
    Fish behavioral features extracted by Likhita's CV module.
    Sent to backend via REST API after each video analysis window.
    """
    __tablename__ = "behavior_readings"

    id                = Column(Integer, primary_key=True, index=True)
    tank_id           = Column(Integer, ForeignKey("tanks.id", ondelete="CASCADE"), nullable=False)

    # Detection metrics
    fish_count        = Column(Integer, default=0)    # Number of fish detected

    # Motion features
    avg_speed         = Column(Float)   # pixels/second — stressed fish move erratically
    avg_acceleration  = Column(Float)   # pixels/second² — sudden bursts = stress indicator
    turning_frequency = Column(Float)   # turns/minute — high turning = stress
    motion_variability= Column(Float)   # std dev of speed — erratic = stressed

    # Positional features
    surface_visits    = Column(Integer, default=0)  # count — gulping air = oxygen stress
    bottom_dwelling   = Column(Float)   # % time at bottom — lethargy indicator
    inactivity_pct    = Column(Float)   # % of fish inactive in frame

    # Social features
    schooling_density = Column(Float)   # clustering coefficient — tight schooling = stress

    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tank = relationship("Tank", back_populates="behavior_readings")

    __table_args__ = (
        Index("ix_behavior_readings_tank_timestamp", "tank_id", "timestamp"),
    )

    def __repr__(self):
        return f"<BehaviorReading tank={self.tank_id} fish={self.fish_count} speed={self.avg_speed}>"


# ── StressScore ───────────────────────────────────────────────────────────────

class StressScore(Base):
    """
    Computed Fish Stress Index (FSI) — combines water quality + behavior.
    Calculated every time new sensor or behavior data arrives.
    FSI formula: weighted sum of normalized deviations from ideal ranges.
    0.0 = perfectly healthy, 1.0 = maximum stress.
    """
    __tablename__ = "stress_scores"

    id                  = Column(Integer, primary_key=True, index=True)
    tank_id             = Column(Integer, ForeignKey("tanks.id", ondelete="CASCADE"), nullable=False)

    # Overall score
    fsi_score           = Column(Float, nullable=False)   # 0.0 - 1.0
    stress_level        = Column(SAEnum(StressLevel), default=StressLevel.NORMAL, nullable=False)

    # Component scores (for analytics breakdown)
    water_quality_score = Column(Float)   # Contribution from sensors (weight: 0.60)
    behavioral_score    = Column(Float)   # Contribution from CV (weight: 0.40)

    # Which readings contributed to this score
    sensor_reading_id   = Column(Integer, ForeignKey("sensor_readings.id"), nullable=True)
    behavior_reading_id = Column(Integer, ForeignKey("behavior_readings.id"), nullable=True)

    computed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    tank = relationship("Tank", back_populates="stress_scores")

    __table_args__ = (
        Index("ix_stress_scores_tank_computed", "tank_id", "computed_at"),
    )

    def __repr__(self):
        return f"<StressScore tank={self.tank_id} fsi={self.fsi_score} level={self.stress_level}>"


# ── Alert ─────────────────────────────────────────────────────────────────────

class Alert(Base):
    """
    Triggered when FSI crosses a threshold or a sensor reading is out of range.
    Tracks which notification channels have been used and whether it's resolved.
    """
    __tablename__ = "alerts"

    id           = Column(Integer, primary_key=True, index=True)
    tank_id      = Column(Integer, ForeignKey("tanks.id", ondelete="CASCADE"), nullable=False)

    # Alert details
    alert_type   = Column(String(50), nullable=False)  # e.g. HIGH_TEMP, LOW_PH, STRESS_CRITICAL
    severity     = Column(SAEnum(StressLevel), nullable=False)
    message      = Column(Text, nullable=False)
    triggered_value  = Column(Float)    # The reading that triggered this alert
    threshold_value  = Column(Float)    # The threshold it crossed

    # Notification status
    telegram_sent = Column(Boolean, default=False)
    email_sent    = Column(Boolean, default=False)
    buzzer_sent   = Column(Boolean, default=False)  # Sent command to Yashwanth's buzzer

    # Resolution
    status       = Column(SAEnum(AlertStatus), default=AlertStatus.ACTIVE, nullable=False)
    resolved_at  = Column(DateTime(timezone=True), nullable=True)
    resolved_note= Column(Text, nullable=True)    # Optional note about how it was resolved

    created_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tank = relationship("Tank", back_populates="alerts")

    __table_args__ = (
        Index("ix_alerts_tank_status", "tank_id", "status"),
        Index("ix_alerts_created", "created_at"),
    )

    def __repr__(self):
        return f"<Alert tank={self.tank_id} type={self.alert_type} severity={self.severity}>"


class FishStressRecord(Base):
    """
    Individual per-fish stress record.
    Created by POST /api/v1/sensors/{tank_id}/behavior/batch
    
    One row per fish per 30-second analysis window.
    Stores behavioral metrics + computed stress score + environmental context.
    
    Professor's requirement: individual fish stress detection,
    not a single tank-level score.
    """
    __tablename__ = "fish_stress_records"

    id              = Column(Integer, primary_key=True, index=True)
    tank_id         = Column(Integer, ForeignKey("tanks.id", ondelete="CASCADE"), nullable=False)

    # Fish identification (ByteTrack persistent ID from Likhita's CV module)
    fish_id         = Column(Integer, nullable=False, index=True)

    # Behavioral metrics sent by Likhita
    avg_speed           = Column(Float)     # pixels/second
    avg_acceleration    = Column(Float)     # pixels/second²
    turning_frequency   = Column(Float)     # turns/minute
    motion_variability  = Column(Float)     # std dev of speed
    surface_visits      = Column(Integer, default=0)   # count — O2 stress indicator
    bottom_dwelling     = Column(Float)     # % time at bottom
    inactivity_pct      = Column(Float)     # % of time stationary

    # Computed by backend (NOT sent by Likhita)
    stress_score    = Column(Float, nullable=False)        # 0.0 – 1.0
    stress_level    = Column(SAEnum(StressLevel), nullable=False)

    # Environmental context at time of analysis (from Yashwanth's latest reading)
    temperature_ctx = Column(Float)     # °C at time of this window
    ph_ctx          = Column(Float)     # pH at time of this window
    do_ctx          = Column(Float)     # Dissolved O2 at time of this window

    # Timestamps
    analysis_timestamp = Column(DateTime(timezone=True), nullable=True)
    recorded_at        = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    tank = relationship("Tank")

    __table_args__ = (
        Index("ix_fish_stress_tank_fish", "tank_id", "fish_id"),
        Index("ix_fish_stress_recorded", "recorded_at"),
    )

    def __repr__(self):
        return f"<FishStressRecord tank={self.tank_id} fish={self.fish_id} score={self.stress_score}>"
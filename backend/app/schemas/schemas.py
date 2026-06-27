from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List
from app.models.models import StressLevel, AlertStatus


# ── Tank schemas ──────────────────────────────────────────────────────────────

class TankCreate(BaseModel):
    tank_id:      str          = Field(..., min_length=1, max_length=50,  example="tank_01")
    name:         str          = Field(..., min_length=1, max_length=100, example="Main Aquarium")
    location:     Optional[str]= Field(None, example="Lab Room 2")
    fish_species: Optional[str]= Field(None, example="Rohu (Labeo rohita)")
    fish_count:   Optional[int]= Field(None, ge=0, example=50)
    volume_liters:Optional[float]=Field(None, gt=0, example=500.0)

class TankUpdate(BaseModel):
    name:         Optional[str]  = None
    location:     Optional[str]  = None
    fish_species: Optional[str]  = None
    fish_count:   Optional[int]  = Field(None, ge=0)
    volume_liters:Optional[float]= Field(None, gt=0)
    is_active:    Optional[bool] = None

class TankResponse(BaseModel):
    id:           int
    tank_id:      str
    name:         str
    location:     Optional[str]
    fish_species: Optional[str]
    fish_count:   int
    volume_liters:Optional[float]
    is_active:    bool
    created_at:   datetime

    class Config:
        from_attributes = True


# ── Sensor reading schemas ────────────────────────────────────────────────────

class SensorReadingCreate(BaseModel):
    """
    Shape of MQTT JSON payload from ESP32.
    Matches exactly what Yashwanth's hardware/main.py publishes.
    """
    tank_id:     str            = Field(..., example="tank_01")
    temperature: Optional[float]= Field(None, ge=-10,  le=60,  example=26.5)
    ph:          Optional[float]= Field(None, ge=0,    le=14,  example=7.2)
    dissolved_o2:Optional[float]= Field(None, ge=0,    le=20,  example=6.8)
    ammonia:     Optional[float]= Field(None, ge=0,    le=100, example=0.01)
    turbidity:   Optional[float]= Field(None, ge=0,            example=2.1)

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v):
        if v is not None and (v < -10 or v > 60):
            raise ValueError("Temperature must be between -10 and 60°C")
        return v

    @field_validator("ph")
    @classmethod
    def validate_ph(cls, v):
        if v is not None and (v < 0 or v > 14):
            raise ValueError("pH must be between 0 and 14")
        return v

class SensorReadingResponse(BaseModel):
    id:          int
    temperature: Optional[float]
    ph:          Optional[float]
    dissolved_o2:Optional[float]
    ammonia:     Optional[float]
    timestamp:   datetime

    class Config:
        from_attributes = True

class SensorHistoryResponse(BaseModel):
    tank_id:  str
    readings: List[SensorReadingResponse]
    count:    int


# ── Behavior reading schemas ──────────────────────────────────────────────────

class BehaviorReadingCreate(BaseModel):
    """
    Shape of data sent by Likhita's CV module after analyzing a video window.
    """
    tank_id:           str            = Field(..., example="tank_01")
    fish_count:        Optional[int]  = Field(None, ge=0, example=12)
    avg_speed:         Optional[float]= Field(None, ge=0, example=45.3)
    avg_acceleration:  Optional[float]= Field(None, example=2.1)
    turning_frequency: Optional[float]= Field(None, ge=0, example=3.5)
    motion_variability:Optional[float]= Field(None, ge=0, example=12.7)
    surface_visits:    Optional[int]  = Field(None, ge=0, example=2)
    bottom_dwelling:   Optional[float]= Field(None, ge=0, le=100, example=15.0)
    inactivity_pct:    Optional[float]= Field(None, ge=0, le=100, example=8.5)
    schooling_density: Optional[float]= Field(None, ge=0, le=1,   example=0.72)

class BehaviorReadingResponse(BaseModel):
    id:                int
    fish_count:        Optional[int]
    avg_speed:         Optional[float]
    avg_acceleration:  Optional[float]
    turning_frequency: Optional[float]
    motion_variability:Optional[float]
    surface_visits:    Optional[int]
    inactivity_pct:    Optional[float]
    schooling_density: Optional[float]
    timestamp:         datetime

    class Config:
        from_attributes = True


# ── Stress score schemas ──────────────────────────────────────────────────────

class StressScoreResponse(BaseModel):
    id:                  int
    fsi_score:           float
    stress_level:        StressLevel
    water_quality_score: Optional[float]
    behavioral_score:    Optional[float]
    computed_at:         datetime

    class Config:
        from_attributes = True


# ── Alert schemas ─────────────────────────────────────────────────────────────

class AlertResponse(BaseModel):
    id:              int
    alert_type:      str
    severity:        StressLevel
    message:         str
    triggered_value: Optional[float]
    threshold_value: Optional[float]
    telegram_sent:   bool
    email_sent:      bool
    status:          AlertStatus
    resolved_at:     Optional[datetime]
    created_at:      datetime

    class Config:
        from_attributes = True

class AlertResolveRequest(BaseModel):
    note: Optional[str] = Field(None, example="Adjusted water temperature manually")


# ── Dashboard summary schema ──────────────────────────────────────────────────

class DashboardSummary(BaseModel):
    """Single response object for the Streamlit dashboard — all data in one call."""
    tank:          TankResponse
    latest_sensor: Optional[SensorReadingResponse]
    latest_stress: Optional[StressScoreResponse]
    active_alerts: List[AlertResponse]
    alert_count:   int
    readings_today:int

class BehaviorIngestResponse(BaseModel):
    """
    What the backend returns to Likhita after receiving behavior data.
    She can use this to confirm her data was received and see the impact on FSI.
    """
    behavior_reading_id: int
    tank_id:             str
    fish_count:          Optional[int]
    timestamp:           datetime
    fsi_score:           float
    stress_level:        StressLevel
    behavioral_score:    Optional[float]
    water_quality_score: Optional[float]
    message:             str

    class Config:
        from_attributes = True
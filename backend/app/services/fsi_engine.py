"""
Fish Stress Index (FSI) — Multi-Modal Stress Scoring Engine
============================================================
Combines water quality parameters and (optionally) behavioral features
into a single normalized stress score from 0.0 to 1.0.

Formula (water-quality-only mode):
    FSI = w_temp * S_temp + w_ph * S_ph + w_do * S_do + w_nh3 * S_nh3
    where each S_x is a normalized deviation from ideal range [0.0, 1.0]

Formula (multi-modal mode, when CV data is available):
    FSI = 0.60 * WQ_score + 0.40 * BEH_score

Stress levels:
    0.00 - 0.29 → NORMAL   (healthy fish, no intervention needed)
    0.30 - 0.59 → WARNING  (monitor closely, check system)
    0.60 - 1.00 → CRITICAL (immediate intervention required)

References:
    - Boyd, C.E. (2015). Water Quality. Springer.
    - Wedemeyer, G.A. (1996). Physiology of Fish in Intensive Culture Systems.
    - Conte, F.S. (2004). Stress and the welfare of cultured fish. Applied Animal Behaviour Science.
"""

from app.models.models import StressLevel

# ── Ideal parameter ranges (from aquaculture literature) ─────────────────────
IDEAL = {
    "temp_low":  22.0,   # °C — below this = cold stress
    "temp_high": 28.0,   # °C — above this = heat stress
    "ph_low":    6.5,    # pH — below this = acid stress
    "ph_high":   8.0,    # pH — above this = alkaline stress
    "do_min":    5.0,    # mg/L — below this = hypoxia
    "do_critical": 4.0,  # mg/L — below this = severe hypoxia
    "nh3_max":   0.02,   # ppm — above this = ammonia toxicity
}

# ── Alert thresholds (wider than ideal — triggers alert but not max stress) ──
THRESHOLDS = {
    "temp_high": 30.0,
    "temp_low":  18.0,
    "ph_high":    8.5,
    "ph_low":     6.0,
    "do_low":     4.0,
    "nh3_high":   0.05,
}

# ── Weights — must sum to 1.0 ─────────────────────────────────────────────────
WQ_WEIGHTS = {
    "temperature": 0.35,   # Most critical — fish are ectotherms
    "ph":          0.30,   # Second — affects enzyme activity
    "dissolved_o2":0.25,   # Third — fish die faster without O2
    "ammonia":     0.10,   # Slower acting but very toxic
}

BEH_WEIGHTS = {
    "avg_speed":         0.25,
    "turning_frequency": 0.25,
    "surface_visits":    0.30,   # Highest — surface gulping = O2 crisis
    "inactivity_pct":    0.20,
}


def _normalize_temp(temp: float) -> float:
    """Normalized temperature stress score [0.0, 1.0]."""
    if temp is None:
        return 0.0
    if IDEAL["temp_low"] <= temp <= IDEAL["temp_high"]:
        return 0.0   # Ideal range — no stress
    elif temp > IDEAL["temp_high"]:
        deviation = temp - IDEAL["temp_high"]
        return min(deviation / 8.0, 1.0)   # 8°C above ideal = max stress
    else:
        deviation = IDEAL["temp_low"] - temp
        return min(deviation / 8.0, 1.0)


def _normalize_ph(ph: float) -> float:
    """Normalized pH stress score [0.0, 1.0]."""
    if ph is None:
        return 0.0
    if IDEAL["ph_low"] <= ph <= IDEAL["ph_high"]:
        return 0.0
    elif ph > IDEAL["ph_high"]:
        return min((ph - IDEAL["ph_high"]) / 3.0, 1.0)
    else:
        return min((IDEAL["ph_low"] - ph) / 3.0, 1.0)


def _normalize_do(do2: float) -> float:
    """Normalized dissolved oxygen stress score [0.0, 1.0]."""
    if do2 is None:
        return 0.0
    if do2 >= IDEAL["do_min"]:
        return 0.0
    elif do2 >= IDEAL["do_critical"]:
        return 0.3 + 0.3 * ((IDEAL["do_min"] - do2) / (IDEAL["do_min"] - IDEAL["do_critical"]))
    else:
        return min(0.6 + 0.4 * ((IDEAL["do_critical"] - do2) / IDEAL["do_critical"]), 1.0)


def _normalize_ammonia(nh3: float) -> float:
    """Normalized ammonia stress score [0.0, 1.0]."""
    if nh3 is None:
        return 0.0
    if nh3 <= IDEAL["nh3_max"]:
        return 0.0
    return min((nh3 - IDEAL["nh3_max"]) / 0.5, 1.0)


def _normalize_behavior(
    avg_speed: float = None,
    turning_frequency: float = None,
    surface_visits: int = None,
    inactivity_pct: float = None,
) -> float:
    """
    Normalized behavioral stress score [0.0, 1.0].
    Uses deviation from normal behavior baselines established from
    healthy fish in controlled conditions.
    """
    score = 0.0

    # High speed = erratic movement = stress
    if avg_speed is not None:
        # Normal: 20-60 px/s. Stressed: >100 px/s or <5 px/s (lethargic)
        if avg_speed > 100:
            score += BEH_WEIGHTS["avg_speed"] * min((avg_speed - 100) / 100, 1.0)
        elif avg_speed < 5:
            score += BEH_WEIGHTS["avg_speed"] * min((5 - avg_speed) / 5, 1.0)

    # High turning = erratic = stress
    if turning_frequency is not None:
        # Normal: 0-3 turns/min. Stressed: >6 turns/min
        if turning_frequency > 6:
            score += BEH_WEIGHTS["turning_frequency"] * min((turning_frequency - 6) / 10, 1.0)

    # Surface visits = O2 stress indicator
    if surface_visits is not None:
        # Any surface visits = mild stress. >5 = severe
        if surface_visits > 0:
            score += BEH_WEIGHTS["surface_visits"] * min(surface_visits / 10, 1.0)

    # High inactivity = lethargy = stress
    if inactivity_pct is not None:
        # Normal: <20%. Stressed: >50%
        if inactivity_pct > 20:
            score += BEH_WEIGHTS["inactivity_pct"] * min((inactivity_pct - 20) / 80, 1.0)

    return min(score, 1.0)


def _score_to_level(score: float) -> StressLevel:
    """Convert numeric FSI score to a StressLevel enum."""
    if score < 0.30:
        return StressLevel.NORMAL
    elif score < 0.60:
        return StressLevel.WARNING
    else:
        return StressLevel.CRITICAL


def compute_fsi(
    temperature: float = None,
    ph: float = None,
    dissolved_o2: float = None,
    ammonia: float = None,
    avg_speed: float = None,
    turning_frequency: float = None,
    surface_visits: int = None,
    inactivity_pct: float = None,
) -> tuple[float, StressLevel, float]:
    """
    Compute the Fish Stress Index.

    Returns:
        fsi_score (float): Overall stress score 0.0–1.0
        stress_level (StressLevel): NORMAL / WARNING / CRITICAL
        wq_score (float): Water quality component score 0.0–1.0
    """
    # Water quality component
    wq_score = (
        WQ_WEIGHTS["temperature"]  * _normalize_temp(temperature)  +
        WQ_WEIGHTS["ph"]           * _normalize_ph(ph)             +
        WQ_WEIGHTS["dissolved_o2"] * _normalize_do(dissolved_o2)   +
        WQ_WEIGHTS["ammonia"]      * _normalize_ammonia(ammonia)
    )
    wq_score = min(wq_score, 1.0)

    # Behavioral component (optional — requires CV data)
    has_behavior = any(v is not None for v in [avg_speed, turning_frequency, surface_visits, inactivity_pct])

    if has_behavior:
        beh_score = _normalize_behavior(avg_speed, turning_frequency, surface_visits, inactivity_pct)
        fsi_score = round(0.60 * wq_score + 0.40 * beh_score, 4)
    else:
        fsi_score = round(wq_score, 4)
        beh_score = None

    stress_level = _score_to_level(fsi_score)

    return fsi_score, stress_level, round(wq_score, 4)


def get_alert_types(
    temperature: float = None,
    ph: float = None,
    dissolved_o2: float = None,
    ammonia: float = None,
) -> list[str]:
    """
    Return list of alert type strings for any parameters outside thresholds.
    Used to create Alert records in the database.
    """
    alerts = []
    if temperature is not None:
        if temperature > THRESHOLDS["temp_high"]:
            alerts.append("HIGH_TEMP")
        elif temperature < THRESHOLDS["temp_low"]:
            alerts.append("LOW_TEMP")
    if ph is not None:
        if ph > THRESHOLDS["ph_high"]:
            alerts.append("HIGH_PH")
        elif ph < THRESHOLDS["ph_low"]:
            alerts.append("LOW_PH")
    if dissolved_o2 is not None and dissolved_o2 < THRESHOLDS["do_low"]:
        alerts.append("LOW_DO")
    if ammonia is not None and ammonia > THRESHOLDS["nh3_high"]:
        alerts.append("HIGH_AMMONIA")
    return alerts

def compute_fish_fsi(
    avg_speed:          float = None,
    avg_acceleration:   float = None,
    turning_frequency:  float = None,
    motion_variability: float = None,
    surface_visits:     int   = None,
    bottom_dwelling:    float = None,
    inactivity_pct:     float = None,
) -> tuple[float, StressLevel]:
    """
    Compute stress score for a single individual fish.
    Uses behavioral metrics only — no water quality needed here
    because the tank-level WQ is already captured in sensor readings.

    Returns:
        stress_score (float): 0.0 – 1.0
        stress_level (StressLevel): NORMAL / WARNING / CRITICAL
    """
    score = 0.0

    # High speed = erratic thrashing = stress (weight 0.20)
    if avg_speed is not None:
        if avg_speed > 100:
            score += 0.20 * min((avg_speed - 100) / 100.0, 1.0)
        elif avg_speed < 3:
            # Very slow = lethargic = also stress
            score += 0.20 * min((3 - avg_speed) / 3.0, 1.0)

    # High acceleration = sudden bursts = stress (weight 0.15)
    if avg_acceleration is not None and avg_acceleration > 5:
        score += 0.15 * min((avg_acceleration - 5) / 10.0, 1.0)

    # High turning = erratic direction changes = stress (weight 0.20)
    if turning_frequency is not None and turning_frequency > 6:
        score += 0.20 * min((turning_frequency - 6) / 14.0, 1.0)

    # High motion variability = inconsistent swimming = stress (weight 0.15)
    if motion_variability is not None and motion_variability > 20:
        score += 0.15 * min((motion_variability - 20) / 40.0, 1.0)

    # Surface visits = gasping for air = severe O2 stress (weight 0.20)
    if surface_visits is not None and surface_visits > 0:
        score += 0.20 * min(surface_visits / 8.0, 1.0)

    # Bottom dwelling = lethargy = chronic stress (weight 0.05)
    if bottom_dwelling is not None and bottom_dwelling > 60:
        score += 0.05 * min((bottom_dwelling - 60) / 40.0, 1.0)

    # High inactivity = listlessness = stress (weight 0.05)
    if inactivity_pct is not None and inactivity_pct > 50:
        score += 0.05 * min((inactivity_pct - 50) / 50.0, 1.0)

    score = round(min(score, 1.0), 4)
    level = _score_to_level(score)
    return score, level
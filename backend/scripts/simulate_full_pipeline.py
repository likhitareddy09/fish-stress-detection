"""
Full pipeline simulation — Day 7 integration test.
Tests the complete real-world scenario end to end:
  Yashwanth ESP32 → MQTT → backend → PostgreSQL
  Likhita CV → per-fish batch → stress scores → Telegram
  Dashboard → reads all data → displays correctly

Run from backend/ folder:
    python scripts/simulate_full_pipeline.py
"""
import urllib.request
import urllib.parse
import json
import time
import subprocess
import sys

BASE = "http://localhost:8000/api/v1"
PASS = []
FAIL = []


def get(path, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        res = urllib.request.urlopen(url, timeout=5)
        raw = res.read()
        return res.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, json.loads(raw) if raw else {}
    except Exception as e:
        return 0, {"error": str(e)}


def post(path, body):
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        res = urllib.request.urlopen(req, timeout=5)
        raw = res.read()
        return res.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, json.loads(raw) if raw else {}
    except Exception as e:
        return 0, {"error": str(e)}


def mqtt_pub(topic, payload):
    msg = json.dumps(payload)
    for cmd in [
        ["mosquitto_pub", "-h", "localhost", "-t", topic, "-m", msg],
        [r"C:\Program Files\mosquitto\mosquitto_pub.exe", "-h", "localhost", "-t", topic, "-m", msg],
    ]:
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=5)
            if r.returncode == 0:
                return True
        except Exception:
            continue
    return False


def check(name, condition, detail=""):
    if condition:
        print(f"  [PASS] {name}")
        PASS.append(name)
    else:
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))
        FAIL.append(name)


print("\n" + "="*60)
print("  Fish Stress Detection — Full Pipeline Simulation")
print("="*60)

# ── Stage 1: Health ───────────────────────────────────────────────────────────
print("\n[1] System health")
s, b = get("/health")
check("Backend API reachable", s == 200, f"HTTP {s}")

s, b = get("/tanks/")
check("Tanks endpoint working", s == 200)
check("tank_01 registered", any(t.get("tank_id") == "tank_01" for t in b) if isinstance(b, list) else False)

# ── Stage 2: Yashwanth ESP32 via MQTT ────────────────────────────────────────
print("\n[2] Yashwanth ESP32 — MQTT sensor data")
ok = mqtt_pub("fish_tank/tank_01/sensors", {
    "tank_id": "tank_01", "temperature": 26.5,
    "ph": 7.2, "do_mg_l": 6.8, "ammonia": None,
    "alerts": [], "status": "ok"
})
check("MQTT publish (normal)", ok, "mosquitto_pub not found")
if ok:
    time.sleep(2)
    s, b = get("/sensors/tank_01/latest")
    check("Normal reading saved to DB", s == 200, f"HTTP {s}")

ok2 = mqtt_pub("fish_tank/tank_01/sensors", {
    "tank_id": "tank_01", "temperature": 34.0,
    "ph": 5.6, "do_mg_l": 2.8, "ammonia": None,
    "alerts": ["HIGH_TEMP", "LOW_PH"], "status": "critical"
})
check("MQTT publish (critical)", ok2)
if ok2:
    time.sleep(2)
    s, b = get("/sensors/tank_01/stress/current")
    check("Critical FSI computed", s == 200 and b.get("fsi_score", 0) > 0.3)
    if s == 200:
        print(f"    FSI={b.get('fsi_score'):.3f} — {b.get('stress_level', '').upper()}")

# ── Stage 3: Likhita per-fish batch ──────────────────────────────────────────
print("\n[3] Likhita CV module — per-fish batch")
s, b = post("/sensors/tank_01/behavior/batch", {
    "tank_id": "tank_01",
    "timestamp": "2026-07-23T12:30:00Z",
    "fish": [
        {
            "fish_id": 1,
            "avg_speed": 40.0,
            "avg_acceleration": 1.8,
            "turning_frequency": 2.5,
            "surface_visits": 0,
            "inactivity_pct": 10.0
        },
        {
            "fish_id": 2,
            "avg_speed": 1.0,
            "avg_acceleration": 0.2,
            "turning_frequency": 25.0,
            "surface_visits": 12,
            "bottom_dwelling": 80.0,
            "inactivity_pct": 75.0
        },
        {
            "fish_id": 3,
            "avg_speed": 150.0,
            "avg_acceleration": 12.0,
            "turning_frequency": 18.0,
            "surface_visits": 6,
            "inactivity_pct": 3.0
        },
    ]
})
check("Batch endpoint responds 201", s == 201, f"HTTP {s} — {b}")
if s == 201:
    check("Returns fish_count",    b.get("fish_count") == 3)
    check("Returns results array", len(b.get("results", [])) == 3)
    check("Returns tank_summary",  "tank_summary" in b)
    print(f"    Fish analysed: {b.get('fish_count')}")
    for r in b.get("results", []):
        bar = "█" * int(r["stress_score"] * 10) + "░" * (10 - int(r["stress_score"] * 10))
        print(f"    Fish #{r['fish_id']}: [{bar}] {r['stress_score']:.3f} — {r['stress_level'].upper()}")
    s2 = b.get("tank_summary", {})
    print(f"    Avg stress: {s2.get('avg_stress'):.3f} | Critical: {s2.get('critical_fish')}")
    check("Has critical fish", s2.get("critical_fish", 0) > 0)
    check("Most stressed fish identified", s2.get("most_stressed_fish_id") is not None)

# ── Stage 4: Dashboard ────────────────────────────────────────────────────────
print("\n[4] Dashboard data")
s, b = get("/tanks/tank_01/dashboard")
check("Dashboard endpoint responds", s == 200, f"HTTP {s}")
if s == 200:
    check("Tank info present",     bool(b.get("tank", {}).get("name")))
    check("Sensor data present",   b.get("latest_sensor") is not None)
    check("Stress score present",  b.get("latest_stress") is not None)
    check("Readings today > 0",    b.get("readings_today", 0) > 0)
    print(f"    Tank: {b['tank']['name']}")
    print(f"    Sensor: temp={b.get('latest_sensor', {}).get('temperature')}°C")
    print(f"    FSI: {b.get('latest_stress', {}).get('fsi_score')}")

# ── Stage 5: Alerts ───────────────────────────────────────────────────────────
print("\n[5] Alerts")
s, b = get("/alerts/stats/summary", {"hours": 24})
check("Alert stats endpoint", s == 200)
if s == 200:
    print(f"    System status: {b.get('system_status')}")
    print(f"    Active alerts: {b.get('active_alerts')}")

# ── Stage 6: Auth ─────────────────────────────────────────────────────────────
print("\n[6] Authentication")
data = urllib.parse.urlencode({"username": "taahira", "password": "backend2024"}).encode()
req  = urllib.request.Request(
    BASE + "/auth/login", data=data,
    headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST"
)
try:
    res  = urllib.request.urlopen(req, timeout=5)
    auth = json.loads(res.read())
    check("Login returns JWT", "access_token" in auth)
    check("Role is admin", auth.get("role") == "admin")
    print(f"    Logged in as: {auth.get('username')} ({auth.get('role')})")
except Exception as e:
    check("Login works", False, str(e))

# ── Stage 7: History ──────────────────────────────────────────────────────────
print("\n[7] Sensor history (for charts)")
s, b = get("/sensors/tank_01/history", {"hours": 24})
check("History endpoint responds", s == 200)
if s == 200:
    count = b.get("count", 0)
    check("Has readings", count > 0, f"count={count}")
    print(f"    Readings last 24h: {count}")

# ── Summary ───────────────────────────────────────────────────────────────────
total = len(PASS) + len(FAIL)
print("\n" + "="*60)
print(f"  Results: {len(PASS)}/{total} checks passed")
if FAIL:
    print(f"  Failed:  {', '.join(FAIL)}")
    print("\n  Fix the failures above before creating the PR.")
else:
    print("  All checks passed!")
    print("  Full pipeline working end-to-end.")
    print("  Ready to create the Pull Request to dev.")
print("="*60 + "\n")
sys.exit(0 if not FAIL else 1)
"""
Full endpoint test suite for Day 4.
Run from the backend/ folder with: python scripts/test_all_endpoints.py
Server must be running on port 8000.
"""
import urllib.request
import urllib.parse
import json
import sys

BASE = "http://localhost:8000/api/v1"
PASS = []
FAIL = []


def req(method, path, body=None, token=None, form=False):
    url = BASE + path
    if form:
        data = urllib.parse.urlencode(body).encode()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
    elif body:
        data = json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
    else:
        data, headers = None, {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        res = urllib.request.urlopen(r)
        raw = res.read()
        return res.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, json.loads(raw) if raw else {}


def check(name, status, body, expect_status=None, expect_key=None):
    ok = True
    if expect_status and status != expect_status:
        ok = False
    if expect_key and expect_key not in body:
        ok = False
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name} → HTTP {status}")
    if not ok:
        print(f"         Response: {json.dumps(body)[:120]}")
    (PASS if ok else FAIL).append(name)
    return body


print("\n" + "="*55)
print("  Fish Stress Detection — Full Endpoint Test")
print("="*55)

# ── Health ────────────────────────────────────────────────
print("\n[1] Health checks")
s, b = req("GET", "/health")
check("GET /health", s, b, 200, "status")

s, b = req("GET", "/ping")
check("GET /ping", s, b, 200, "ping")

# ── Auth ──────────────────────────────────────────────────
print("\n[2] Authentication")
s, b = req("POST", "/auth/login",
           {"username": "taahira", "password": "backend2024"}, form=True)
check("POST /auth/login (taahira)", s, b, 200, "access_token")
admin_token = b.get("access_token", "")

s, b = req("POST", "/auth/login",
           {"username": "likhita", "password": "cv2024"}, form=True)
check("POST /auth/login (likhita)", s, b, 200, "access_token")
likhita_token = b.get("access_token", "")

s, b = req("GET", "/auth/me", token=admin_token)
check("GET /auth/me", s, b, 200, "username")

s, b = req("POST", "/auth/login",
           {"username": "taahira", "password": "wrongpassword"}, form=True)
check("POST /auth/login (wrong password → 401)", s, b, 401)

# ── Tanks ─────────────────────────────────────────────────
print("\n[3] Tanks")
s, b = req("GET", "/tanks/")
check("GET /tanks/ (list)", s, b, 200)

# Clean up tank_test from any previous test run before creating it fresh
req("DELETE", "/tanks/tank_test")

s, b = req("POST", "/tanks/", {
    "tank_id": "tank_test",
    "name": "Test Tank",
    "fish_species": "Catla",
    "fish_count": 20,
})
check("POST /tanks/ (create)", s, b, 201, "tank_id")

s, b = req("GET", "/tanks/tank_test")
check("GET /tanks/tank_test", s, b, 200, "tank_id")

s, b = req("PATCH", "/tanks/tank_test", {"fish_count": 25, "name": "Updated Tank"})
check("PATCH /tanks/tank_test", s, b, 200, "fish_count")

# ── Sensor readings ───────────────────────────────────────
print("\n[4] Sensor readings")
s, b = req("POST", "/sensors/tank_01/readings", {
    "tank_id": "tank_01",
    "temperature": 27.0,
    "ph": 7.4,
    "dissolved_o2": 7.1,
    "ammonia": 0.01,
})
check("POST /sensors/tank_01/readings (normal)", s, b, 201, "id")

s, b = req("GET", "/sensors/tank_01/latest")
check("GET /sensors/tank_01/latest", s, b, 200, "temperature")

s, b = req("GET", "/sensors/tank_01/history?hours=24")
check("GET /sensors/tank_01/history", s, b, 200, "readings")
print(f"         Readings in last 24h: {b.get('count', '?')}")

s, b = req("GET", "/sensors/tank_01/stress/current")
check("GET /sensors/tank_01/stress/current", s, b, 200, "fsi_score")
print(f"         Current FSI: {b.get('fsi_score')} ({b.get('stress_level')})")

# ── Behavior (Likhita's endpoint) ─────────────────────────
print("\n[5] Behavior readings (Likhita's CV module)")
s, b = req("POST", "/sensors/tank_01/behavior", {
    "tank_id":          "tank_01",
    "fish_count":       15,
    "avg_speed":        55.2,
    "avg_acceleration": 3.1,
    "turning_frequency":4.2,
    "motion_variability":18.5,
    "surface_visits":   0,
    "bottom_dwelling":  12.0,
    "inactivity_pct":   10.0,
    "schooling_density":0.68,
})
check("POST /sensors/tank_01/behavior (normal fish)", s, b, 201, "fsi_score")
print(f"         FSI after CV data: {b.get('fsi_score')} — {b.get('message', '')}")

s, b = req("POST", "/sensors/tank_01/behavior", {
    "tank_id":          "tank_01",
    "fish_count":       8,
    "avg_speed":        120.0,
    "turning_frequency":12.0,
    "surface_visits":   7,
    "inactivity_pct":   5.0,
})
check("POST /sensors/tank_01/behavior (stressed fish)", s, b, 201, "fsi_score")
print(f"         FSI after stressed CV data: {b.get('fsi_score')} — {b.get('message', '')}")

# ── Alerts ────────────────────────────────────────────────
print("\n[6] Alerts")
s, b = req("GET", "/alerts/tank_01?status=all&hours=168")
check("GET /alerts/tank_01 (all)", s, b, 200)
alerts_list = b if isinstance(b, list) else []
print(f"         Total alerts found: {len(alerts_list)}")

if alerts_list:
    first_id = alerts_list[0]["id"]
    s, b = req("PATCH", f"/alerts/{first_id}/resolve", {"note": "Fixed manually during test"})
    check(f"PATCH /alerts/{first_id}/resolve", s, b, 200, "status")

s, b = req("GET", "/alerts/stats/summary?hours=24")
check("GET /alerts/stats/summary", s, b, 200, "system_status")
print(f"         System status: {b.get('system_status')} | Active: {b.get('active_alerts')}")

# ── Dashboard ─────────────────────────────────────────────
print("\n[7] Dashboard summary")
s, b = req("GET", "/tanks/tank_01/dashboard")
check("GET /tanks/tank_01/dashboard", s, b, 200, "tank")
print(f"         Tank: {b.get('tank', {}).get('name')}")
print(f"         FSI:  {b.get('latest_stress', {}).get('fsi_score')}")
print(f"         Alerts: {b.get('alert_count')}")

# ── Cleanup ───────────────────────────────────────────────
print("\n[8] Cleanup")
s, b = req("DELETE", "/tanks/tank_test")
check("DELETE /tanks/tank_test (deactivate)", s, b, 204)

# ── Summary ───────────────────────────────────────────────
total = len(PASS) + len(FAIL)
print("\n" + "="*55)
print(f"  Results: {len(PASS)}/{total} passed")
if FAIL:
    print(f"  Failed:  {', '.join(FAIL)}")
else:
    print("  All tests passed! Day 4 is complete.")
print("="*55 + "\n")

sys.exit(0 if not FAIL else 1)
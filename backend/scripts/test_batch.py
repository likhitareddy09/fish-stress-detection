import urllib.request, json

payload = {
    "tank_id": "tank_01",
    "timestamp": "2026-07-23T12:30:00Z",
    "fish": [
        {
            "fish_id": 2,
            "avg_speed": 3.2,
            "avg_acceleration": 1.5,
            "turning_frequency": 6.0,
            "motion_variability": 2.8,
            "surface_visits": 1,
            "bottom_dwelling": 12.0,
            "inactivity_pct": 15.0
        },
        {
            "fish_id": 3,
            "avg_speed": 1.0,
            "avg_acceleration": 0.4,
            "turning_frequency": 18.0,
            "motion_variability": 6.1,
            "surface_visits": 8,
            "bottom_dwelling": 70.0,
            "inactivity_pct": 62.0
        },
        {
            "fish_id": 7,
            "avg_speed": 45.0,
            "avg_acceleration": 2.1,
            "turning_frequency": 3.0,
            "motion_variability": 8.5,
            "surface_visits": 0,
            "bottom_dwelling": 10.0,
            "inactivity_pct": 8.0
        }
    ]
}

data = json.dumps(payload).encode()
req = urllib.request.Request(
    "http://localhost:8000/api/v1/sensors/tank_01/behavior/batch",
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST"
)

try:
    res = urllib.request.urlopen(req)
    result = json.loads(res.read())

    print("=== Per-Fish Stress Results ===")
    print(f"Tank: {result['tank_id']}")
    print(f"Fish analysed: {result['fish_count']}")
    print()

    for r in result["results"]:
        filled = int(r["stress_score"] * 10)
        bar = "█" * filled + "░" * (10 - filled)
        print(f"  Fish #{r['fish_id']}: [{bar}] {r['stress_score']:.3f} — {r['stress_level'].upper()}")

    print()
    summary = result["tank_summary"]
    print(f"Tank average stress: {summary['avg_stress']:.3f}")
    print(f"Critical fish count: {summary['critical_fish']}")
    print(f"Most stressed fish:  #{summary['most_stressed_fish_id']} ({summary['most_stressed_score']:.3f})")

except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}: {e.read().decode()}")
except Exception as e:
    print(f"Error: {e}")
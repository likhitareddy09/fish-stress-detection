import urllib.request
import json

try:
    res  = urllib.request.urlopen(
        "http://localhost:8000/api/v1/sensors/tank_01/fish-stress/latest",
        timeout=5
    )
    data = json.loads(res.read())
    print("Fish count:", data["fish_count"])
    print("Avg stress:", data["avg_stress"])
    print()
    for f in data["fish"]:
        score = f["stress_score"]
        level = f["stress_level"].upper()
        bar   = "█" * int(score * 10) + "░" * (10 - int(score * 10))
        print(f"  Fish #{f['fish_id']}: [{bar}] {score:.3f} — {level}")
except urllib.error.HTTPError as e:
    print(f"HTTP error: {e.code} — {e.read().decode()}")
except Exception as e:
    print(f"Error: {e}")
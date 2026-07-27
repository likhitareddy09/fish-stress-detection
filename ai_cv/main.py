import cv2
import math
import requests
from datetime import datetime, timezone
from ultralytics import YOLO

from behavior import FishBehavior
from stress_score import calculate_stress


# =========================================================
# SEND BEHAVIOR DATA TO TAAHIRA'S FASTAPI BACKEND
# =========================================================

def send_fish_data(metrics, video_duration):

    url = "http://localhost:8000/api/v1/sensors/tank_01/behavior/batch"

    # ---------------------------------
    # Convert total turns -> turns/minute
    # ---------------------------------

    total_turns = metrics.get("turning_frequency", 0)

    if video_duration > 0:
        turns_per_minute = (total_turns / video_duration) * 60
    else:
        turns_per_minute = 0


    # ---------------------------------
    # Single-fish metrics
    # ---------------------------------

    fish_data = {

        # Current project tracks one fish
        "fish_id": 1,

        "avg_speed": metrics.get(
            "avg_speed"
        ),

        "avg_acceleration": metrics.get(
            "avg_acceleration"
        ),

        "turning_frequency": round(
            turns_per_minute,
            2
        ),

        # These metrics are not implemented yet.
        # None becomes null in JSON.
        "motion_variability": None,

        "surface_visits": None,

        "bottom_dwelling": None,

        "inactivity_pct": metrics.get(
            "inactivity_percentage"
        )
    }


    # ---------------------------------
    # Final API payload
    # ---------------------------------

    payload = {

        "tank_id": "tank_01",

        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),

        "fish": [
            fish_data
        ]
    }


    print("\n--------------------------------")
    print("Sending behavior data to backend")
    print("--------------------------------")

    print(payload)


    # ---------------------------------
    # POST request
    # ---------------------------------

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=10
        )


        print(
            "\nBackend status:",
            response.status_code
        )


        if response.status_code in (200, 201):

            result = response.json()

            print("\nBackend FSI Result")
            print(result)

            return result


        else:

            print("\nBackend rejected the data:")
            print(response.text)


    except requests.exceptions.ConnectionError:

        print("\nCould not connect to Taahira's backend.")

        print(
            "Make sure FastAPI is running on "
            "http://localhost:8000"
        )


    except requests.exceptions.RequestException as e:

        print("\nAPI request error:")
        print(e)


    return None


# =========================================================
# SETTINGS
# =========================================================

MODEL_PATH = "models/fish_stress_project_best.pt"

VIDEO_PATH = "test_1.mp4"

CONFIDENCE_THRESHOLD = 0.60

MIN_BOX_AREA = 2500

MAX_TRAJECTORY_POINTS = 30

MIN_MOVEMENT_DISTANCE = 2


# =========================================================
# LOAD YOLO MODEL
# =========================================================

print("Loading YOLO model...")

model = YOLO(MODEL_PATH)

print("Model loaded.")


# =========================================================
# OPEN VIDEO
# =========================================================

cap = cv2.VideoCapture(VIDEO_PATH)


if not cap.isOpened():

    print("Cannot open video.")

    raise SystemExit


# ---------------------------------
# Get FPS
# ---------------------------------

fps = cap.get(
    cv2.CAP_PROP_FPS
)


if fps <= 0:

    fps = 30


print(
    f"Video FPS: {fps:.2f}"
)


# =========================================================
# INITIALIZE BEHAVIOR TRACKER
# =========================================================

fish = FishBehavior(
    fps=fps
)


previous_center = None

trajectory = []

processed_frames = 0


# =========================================================
# PROCESS VIDEO
# =========================================================

while True:

    ret, frame = cap.read()


    if not ret:

        break


    processed_frames += 1


    # ---------------------------------
    # YOLO detection
    # ---------------------------------

    results = model(
        frame,
        conf=CONFIDENCE_THRESHOLD,
        verbose=False
    )


    candidates = []


    # ---------------------------------
    # Collect valid detections
    # ---------------------------------

    for result in results:

        for box in result.boxes:

            confidence = float(
                box.conf[0]
            )


            x1, y1, x2, y2 = box.xyxy[0]


            x1 = int(x1)

            y1 = int(y1)

            x2 = int(x2)

            y2 = int(y2)


            width = x2 - x1

            height = y2 - y1


            area = width * height


            # Ignore tiny detections
            if area < MIN_BOX_AREA:

                continue


            cx = (
                x1 + x2
            ) // 2


            cy = (
                y1 + y2
            ) // 2


            candidates.append({

                "box": (
                    x1,
                    y1,
                    x2,
                    y2
                ),

                "center": (
                    cx,
                    cy
                ),

                "confidence":
                    confidence
            })


    # =====================================================
    # SELECT ONE FISH
    # =====================================================

    selected = None


    if len(candidates) > 0:


        # ---------------------------------
        # First detection:
        # choose highest confidence
        # ---------------------------------

        if previous_center is None:

            selected = max(
                candidates,
                key=lambda d:
                    d["confidence"]
            )


        # ---------------------------------
        # Following frames:
        # choose detection nearest
        # previous fish position
        # ---------------------------------

        else:

            selected = min(
                candidates,
                key=lambda d:
                    math.dist(
                        previous_center,
                        d["center"]
                    )
            )


    # =====================================================
    # PROCESS SELECTED FISH
    # =====================================================

    if selected is not None:


        x1, y1, x2, y2 = selected["box"]

        cx, cy = selected["center"]


        previous_center = (
            cx,
            cy
        )


        # ---------------------------------
        # CLEAN TRAJECTORY
        # ---------------------------------

        if len(trajectory) == 0:

            trajectory.append(
                (cx, cy)
            )


        else:

            movement = math.dist(
                trajectory[-1],
                (cx, cy)
            )


            # Ignore tiny YOLO jitter
            if movement > MIN_MOVEMENT_DISTANCE:

                trajectory.append(
                    (cx, cy)
                )


        # ---------------------------------
        # Keep only recent trajectory
        # ---------------------------------

        if len(trajectory) > MAX_TRAJECTORY_POINTS:

            trajectory.pop(0)


        # ---------------------------------
        # Send position to behavior module
        # ---------------------------------

        fish.add_position(
            cx,
            cy
        )


        # =================================================
        # DRAW BOUNDING BOX
        # =================================================

        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            2
        )


        # ---------------------------------
        # Center point
        # ---------------------------------

        cv2.circle(
            frame,
            (cx, cy),
            3,
            (0, 0, 255),
            -1
        )


        # ---------------------------------
        # Confidence
        # ---------------------------------

        cv2.putText(
            frame,
            f"Fish {selected['confidence']:.2f}",
            (
                x1,
                max(y1 - 10, 20)
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2
        )


    # =====================================================
    # DRAW TRAJECTORY
    # =====================================================

    for i in range(
        2,
        len(trajectory),
        2
    ):

        cv2.line(
            frame,
            trajectory[i - 2],
            trajectory[i],
            (255, 0, 0),
            1
        )


    # =====================================================
    # SHOW VIDEO
    # =====================================================

    cv2.imshow(
        "FishSense Detection",
        frame
    )


    # Press Q to stop
    if cv2.waitKey(1) & 0xFF == ord("q"):

        break


# =========================================================
# CLEANUP
# =========================================================

cap.release()

cv2.destroyAllWindows()


# =========================================================
# VIDEO DURATION
# =========================================================

video_duration = (
    processed_frames / fps
)


print(
    f"\nProcessed duration: "
    f"{video_duration:.2f} seconds"
)


# =========================================================
# FINAL BEHAVIOR ANALYSIS
# =========================================================

metrics = fish.calculate_metrics()


print("\nBehavior Metrics")

print(metrics)


# =========================================================
# STRESS + BACKEND
# =========================================================

if metrics:


    # ---------------------------------
    # Your local prototype stress score
    # ---------------------------------

    stress = calculate_stress(
        metrics
    )


    print("\nLocal Stress Result")

    print(stress)


    # ---------------------------------
    # Send behavior to FastAPI
    # ---------------------------------

    backend_result = send_fish_data(
        metrics,
        video_duration
    )


    # ---------------------------------
    # Show final backend result
    # ---------------------------------

    if backend_result is not None:

        print("\n==============================")
        print("FINAL BACKEND ANALYSIS")
        print("==============================")


        results = backend_result.get(
            "results",
            []
        )


        for result in results:

            print(
                f"Fish ID: "
                f"{result.get('fish_id')}"
            )

            print(
                f"FSI Stress Score: "
                f"{result.get('stress_score')}"
            )

            print(
                f"FSI Stress Level: "
                f"{result.get('stress_level')}"
            )


else:

    print(
        "\nNot enough fish tracking data "
        "to calculate behavior."
    )
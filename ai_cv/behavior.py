import numpy as np


class FishBehavior:

    def __init__(self, fps=30):
        self.fps = fps
        self.positions = []

    def add_position(self, x, y):
        self.positions.append((x, y))

    def calculate_metrics(self):

        if len(self.positions) < 5:
            return None

        # ---------------------------------
        # Convert positions to numpy array
        # ---------------------------------
        points = np.array(self.positions, dtype=float)

        # ---------------------------------
        # Smooth trajectory (without modifying original)
        # ---------------------------------
        window = 5
        smoothed = points.copy()

        for i in range(window, len(points)):
            smoothed[i] = np.mean(points[i - window:i], axis=0)

        points = smoothed

        # ---------------------------------
        # Calculate movement
        # ---------------------------------
        dx = np.diff(points[:, 0])
        dy = np.diff(points[:, 1])

        distance = np.sqrt(dx ** 2 + dy ** 2)

        # Remove tiny jitter
        distance[distance < 1] = 0

        FRAME_WIDTH = 1280

        # Normalized speed
        speed = distance / FRAME_WIDTH

        # Acceleration
        acceleration = np.diff(speed)

        # ---------------------------------
        # Direction
        # ---------------------------------
        angles = np.arctan2(dy, dx)

        angle_change = np.abs(np.diff(angles))

        angle_change = np.degrees(angle_change)

        angle_change = np.where(
            angle_change > 180,
            360 - angle_change,
            angle_change
        )

        # ---------------------------------
        # Turning Events
        # ---------------------------------
        TURN_ANGLE = 45
        MIN_SPEED = 0.003

        turns = 0
        currently_turning = False

        for i in range(len(angle_change)):

            if speed[i + 1] < MIN_SPEED:
                currently_turning = False
                continue

            if angle_change[i] > TURN_ANGLE:

                if not currently_turning:
                    turns += 1
                    currently_turning = True

            else:
                currently_turning = False

        # ---------------------------------
        # Activity Detection
        # Uses pixel movement instead of normalized speed
        # ---------------------------------
        MOVEMENT_THRESHOLD = 1.5

        moving = distance > MOVEMENT_THRESHOLD

        inactivity = np.mean(~moving) * 100

        active_time = np.sum(moving) / self.fps

        # ---------------------------------
        # Other Metrics
        # ---------------------------------
        total_distance = np.sum(distance)

        if len(angle_change) > 0:
            avg_direction_change = np.mean(angle_change)
        else:
            avg_direction_change = 0

        return {

            "avg_speed": round(float(np.mean(speed)), 3),

            "max_speed": round(float(np.max(speed)), 3),

            "avg_acceleration": round(float(np.mean(np.abs(acceleration))), 3),

            "turning_frequency": int(turns),

            "avg_direction_change": round(float(avg_direction_change), 2),

            "total_distance": round(float(total_distance), 2),

            "active_time_seconds": round(float(active_time), 2),

            "inactivity_percentage": round(float(inactivity), 2)

        }
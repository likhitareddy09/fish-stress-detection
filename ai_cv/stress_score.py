def calculate_stress(metrics):

    score = 0
    reasons = []

    # -----------------------------
    # Average Speed (0–25)
    # -----------------------------
    speed = metrics["avg_speed"]

    if speed >= 0.10:
        score += 25
        reasons.append("Very high swimming speed")

    elif speed >= 0.07:
        score += 18
        reasons.append("High swimming speed")

    elif speed >= 0.05:
        score += 10
        reasons.append("Moderately increased swimming speed")

    # -----------------------------
    # Acceleration (0–20)
    # -----------------------------
    acceleration = metrics["avg_acceleration"]

    if acceleration >= 0.08:
        score += 20
        reasons.append("Sudden movement changes")

    elif acceleration >= 0.05:
        score += 12
        reasons.append("Moderate movement changes")

    elif acceleration >= 0.03:
        score += 6

    # -----------------------------
    # Turning Frequency (0–20)
    # -----------------------------
    turns = metrics["turning_frequency"]

    if turns >= 40:
        score += 20
        reasons.append("Very frequent turning")

    elif turns >= 20:
        score += 12
        reasons.append("Frequent turning")

    elif turns >= 10:
        score += 6

    # -----------------------------
    # Inactivity (0–20)
    # -----------------------------
    inactivity = metrics["inactivity_percentage"]

    if inactivity >= 70:
        score += 20
        reasons.append("Very high inactivity")

    elif inactivity >= 50:
        score += 12
        reasons.append("High inactivity")

    elif inactivity >= 30:
        score += 6

    # -----------------------------
    # Direction Change (0–15)
    # -----------------------------
    direction = metrics.get("avg_direction_change", 0)

    if direction >= 120:
        score += 15
        reasons.append("Erratic swimming direction")

    elif direction >= 90:
        score += 10

    elif direction >= 60:
        score += 5

    # -----------------------------
    # Limit Score
    # -----------------------------
    score = min(score, 100)

    # -----------------------------
    # Stress Level
    # -----------------------------
    if score < 30:
        level = "LOW STRESS"

    elif score < 60:
        level = "MODERATE STRESS"

    else:
        level = "HIGH STRESS"

    # -----------------------------
    # Recommendation
    # -----------------------------
    if level == "LOW STRESS":

        recommendation = (
            "Fish behavior appears normal. Continue routine monitoring."
        )

    elif level == "MODERATE STRESS":

        recommendation = (
            "Observe the fish closely and inspect water quality if unusual behavior persists."
        )

    else:

        recommendation = (
            "Immediate inspection is recommended. Check dissolved oxygen, temperature, pH, and reduce environmental disturbances."
        )

    return {

        "stress_score": score,

        "stress_level": level,

        "reasons": reasons,

        "recommendation": recommendation

    }
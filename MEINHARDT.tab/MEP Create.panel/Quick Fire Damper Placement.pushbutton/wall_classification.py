import re


def classify_wall_material(value):
    normalized = re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()
    if not normalized:
        return "UNKNOWN"
    if normalized in ("0", "false", "no", "none", "unrated", "non rated", "not rated", "nr"):
        return "NOT_RATED"

    fire_negative = re.search(
        r"\b(?:not|non|no)\s+(?:fire|frl|fr)\b|\b(?:fire|frl|fr)\s+(?:not|non)\s+(?:rated|required|applicable)\b",
        normalized,
    )
    smoke_negative = re.search(
        r"\b(?:not|non|no)\s+smoke\b|\bsmoke\s+(?:not|non)\s+(?:rated|required|applicable)\b",
        normalized,
    )
    generally_not_rated = re.search(r"\b(?:not|non)\s+rated\b|\bunrated\b", normalized)

    has_fire = bool(re.search(
        r"\b(?:frl|fr)\b|\bfire\s+(?:rated|resistant|resistance|rating)\b|\bfirerated\b|\bfireresistant\b",
        normalized,
    )) and not fire_negative and not generally_not_rated
    has_smoke = (normalized == "smoke" or bool(re.search(r"\bsmoke\s+(?:rated|resistant|resistance)\b", normalized)))
    has_smoke = has_smoke and not smoke_negative and not generally_not_rated

    if has_fire and has_smoke:
        return "BOTH"
    if has_fire:
        return "FIRE"
    if has_smoke:
        return "SMOKE"
    if fire_negative or smoke_negative or generally_not_rated:
        return "NOT_RATED"
    return "UNKNOWN"


def is_rated_wall_material(value):
    return classify_wall_material(value) in ("FIRE", "SMOKE", "BOTH")
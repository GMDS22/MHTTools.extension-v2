import re


def classify_wall_material(value):
    raw_value = str(value or "").strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", raw_value).strip()
    if not normalized:
        return "UNKNOWN"
    if normalized in ("0", "false", "no", "none", "unrated", "non rated", "not rated", "nr", "n a"):
        return "NOT_RATED"

    fire_negative = re.search(
        r"\b(?:not|non|no)\s+(?:fire|f|fr|frl|frr|ei|rei)\b|"
        r"\b(?:fire|f|fr|frl|frr|ei|rei)\s+(?:not|non|no)\s+(?:rated|required|applicable)\b|"
        r"\b(?:not|non|no)\s+(?:astm\s+e\s*119|ul\s+(?:263|10c)|bs\s+476|as\s+1530\s+4|en\s+13501\s+2)\b|"
        r"\b(?:astm\s+e\s*119|ul\s+(?:263|10c)|bs\s+476|as\s+1530\s+4|en\s+13501\s+2)\s+(?:not|non|no)\s+(?:rated|required|applicable|compliant)\b",
        normalized,
    )
    smoke_negative = re.search(
        r"\b(?:not|non|no)\s+(?:smoke|s\s*\d{2,3}|ul\s+1784|en\s+1634\s+3|nfpa\s+105)\b|"
        r"\b(?:smoke|s\s*\d{2,3}|ul\s+1784|en\s+1634\s+3|nfpa\s+105)\s+(?:not|non|no)\s+(?:rated|required|applicable|compliant)\b",
        normalized,
    )
    generally_not_rated = re.search(
        r"\b(?:not|non)\s+(?:rated|applicable|compliant)\b|\bunrated\b|\bno\s+(?:fire\s+)?rating\b",
        normalized,
    )
    if generally_not_rated:
        return "NOT_RATED"

    fire_standard = re.search(
        r"\b(?:astm\s+e\s*119|ul\s+(?:263|10c)|bs\s+476|as\s+1530\s+4|en\s+13501\s+2)\b|"
        r"\b(?:ei|rei)\s*\d{1,3}\b",
        normalized,
    )
    fire_triplet = re.search(
        r"(?:\d{1,3}|-)\s*/\s*(?:\d{1,3}|-)\s*/\s*(?:\d{1,3}|-)",
        raw_value,
    )
    if fire_triplet and not re.search(r"\d", fire_triplet.group(0)):
        fire_triplet = None
    fire_rating = re.search(
        r"\b(?:f|fr|frl|frr)\b|\bf\s+rated\b|\b(?:f|fr|frl|frr)\s*[-:]?\s*\d{1,3}\b|"
        r"\bfrl\s+\d+\s*(?:\s*\d+\s*){0,2}\b|"
        r"\bf\s*\d+\s*(?:min|mins|minute|minutes|hr|hrs|hour|hours)\b|"
        r"\bfire\b|"
        r"\bfirerated\b|\bfireresistant\b",
        normalized,
    )
    has_fire = bool(fire_standard or fire_triplet or fire_rating) and not fire_negative
    has_smoke = bool(re.search(
        r"\bsmoke\b|\bul\s+1784\b|\ben\s+1634\s+3\b|\bnfpa\s+105\b|\bsa\b|\bs\s*\d{2,3}\b",
        normalized,
    )) and not smoke_negative

    if has_fire and has_smoke:
        return "BOTH"
    if has_fire:
        return "FIRE"
    if has_smoke:
        return "SMOKE"
    if fire_negative or smoke_negative:
        return "NOT_RATED"
    return "UNKNOWN"


def is_rated_wall_material(value):
    return classify_wall_material(value) in ("FIRE", "SMOKE", "BOTH")


def classify_wall_descriptors(values):
    classifications = [classify_wall_material(value) for value in values if value]
    has_fire = any(value in ("FIRE", "BOTH") for value in classifications)
    has_smoke = any(value in ("SMOKE", "BOTH") for value in classifications)
    if has_fire and has_smoke:
        return "BOTH"
    if has_fire:
        return "FIRE"
    if has_smoke:
        return "SMOKE"
    if "NOT_RATED" in classifications:
        return "NOT_RATED"
    return "UNKNOWN"
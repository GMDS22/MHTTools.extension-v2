import math


MM_PER_FOOT = 304.8
DEFAULT_DUPLICATE_RADIUS_MM = 200.0


def millimeters_to_feet(value):
    radius_mm = float(value)
    if radius_mm <= 0 or math.isnan(radius_mm) or math.isinf(radius_mm):
        raise ValueError("Duplicate radius must be a positive finite number of millimeters")
    return radius_mm / MM_PER_FOOT


def points_within_radius(first, second, radius_feet):
    dx = float(first[0]) - float(second[0])
    dy = float(first[1]) - float(second[1])
    dz = float(first[2]) - float(second[2])
    radius = float(radius_feet)
    return dx * dx + dy * dy + dz * dz <= radius * radius